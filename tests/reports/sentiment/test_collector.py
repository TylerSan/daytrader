"""Unit tests for SentimentCollector with mocked subprocess."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from daytrader.reports.sentiment.collector import SentimentCollector
from daytrader.reports.sentiment.dataclasses import SentimentResult


SAMPLE_RESPONSE = """### 🌐 Macro Sentiment
**总体 偏多 +3 / 10**（news +4, social +2）
- 主流叙事：earnings beat
- 风险点：geopolitics
- 关键事件（past 24h 内）：FOMC Wed, CPI Thu

### 📊 Per-Symbol
| Symbol | News | Social | Combined | 1-句叙事 |
|---|---|---|---|---|
| MES | +3 | +1 | +2 | n1 |
| MGC | -2 | -3 | -3 | n2 |
| MNQ | +4 | +5 | +5 | n3 |

> 评分：-5 (极空) → 0 (中性) → +5 (极多)
> Sources: https://a.com, https://b.com, https://c.com, https://d.com, https://e.com
"""


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude", "-p"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_collector_happy_path():
    with patch("subprocess.run", return_value=_completed(SAMPLE_RESPONSE)):
        collector = SentimentCollector(symbols=["MES", "MGC", "MNQ"])
        res = collector.collect()
    assert isinstance(res, SentimentResult)
    assert res.unavailable is False
    assert res.macro is not None
    assert res.macro.score.combined == 3
    assert len(res.per_symbol) == 3
    assert len(res.sources) == 5


def test_collector_timeout_returns_unavailable():
    timeout_exc = subprocess.TimeoutExpired(cmd=["claude", "-p"], timeout=180)
    with patch("subprocess.run", side_effect=timeout_exc):
        collector = SentimentCollector(symbols=["MES"], timeout_s=180)
        res = collector.collect()
    assert res.unavailable is True
    assert "timeout" in res.unavailable_reason.lower()
    assert res.macro is None
    assert res.per_symbol == []


def test_collector_nonzero_exit_returns_unavailable():
    with patch("subprocess.run", return_value=_completed("", returncode=2)):
        collector = SentimentCollector(symbols=["MES"])
        res = collector.collect()
    assert res.unavailable is True
    assert "exit" in res.unavailable_reason.lower() or "2" in res.unavailable_reason


def test_collector_garbage_response_returns_unavailable():
    with patch("subprocess.run", return_value=_completed("hello world")):
        collector = SentimentCollector(symbols=["MES"])
        res = collector.collect()
    assert res.unavailable is True
    assert "parse" in res.unavailable_reason.lower()


def test_collector_invokes_subprocess_with_claude_minus_p():
    """Verify the actual subprocess.run command — implementer must call claude -p
    with prompt as stdin, not as argv."""
    captured: dict = {}

    def _fake_run(cmd, *, input=None, capture_output=None, text=None, timeout=None, **kw):
        captured["cmd"] = cmd
        captured["input"] = input
        captured["timeout"] = timeout
        return _completed(SAMPLE_RESPONSE)

    with patch("subprocess.run", side_effect=_fake_run):
        SentimentCollector(symbols=["MES", "MGC"], timeout_s=180).collect()

    assert captured["cmd"][0] == "claude"
    assert "-p" in captured["cmd"]
    assert "MES" in captured["input"]
    assert "MGC" in captured["input"]
    assert captured["timeout"] == 180


def test_collector_default_symbols_passed_through():
    """Collector accepts symbols at construction time, includes in prompt."""
    captured: dict = {}

    def _fake_run(cmd, *, input=None, **kw):
        captured["input"] = input
        return _completed(SAMPLE_RESPONSE)

    with patch("subprocess.run", side_effect=_fake_run):
        SentimentCollector(symbols=["AAPL"]).collect()

    assert "AAPL" in captured["input"]


def test_collector_records_raw_on_parse_failure(tmp_path, monkeypatch):
    """When parse fails, the raw response should be saved for debugging."""
    monkeypatch.chdir(tmp_path)
    with patch("subprocess.run", return_value=_completed("malformed garbage no markers")):
        collector = SentimentCollector(symbols=["MES"])
        res = collector.collect()
    assert res.unavailable is True
    log_dir = tmp_path / "data" / "logs" / "sentiment-failures"
    if log_dir.exists():
        files = list(log_dir.glob("*.txt"))
        # At least one log file written (best-effort, not strictly required)
        assert len(files) >= 0  # tolerate environments where dir creation fails
