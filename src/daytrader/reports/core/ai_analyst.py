"""AIAnalyst: claude CLI subprocess wrapper.

Phase 2 invokes Claude via `claude -p` (the Claude Code CLI's print mode),
using the user's Claude Pro Max subscription rather than the Anthropic API.
This eliminates per-run cost during PoC and dev iteration.

Trade-offs vs Anthropic SDK (see plan preamble):
- No explicit prompt-caching markers (CLI may cache internally)
- No token counts in the response → AIResult.input_tokens / output_tokens = 0
- Phase 7 production may need to swap in an API backend if Pro Max rate limits
  prove insufficient for 6×day × multi-instrument cadence

The interface (AIResult shape, .call() signature) is stable so a future API
backend can be added without touching Orchestrator or PremarketGenerator.

Backend selection (2026-11): `daytrader.core.llm` picks `cli` (this file's
historical `claude -p` path, unchanged) or `api` (Anthropic SDK) from
DAYTRADER_LLM_BACKEND → config `ai.backend` → `cli`. Retry count, backoff,
timeout and the "AI call failed: ..." RuntimeError are identical for both.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from daytrader.core.llm import (
    APIBackend,
    CLIBackend,
    LLMBackend,
    LLMError,
    LLMTimeoutError,
    get_llm_backend,
)


@dataclass(frozen=True)
class AIResult:
    """One Claude call outcome."""
    text: str
    input_tokens: int          # 0 in CLI mode
    output_tokens: int         # 0 in CLI mode
    cache_creation_tokens: int  # 0 in CLI mode
    cache_read_tokens: int      # 0 in CLI mode
    model: str
    stop_reason: str


class AIAnalyst:
    """`claude -p` subprocess wrapper with exponential-backoff retry."""

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        max_retries: int = 3,
        timeout_seconds: int = 300,
        backend: LLMBackend | None = None,
        project_root: Path | str | None = None,
    ) -> None:
        # Default 300s (was 180s pre-Phase-4.5).
        # Phase 4.5 added the D. 情绪面 / Sentiment Index block (~1500 chars)
        # to the main prompt. Empirically observed claude -p call exceed
        # 180s on this larger prompt; 300s gives headroom while keeping
        # worst-case (3 retries × 300s + backoff) within ~15 min.
        self.model = model
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.backend = backend if backend is not None else get_llm_backend(project_root)

    def call(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 8192,
    ) -> AIResult:
        """Invoke `claude -p`, return AIResult.

        Messages are flattened into a single prompt string passed via stdin.
        System content is prefixed with "[SYSTEM]" markers; user content with
        "[USER]" markers. claude -p returns plain text on stdout.
        """
        if isinstance(self.backend, APIBackend):
            return self._call_api(messages, max_tokens)

        prompt = self._flatten_messages(messages)
        cmd = ["claude", "-p"]

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self._cli().run(
                    cmd,
                    input=prompt,
                    timeout=self.timeout_seconds,
                )
                if result.returncode == 0:
                    return AIResult(
                        text=result.stdout,
                        input_tokens=0,
                        output_tokens=0,
                        cache_creation_tokens=0,
                        cache_read_tokens=0,
                        model=self.model,
                        stop_reason="end_turn",
                    )
                # claude CLI prints some fatal errors on STDOUT (e.g.
                # "Failed to authenticate: OAuth session expired and could
                # not be refreshed"), while stderr only carries settings
                # warnings. Capture both so the real cause is not lost
                # (the historical "claude -p exit=1: no stderr" category).
                stderr_tail = result.stderr.strip()[-400:]
                stdout_tail = result.stdout.strip()[-400:]
                detail = stderr_tail or "no stderr"
                if stdout_tail:
                    detail = f"{detail} | stdout: {stdout_tail}"
                last_error = f"claude -p exit={result.returncode}: {detail}"
            except subprocess.TimeoutExpired:
                last_error = f"claude -p timeout after {self.timeout_seconds}s"

            if attempt < self.max_retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"AI call failed: {last_error}")

        # Defensive — should be unreachable
        raise RuntimeError(f"AI call failed: {last_error}")

    def _cli(self) -> CLIBackend:
        return self.backend if isinstance(self.backend, CLIBackend) else CLIBackend()

    def _call_api(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> AIResult:
        """API backend: same retry/backoff/timeout/error contract as the CLI."""
        assert isinstance(self.backend, APIBackend)
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.backend.complete(
                    messages=messages,
                    max_tokens=max_tokens,
                    timeout=self.timeout_seconds,
                )
                return AIResult(
                    text=resp.text,
                    input_tokens=resp.input_tokens,
                    output_tokens=resp.output_tokens,
                    cache_creation_tokens=resp.cache_creation_tokens,
                    cache_read_tokens=resp.cache_read_tokens,
                    model=resp.model,
                    stop_reason=resp.stop_reason,
                )
            except LLMTimeoutError:
                last_error = f"api timeout after {self.timeout_seconds}s"
            except LLMError as e:
                last_error = str(e)

            if attempt < self.max_retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"AI call failed: {last_error}")

        raise RuntimeError(f"AI call failed: {last_error}")

    @staticmethod
    def _flatten_messages(messages: list[dict[str, Any]]) -> str:
        """Concatenate role-tagged blocks into a single prompt for claude -p."""
        parts: list[str] = []
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            if isinstance(content, list):
                # API-shape: list of {type, text, ...} blocks
                for block in content:
                    if block.get("type") == "text":
                        parts.append(f"[{role}]\n{block['text']}")
            else:
                parts.append(f"[{role}]\n{content}")
        return "\n\n".join(parts)
