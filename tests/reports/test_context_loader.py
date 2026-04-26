"""Tests for ContextLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.core.context_loader import (
    ContextLoader,
    ContractStatus,
    ReportContext,
)


def test_context_loader_missing_contract_returns_not_started(tmp_path):
    """When Contract.md doesn't exist, status is NOT_CREATED."""
    loader = ContextLoader(
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.NOT_CREATED
    assert ctx.contract_text is None
    assert ctx.lock_in_trades_done == 0


def test_context_loader_empty_contract_returns_skeletal(tmp_path):
    """When Contract.md exists but has no parseable content, status is SKELETAL."""
    contract = tmp_path / "Contract.md"
    contract.write_text("# Contract\n\n*not yet filled*\n")
    loader = ContextLoader(
        contract_path=contract,
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.SKELETAL
    assert ctx.contract_text == "# Contract\n\n*not yet filled*\n"


def test_context_loader_handles_missing_journal_db(tmp_path):
    """Missing journal DB → trades_done = 0, no error."""
    loader = ContextLoader(
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.lock_in_trades_done == 0
    assert ctx.lock_in_target == 30
