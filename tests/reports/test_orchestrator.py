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
    # 🌐 Cross-Asset Narrative + 📰 Breaking News added 2026-05-05 (I7) —
    # validator now enforces these sections per eod.md template lines 11-12.
    "## 🌐 Cross-Asset Narrative\nstocks up, dollar flat\n\n"
    "## 📰 Breaking News\nnone\n\n"
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


# ---------------------------------------------------------------------------
# C2 — intraday fetcher uses date_et to pin end_time (not "now")
# Caught 2026-05-05 by code-reviewer agent. Pre-fix the lambda was:
#   lambda sym, d: self.ib_client.get_bars(symbol=sym, timeframe="5m", bars=78)
# discarding `d` and defaulting end_time=None → "now". Backfilling Monday's
# EOD on Tuesday morning thus fetched Tuesday morning's bars instead of
# Monday's full session — wrong day's data into plan_retrospective_daily.
# ---------------------------------------------------------------------------


def test_run_eod_persists_warnings_to_state_failures(tmp_path):
    """When EODGenerator returns warnings (non-fatal failures during the
    pipeline), orchestrator must persist each one via state.log_failure
    so the user can audit them. I1 fix 2026-05-05."""
    fake_ib = _eod_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_EOD_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)

    # Patch the EODGenerator class within run_eod so .generate() returns
    # an outcome with non-empty warnings, regardless of the real pipeline.
    from daytrader.reports.types.eod import EODOutcome
    from daytrader.reports.core.output_validator import ValidationResult

    fake_outcome = EODOutcome(
        report_text=VALID_EOD_REPORT,
        ai_result=_ai_result(text=VALID_EOD_REPORT),
        validation=ValidationResult(ok=True, missing=[]),
        retrospective_rows={},
        bars_by_symbol_and_tf={},
        warnings=(
            "retrospective: ValueError: simulator exploded",
            "tomorrow: KeyError: missing sentiment field",
        ),
    )

    # EODGenerator is lazy-imported inside run_eod, so patch the source module.
    with patch(
        "daytrader.reports.types.eod.EODGenerator"
    ) as mock_gen_cls:
        mock_gen_cls.return_value.generate.return_value = fake_outcome
        result = orchestrator.run_eod(
            run_at=datetime(2026, 5, 4, 21, tzinfo=timezone.utc),
        )
        assert result.success is True

    # Both warnings must appear in state.failures
    failures = state.list_unresolved_failures()
    stages = sorted(f["failure_stage"] for f in failures)
    assert stages == ["retrospective", "tomorrow"], (
        f"expected stages ['retrospective', 'tomorrow'], got {stages!r}"
    )
    reasons = {f["failure_stage"]: f["failure_reason"] for f in failures}
    assert "ValueError: simulator exploded" in reasons["retrospective"]
    assert "KeyError" in reasons["tomorrow"]


def test_intraday_fetcher_pins_end_time_to_date_et_rth_close(tmp_path):
    """Orchestrator._make_intraday_fetcher returns a closure that calls
    ib_client.get_bars with end_time = <date_et> 16:00 ET (= RTH close)
    so backfill runs see the correct trading day's bars, not "now"."""
    fake_ib = _eod_fake_ib()
    fake_ai = MagicMock()
    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)

    fetcher = orchestrator._make_intraday_fetcher()
    fetcher("MES", "2026-05-04")

    # Verify get_bars was called with the right end_time
    assert fake_ib.get_bars.called
    call_kwargs = fake_ib.get_bars.call_args.kwargs
    assert call_kwargs["symbol"] == "MES"
    assert call_kwargs["timeframe"] == "5m"
    assert call_kwargs["bars"] == 78
    end_time = call_kwargs.get("end_time")
    assert end_time is not None, (
        "fetcher must pass end_time to pin the bar window to date_et — "
        "default 'now' fetches the wrong trading day on backfill runs"
    )
    # Should be 2026-05-04 16:00 ET (RTH close)
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    expected = datetime(2026, 5, 4, 16, 0, tzinfo=ET)
    assert end_time == expected, (
        f"end_time mismatch: got {end_time!r}, expected {expected!r}"
    )


# ---------- Phase 5.5: intraday-4h orchestrator tests ----------


VALID_INTRADAY_4H_REPORT = (
    "# Intraday 4H Report\n"
    "## 🔒 Lock-in Metadata\nstatus\n\n"
    "## 📊 MES — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "## 📊 MNQ — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "## 📊 MGC — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "## 🌐 Cross-Asset\nx\n## 📰 Breaking News\nx\n"
    "## F. 期货结构\nx\n## D. 情绪面\nx\n"
    "## 今日交易档案\nx\n## 🔄 Plan Retrospective\nx\n"
    "## C. 计划复核\nx\n## B. 市场叙事\nx\n## A. 建议\nA-3\n## 📑 数据快照\nx\n"
)


def _intraday_fake_ib():
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    return fake_ib


def test_run_intraday_4h_1_writes_obsidian_and_marks_success(tmp_path):
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_intraday_4h_1(
        run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
    )
    assert result.success is True
    assert result.report_path is not None
    assert result.report_path.name == "2026-05-05-0700PT-4H1.md"

    report_row = state.get_report_by_id(result.report_id)
    assert report_row["status"] == "success"
    assert report_row["report_type"] == "intraday-4h-1"


def test_run_intraday_4h_1_idempotent(tmp_path):
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    first = orchestrator.run_intraday_4h_1(
        run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
    )
    assert first.success is True
    second = orchestrator.run_intraday_4h_1(
        run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
    )
    assert second.skipped_idempotent is True
    assert fake_ai.call.call_count == 1


def test_run_intraday_4h_2_writes_4h2_filename(tmp_path):
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_intraday_4h_2(
        run_at=datetime(2026, 5, 5, 18, tzinfo=timezone.utc),
    )
    assert result.success is True
    assert result.report_path.name == "2026-05-05-1100PT-4H2.md"


def test_run_intraday_4h_validation_fail_marks_failed(tmp_path):
    """If AI output fails section validation, run marks the row failed."""
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text="(too short)")

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_intraday_4h_1(
        run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
    )
    assert result.success is False
    assert "validation" in (result.failure_reason or "").lower()


def test_run_intraday_4h_2_pins_retrospective_end_time_to_11_pt(tmp_path):
    """C2-style guarantee: 4h-2 retrospective fetcher uses end_time = 11:00 PT (14:00 ET)."""
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)

    # Use the public factory for 4h-2 fetcher
    fetcher = orchestrator._make_intraday_fetcher_for_cadence(
        end_time_et="14:00"
    )
    fetcher("MES", "2026-05-05")

    call_kwargs = fake_ib.get_bars.call_args.kwargs
    end_time = call_kwargs.get("end_time")
    assert end_time is not None
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    expected = datetime(2026, 5, 5, 14, 0, tzinfo=ET)
    assert end_time == expected


def test_run_intraday_4h_persists_warnings_to_state_failures(tmp_path):
    """When generator returns warnings, orchestrator persists to state.failures."""
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)

    from daytrader.reports.types.base import CadenceOutcome
    from daytrader.reports.core.output_validator import ValidationResult

    fake_outcome = CadenceOutcome(
        report_text=VALID_INTRADAY_4H_REPORT,
        ai_result=_ai_result(text=VALID_INTRADAY_4H_REPORT),
        validation=ValidationResult(ok=True, missing=[]),
        bars_by_symbol_and_tf={},
        warnings=("retrospective: ValueError: bad", "news: TimeoutError: net"),
    )

    with patch(
        "daytrader.reports.types.intraday_4h.IntradayFourHGenerator"
    ) as mock_gen_cls:
        mock_gen_cls.return_value.generate.return_value = fake_outcome
        result = orchestrator.run_intraday_4h_1(
            run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
        )
        assert result.success is True

    failures = state.list_unresolved_failures()
    stages = sorted(f["failure_stage"] for f in failures)
    assert "retrospective" in stages
    assert "news" in stages


# ---------- Phase 5.5: night/asia orchestrator tests ----------


VALID_NIGHT_ASIA_REPORT = (
    "# D-Archive\n"
    "## 🔒 Lock-in Metadata\nx\n"
    "## 📊 MES — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
    "## 📊 MNQ — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
    "## 📊 MGC — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
    "## F. 期货结构\nx\n## 📰 Breaking News\nx\n"
    "## D. Pattern Archive\npatterns\n## 📑 数据快照\nok\n"
)


def _night_fake_ib():
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    return fake_ib


def test_run_night_writes_obsidian_with_night_filename(tmp_path):
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_NIGHT_ASIA_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_night(
        run_at=datetime(2026, 5, 6, 2, tzinfo=timezone.utc),  # 19:00 PT (PDT)
    )
    assert result.success is True
    assert result.report_path.name == "2026-05-05-1900PT-night.md"
    report_row = state.get_report_by_id(result.report_id)
    assert report_row["report_type"] == "night"


def test_run_asia_writes_obsidian_with_asia_filename(tmp_path):
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_NIGHT_ASIA_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_asia(
        run_at=datetime(2026, 5, 6, 6, tzinfo=timezone.utc),  # 23:00 PT (PDT)
    )
    assert result.success is True
    assert result.report_path.name == "2026-05-05-2300PT-asia.md"


def test_run_night_does_not_push_telegram(tmp_path):
    """night/asia explicitly skip Telegram per spec §2.2."""
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_NIGHT_ASIA_REPORT)

    fake_telegram = MagicMock()
    push_calls = []
    async def _push(*args, **kwargs):
        push_calls.append((args, kwargs))
        return MagicMock(success=True, message_count=1)
    fake_telegram.push = _push

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    orchestrator.telegram_pusher = fake_telegram

    result = orchestrator.run_night(
        run_at=datetime(2026, 5, 6, 2, tzinfo=timezone.utc),
    )
    assert result.success is True
    # Telegram pusher.push should NOT have been called for night
    assert push_calls == [], (
        f"night cadence must not push Telegram, got {len(push_calls)} pushes"
    )


def test_run_asia_idempotent(tmp_path):
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_NIGHT_ASIA_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    first = orchestrator.run_asia(
        run_at=datetime(2026, 5, 6, 6, tzinfo=timezone.utc),
    )
    second = orchestrator.run_asia(
        run_at=datetime(2026, 5, 6, 6, tzinfo=timezone.utc),
    )
    assert first.success is True
    assert second.skipped_idempotent is True
    assert fake_ai.call.call_count == 1


def test_run_night_validation_fail_marks_failed(tmp_path):
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text="(too short)")

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_night(
        run_at=datetime(2026, 5, 6, 2, tzinfo=timezone.utc),
    )
    assert result.success is False
    assert "validation" in (result.failure_reason or "").lower()
