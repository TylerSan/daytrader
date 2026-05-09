"""Tests for AIAnalyst (claude -p backend)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from daytrader.reports.core.ai_analyst import AIAnalyst, AIResult


def _completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    cp = MagicMock()
    cp.stdout = stdout
    cp.stderr = stderr
    cp.returncode = returncode
    return cp


def test_ai_analyst_returns_text_from_claude_cli(monkeypatch):
    """call() invokes `claude -p` and returns the stdout in AIResult.text."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return _completed_process("# Report\n\nbody")

    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.subprocess.run", fake_run
    )

    analyst = AIAnalyst()
    result = analyst.call(
        messages=[
            {"role": "system", "content": [{"type": "text", "text": "system instructions"}]},
            {"role": "user", "content": "user message"},
        ],
        max_tokens=4096,
    )

    assert isinstance(result, AIResult)
    assert result.text == "# Report\n\nbody"
    # tokens unavailable in CLI mode → 0
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    # cmd starts with "claude" and contains "-p"
    assert captured["cmd"][0] == "claude"
    assert "-p" in captured["cmd"]
    # Combined system + user content was passed via stdin
    assert "system instructions" in captured["input"]
    assert "user message" in captured["input"]


def test_ai_analyst_retries_on_nonzero_exit(monkeypatch):
    """Two non-zero exits then success → retried 3 times total."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) < 3:
            return _completed_process("", returncode=1, stderr="transient error")
        return _completed_process("ok")

    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.time.sleep", lambda _: None
    )

    analyst = AIAnalyst()
    result = analyst.call(
        messages=[{"role": "user", "content": "x"}],
        max_tokens=128,
    )

    assert result.text == "ok"
    assert len(calls) == 3


def test_ai_analyst_raises_after_max_retries(monkeypatch):
    """4 non-zero exits surface as RuntimeError (max_retries=3 means 1 initial + 3 retries)."""

    def fake_run(cmd, **kwargs):
        return _completed_process("", returncode=2, stderr="persistent")

    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.time.sleep", lambda _: None
    )

    analyst = AIAnalyst()
    with pytest.raises(RuntimeError, match="persistent"):
        analyst.call(
            messages=[{"role": "user", "content": "x"}],
            max_tokens=128,
        )


def test_ai_analyst_handles_subprocess_timeout(monkeypatch):
    """A subprocess.TimeoutExpired surfaces as a retry trigger, then RuntimeError."""

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=180)

    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.time.sleep", lambda _: None
    )

    analyst = AIAnalyst(max_retries=1)
    with pytest.raises(RuntimeError, match="timeout"):
        analyst.call(messages=[{"role": "user", "content": "x"}], max_tokens=128)
