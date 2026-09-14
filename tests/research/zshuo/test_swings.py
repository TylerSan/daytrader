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
    # low - 1 == [-1, 0, 3, 0, -0.5, 0, 1]. The only value that is the strict
    # minimum of its own full +/-2 window is idx 4 (window [3, 0, -0.5, 0, 1]);
    # idx 0's -1 is lower but sits at the edge without a full window.
    ls = sw[sw.kind == "L"]
    assert list(ls.idx) == [4] and list(ls.price) == [-0.5]
    assert list(ls.confirmed_idx) == [6]  # i + k, never i (no lookahead)


def test_ties_are_not_swings():
    high = _series([1, 5, 5, 1, 1])
    low = _series([0, 0, 0, 0, 0])
    sw = find_swings(high, low, k=1)
    assert (sw.kind == "H").sum() == 0  # tie at max -> no strict swing


def test_low_ties_are_not_swings():
    high = _series([0, 0, 0, 0, 0])
    low = _series([5, 0, 0, 5, 5])
    sw = find_swings(high, low, k=1)
    assert (sw.kind == "L").sum() == 0  # flat bottom -> no strict swing


def test_edges_excluded():
    high = _series([9, 1, 1, 1, 9])
    low = _series([0, 0, 0, 0, 0])
    sw = find_swings(high, low, k=2)
    assert len(sw[sw.kind == "H"]) == 0  # peaks at edges lack full window


def test_low_edges_excluded():
    high = _series([0, 0, 0, 0, 0])
    low = _series([-9, 1, 1, 1, -9])
    sw = find_swings(high, low, k=2)
    assert len(sw[sw.kind == "L"]) == 0  # troughs at edges lack full window
