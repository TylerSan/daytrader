"""Basis computation: futures price - underlying index/spot price."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BasisResult:
    future_price: float
    underlying_price: float
    basis: float


def compute_basis(future_price: float, underlying_price: float) -> BasisResult:
    return BasisResult(
        future_price=future_price,
        underlying_price=underlying_price,
        basis=future_price - underlying_price,
    )
