"""SentimentCollector — invokes `claude -p` with sentiment prompt, parses response."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from daytrader.reports.sentiment.dataclasses import SentimentResult
from daytrader.reports.sentiment.parser import ParseError, parse_sentiment_response
from daytrader.reports.sentiment.prompts import build_sentiment_prompt


class SentimentCollector:
    """Calls `claude -p` with a focused sentiment prompt; parses the response.

    Failures (timeout, non-zero exit, parse error) are caught and translated
    into `SentimentResult.unavailable_due_to(...)` — never raises to the
    caller. The orchestrator must always be able to continue after this.
    """

    DEFAULT_TIMEOUT_S = 180

    def __init__(
        self,
        symbols: list[str],
        time_window: str = "past 24h",
        timeout_s: int = DEFAULT_TIMEOUT_S,
        failure_log_dir: Path | None = None,
    ) -> None:
        self._symbols = list(symbols)
        self._time_window = time_window
        self._timeout_s = timeout_s
        self._failure_log_dir = failure_log_dir or (
            Path("data") / "logs" / "sentiment-failures"
        )

    def collect(self) -> SentimentResult:
        prompt = build_sentiment_prompt(self._symbols, time_window=self._time_window)
        try:
            result = subprocess.run(
                ["claude", "-p"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
        except subprocess.TimeoutExpired:
            return SentimentResult.unavailable_due_to(
                f"claude -p timeout after {self._timeout_s}s"
            )
        except FileNotFoundError:
            return SentimentResult.unavailable_due_to(
                "claude CLI not found on PATH"
            )

        if result.returncode != 0:
            return SentimentResult.unavailable_due_to(
                f"claude -p exit={result.returncode}: {result.stderr.strip()[:200]}"
            )

        raw = result.stdout
        try:
            return parse_sentiment_response(raw, expected_symbols=self._symbols)
        except ParseError as e:
            self._log_raw_response(raw, str(e))
            return SentimentResult.unavailable_due_to(f"parse failed: {e}")

    def _log_raw_response(self, raw: str, reason: str) -> None:
        """Best-effort save of unparseable responses for debugging."""
        try:
            self._failure_log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            target = self._failure_log_dir / f"sentiment-{ts}.txt"
            target.write_text(f"# parse failure: {reason}\n\n{raw}", encoding="utf-8")
        except Exception as e:
            # Non-fatal — log to stderr but don't propagate
            print(f"[sentiment_collector] could not save raw response: {e}",
                  file=sys.stderr)
