"""Tests for term structure (front/back month)."""

from __future__ import annotations

import pytest

from daytrader.reports.futures_data.term_structure import (
    TermStructure,
    compute_term_structure,
)


def test_compute_term_structure_contango():
    ts = compute_term_structure(
        front_price=5246.75,
        next_price=5252.00,
        far_price=5258.50,
    )
    assert isinstance(ts, TermStructure)
    assert ts.front == pytest.approx(5246.75)
    assert ts.next == pytest.approx(5252.00)
    assert ts.far == pytest.approx(5258.50)
    assert ts.contango is True
    assert ts.spread_front_next == pytest.approx(5.25)
    assert ts.spread_next_far == pytest.approx(6.50)


def test_compute_term_structure_backwardation():
    ts = compute_term_structure(
        front_price=2350.00,
        next_price=2348.00,
        far_price=2345.00,
    )
    assert ts.contango is False
    assert ts.spread_front_next == pytest.approx(-2.00)
