import math

from daytrader.research.zshuo.stats import diff_ci, wilson


def test_wilson_score_interval():
    p, lo, hi = wilson(8, 10)
    assert p == 0.8
    assert abs(lo - 0.490) < 0.005
    assert abs(hi - 0.943) < 0.005
    assert lo < p < hi


def test_wilson_with_no_observations_is_nan():
    assert all(math.isnan(v) for v in wilson(0, 0))


def test_newcombe_difference_interval():
    d, lo, hi = diff_ci(80, 100, 50, 100)
    assert abs(d - 0.30) < 1e-12
    assert 0 < lo < d < hi
    assert abs(lo - 0.169) < 0.005
    assert abs(hi - 0.417) < 0.005
