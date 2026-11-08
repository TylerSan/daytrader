"""Shared LLM backend for every Claude call in daytrader.

Two backends:

- ``cli`` (default) — shells out to the Claude Code CLI (``claude -p``),
  billed against the user's Claude subscription. This is the historical
  behavior on the Mac; callers keep their own subprocess error handling
  via :meth:`CLIBackend.run`, so nothing about the CLI path changes.
- ``api`` — calls the Anthropic Messages API through the official Python
  SDK. Needed on a cloud Linux box where the ``claude`` CLI is not
  installed / logged in.

Resolution order (first match wins):

- backend:    env ``DAYTRADER_LLM_BACKEND`` → config ``ai.backend`` → ``cli``
- model:      env ``DAYTRADER_LLM_MODEL``   → config ``ai.model``   → ``DEFAULT_API_MODEL``
- max_tokens: env ``DAYTRADER_LLM_MAX_TOKENS`` → config ``ai.max_tokens`` → 32000
- API key:    env ``ANTHROPIC_API_KEY`` → ``anthropic.api_key`` in ``config/secrets.yaml``

Config comes from ``config/default.yaml`` deep-merged with ``config/user.yaml``
(same loader as the rest of the app).

The API backend raises :class:`LLMTimeoutError` / :class:`LLMCallError`;
each caller maps those onto the exact error semantics it already had for
the CLI (RuntimeError after retries, "unavailable" sentiment result, empty
string, ...).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

# Claude Opus 5.5: current Opus generation and the claude-api skill's default.
# Cheaper per token ($4 / $20 per MTok) than the Opus 4.7 the CLI pipeline was
# built against, with comparable-or-better report quality. Override with
# DAYTRADER_LLM_MODEL (e.g. claude-sonnet-5-5 at $2 / $10) to cut cost further.
DEFAULT_API_MODEL = "claude-opus-5-5"
DEFAULT_MAX_TOKENS = 32000
VALID_BACKENDS = ("cli", "api")

ENV_BACKEND = "DAYTRADER_LLM_BACKEND"
ENV_MODEL = "DAYTRADER_LLM_MODEL"
ENV_MAX_TOKENS = "DAYTRADER_LLM_MAX_TOKENS"
ENV_API_KEY = "ANTHROPIC_API_KEY"

# Server-side refusal fallback (beta). "default" routes by refusal category.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
WEB_SEARCH_TOOL_TYPE = "web_search_20260209"
MAX_PAUSE_CONTINUATIONS = 5

# Repo root when running from a checkout / editable install:
# src/daytrader/core/llm.py → parents[3]
_DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class LLMError(Exception):
    """Base class for API-backend failures."""


class LLMTimeoutError(LLMError):
    """The call exceeded the caller's timeout."""


class LLMCallError(LLMError):
    """Any other API failure (HTTP error, connection error, refusal, ...)."""


class LLMConfigError(LLMError):
    """Backend misconfigured (unknown backend name, missing API key)."""


@dataclass(frozen=True)
class LLMSettings:
    backend: str
    backend_source: str
    model: str
    model_source: str
    max_tokens: int
    effort: str | None
    web_search: bool
    web_search_max_uses: int
    fallbacks: bool


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    stop_reason: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


# ---------------------------------------------------------------------------
# Settings resolution
# ---------------------------------------------------------------------------


def _load_ai_config(project_root: Path):
    from daytrader.core.config import AIConfig, load_config

    try:
        cfg = load_config(
            default_config=project_root / "config" / "default.yaml",
            user_config=project_root / "config" / "user.yaml",
        )
        return cfg.ai
    except Exception:  # noqa: BLE001 — unreadable config → defaults
        return AIConfig()


def load_llm_settings(
    project_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> LLMSettings:
    """Resolve backend / model / max_tokens from env → config → defaults."""
    env = os.environ if env is None else env
    root = Path(project_root) if project_root else _DEFAULT_PROJECT_ROOT
    ai = _load_ai_config(root)

    env_backend = (env.get(ENV_BACKEND) or "").strip().lower()
    if env_backend:
        backend, backend_source = env_backend, f"env {ENV_BACKEND}"
    elif ai.backend:
        backend, backend_source = ai.backend.strip().lower(), "config ai.backend"
    else:
        backend, backend_source = "cli", "default"
    if backend not in VALID_BACKENDS:
        raise LLMConfigError(
            f"unknown LLM backend {backend!r} (from {backend_source}); "
            f"expected one of {VALID_BACKENDS}"
        )

    env_model = (env.get(ENV_MODEL) or "").strip()
    if env_model:
        model, model_source = env_model, f"env {ENV_MODEL}"
    elif ai.model:
        model, model_source = ai.model, "config ai.model"
    else:
        model, model_source = DEFAULT_API_MODEL, "default"

    env_max = (env.get(ENV_MAX_TOKENS) or "").strip()
    if env_max:
        try:
            max_tokens = int(env_max)
        except ValueError as e:
            raise LLMConfigError(f"{ENV_MAX_TOKENS}={env_max!r} is not an int") from e
    else:
        max_tokens = int(ai.max_tokens or DEFAULT_MAX_TOKENS)

    return LLMSettings(
        backend=backend,
        backend_source=backend_source,
        model=model,
        model_source=model_source,
        max_tokens=max_tokens,
        effort=ai.effort or None,
        web_search=bool(ai.web_search),
        web_search_max_uses=int(ai.web_search_max_uses),
        fallbacks=bool(ai.fallbacks),
    )


def resolve_api_key(
    project_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str | None, str]:
    """Return ``(key, source)``. Never logs or prints the key itself.

    ``source`` is ``"env ANTHROPIC_API_KEY"``, ``"config/secrets.yaml"`` or
    ``"missing"``. Only ``anthropic.api_key`` is read from secrets.yaml, so
    a box without Telegram secrets still works.
    """
    env = os.environ if env is None else env
    key = (env.get(ENV_API_KEY) or "").strip()
    if key:
        return key, f"env {ENV_API_KEY}"
    root = Path(project_root) if project_root else _DEFAULT_PROJECT_ROOT
    path = root / "config" / "secrets.yaml"
    try:
        import yaml

        raw = yaml.safe_load(path.read_text()) or {}
        key = str(((raw.get("anthropic") or {}).get("api_key")) or "").strip()
    except Exception:  # noqa: BLE001 — missing/unreadable file → missing
        key = ""
    if key:
        return key, "config/secrets.yaml"
    return None, "missing"


# ---------------------------------------------------------------------------
# Logging (stderr, once per backend/model per process — launchd/cron logs
# capture stderr; the app does not configure `logging` handlers)
# ---------------------------------------------------------------------------

_announced: set[tuple[str, str]] = set()


def _announce(backend: str, model: str, detail: str) -> None:
    key = (backend, model)
    if key in _announced:
        return
    _announced.add(key)
    print(f"[llm] backend={backend} model={model} ({detail})", file=sys.stderr)


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class CLIBackend:
    """``claude -p`` — thin subprocess wrapper, behavior unchanged.

    Callers pass the exact argv they always used and keep their own handling
    of ``subprocess.TimeoutExpired`` / ``FileNotFoundError`` / exit codes.
    """

    name = "cli"

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings

    def run(
        self,
        cmd: list[str],
        *,
        timeout: float,
        input: str | None = None,
    ) -> subprocess.CompletedProcess:
        _announce("cli", "claude-cli-default", "claude -p subprocess")
        return subprocess.run(
            cmd,
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
        )


class APIBackend:
    """Anthropic Messages API via the official SDK (streaming)."""

    name = "api"

    def __init__(
        self,
        settings: LLMSettings,
        api_key: str | None,
        key_source: str = "",
        client: Any = None,
    ) -> None:
        self.settings = settings
        self.model = settings.model
        self._api_key = api_key
        self._key_source = key_source
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise LLMConfigError(
                    "LLM backend=api but no API key: set ANTHROPIC_API_KEY or "
                    "anthropic.api_key in config/secrets.yaml"
                )
            import anthropic

            # SDK retries disabled: callers own retry/backoff so the retry
            # count matches the CLI path exactly.
            self._client = anthropic.Anthropic(api_key=self._api_key, max_retries=0)
        return self._client

    @staticmethod
    def _split_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """System-role entries → top-level ``system`` blocks; rest → messages."""
        system: list[dict[str, Any]] = []
        convo: list[dict[str, Any]] = []
        for msg in messages:
            content = msg["content"]
            if msg["role"] == "system":
                if isinstance(content, list):
                    system.extend(b for b in content if b.get("type") == "text")
                else:
                    system.append({"type": "text", "text": str(content)})
            else:
                convo.append({"role": msg["role"], "content": content})
        return system, convo

    @staticmethod
    def _final_text(content: list[Any]) -> str:
        """Text the model wrote after its last web-search round.

        `claude -p` prints only the final answer; with server-side web search
        the API returns pre-search narration ("I'll search for...") in the
        same message, which would break the strict output parsers. Take the
        text blocks after the last server-tool block (all text if none).
        """
        last_tool = -1
        for i, block in enumerate(content):
            btype = getattr(block, "type", "")
            if btype == "server_tool_use" or btype.endswith("_tool_result"):
                last_tool = i
        texts = [
            getattr(b, "text", "")
            for b in content[last_tool + 1:]
            if getattr(b, "type", "") == "text"
        ]
        if not any(t.strip() for t in texts):
            texts = [getattr(b, "text", "") for b in content if getattr(b, "type", "") == "text"]
        return "".join(texts)

    def complete(
        self,
        *,
        timeout: float,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """One logical completion (resuming ``pause_turn`` internally).

        ``timeout`` is a wall-clock budget for the whole call, mirroring the
        CLI's ``subprocess.run(timeout=...)``.
        """
        if messages is None:
            messages = [{"role": "user", "content": prompt or ""}]
        system, convo = self._split_messages(messages)
        s = self.settings
        # Adaptive thinking shares max_tokens with the answer, so never go
        # below the configured floor even if the caller asked for less.
        eff_max = max(int(max_tokens or 0), s.max_tokens)

        params: dict[str, Any] = {"model": self.model, "max_tokens": eff_max}
        if system:
            params["system"] = system
        if s.web_search:
            params["tools"] = [{
                "type": WEB_SEARCH_TOOL_TYPE,
                "name": "web_search",
                "max_uses": s.web_search_max_uses,
            }]
        if s.effort:
            params["output_config"] = {"effort": s.effort}

        client = self._get_client()
        _announce("api", self.model, f"Anthropic API, key from {self._key_source or 'n/a'}")

        import anthropic

        deadline = time.monotonic() + timeout
        totals = {"in": 0, "out": 0, "cw": 0, "cr": 0}
        msg = None
        for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMTimeoutError(f"api timeout after {timeout}s")
            try:
                msg = self._stream_once(client, params, convo, remaining, deadline, timeout)
            except LLMError:
                raise
            except anthropic.APITimeoutError as e:
                raise LLMTimeoutError(f"api timeout after {timeout}s") from e
            except anthropic.APIStatusError as e:
                raise LLMCallError(
                    f"api status={e.status_code} {type(e).__name__}: {str(e)[:300]}"
                ) from e
            except anthropic.APIConnectionError as e:
                raise LLMCallError(f"api connection error: {str(e)[:300]}") from e

            usage = getattr(msg, "usage", None)
            if usage is not None:
                totals["in"] += getattr(usage, "input_tokens", 0) or 0
                totals["out"] += getattr(usage, "output_tokens", 0) or 0
                totals["cw"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
                totals["cr"] += getattr(usage, "cache_read_input_tokens", 0) or 0

            if msg.stop_reason == "pause_turn":
                # Server-side tool loop hit its iteration cap; resend so it
                # resumes (no extra "continue" user message).
                convo = convo + [{"role": "assistant", "content": msg.content}]
                continue
            break

        assert msg is not None
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMCallError(f"api refusal (category={category})")
        if msg.stop_reason == "pause_turn":
            raise LLMCallError("api pause_turn not resolved after continuations")
        if msg.stop_reason == "max_tokens":
            print(
                f"[llm] warning: response hit max_tokens={eff_max}; output may be truncated",
                file=sys.stderr,
            )

        return LLMResponse(
            text=self._final_text(list(msg.content)),
            model=getattr(msg, "model", None) or self.model,
            stop_reason=msg.stop_reason or "end_turn",
            input_tokens=totals["in"],
            output_tokens=totals["out"],
            cache_creation_tokens=totals["cw"],
            cache_read_tokens=totals["cr"],
        )

    def _stream_once(
        self,
        client: Any,
        params: dict[str, Any],
        convo: list[dict[str, Any]],
        remaining: float,
        deadline: float,
        timeout: float,
    ) -> Any:
        call = dict(params, messages=convo, timeout=remaining)
        if self.settings.fallbacks:
            stream_ctx = client.beta.messages.stream(
                **call, betas=[FALLBACK_BETA], extra_body={"fallbacks": "default"}
            )
        else:
            stream_ctx = client.messages.stream(**call)
        with stream_ctx as stream:
            for _event in stream:
                if time.monotonic() > deadline:
                    raise LLMTimeoutError(f"api timeout after {timeout}s")
            return stream.get_final_message()


LLMBackend = CLIBackend | APIBackend


def get_llm_backend(
    project_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> LLMBackend:
    """Build the backend selected by env/config. Does not contact the network."""
    settings = load_llm_settings(project_root, env)
    if settings.backend == "api":
        key, source = resolve_api_key(project_root, env)
        return APIBackend(settings, api_key=key, key_source=source)
    return CLIBackend(settings)
