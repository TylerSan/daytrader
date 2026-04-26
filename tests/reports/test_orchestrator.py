"""Tests for end-to-end Orchestrator (mocked services)."""

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
    "## 1W\nx\n## 1D\nx\n## 4H\nx\n## 1H\nx\n\n"
    "## 突发新闻\nnone\n\n"
    "## C. 计划复核\n\n**Today's plan**:\n"
    "- Setup: ORB long\n"
    "- Direction: long\n"
    "- Entry: 5240.00\n"
    "- Stop: 5232.00\n"
    "- Target: 5256.00\n"
    "- R unit: $25\n\n"
    "**Invalidation conditions**:\n"
    "1. Below 5232\n2. SPY drop\n3. VIX above 18\n\n"
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


def test_orchestrator_run_premarket_persists_plan_and_writes(tmp_path):
    state_db_path = tmp_path / "state.db"
    state = StateDB(str(state_db_path))
    state.initialize()

    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    orchestrator = Orchestrator(
        state_db=state,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        contract_path=tmp_path / "missing-contract.md",
        journal_db_path=tmp_path / "missing-journal.db",
        vault_root=tmp_path / "vault",
        fallback_dir=tmp_path / "fallback",
        daily_folder="Daily",
        symbol="MES",
    )

    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),  # 06:00 PT == 13:00 UTC
    )

    assert isinstance(result, PipelineResult)
    assert result.success is True
    assert result.report_path is not None
    assert result.report_path.exists()
    # Plan saved
    plan_row = state.get_plan_for_date("2026-04-25", "MES")
    assert plan_row is not None
    assert plan_row["setup_name"] == "ORB long"
    assert plan_row["entry"] == pytest.approx(5240.0)
    # Report row marked success
    report_id = result.report_id
    report_row = state.get_report_by_id(report_id)
    assert report_row["status"] == "success"


def test_orchestrator_marks_validation_failure(tmp_path):
    state = StateDB(str(tmp_path / "state.db"))
    state.initialize()

    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text="(too short)")

    orchestrator = Orchestrator(
        state_db=state,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "missing.db",
        vault_root=tmp_path / "vault",
        fallback_dir=tmp_path / "fallback",
        daily_folder="Daily",
        symbol="MES",
    )
    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert result.success is False
    assert "validation" in (result.failure_reason or "").lower()


def test_orchestrator_idempotency_skips_repeat(tmp_path):
    state = StateDB(str(tmp_path / "state.db"))
    state.initialize()

    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    orchestrator = Orchestrator(
        state_db=state,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "missing.db",
        vault_root=tmp_path / "vault",
        fallback_dir=tmp_path / "fallback",
        daily_folder="Daily",
        symbol="MES",
    )

    first = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert first.success is True

    second = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert second.skipped_idempotent is True
    # AI not re-called
    assert fake_ai.call.call_count == 1
