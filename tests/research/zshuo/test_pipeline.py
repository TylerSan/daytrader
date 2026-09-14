import numpy as np
import pandas as pd
import pytest

from daytrader.research.zshuo.config import AuditConfig
from daytrader.research.zshuo.gaps import scan_lines
from daytrader.research.zshuo.pipeline import (EVENT_COLUMNS, apply_nonoverlap,
                                               bounds_rates, build_events,
                                               classify,
                                               placebo_same_bar_share,
                                               rule_counts, summarize, verdict)


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


def _sessions(df, *runs):
    dates = []
    for day, count in runs:
        dates += [pd.Timestamp(day).date()] * count
    assert len(dates) == len(df)
    df["session_date"] = dates
    return df


def _events(ev_rows):
    """Minimal event frame for the pure-reduction helpers."""
    return pd.DataFrame(ev_rows, columns=["kind", "direction", "touched_idx",
                                          "outcome"])


# ------------------------------------------------------------ build_events

# gap line 12.0 (+1) created on bar 3, first touched on bar 5.
# x_ticks=2 at tick 0.25 -> bounce target 12.5, penetration target 11.5.
_SCORED = [
    (10.0, 10.5, 9.5, 10.0),      # 0
    (10.0, 12.0, 9.8, 11.0),      # 1 swing H 12.0, confirmed_idx 2
    (11.0, 11.0, 10.5, 10.8),     # 2
    (10.8, 13.0, 10.7, 12.5),     # 3 body break -> gap @ 12.0
    (12.5, 13.5, 12.4, 13.2),     # 4 FT+, stays clear of the line
    (13.2, 13.3, 11.9, 12.0),     # 5 t0: touches 12.0, neither target
    (12.0, 12.2, 11.8, 12.1),     # 6 low 11.8 > 11.5, high 12.2 < 12.5
    (12.1, 12.6, 12.0, 12.55),    # 7 high 12.6 >= 12.5 -> bounce, race ends
    (12.55, 12.7, 12.4, 12.6),    # 8
    (12.6, 12.8, 12.5, 12.7),     # 9
    (12.7, 12.9, 12.6, 12.8),     # 10
    (12.8, 13.1, 12.7, 13.0),     # 11 t0 + 6
    (13.0, 13.2, 12.9, 13.1),     # 12
    (13.1, 13.3, 13.0, 13.2),     # 13
]

SCORED_CFG = AuditConfig(k=1, x_ticks=2, race_timeout_bars=10)


def _scored_gap(rows=None):
    df = _bars(rows or _SCORED)
    ev = build_events(df, SCORED_CFG)
    gap = ev[(ev.kind == "gap") & (ev.created_idx == 3)]
    assert len(gap) == 1
    return ev, gap.iloc[0]


def test_build_events_emits_every_column():
    ev, _ = _scored_gap()
    assert list(ev.columns) == EVENT_COLUMNS
    assert ev["touched_idx"].notna().all()


def test_build_events_scores_race_age_and_session():
    _, gap = _scored_gap()
    assert gap.outcome == "bounce"
    assert gap.touched_idx == 5
    assert gap.line_age_bars == 2        # touched 5 - created 3
    assert gap.rth is np.True_ or gap.rth is True
    assert gap.follow_through is True
    assert gap.race_end_idx == 7


def test_build_events_forward_returns_are_directional_ticks():
    _, gap = _scored_gap()
    # t0 + 6 = bar 11, close 13.0, line 12.0, +1 direction, 0.25 tick.
    assert gap.fwd_ret_6 == pytest.approx(4.0)
    # t0 + 12 and t0 + 24 fall past the end of the 14-bar frame.
    assert np.isnan(gap.fwd_ret_12) and np.isnan(gap.fwd_ret_24)


def test_build_events_excursions_span_t0_plus_one_to_race_end():
    _, gap = _scored_gap()
    # bars 6..7: highest high 12.6, lowest low 11.8, measured from 12.0.
    assert gap.mfe_ticks == pytest.approx(2.4)
    assert gap.mae_ticks == pytest.approx(-0.8)


def test_excursions_are_nan_when_the_touch_bar_itself_resolves():
    rows = list(_SCORED)
    rows[5] = (12.2, 12.4, 11.0, 11.2)   # t0 blows through 11.5 and not 12.5
    _, gap = _scored_gap(rows)
    assert gap.outcome == "penetrate"
    assert gap.race_end_idx == 5
    assert np.isnan(gap.mfe_ticks) and np.isnan(gap.mae_ticks)


def test_downward_line_excursions_are_mirrored():
    rows = [
        (10.0, 10.5, 9.5, 10.0),    # 0
        (10.0, 10.2, 8.0, 9.0),     # 1 swing L 8.0, confirmed_idx 2
        (9.0, 9.6, 9.4, 9.5),       # 2
        (9.5, 9.6, 7.0, 7.5),       # 3 body break -> gap @ 8.0, direction -1
        (7.5, 7.7, 6.5, 6.8),       # 4 FT+
        (6.8, 8.1, 6.7, 8.0),       # 5 t0: touches 8.0; 8.5 pen target unhit
        (8.0, 8.2, 7.4, 7.5),       # 6 low 7.4 <= 7.5 -> bounce (down), race ends
        (7.5, 7.8, 7.3, 7.4),       # 7
    ]
    df = _bars(rows)
    ev = build_events(df, SCORED_CFG)
    gap = ev[ev.kind == "gap"].iloc[0]
    assert gap.direction == -1
    assert gap.outcome == "bounce" and gap.race_end_idx == 6
    # window is bar 6 alone: favourable is the low 7.4, adverse the high 8.2.
    assert gap.mfe_ticks == pytest.approx((8.0 - 7.4) / 0.25)
    assert gap.mae_ticks == pytest.approx((8.0 - 8.2) / 0.25)


# ----------------------------------------------------------- non-overlap

def test_nonoverlap_keeps_the_earlier_event_within_the_window():
    ev = _events([
        ("gap", 1, 0, "bounce"),
        ("gap", 1, 5, "penetrate"),    # < 24 bars after the kept one -> dropped
        ("gap", 1, 24, "bounce"),      # exactly 24 after the kept one -> kept
        ("gap", 1, 40, "bounce"),      # < 24 after bar 24 -> dropped
        ("gap", -1, 5, "bounce"),      # other direction: own clock
        ("plain", 1, 5, "bounce"),     # other kind: own clock
    ])
    kept = apply_nonoverlap(ev, 24)
    assert list(zip(kept.kind, kept.direction, kept.touched_idx)) == [
        ("gap", 1, 0), ("gap", 1, 24), ("gap", -1, 5), ("plain", 1, 5)]


def test_nonoverlap_is_a_noop_on_an_empty_frame():
    assert not len(apply_nonoverlap(_events([]), 24))


# ---------------------------------------------------- reductions & bounds

def test_placebo_same_bar_share_counts_collisions_with_gap_events():
    ev = _events([
        ("gap", 1, 10, "bounce"),
        ("gap", 1, 40, "penetrate"),
        ("phantom", 1, 10, "bounce"),     # collides
        ("phantom", 1, 11, "bounce"),
        ("phantom", 1, 40, "timeout"),    # collides
        ("phantom", 1, 99, "bounce"),
    ])
    assert placebo_same_bar_share(ev) == 0.5


def test_bounds_rates_bracket_the_indeterminate_events():
    ev = _events([("gap", 1, i, o) for i, o in enumerate(
        ["bounce"] * 6 + ["penetrate"] * 2 + ["indeterminate"] * 2
        + ["timeout"] * 3)])
    b = bounds_rates(ev, "gap")
    assert b.n == 10                          # timeouts never enter the bounds
    assert (b.k_all_penetrate, b.rate_all_penetrate) == (6, 0.6)
    assert (b.k_all_bounce, b.rate_all_bounce) == (8, 0.8)
    assert rule_counts(ev, "gap", "resolved") == (6, 8)
    assert summarize(ev).loc["gap", "rate"] == 0.75
    assert summarize(ev).loc["gap", "timeout"] == 3


# ------------------------------------------------------------- §4 verdict

def test_classify_confirmed():
    assert classify((700, 1000), (500, 1000), (500, 1000)) == "CONFIRMED"


def test_classify_partial_when_plain_is_not_beaten():
    assert classify((700, 1000), (500, 1000), (750, 1000)) == "PARTIAL"


def test_classify_refuted_when_placebo_is_not_beaten():
    assert classify((500, 1000), (500, 1000), (400, 1000)) == "REFUTED"


def test_classify_undecided_when_the_effect_is_below_five_points():
    # significant against both controls at n = 10k, but only +2pp.
    assert classify((5100, 10000), (4900, 10000), (4900, 10000)) == "UNDECIDED"


def _verdict_frame(gap, phantom, plain, indeterminate=0):
    rows = []
    t = 0
    for kind, (b, n) in (("gap", gap), ("phantom", phantom), ("plain", plain)):
        outs = ["bounce"] * b + ["penetrate"] * (n - b)
        if kind == "gap":
            outs += ["indeterminate"] * indeterminate
        for o in outs:
            rows.append((kind, 1, t, o))
            t += 1
    return _events(rows)


def test_verdict_stands_when_all_three_readings_agree():
    out = verdict(_verdict_frame((700, 1000), (500, 1000), (500, 1000)))
    assert out["verdict"] == "CONFIRMED" and out["robust"] is True
    assert out["tendency"] is None


def test_verdict_degrades_to_undecided_when_the_bounds_disagree():
    # resolved-only reads REFUTED; forcing 900 indeterminate gap events to
    # bounce lifts the gap arm above both controls, so the reading flips.
    ev = _verdict_frame((500, 1000), (500, 1000), (400, 1000),
                        indeterminate=900)
    out = verdict(ev)
    assert out["by_rule"]["resolved"] == "REFUTED"
    assert out["by_rule"]["all_bounce"] != "REFUTED"
    assert out["verdict"] == "UNDECIDED"
    assert out["robust"] is False and out["tendency"] == "REFUTED"


# ------------------------------------------------------- counter channel

_UP_BREAK = [
    (10.0, 10.5, 9.5, 10.0),
    (10.0, 12.0, 9.8, 11.0),
    (11.0, 11.0, 10.5, 10.8),
    (10.8, 13.0, 10.7, 12.5),
    (12.5, 13.5, 12.4, 13.2),
    (13.2, 13.3, 11.5, 11.8),
]

_PLAIN = [
    (10.0, 10.5, 9.5, 10.0),
    (10.0, 12.0, 9.8, 11.0),
    (11.0, 11.0, 10.5, 10.6),
    (10.6, 10.8, 10.2, 10.4),
    (10.4, 12.3, 10.3, 11.0),
    (11.0, 11.2, 10.8, 11.0),
]

CFG = AuditConfig(k=1)


def test_counters_do_not_change_the_line_table():
    df = _bars(_UP_BREAK)
    plain_out = scan_lines(df, CFG)
    with_counts, counters = scan_lines(df, CFG, with_counters=True)
    pd.testing.assert_frame_equal(plain_out, with_counts)
    assert counters["gap"]["created"] == 1
    assert counters["gap"]["touched"] == 1
    assert counters["phantom"]["skipped_no_anchor"] == 1  # single session
    assert counters["phantom"]["created"] == 0


def test_counters_split_expiry_from_gap_through():
    voided = _bars(_UP_BREAK[:5] + [
        (11.0, 11.5, 10.5, 11.0),    # whole bar below 12.0 -> never traded at it
        (11.0, 12.5, 10.9, 11.5),
    ])
    _, counters = scan_lines(voided, CFG, with_counters=True)
    assert counters["gap"]["voided_gap_through"] == 1
    assert counters["gap"]["touched"] == 0
    assert counters["gap"]["expired"] == 0

    stale = _sessions(_bars(_UP_BREAK),
                      ("2024-06-03", 4), ("2024-06-04", 1), ("2024-06-05", 1))
    _, counters = scan_lines(stale, AuditConfig(k=1, expiry_days=2),
                             with_counters=True)
    assert counters["gap"]["expired"] == 1
    assert counters["gap"]["touched"] == 0


def test_counters_report_the_c2_candidates_the_expiry_clock_removes():
    stale = _sessions(_bars(_PLAIN),
                      ("2024-06-03", 3), ("2024-06-04", 1), ("2024-06-05", 2))
    _, counters = scan_lines(stale, AuditConfig(k=1, expiry_days=2),
                             with_counters=True)
    assert counters["plain"]["expired_at_touch"] == 1
    assert counters["plain"]["touched"] == 0

    _, fresh = scan_lines(stale, AuditConfig(k=1, expiry_days=3),
                          with_counters=True)
    assert fresh["plain"]["expired_at_touch"] == 0
    assert fresh["plain"]["touched"] == 1
