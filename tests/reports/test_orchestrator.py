"""Tests for end-to-end Orchestrator (multi-instrument, mocked services)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from daytrader.core.state import StateDB
from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.core.orchestrator import (
    Orchestrator,
    PipelineResult,
)
from daytrader.reports.sentiment.dataclasses import SentimentResult


@pytest.fixture(autouse=True)
def _mock_sentiment_section():
    """Stub out SentimentSection in the orchestrator so unit tests never spawn
    real `claude -p` subprocesses. Phase 4.5 wiring."""
    with patch(
        "daytrader.reports.core.orchestrator.SentimentSection"
    ) as mock_section_cls:
        mock_section = mock_section_cls.return_value
        mock_section.collect.return_value = SentimentResult.unavailable_due_to(
            "test mock — sentiment disabled"
        )
        mock_section.render.return_value = (
            "## D. 情绪面 / Sentiment Index\n\n"
            "⚠️ test mock — sentiment disabled\n"
        )
        yield mock_section_cls


VALID_REPORT = (
    "## Lock-in\nstatus\n\n"
    "## Multi-TF Analysis\n"
    "### 📊 MES\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "### 📊 MNQ\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "### 📊 MGC\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n\n"
    "## 突发新闻\nnone\n\n"
    "## F. 期货结构\n### F-MES\nok\n### F-MGC\nok\n\n"
    "## D. 情绪面 / Sentiment Index\n⚠️ unavailable\n\n"
    "## C. 计划复核\n\n"
    "### C-MES\n\n**Today's plan**:\n"
    "- Setup: ORB long\n- Direction: long\n- Entry: 5240.00\n"
    "- Stop: 5232.00\n- Target: 5256.00\n- R unit: $50\n\n"
    "**Invalidation conditions**:\n1. below 5232\n2. SPY drop\n3. VIX above 18\n\n"
    "### C-MGC\n\n**Today's plan**:\n"
    "- Setup: VWAP fade\n- Direction: short\n- Entry: 2350.00\n"
    "- Stop: 2355.00\n- Target: 2340.00\n- R unit: $50\n\n"
    "**Invalidation conditions**:\n1. above 2355\n2. DXY drop\n3. Rate cut\n\n"
    "## B. 市场叙事\nnarr\n\n"
    "## A. 建议\nno action\n\n"
    "## 数据快照\nok\n"
)


def _ai_result(text=VALID_REPORT):
    r = MagicMock()
    r.text = text
    r.input_tokens = 1000
    r.output_tokens = 500
    r.cache_creation_tokens = 0
    r.cache_read_tokens = 0
    r.model = "claude-opus-4-7"
    r.stop_reason = "end_turn"
    return r


def _ohlcv(c=5240.0):
    return OHLCV(
        timestamp=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def _make_orchestrator(tmp_path, fake_ib, fake_ai):
    state_db_path = tmp_path / "state.db"
    state = StateDB(str(state_db_path))
    state.initialize()
    return state, Orchestrator(
        state_db=state,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        contract_path=tmp_path / "missing-contract.md",
        journal_db_path=tmp_path / "missing-journal.db",
        vault_root=tmp_path / "vault",
        fallback_dir=tmp_path / "fallback",
        daily_folder="Daily",
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
    )


def test_orchestrator_run_premarket_persists_per_instrument_plans(tmp_path):
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )

    assert isinstance(result, PipelineResult)
    assert result.success is True
    assert result.report_path is not None
    assert result.report_path.exists()

    # Two plan rows: MES + MGC
    mes_plan = state.get_plan_for_date("2026-04-25", "MES")
    assert mes_plan is not None
    assert mes_plan["setup_name"] == "ORB long"
    assert mes_plan["entry"] == pytest.approx(5240.0)

    mgc_plan = state.get_plan_for_date("2026-04-25", "MGC")
    assert mgc_plan is not None
    assert mgc_plan["setup_name"] == "VWAP fade"
    assert mgc_plan["entry"] == pytest.approx(2350.0)

    # MNQ context-only — no plan saved
    mnq_plan = state.get_plan_for_date("2026-04-25", "MNQ")
    assert mnq_plan is None

    # source_report_path on plan rows points to the actual file written
    assert mes_plan["source_report_path"] == str(result.report_path)
    assert mgc_plan["source_report_path"] == str(result.report_path)

    # Report row marked success
    report_row = state.get_report_by_id(result.report_id)
    assert report_row["status"] == "success"


def test_orchestrator_marks_validation_failure(tmp_path):
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text="(too short)")

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert result.success is False
    assert "validation" in (result.failure_reason or "").lower()


def test_orchestrator_idempotency_skips_repeat(tmp_path):
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    first = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert first.success is True

    second = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert second.skipped_idempotent is True
    assert fake_ai.call.call_count == 1


def test_orchestrator_marks_failed_on_pipeline_exception(tmp_path):
    """Pipeline exception → row marked 'failed' + exception re-raised."""
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.side_effect = ConnectionError("IB dropped")

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)

    with pytest.raises(ConnectionError, match="IB dropped"):
        orchestrator.run_premarket(
            run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
        )

    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "state.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM reports ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["status"] == "failed"
    assert "ConnectionError" in row["failure_reason"]


def test_orchestrator_invokes_pdf_and_telegram_when_provided(tmp_path):
    """When deliverers are wired, they get called with the report content."""
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    from daytrader.core.ib_client import OpenInterest
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    fake_pdf = MagicMock()
    fake_pdf.render_to_pdf.return_value = tmp_path / "out.pdf"
    (tmp_path / "out.pdf").write_bytes(b"%PDF-1.4 fake")

    fake_charts = MagicMock()
    fake_charts.render_all.return_value = MagicMock(
        tf_stack_paths={"MES": tmp_path / "c.png"}
    )
    (tmp_path / "c.png").write_bytes(b"\x89PNG fake")

    fake_telegram = MagicMock()
    async def _push(*args, **kwargs):
        return MagicMock(success=True, message_count=3)
    fake_telegram.push = _push

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    orchestrator.pdf_renderer = fake_pdf
    orchestrator.chart_renderer = fake_charts
    orchestrator.telegram_pusher = fake_telegram

    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert result.success is True
    fake_pdf.render_to_pdf.assert_called_once()
    fake_charts.render_all.assert_called_once()


def test_orchestrator_succeeds_when_pdf_renderer_fails(tmp_path):
    """PDF failure (e.g., missing libs) does NOT block the pipeline."""
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    from daytrader.core.ib_client import OpenInterest
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    fake_pdf = MagicMock()
    fake_pdf.render_to_pdf.side_effect = OSError("missing libpango")

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    orchestrator.pdf_renderer = fake_pdf

    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    # PDF failed but the report still succeeded
    assert result.success is True


# ---------- Phase 5 T10: run_eod tests ----------


VALID_EOD_REPORT = (
    "# EOD Report\n"
    "## Lock-in Metadata\nstatus\n\n"
    "## 📊 MES — Multi-TF\n#### W\nx\n#### D\nx\n#### 4H\nx\n\n"
    "## 📊 MNQ — Multi-TF\n#### W\nx\n#### D\nx\n#### 4H\nx\n\n"
    "## 📊 MGC — Multi-TF\n#### W\nx\n#### D\nx\n#### 4H\nx\n\n"
    "## F. 期货结构\n### F-MES\nbullish\n\n"
    "## D. 情绪面 / Sentiment Index\nx\n\n"
    "## 今日交易档案 / Today's Trade Archive\n0 trades\n\n"
    "## 🔄 Plan Retrospective\n(no plan)\n\n"
    "## C. 计划复核\nx\n\n"
    "## B. 市场叙事\nnarr\n\n"
    "## 📅 Tomorrow Preliminary\nplan\n\n"
    "## 数据快照\nok\n"
)


def _eod_fake_ib():
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    return fake_ib


def test_run_eod_idempotent_skips_repeat(tmp_path):
    """If state_db says EOD already done today, skip without spawning pipeline."""
    fake_ib = _eod_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_EOD_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    first = orchestrator.run_eod(
        run_at=datetime(2026, 5, 4, 21, tzinfo=timezone.utc),
    )
    assert first.success is True

    second = orchestrator.run_eod(
        run_at=datetime(2026, 5, 4, 21, tzinfo=timezone.utc),
    )
    assert second.skipped_idempotent is True
    # AI was only called once (second run skipped)
    assert fake_ai.call.call_count == 1


def test_run_eod_writes_eod_md_and_marks_success(tmp_path):
    """run_eod writes <date>-eod.md and marks the report row 'success'."""
    fake_ib = _eod_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_EOD_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_eod(
        run_at=datetime(2026, 5, 4, 21, tzinfo=timezone.utc),
    )
    assert result.success is True
    assert result.report_path is not None
    assert result.report_path.name == "2026-05-04-eod.md"
    assert result.report_path.exists()

    report_row = state.get_report_by_id(result.report_id)
    assert report_row["status"] == "success"
    assert report_row["report_type"] == "eod"

    # No premarket plan was extracted/persisted from EOD output (retrospective,
    # not forward-looking).
    assert state.get_plan_for_date("2026-05-04", "MES") is None


def test_run_eod_marks_validation_failure(tmp_path):
    """If AI output fails section validation, run_eod marks the row failed."""
    fake_ib = _eod_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text="(too short)")

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_eod(
        run_at=datetime(2026, 5, 4, 21, tzinfo=timezone.utc),
    )
    assert result.success is False
    assert "validation" in (result.failure_reason or "").lower()
    report_row = state.get_report_by_id(result.report_id)
    assert report_row["status"] == "failed"
