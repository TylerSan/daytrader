"""Unit tests for TermPricesFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from daytrader.reports.futures_data.term_prices import TermPricesFetcher


def _mk_chain(*expiries: str) -> list:
    """Build a fake contract chain (list of ContractDetails-like)."""
    out = []
    for expiry in expiries:
        d = MagicMock()
        d.contract = MagicMock()
        d.contract.lastTradeDateOrContractMonth = expiry
        d.contract.symbol = "MES"
        out.append(d)
    return out


def _stub_ib(chain, active_expiry, closes):
    """Build a fake IBClient mock with chain + active_expiry + close sequence."""
    fake_ib = MagicMock()
    fake_ib.get_contract_chain.return_value = chain
    fake_ib.get_active_front_expiry.return_value = active_expiry
    fake_ib.get_daily_close.side_effect = closes
    return fake_ib


def test_fetcher_happy_path_returns_3_tuple():
    """Happy path: chain has 3+ months, active expiry = chain[0] → tuple from chain[0..2]."""
    fake_ib = _stub_ib(
        chain=_mk_chain("20260618", "20260918", "20261218", "20270319"),
        active_expiry="20260618",
        closes=[7258.0, 7271.5, 7285.25],
    )

    fetcher = TermPricesFetcher(fake_ib)
    out = fetcher(["MES"])

    assert "MES" in out
    front, nxt, far = out["MES"]
    assert front == pytest.approx(7258.0)
    assert nxt == pytest.approx(7271.5)
    assert far == pytest.approx(7285.25)


def test_fetcher_anchors_to_active_expiry_skipping_near_expiry():
    """If chain[0] is a near-expiry low-volume contract and ContFuture-active is chain[1],
    fetcher must take chain[1..3] as front/next/far — NOT chain[0..2]."""
    # Simulating MGC scenario: May (near expiry) sits in chain[0], active = Jun
    fake_ib = _stub_ib(
        chain=_mk_chain("20260528", "20260626", "20260729", "20260828", "20260929"),
        active_expiry="20260626",  # ContFuture-resolved active = Jun
        closes=[4644.50, 4679.90, 4710.0],  # Jun, Jul, Aug
    )

    fetcher = TermPricesFetcher(fake_ib)
    out = fetcher(["MGC"])

    assert "MGC" in out
    front, nxt, far = out["MGC"]
    assert front == pytest.approx(4644.50)  # NOT 4591 (May near-expiry)
    assert nxt == pytest.approx(4679.90)
    assert far == pytest.approx(4710.0)
    # Confirm fetcher called close on chain[1], chain[2], chain[3]
    called_contracts = [c.args[0] for c in fake_ib.get_daily_close.call_args_list]
    assert called_contracts[0] is fake_ib.get_contract_chain.return_value[1].contract


def test_fetcher_skips_symbol_when_active_expiry_not_in_chain(capsys):
    """If active_expiry doesn't match any chain entry, symbol is skipped."""
    fake_ib = _stub_ib(
        chain=_mk_chain("20260618", "20260918", "20261218"),
        active_expiry="20990101",  # not in chain
        closes=[],
    )

    fetcher = TermPricesFetcher(fake_ib)
    out = fetcher(["MES"])

    assert "MES" not in out
    captured = capsys.readouterr()
    assert "not in chain" in captured.err


def test_fetcher_skips_symbol_with_insufficient_months_after_active(capsys):
    """If only 1 month exists past active expiry, fetcher needs >=2 more → skip."""
    fake_ib = _stub_ib(
        chain=_mk_chain("20260618", "20260918"),  # only front + next, no far
        active_expiry="20260618",
        closes=[],
    )

    fetcher = TermPricesFetcher(fake_ib)
    out = fetcher(["MES"])

    assert "MES" not in out
    assert fake_ib.get_daily_close.call_count == 0
    captured = capsys.readouterr()
    assert "insufficient months" in captured.err


def test_fetcher_per_symbol_failure_does_not_abort_others(capsys):
    """If MGC fails, MES still succeeds."""
    fake_ib = MagicMock()

    def _chain(sym):
        if sym == "MES":
            return _mk_chain("20260618", "20260918", "20261218")
        if sym == "MGC":
            raise RuntimeError("MGC chain fetch error")
        raise AssertionError(sym)

    fake_ib.get_contract_chain.side_effect = _chain
    fake_ib.get_active_front_expiry.return_value = "20260618"
    fake_ib.get_daily_close.side_effect = [7258.0, 7271.5, 7285.25]

    fetcher = TermPricesFetcher(fake_ib)
    out = fetcher(["MES", "MGC"])

    assert "MES" in out
    assert "MGC" not in out
    captured = capsys.readouterr()
    assert "MGC" in captured.err


def test_fetcher_empty_symbols_returns_empty_dict():
    fake_ib = MagicMock()
    fetcher = TermPricesFetcher(fake_ib)
    assert fetcher([]) == {}
    fake_ib.get_contract_chain.assert_not_called()


def test_fetcher_close_fetch_failure_skips_symbol(capsys):
    """If chain + active_expiry succeed but get_daily_close raises mid-way, symbol skipped."""
    fake_ib = _stub_ib(
        chain=_mk_chain("20260618", "20260918", "20261218"),
        active_expiry="20260618",
        closes=[7258.0, RuntimeError("IB timeout")],
    )

    fetcher = TermPricesFetcher(fake_ib)
    out = fetcher(["MES"])

    assert "MES" not in out
    captured = capsys.readouterr()
    assert "IB timeout" in captured.err
