import numpy as np
import pandas as pd
import pytest

from daytrader.research.zshuo.bars import resample_5m, tag_sessions


def _mk_1m(start="2024-06-03 13:30", n=10, iid=1):
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": np.arange(n, dtype=float) + 100,
            "high": np.arange(n, dtype=float) + 100.5,
            "low": np.arange(n, dtype=float) + 99.5,
            "close": np.arange(n, dtype=float) + 100.25,
            "volume": np.ones(n),
            "instrument_id": iid,
        },
        index=idx,
    )


def test_resample_5m_ohlcv():
    df = resample_5m(_mk_1m())
    assert len(df) == 2
    r = df.iloc[0]
    assert r.open == 100.0 and r.high == 104.5 and r.low == 99.5 and r.close == 104.25
    assert r.volume == 5


def test_resample_marks_rollover():
    a = _mk_1m(n=5, iid=1)
    b = _mk_1m(start="2024-06-03 13:35", n=5, iid=2)
    df = resample_5m(pd.concat([a, b]))
    assert list(df.rollover) == [False, True]


def test_tag_sessions_rth():
    df = resample_5m(_mk_1m(start="2024-06-03 13:30", n=5))   # 09:30 ET
    night = resample_5m(_mk_1m(start="2024-06-03 22:00", n=5))  # 18:00 ET
    assert tag_sessions(df).rth.all()
    assert not tag_sessions(night).rth.any()
