import numpy as np
import pandas as pd

from daytrader.research.zshuo.race import run_race

TICK = 0.25
X = 8  # half-width = 2.0 points


def _bars(rows):
    idx = pd.date_range("2024-06-03 14:00", periods=len(rows), freq="5min",
                        tz="UTC")
    h, l = map(np.array, zip(*rows))
    return pd.DataFrame({"open": l, "high": h, "low": l, "close": l}, index=idx)


def _race(rows, direction=1, t0=0, timeout=4):
    return run_race(_bars(rows), t0, 100.0, direction, X, TICK, timeout)


def test_bounce_target_reached_first():
    # line 100, +1: bounce at 102, penetration at 98.
    assert _race([(100.5, 99.0), (101.0, 99.5), (102.0, 100.5)]) == "bounce"


def test_penetration_target_reached_first():
    assert _race([(100.5, 99.0), (100.0, 98.0), (103.0, 97.0)]) == "penetrate"


def test_touch_bar_blow_through_is_penetration():
    # t0 already trades through 98: the bounce side of that bar is polluted by
    # the pre-touch range, so only penetration may be judged there.
    assert _race([(103.0, 97.5), (102.5, 102.0)]) == "penetrate"


def test_both_targets_on_the_same_bar_is_indeterminate():
    assert _race([(100.5, 99.0), (102.5, 97.5)]) == "indeterminate"


def test_neither_target_within_timeout():
    rows = [(100.5, 99.0)] + [(101.0, 99.0)] * 6
    assert _race(rows, timeout=3) == "timeout"


def test_direction_minus_one_is_mirrored():
    # line 100, -1: bounce is down at 98, penetration is up at 102.
    rows = [(100.5, 99.5), (101.0, 99.0), (100.5, 97.5)]
    assert _race(rows, direction=-1) == "bounce"
    rows = [(100.5, 99.5), (102.5, 100.0), (99.0, 97.0)]
    assert _race(rows, direction=-1) == "penetrate"
    assert _race([(102.5, 99.5), (98.0, 97.0)], direction=-1) == "penetrate"
