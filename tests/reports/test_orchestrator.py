"""Tests for end-to-end Orchestrator (multi-instrument, mocked services)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from daytrader.core.state import StateDB
from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.core.orchestrator import (
    Orchestrator,
    PipelineResult,
)


VALID_REPORT = (
    "## Lock-in\nstatus\n\n"
    "## Multi-TF Analysis\n"
    "### 📊 MES\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "### 📊 MNQ\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "### 📊 MGC\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n\n"
    "## 突发新闻\nnone\n\n"
    "## F. 期货结构\n### F-MES\nok\n### F-MGC\nok\n\n"
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
