"""Term structure computation: front, next, far month spreads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TermStructure:
    front: float
    next: float
    far: float
    spread_front_next: float
    spread_next_far: float
    contango: bool


def compute_term_structure(
    front_price: float, next_price: float, far_price: float
) -> TermStructure:
    spread_front_next = next_price - front_price
    spread_next_far = far_price - next_price
    return TermStructure(
        front=front_price,
        next=next_price,
        far=far_price,
        spread_front_next=spread_front_next,
        spread_next_far=spread_next_far,
        contango=spread_front_next > 0,
    )
