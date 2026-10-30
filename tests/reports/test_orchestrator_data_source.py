"""Orchestrator data-source provenance: footer, Telegram prefix, state row."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.core.state import StateDB
from daytrader.reports.core.data_source import DATA_SOURCE_NOTE_YF
from daytrader.reports.core.orchestrator import Orchestrator
from daytrader.reports.sentiment.dataclasses import SentimentResult

from tests.reports.test_orchestrator import (
    VALID_EOD_REPORT,
    VALID_INTRADAY_4H_REPORT,
    VALID_NIGHT_ASIA_REPORT,
    VALID_REPORT,
)

FOOTER = "\n\n---\n" + DATA_SOURCE_NOTE_YF + "\n"


@pytest.fixture(autouse=True)
def _mock_sentiment_section():
    with patch("daytrader.reports.core.orchestrator.SentimentSection") as cls:
        cls.return_value.collect.return_value = SentimentResult.unavailable_due_to("mock")
        cls.return_value.render.return_value = "## D. 情绪面 / Sentiment Index\n\nmock\n"
        yield cls


def _ai_result(text):
    r = MagicMock()
    r.text = text
    r.input_tokens = 1000
    r.output_tokens = 500
    r.cache_creation_tokens = 0
    r.cache_read_tokens = 0
    return r


def _fake_client():
    c = MagicMock()
    c.is_healthy.return_value = True
    c.get_bars.return_value = [
        OHLCV(
            timestamp=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
            open=5240.0, high=5241.0, low=5239.0, close=5240.0, volume=1000,
        )
    ]
    c.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    return c


class _Telegram:
    def __init__(self):
        self.calls: list[dict] = []

    async def push(self, **kwargs):
        self.calls.append(kwargs)
        return MagicMock(success=True)


def _make(tmp_path, text, **kw):
    state = StateDB(str(tmp_path / "state.db"))
    state.initialize()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text)
    tg = _Telegram()
    orch = Orchestrator(
        state_db=state,
        ib_client=_fake_client(),
        ai_analyst=fake_ai,
        contract_path=tmp_path / "missing-contract.md",
        journal_db_path=tmp_path / "missing-journal.db",
        vault_root=tmp_path / "vault",
        fallback_dir=tmp_path / "fallback",
        daily_folder="Daily",
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
        telegram_pusher=tg,
        **kw,
    )
    return state, orch, tg, fake_ai


CASES = [
    ("run_premarket", VALID_REPORT, datetime(2026, 4, 25, 13, tzinfo=timezone.utc), True),
    ("run_eod", VALID_EOD_REPORT, datetime(2026, 5, 4, 21, tzinfo=timezone.utc), True),
    ("run_intraday_4h_1", VALID_INTRADAY_4H_REPORT, datetime(2026, 5, 5, 14, tzinfo=timezone.utc), True),
    ("run_night", VALID_NIGHT_ASIA_REPORT, datetime(2026, 5, 6, 2, tzinfo=timezone.utc), False),
]


def test_default_data_source_is_ib(tmp_path):
    _, orch, _, _ = _make(tmp_path, VALID_REPORT)
    assert orch.data_source == "ib"


@pytest.mark.parametrize("method,text,run_at,pushes", CASES)
def test_ib_run_has_no_footer_no_prefix(tmp_path, method, text, run_at, pushes):
    state, orch, tg, _ = _make(tmp_path, text)
    result = getattr(orch, method)(run_at=run_at)
    assert result.success is True, result.failure_reason
    written = result.report_path.read_text()
    assert "数据源：yfinance" not in written
    assert written.rstrip().endswith(text.rstrip())
    assert state.get_report_by_id(result.report_id)["data_source"] == "ib"
    if pushes:
        assert len(tg.calls) == 1
        assert tg.calls[0]["text_messages"] == [text]
    else:
        assert tg.calls == []


@pytest.mark.parametrize("method,text,run_at,pushes", CASES)
def test_yfinance_run_footer_prefix_and_row(tmp_path, method, text, run_at, pushes):
    state, orch, tg, fake_ai = _make(tmp_path, text, data_source="yfinance")
    result = getattr(orch, method)(run_at=run_at)
    assert result.success is True, result.failure_reason
    written = result.report_path.read_text()
    assert FOOTER.strip() in written
    assert written.rstrip().endswith(DATA_SOURCE_NOTE_YF)
    assert state.get_report_by_id(result.report_id)["data_source"] == "yfinance"
    if pushes:
        assert len(tg.calls) == 1
        msgs = tg.calls[0]["text_messages"]
        assert msgs[0].startswith("[yfinance 降级] ")
        assert DATA_SOURCE_NOTE_YF in msgs[0]
    else:
        assert tg.calls == []
    # The prompt sent to the AI carries the provenance note too.
    sent = fake_ai.call.call_args.kwargs["messages"][1]["content"]
    assert "数据源：yfinance" in sent


def test_yfinance_validation_failure_records_source_without_writing(tmp_path):
    state, orch, tg, _ = _make(tmp_path, "(too short)", data_source="yfinance")
    result = orch.run_premarket(run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc))
    assert result.success is False
    row = state.get_report_by_id(result.report_id)
    assert row["status"] == "failed" and row["data_source"] == "yfinance"
    assert tg.calls == []


def test_helpers_are_identity_for_ib(tmp_path):
    _, orch, _, _ = _make(tmp_path, VALID_REPORT)
    assert orch._annotate_report_text("abc") == "abc"
    assert orch._telegram_messages("abc") == ["abc"]
    orch.data_source = "yfinance"
    assert orch._annotate_report_text("abc") == "abc" + FOOTER
    assert orch._telegram_messages("abc") == ["[yfinance 降级] abc"]
