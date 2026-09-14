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


def _sessions(df, *runs):
    """Overwrite session_date with explicit (date, bar count) runs."""
    dates = []
    for day, count in runs:
        dates += [pd.Timestamp(day).date()] * count
    assert len(dates) == len(df)
    df["session_date"] = dates
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
    (13.2, 13.3, 11.5, 11.8),   # 5 low 11.5 <= 12.0 <= high -> first touch
]

_DOWN_BREAK = [
    (10.0, 10.5, 9.5, 10.0),   # 0
    (10.0, 10.2, 8.0, 9.0),    # 1 swing L 8.0, confirmed_idx 2
    (9.0, 9.6, 9.4, 9.5),      # 2
    (9.5, 9.6, 7.0, 7.5),      # 3 close 7.5 < 8.0 -> down-break
    (7.5, 7.7, 6.5, 6.8),      # 4 close still below -> FT+
    (6.8, 8.5, 6.7, 8.2),      # 5 low 6.7 <= 8.0 <= high 8.5 -> first touch
]

CFG = AuditConfig(k=1)


# --------------------------------------------------------------- gap creation

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


def test_follow_through_is_unknown_at_the_end_of_the_frame():
    lines = scan_lines(_bars(_UP_BREAK[:4]), CFG)  # break on the last bar
    gap = _only(lines, "gap")
    assert gap.created_idx == 3
    assert gap.follow_through is None  # unknown, not FT-
    assert pd.isna(gap.touched_idx)


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
    lines = scan_lines(_bars(_DOWN_BREAK), CFG)
    gap = _only(lines, "gap")
    assert gap.price == 8.0
    assert gap.direction == -1         # broken swing L -> resistance, bounce down
    assert gap.created_idx == 3
    assert gap.follow_through is True
    assert gap.touched_idx == 5
    # single-session frame: no anchor bar a trading day away, so no placebo
    assert (lines.kind == "phantom").sum() == 0


# ------------------------------------------------------------------ touch rule

def test_line_is_voided_when_price_gaps_straight_through_it():
    rows = _UP_BREAK[:5] + [
        (11.0, 11.5, 10.5, 11.0),   # 5 whole bar below 12.0 -> never traded at it
        (11.0, 12.5, 10.9, 11.5),   # 6 returns to 12.0, but the line is dead
    ]
    lines = scan_lines(_bars(rows), CFG)
    gap = _only(lines, "gap")
    assert gap.created_idx == 3
    assert pd.isna(gap.touched_idx)
    assert not (lines.touched_idx == 6).any()


def test_bar_that_stops_short_of_the_line_neither_touches_nor_voids():
    rows = _UP_BREAK[:5] + [
        (12.4, 12.8, 12.1, 12.6),   # 5 low 12.1 > 12.0 -> still open
        (12.6, 12.7, 11.9, 12.0),   # 6 straddles the line -> touch
    ]
    lines = scan_lines(_bars(rows), CFG)
    assert _only(lines, "gap").touched_idx == 6


# ----------------------------------------------------------------- plain lines

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
    assert row.follow_through is None
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
    assert list(lines[lines.swing_idx == 1].kind) == ["gap"]
    gap = _only(lines, "gap")
    assert gap.created_idx == 4 and gap.price == 12.0


# -------------------------------------------------------------------- rollover

def test_rollover_voids_open_lines():
    rows = _UP_BREAK[:4] + [
        (12.5, 13.5, 12.4, 13.2),   # 4
        (13.2, 13.4, 12.6, 13.0),   # 5
        (13.0, 13.2, 12.7, 12.9),   # 6 rollover bar
        (12.9, 13.0, 12.8, 12.9),   # 7 blackout
        (12.9, 13.0, 11.5, 11.8),   # 8 would have touched the voided line
    ]
    cfg = AuditConfig(k=1, rollover_blackout_bars=1)
    lines = scan_lines(_roll(_bars(rows), 6), cfg)
    gap = _only(lines, "gap")
    assert gap.created_idx == 3
    assert pd.isna(gap.touched_idx)
    assert lines.touched_idx.isna().all()


def test_break_inside_the_pre_rollover_blackout_creates_nothing():
    # blackout is two-sided: the break on bar 3 sits one bar ahead of the roll.
    cfg = AuditConfig(k=1, rollover_blackout_bars=1)
    lines = scan_lines(_roll(_bars(_UP_BREAK), 4), cfg)
    assert len(lines) == 0


def test_swing_confirmed_inside_blackout_never_becomes_a_line():
    rows = [
        (10.0, 10.5, 9.5, 10.0),    # 0
        (10.0, 10.6, 9.6, 10.2),    # 1
        (10.2, 10.7, 9.7, 10.4),    # 2
        (10.4, 10.8, 9.8, 10.5),    # 3
        (10.5, 12.0, 10.0, 11.0),   # 4 swing H 12.0 (k=2), confirmed_idx 6
        (11.0, 11.2, 10.4, 10.9),   # 5 rollover -> blackout covers 3..7
        (10.9, 11.0, 10.3, 10.6),   # 6 confirmation lands inside blackout
        (10.6, 11.1, 10.2, 10.5),   # 7
        (10.5, 12.8, 10.4, 12.5),   # 8 would have body-broken the dropped swing
        (12.5, 13.0, 11.0, 11.5),   # 9
    ]
    cfg = AuditConfig(k=2, rollover_blackout_bars=2)
    lines = scan_lines(_roll(_bars(rows), 5), cfg)
    assert len(lines) == 0


# ---------------------------------------------------------------------- expiry

_EXPIRY = [
    (10.0, 10.5, 9.5, 10.0),    # 0
    (10.0, 12.0, 9.8, 11.0),    # 1 swing H 12.0, confirmed_idx 2
    (11.0, 11.0, 10.5, 10.8),   # 2
    (10.8, 13.0, 10.7, 12.5),   # 3 up-break -> gap @ 12.0 on session ordinal 0
    (12.5, 13.5, 12.4, 13.2),   # 4
    (13.2, 13.4, 12.6, 13.0),   # 5
    (13.0, 13.1, 11.5, 11.8),   # 6 low 11.5 <= 12.0 -> touch, 2 sessions later
]


def _expiry_bars():
    return _sessions(_bars(_EXPIRY),
                     ("2024-06-03", 4), ("2024-06-04", 1), ("2024-06-05", 2))


def test_line_expires_after_expiry_days_trading_days():
    lines = scan_lines(_expiry_bars(), AuditConfig(k=1, expiry_days=2))
    gap = _only(lines, "gap")
    assert gap.created_idx == 3
    assert pd.isna(gap.touched_idx)  # ordinal 2 - 0 >= 2 -> void before the touch


def test_line_survives_when_expiry_window_is_wider():
    lines = scan_lines(_expiry_bars(), AuditConfig(k=1, expiry_days=3))
    assert _only(lines, "gap").touched_idx == 6


def _stale_plain_bars():
    return _sessions(_bars(_PLAIN),
                     ("2024-06-03", 3), ("2024-06-04", 1), ("2024-06-05", 2))


def test_plain_line_runs_on_the_same_expiry_clock():
    # confirmed on ordinal 0, wick-tested on ordinal 2: expired for C2 as well,
    # otherwise the control would outlive every gap it is compared against.
    stale = scan_lines(_stale_plain_bars(), AuditConfig(k=1, expiry_days=2))
    assert (stale.kind == "plain").sum() == 0
    fresh = scan_lines(_stale_plain_bars(), AuditConfig(k=1, expiry_days=3))
    assert (fresh.kind == "plain").sum() == 1


# ------------------------------------------------------- C1 time-shifted placebo

_QUIET = (11.8, 12.0, 11.6, 11.7)


def _placebo_frame(n_second=12, rth_second=None, rollover_at=None, cfg_bars=None):
    """_UP_BREAK (session A) followed by a quiet second session of anchors."""
    rows = list(_UP_BREAK) + [_QUIET] * n_second
    df = _sessions(_bars(rows), ("2024-06-03", 6), ("2024-06-04", n_second))
    if rth_second is not None:
        df["rth"] = [True] * 6 + list(rth_second)
    if rollover_at is not None:
        _roll(df, rollover_at)
    return df


def test_placebo_matches_gap_geometry_at_a_displaced_anchor():
    df = _placebo_frame(rth_second=[False, False] + [True] * 10)
    lines = scan_lines(df, CFG)
    gap = _only(lines, "gap")
    ghost = _only(lines, "phantom")
    anchor = int(ghost.created_idx)
    close = df["close"].to_numpy()
    distance = abs(close[int(gap.created_idx)] - gap.price)  # 12.5 - 12.0
    assert distance == 0.5
    assert ghost.price == close[anchor] - gap.direction * distance == 11.2
    assert ghost.direction == gap.direction          # same approach side
    assert ghost.swing_idx == gap.swing_idx
    assert ghost.follow_through is None
    assert anchor >= 8                               # rth flag must match
    assert df["session_date"].iloc[anchor] != df["session_date"].iloc[3]


def test_placebo_for_a_down_break_sits_above_its_anchor_close():
    rows = list(_DOWN_BREAK) + [(8.0, 8.3, 7.9, 8.1)] * 8
    df = _sessions(_bars(rows), ("2024-06-03", 6), ("2024-06-04", 8))
    lines = scan_lines(df, CFG)
    gap = _only(lines, "gap")
    ghost = _only(lines, "phantom")
    anchor = int(ghost.created_idx)
    assert anchor >= 6
    assert ghost.direction == -1
    assert ghost.price == 8.1 + 0.5          # close[anchor] + |7.5 - 8.0|
    assert ghost.price > df["close"].iloc[anchor]   # approached from below, as the gap was


def test_placebo_anchor_is_reproducible_under_seed():
    first = _only(scan_lines(_placebo_frame(), CFG), "phantom")
    second = _only(scan_lines(_placebo_frame(), CFG), "phantom")
    assert first.created_idx == second.created_idx
    assert first.price == second.price


def test_placebo_anchor_never_lands_inside_a_blackout():
    # session B spans bars 6..13; the roll on bar 9 masks 6..12, leaving bar 13
    # as the only admissible anchor.
    df = _placebo_frame(n_second=8, rollover_at=9)
    lines = scan_lines(df, AuditConfig(k=1, rollover_blackout_bars=3))
    assert _only(lines, "phantom").created_idx == 13


def _placebo_rollover_frame(with_roll):
    rows = list(_UP_BREAK) + [_QUIET] * 5 + [(11.7, 11.9, 10.9, 11.6)]
    df = _sessions(_bars(rows), ("2024-06-03", 6), ("2024-06-04", 6))
    df["rth"] = [True] * 6 + [True] + [False] * 5  # bar 6 is the only anchor
    if with_roll:
        _roll(df, 9)
    return df


def test_placebo_is_voided_by_an_intervening_rollover():
    cfg = AuditConfig(k=1, rollover_blackout_bars=1)
    live = _only(scan_lines(_placebo_rollover_frame(False), cfg), "phantom")
    assert live.created_idx == 6 and live.price == 11.2
    assert live.touched_idx == 11          # bar 11 dips to 10.9, through 11.2

    rolled = _only(scan_lines(_placebo_rollover_frame(True), cfg), "phantom")
    assert rolled.created_idx == 6 and rolled.price == 11.2
    assert pd.isna(rolled.touched_idx)     # rollover on bar 9 kills it first


def test_placebo_is_skipped_when_no_anchor_session_exists():
    assert (scan_lines(_bars(_UP_BREAK), CFG).kind == "phantom").sum() == 0
