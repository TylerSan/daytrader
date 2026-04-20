"""Unit tests for S2a + S2b Intraday Momentum strategy classes."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from daytrader.research.bakeoff.strategies._trade import TradeOutcome
from daytrader.research.bakeoff.strategies.s2_intraday_momentum import (
    S2a_IntradayMomentum_Max1,
    S2b_IntradayMomentum_Max5,
)


ET = ZoneInfo("America/New_York")


def _minutes(date_str, rows):
    ts = [
        pd.Timestamp(f"{date_str} {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows
    ]
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1}
         for _hm, o, h, l, c in rows],
        index=pd.DatetimeIndex(ts),
    )


# Use 20 warmup days so both ATR_14 (shifted, first valid at daily idx 15
# because TR[0] is NaN) and avg_intraday_return_14d (shifted, first valid
# at idx 14) are ready on the trading day. 20 is also what the spec
# recommends as the full S2 warmup.
WARMUP_DAYS = 20


def _build_warmup_1m():
    """Uneventful prior days: 09:30 + each check time + 15:55, all at 100.0."""
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    frames = []
    for k in range(WARMUP_DAYS):
        d = f"2024-05-{k+1:02d}"
        rows = [(hm, 100.0, 100.0, 100.0, 100.0) for hm in hm_list]
        frames.append(_minutes(d, rows))
    return pd.concat(frames).sort_index()


def _build_warmup_daily():
    """Prior daily bars with TR=1.0 each → ATR_14=1.0 once warmed up."""
    rows = [
        (f"2024-05-{k+1:02d}", 100.0, 100.5, 99.5, 100.0)
        for k in range(WARMUP_DAYS)
    ]
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c}
         for _d, o, h, l, c in rows],
        index=pd.DatetimeIndex([r[0] for r in rows]).normalize(),
    )
    df.index.name = "date"
    return df


def _trading_date():
    """Day immediately after warmup."""
    return f"2024-05-{WARMUP_DAYS + 1:02d}"


def test_s2a_no_trigger_day_produces_no_trade():
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    warmup_1m = _build_warmup_1m()
    warmup_d = _build_warmup_daily()

    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    flat_rows = [(hm, 100.0, 100.0, 100.0, 100.0) for hm in hm_list]
    trading = _minutes(_trading_date(), flat_rows)
    trading_d = pd.DataFrame(
        [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}],
        index=pd.DatetimeIndex([_trading_date()]).normalize(),
    )
    trading_d.index.name = "date"

    bars_1m = pd.concat([warmup_1m, trading]).sort_index()
    bars_1d = pd.concat([warmup_d, trading_d])

    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    assert trades == []


def test_s2a_long_entry_on_upward_break():
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    warmup_1m = _build_warmup_1m()
    warmup_d = _build_warmup_daily()

    # Trading day: daily_open=100.0 (09:30 bar), upper=100.0 (avg_intra=0 from
    # flat warmup), so price 100.5 at 10:00 triggers long entry.
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    rows = []
    for hm in hm_list:
        if hm == "09:30":
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
        elif hm == "15:55":
            rows.append((hm, 100.5, 100.6, 100.4, 100.5))
        else:
            # 10:00 onward sits at 100.5 — triggers at 10:00, walks flat to EOD.
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))
    trading = _minutes(_trading_date(), rows)
    trading_d = pd.DataFrame(
        [{"open": 100.0, "high": 100.6, "low": 99.9, "close": 100.5}],
        index=pd.DatetimeIndex([_trading_date()]).normalize(),
    )
    trading_d.index.name = "date"

    bars_1m = pd.concat([warmup_1m, trading]).sort_index()
    bars_1d = pd.concat([warmup_d, trading_d])

    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.entry_price == pytest.approx(100.5)


def test_s2a_ignores_second_trigger_same_day():
    """S2a max 1/day: after first trade closes, later triggers ignored."""
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    warmup_1m = _build_warmup_1m()
    warmup_d = _build_warmup_daily()

    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    rows = []
    for hm in hm_list:
        if hm == "09:30":
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
        elif hm == "10:00":
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))   # entry long @ 100.5
        elif hm == "10:30":
            rows.append((hm, 98.0, 98.0, 98.0, 98.0))       # stop hit (< 98.5)
        elif hm == "11:00":
            rows.append((hm, 101.0, 101.0, 101.0, 101.0))   # would re-trigger
        elif hm == "15:55":
            rows.append((hm, 101.0, 101.0, 100.0, 100.0))
        else:
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
    trading = _minutes(_trading_date(), rows)
    trading_d = pd.DataFrame(
        [{"open": 100.0, "high": 101.0, "low": 98.0, "close": 100.0}],
        index=pd.DatetimeIndex([_trading_date()]).normalize(),
    )
    trading_d.index.name = "date"

    bars_1m = pd.concat([warmup_1m, trading]).sort_index()
    bars_1d = pd.concat([warmup_d, trading_d])

    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    assert len(trades) == 1


def test_s2b_allows_up_to_5_trades_same_day():
    """S2b with 2 sequential breakouts on same day → both recorded."""
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    warmup_1m = _build_warmup_1m()
    warmup_d = _build_warmup_daily()

    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    rows = []
    for hm in hm_list:
        if hm == "09:30":
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
        elif hm == "10:00":
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))   # entry 1 long
        elif hm == "10:30":
            rows.append((hm, 98.0, 98.0, 98.0, 98.0))       # stop out trade 1
        elif hm == "11:00":
            rows.append((hm, 101.0, 101.0, 101.0, 101.0))   # entry 2 long
        elif hm == "11:30":
            rows.append((hm, 97.0, 97.0, 97.0, 97.0))       # stop out trade 2
        elif hm == "15:55":
            rows.append((hm, 97.0, 97.0, 97.0, 97.0))
        else:
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
    trading = _minutes(_trading_date(), rows)
    trading_d = pd.DataFrame(
        [{"open": 100.0, "high": 101.0, "low": 97.0, "close": 97.0}],
        index=pd.DatetimeIndex([_trading_date()]).normalize(),
    )
    trading_d.index.name = "date"

    bars_1m = pd.concat([warmup_1m, trading]).sort_index()
    bars_1d = pd.concat([warmup_d, trading_d])

    strat = S2b_IntradayMomentum_Max5(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    assert len(trades) == 2


def test_s2_skips_days_before_warmup_ready():
    """First day in the input (no 14d history) → no signal, silent skip."""
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    rows = [(hm, 100.0, 101.0, 99.0, 101.0) for hm in hm_list]
    day1 = _minutes("2024-05-01", rows)
    day1_d = pd.DataFrame(
        [{"open": 100.0, "high": 101.0, "low": 99.0, "close": 101.0}],
        index=pd.DatetimeIndex(["2024-05-01"]).normalize(),
    )
    day1_d.index.name = "date"
    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(day1, day1_d)
    assert trades == []
