import pandas as pd

from daytrader.research.zshuo.swings import find_swings


def _series(vals):
    return pd.Series(vals, dtype=float)


def test_finds_strict_swing_high_and_low():
    high = _series([1, 2, 5, 2, 1, 2, 3])
    low = _series([0, 1, 4, 1, 0.5, 1, 2])
    sw = find_swings(high, low - 1, k=2)
    hs = sw[sw.kind == "H"]
    assert list(hs.idx) == [2] and list(hs.price) == [5.0]
    assert list(hs.confirmed_idx) == [4]


def test_ties_are_not_swings():
    high = _series([1, 5, 5, 1, 1])
    low = _series([0, 0, 0, 0, 0])
    sw = find_swings(high, low, k=1)
    assert (sw.kind == "H").sum() == 0  # tie at max -> no strict swing


def test_edges_excluded():
    high = _series([9, 1, 1, 1, 9])
    low = _series([0, 0, 0, 0, 0])
    sw = find_swings(high, low, k=2)
    assert len(sw[sw.kind == "H"]) == 0  # peaks at edges lack full window
