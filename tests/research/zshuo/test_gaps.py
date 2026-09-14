import numpy as np
import pandas as pd

from daytrader.research.zshuo.config import AuditConfig
from daytrader.research.zshuo.gaps import scan_lines


def _bars(rows, start="2024-06-03 14:00"):
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC")
    o, h, l, c = map(np.array, zip(*rows))
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                       "volume": 1.0, "instrument_id": 1, "rollover": False},
                      index=idx)
    et = df.index.tz_convert("America/New_York")
    df["rth"] = True
    df["session_date"] = (et + pd.Timedelta(hours=6)).date
    return df


def _roll(df, i):
    df.iloc[i, df.columns.get_loc("rollover")] = True
    return df


def _only(lines, kind):
    sub = lines[lines.kind == kind]
    assert len(sub) == 1, f"expected exactly one {kind} line, got {len(sub)}"
    return sub.iloc[0]


# swing H = 12.0 at idx 1 (k=1), confirmed at idx 2, body-broken at idx 3.
_UP_BREAK = [
    (10.0, 10.5, 9.5, 10.0),    # 0
    (10.0, 12.0, 9.8, 11.0),    # 1 swing H 12.0, confirmed_idx 2
    (11.0, 11.0, 10.5, 10.8),   # 2
    (10.8, 13.0, 10.7, 12.5),   # 3 close 12.5 > 12.0 -> up-break
    (12.5, 13.5, 12.4, 13.2),   # 4 close still above -> FT+; low 12.4 no touch
    (13.2, 13.3, 11.5, 11.8),   # 5 low 11.5 <= 12.0 -> first touch
]

CFG = AuditConfig(k=1)


def test_body_break_creates_gap_line_with_follow_through():
    lines = scan_lines(_bars(_UP_BREAK), CFG)
    gap = _only(lines, "gap")
    assert gap.price == 12.0
    assert gap.direction == 1          # broken swing H -> support, bounce up
    assert gap.created_idx == 3
    assert gap.swing_idx == 1
    assert gap.follow_through is True
    assert gap.touched_idx == 5


def test_follow_through_false_when_next_close_returns():
    rows = list(_UP_BREAK)
    rows[4] = (12.5, 13.0, 11.9, 11.9)  # close back below 12.0 -> FT-, and touches
    rows[5] = (11.9, 12.1, 11.8, 12.0)
    lines = scan_lines(_bars(rows), CFG)
    gap = _only(lines, "gap")
    assert gap.follow_through is False
    assert gap.touched_idx == 4


def test_break_bar_itself_cannot_touch_its_own_line():
    rows = list(_UP_BREAK)
    rows[3] = (10.8, 13.0, 11.0, 12.5)  # break bar dips to 11.0, below the line
    rows[4] = (12.5, 12.6, 11.9, 12.2)  # next bar is the first legal touch
    rows[5] = (12.2, 12.4, 12.0, 12.3)
    lines = scan_lines(_bars(rows), CFG)
    gap = _only(lines, "gap")
    assert gap.created_idx == 3
    assert gap.touched_idx == 4


def test_down_break_creates_negative_direction_line():
    rows = [
        (10.0, 10.5, 9.5, 10.0),   # 0
        (10.0, 10.2, 8.0, 9.0),    # 1 swing L 8.0, confirmed_idx 2
        (9.0, 9.6, 9.4, 9.5),      # 2
        (9.5, 9.6, 7.0, 7.5),      # 3 close 7.5 < 8.0 -> down-break; high 9.6 must not touch
        (7.5, 7.7, 6.5, 6.8),      # 4 close still below -> FT+
        (6.8, 8.5, 6.7, 8.2),      # 5 high 8.5 >= 8.0 -> first touch
    ]
    lines = scan_lines(_bars(rows), CFG)
    gap = _only(lines, "gap")
    assert gap.price == 8.0
    assert gap.direction == -1         # broken swing L -> resistance, bounce down
    assert gap.created_idx == 3
    assert gap.follow_through is True
    assert gap.touched_idx == 5
    phantom = _only(lines, "phantom")
    assert phantom.price < gap.price   # offset toward the price side (downward)


def test_phantom_is_created_with_the_gap_and_offset_toward_price():
    lines = scan_lines(_bars(_UP_BREAK), CFG)
    gap = _only(lines, "gap")
    phantom = _only(lines, "phantom")
    assert phantom.created_idx == gap.created_idx == 3
    assert phantom.direction == gap.direction
    assert phantom.swing_idx == gap.swing_idx
    assert pd.isna(phantom.follow_through)
    offset_ticks = (phantom.price - gap.price) / CFG.tick_size
    assert offset_ticks == round(offset_ticks)
    assert CFG.phantom_offset_ticks[0] <= offset_ticks <= CFG.phantom_offset_ticks[1]
    again = _only(scan_lines(_bars(_UP_BREAK), CFG), "phantom")
    assert again.price == phantom.price  # seeded rng -> reproducible


# swing H = 12.0 at idx 1 survives unbroken and is only wick-tested.
_PLAIN = [
    (10.0, 10.5, 9.5, 10.0),    # 0
    (10.0, 12.0, 9.8, 11.0),    # 1 swing H 12.0, confirmed_idx 2
    (11.0, 11.0, 10.5, 10.6),   # 2
    (10.6, 10.8, 10.2, 10.4),   # 3
    (10.4, 12.3, 10.3, 11.0),   # 4 wick through 12.0, close below -> plain test
    (11.0, 11.2, 10.8, 11.0),   # 5
]


def test_unbroken_swing_wick_touch_emits_plain_event():
    lines = scan_lines(_bars(_PLAIN), CFG)
    plain = lines[(lines.kind == "plain") & (lines.swing_idx == 1)]
    assert len(plain) == 1
    row = plain.iloc[0]
    assert row.price == 12.0
    assert row.direction == -1         # unbroken swing H is resistance
    assert row.created_idx == 2        # available from confirmed_idx
    assert row.touched_idx == 4
    assert pd.isna(row.follow_through)
    assert (lines.kind == "gap").sum() == 0


def test_plain_swing_emits_only_one_event():
    rows = list(_PLAIN) + [(11.0, 12.5, 10.9, 11.5)]  # second wick through 12.0
    lines = scan_lines(_bars(rows), CFG)
    plain = lines[(lines.kind == "plain") & (lines.swing_idx == 1)]
    assert len(plain) == 1
    assert plain.iloc[0].touched_idx == 4


def test_body_break_preempts_plain_event_on_the_same_bar():
    rows = list(_PLAIN)
    rows[4] = (10.4, 12.6, 10.3, 12.5)  # same bar wicks AND closes through 12.0
    rows[5] = (12.5, 12.7, 12.2, 12.4)
    lines = scan_lines(_bars(rows), CFG)
    assert (lines.swing_idx == 1).sum() == 2           # gap + phantom only
    assert set(lines[lines.swing_idx == 1].kind) == {"gap", "phantom"}
    gap = _only(lines, "gap")
    assert gap.created_idx == 4 and gap.price == 12.0


def test_rollover_voids_open_lines():
    rows = _UP_BREAK[:4] + [
        (12.5, 13.5, 12.4, 13.2),   # 4 rollover bar
        (13.2, 13.4, 12.6, 13.0),   # 5 blackout
        (13.0, 13.2, 12.7, 12.9),   # 6 blackout
        (12.9, 13.0, 11.5, 11.8),   # 7 would have touched the voided line
    ]
    cfg = AuditConfig(k=1, rollover_blackout_bars=2)
    lines = scan_lines(_roll(_bars(rows), 4), cfg)
    gap = _only(lines, "gap")
    assert gap.created_idx == 3
    assert pd.isna(gap.touched_idx)
    assert lines.touched_idx.isna().all()


def test_swing_confirmed_inside_blackout_never_becomes_a_line():
    rows = [
        (10.0, 10.5, 9.5, 10.0),    # 0
        (10.0, 10.6, 9.6, 10.2),    # 1
        (10.2, 10.7, 9.7, 10.4),    # 2
        (10.4, 10.8, 9.8, 10.5),    # 3
        (10.5, 12.0, 10.0, 11.0),   # 4 swing H 12.0 (k=2), confirmed_idx 6
        (11.0, 11.2, 10.4, 10.9),   # 5 rollover -> blackout covers 5..7
        (10.9, 11.0, 10.3, 10.6),   # 6 confirmation lands inside blackout
        (10.6, 11.1, 10.2, 10.5),   # 7
        (10.5, 12.8, 10.4, 12.5),   # 8 would have body-broken the dropped swing
        (12.5, 13.0, 11.0, 11.5),   # 9
    ]
    cfg = AuditConfig(k=2, rollover_blackout_bars=2)
    lines = scan_lines(_roll(_bars(rows), 5), cfg)
    assert len(lines) == 0


_EXPIRY = [
    (10.0, 10.5, 9.5, 10.0),    # 0
    (10.0, 12.0, 9.8, 11.0),    # 1 swing H 12.0, confirmed_idx 2
    (11.0, 11.0, 10.5, 10.8),   # 2
    (10.8, 13.0, 10.7, 12.5),   # 3 up-break -> gap @ 12.0 on session ordinal 0
    (12.5, 13.5, 12.4, 13.2),   # 4
    (13.2, 13.4, 12.6, 13.0),   # 5
    (13.0, 13.1, 11.5, 11.8),   # 6 low 11.5 <= 12.0 -> touch, 2 sessions later
]
_SESSIONS = ["2024-06-03"] * 4 + ["2024-06-04"] + ["2024-06-05"] * 2


def _expiry_bars():
    df = _bars(_EXPIRY)
    df["session_date"] = [pd.Timestamp(d).date() for d in _SESSIONS]
    return df


def test_line_expires_after_expiry_days_trading_days():
    lines = scan_lines(_expiry_bars(), AuditConfig(k=1, expiry_days=2))
    gap = _only(lines, "gap")
    assert gap.created_idx == 3
    assert pd.isna(gap.touched_idx)  # ordinal 2 - 0 >= 2 -> void before the touch


def test_line_survives_when_expiry_window_is_wider():
    lines = scan_lines(_expiry_bars(), AuditConfig(k=1, expiry_days=3))
    gap = _only(lines, "gap")
    assert gap.touched_idx == 6


def _stale_plain_bars():
    df = _bars(_PLAIN)
    df["session_date"] = [pd.Timestamp(d).date() for d in
                          ["2024-06-03"] * 3 + ["2024-06-04"] + ["2024-06-05"] * 2]
    return df


def test_plain_line_runs_on_the_same_expiry_clock():
    # confirmed on ordinal 0, wick-tested on ordinal 2: expired for C2 as well,
    # otherwise the control would outlive every gap it is compared against.
    stale = scan_lines(_stale_plain_bars(), AuditConfig(k=1, expiry_days=2))
    assert (stale.kind == "plain").sum() == 0
    fresh = scan_lines(_stale_plain_bars(), AuditConfig(k=1, expiry_days=3))
    assert (fresh.kind == "plain").sum() == 1
