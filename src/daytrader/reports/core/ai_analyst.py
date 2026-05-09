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
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Any


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
    ) -> None:
        # Default 300s (was 180s pre-Phase-4.5).
        # Phase 4.5 added the D. 情绪面 / Sentiment Index block (~1500 chars)
        # to the main prompt. Empirically observed claude -p call exceed
        # 180s on this larger prompt; 300s gives headroom while keeping
        # worst-case (3 retries × 300s + backoff) within ~15 min.
        self.model = model
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

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
        prompt = self._flatten_messages(messages)
        cmd = ["claude", "-p"]

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
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
                last_error = (
                    f"claude -p exit={result.returncode}: "
                    f"{result.stderr.strip() or 'no stderr'}"
                )
            except subprocess.TimeoutExpired:
                last_error = f"claude -p timeout after {self.timeout_seconds}s"

            if attempt < self.max_retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"AI call failed: {last_error}")

        # Defensive — should be unreachable
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
