"""Tests for basis (futures - underlying)."""

from __future__ import annotations

import pytest

from daytrader.reports.futures_data.basis import compute_basis, BasisResult


def test_compute_basis_simple():
    result = compute_basis(future_price=5246.75, underlying_price=5244.50)
    assert isinstance(result, BasisResult)
    assert result.basis == pytest.approx(2.25)
    assert result.future_price == pytest.approx(5246.75)
    assert result.underlying_price == pytest.approx(5244.50)


def test_compute_basis_negative():
    result = compute_basis(future_price=5240.00, underlying_price=5245.00)
    assert result.basis == pytest.approx(-5.00)
