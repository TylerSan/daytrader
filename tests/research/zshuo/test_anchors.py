import numpy as np
import pandas as pd
import pytest

from daytrader.research.zshuo.anchors import (ANCHOR_COLUMNS, SUBGROUPS,
                                              annotate_anchor_features,
                                              subgroup_mask)
from daytrader.research.zshuo.config import AuditConfig
from daytrader.research.zshuo.gaps import LINE_COLUMNS, scan_lines


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


def _lines(rows):
    """Minimal line table: (kind, direction, swing_idx)."""
    recs = [{"line_id": i, "price": 0.0, "direction": d, "kind": k,
             "created_idx": s, "swing_idx": s, "follow_through": None,
             "touched_idx": None}
            for i, (k, d, s) in enumerate(rows)]
    return pd.DataFrame(recs, columns=LINE_COLUMNS)


# Anchor bar catalogue. Index = position in the frame.
#            open,  high,  low,  close
_ANCHORS = [
    (12.0, 12.0, 10.0, 10.5),   # 0 bald-top bear: shadow 0.0 / range 2.0 = 0.00
    (10.0, 12.0, 10.0, 11.5),   # 1 bald-bottom bull: shadow 0.0 / 2.0 = 0.00
    (10.2, 12.0, 10.0, 10.1),   # 2 bear pin top: 1.8 / 2.0 = 0.90
    (10.0, 12.0, 9.9, 11.9),    # 3 BULL top -> wrong colour for an up-break
    (12.0, 12.0, 12.0, 12.0),   # 4 doji, range 0
    (11.0, 12.0, 10.0, 10.3),   # 5 bear, shadow 1.0 / 2.0 = 0.50 (S3 boundary)
    (10.7, 12.0, 10.0, 10.3),   # 6 bear, shadow 1.3 / 2.0 = 0.65
    (10.4, 12.0, 10.0, 10.0),   # 7 bear, shadow 1.6 / 2.0 = 0.80
    (10.5, 12.0, 10.0, 10.2),   # 8 bear, shadow 1.5 / 2.0 = 0.75
    (11.0, 12.0, 7.0, 8.0),     # 9 bear, shadow 1.0 / 5.0 = 0.20 (S2 boundary)
    (11.3, 12.0, 10.0, 10.4),   # 10 bear, shadow 0.7 / 2.0 = 0.35 (S1 middle)
    (10.0, 12.0, 10.0, 9.5),    # 11 pathological placeholder, unused
]
_BARS = _bars([r for r in _ANCHORS])


def _ann(rows, **kw):
    return annotate_anchor_features(_lines(rows), _BARS, **kw)


# ------------------------------------------------------- feature computation

def test_bald_top_bear_anchor_is_s1_s2_s4_for_up_break():
    row = _ann([("gap", 1, 0)]).iloc[0]
    assert row.anchor_color == "bear"
    assert row.anchor_range == pytest.approx(2.0)
    assert row.anchor_end_shadow == pytest.approx(0.0)
    assert row.anchor_end_shadow_ratio == pytest.approx(0.0)
    assert (row.s1, row.s2, row.s3, row.s4) == (True, True, False, True)


def test_bald_bottom_bull_anchor_is_s1_s2_s4_for_down_break():
    row = _ann([("gap", -1, 1)]).iloc[0]
    assert row.anchor_color == "bull"
    assert row.anchor_end_shadow == pytest.approx(0.0)  # min(o,c) - low
    assert row.anchor_end_shadow_ratio == pytest.approx(0.0)
    assert (row.s1, row.s2, row.s3, row.s4) == (True, True, False, True)


def test_pin_anchor_is_s1_s3_s4_not_s2():
    row = _ann([("gap", 1, 2)]).iloc[0]
    assert row.anchor_end_shadow == pytest.approx(1.8)
    assert row.anchor_end_shadow_ratio == pytest.approx(0.9)
    assert (row.s1, row.s2, row.s3, row.s4) == (True, False, True, True)


def test_colour_mismatch_fails_every_subgroup_despite_tiny_shadow():
    row = _ann([("gap", 1, 3)]).iloc[0]
    assert row.anchor_color == "bull"          # up-break wants a bear anchor
    assert row.anchor_end_shadow_ratio == pytest.approx(0.1 / 2.1)
    assert (row.s1, row.s2, row.s3, row.s4) == (False, False, False, False)


def test_down_break_with_bear_anchor_fails_s1():
    # bar 0 is a bear bar; for a down-break (dir=-1) S1 demands a bull anchor.
    row = _ann([("gap", -1, 0)]).iloc[0]
    assert row.s1 is False or row.s1 == False  # noqa: E712
    assert row.s4 == False                      # noqa: E712


def test_zero_range_doji_yields_nan_ratio_and_no_subgroup():
    row = _ann([("gap", 1, 4)]).iloc[0]
    assert row.anchor_color is None
    assert row.anchor_range == pytest.approx(0.0)
    assert np.isnan(row.anchor_end_shadow_ratio)
    assert (row.s1, row.s2, row.s3, row.s4) == (False, False, False, False)


def test_threshold_boundaries_are_inclusive():
    # ratio exactly 0.20 -> S2 (<= 0.20); ratio exactly 0.50 -> S3 (>= 0.50)
    out = _ann([("gap", 1, 9), ("gap", 1, 5)])
    assert out.iloc[0].anchor_end_shadow_ratio == pytest.approx(0.20)
    assert (out.iloc[0].s2, out.iloc[0].s3) == (True, False)
    assert out.iloc[1].anchor_end_shadow_ratio == pytest.approx(0.50)
    assert (out.iloc[1].s2, out.iloc[1].s3) == (False, True)


def test_s1_middle_band_is_s1_only():
    row = _ann([("gap", 1, 10)]).iloc[0]
    assert row.anchor_end_shadow_ratio == pytest.approx(0.35)
    assert (row.s1, row.s2, row.s3, row.s4) == (True, False, False, False)


def test_thresholds_are_parametrisable():
    out = _ann([("gap", 1, 10)], s2_max=0.40, s3_min=0.30)
    assert (out.iloc[0].s2, out.iloc[0].s3, out.iloc[0].s4) == (True, True, True)


def test_body_end_price_is_the_body_edge_at_the_line_side():
    up = _ann([("gap", 1, 0)]).iloc[0]       # open 12.0, close 10.5
    assert up.anchor_body_price == pytest.approx(12.0)
    down = _ann([("gap", -1, 1)]).iloc[0]    # open 10.0, close 11.5
    assert down.anchor_body_price == pytest.approx(10.0)


def test_body_end_price_never_beyond_the_extremum():
    out = _ann([("gap", 1, 2)]).iloc[0]
    assert out.anchor_body_price == pytest.approx(10.2)
    assert out.anchor_body_price <= _ANCHORS[2][1]      # <= the swing high


# ----------------------------------------------------------- kind behaviour

def test_plain_rows_get_na_labels_and_nan_features():
    row = _ann([("plain", 1, 0)]).iloc[0]
    assert row.anchor_color is None
    assert np.isnan(row.anchor_end_shadow_ratio)
    assert np.isnan(row.anchor_range)
    for s in SUBGROUPS:
        assert row[s] is pd.NA


def test_phantom_row_gets_the_label_of_its_parent_anchor():
    out = _ann([("gap", 1, 0), ("phantom", 1, 0), ("plain", -1, 0)])
    gap, phantom = out.iloc[0], out.iloc[1]
    for col in ANCHOR_COLUMNS:
        if isinstance(gap[col], float) and np.isnan(gap[col]):
            assert np.isnan(phantom[col])
        else:
            assert gap[col] == phantom[col]


def test_annotate_is_additive_and_keeps_original_columns():
    src = _lines([("gap", 1, 0)])
    out = annotate_anchor_features(src, _BARS)
    assert list(out.columns) == LINE_COLUMNS + list(ANCHOR_COLUMNS)
    assert list(src.columns) == LINE_COLUMNS      # input untouched
    pd.testing.assert_frame_equal(out[LINE_COLUMNS], src)


def test_empty_frame_returns_typed_empty_frame():
    out = annotate_anchor_features(_lines([]), _BARS)
    assert len(out) == 0
    assert list(out.columns) == LINE_COLUMNS + list(ANCHOR_COLUMNS)


# --------------------------------------------------------------- subgrouping

def test_subgroup_mask_selects_label_and_complement():
    out = _ann([("gap", 1, 0), ("gap", 1, 3), ("plain", 1, 0)])
    assert list(subgroup_mask(out, "s4")) == [True, False, False]
    assert list(subgroup_mask(out, "s4", complement=True)) == [False, True, False]


def test_subgroup_mask_rejects_unknown_label():
    with pytest.raises(ValueError):
        subgroup_mask(_ann([("gap", 1, 0)]), "s9")


# --------------------------------------- phantom parentage inside scan_lines

_UP_BREAK = [
    (10.0, 10.5, 9.5, 10.0),    # 0
    (10.0, 12.0, 9.8, 11.0),    # 1 swing H 12.0, confirmed_idx 2
    (11.0, 11.0, 10.5, 10.8),   # 2
    (10.8, 13.0, 10.7, 12.5),   # 3 body break -> gap @ 12.0
    (12.5, 13.5, 12.4, 13.2),   # 4
    (13.2, 13.3, 11.5, 11.8),   # 5 first touch
    (11.8, 12.0, 11.0, 11.2),   # 6
    (11.2, 11.6, 10.8, 11.0),   # 7
]


def _two_day(rows):
    """Placebo anchors must sit a trading day away from the gap, so the frame
    needs at least two sessions or scan_lines draws none at all."""
    df = _bars(rows)
    half = len(rows) // 2
    df["session_date"] = ([pd.Timestamp("2024-06-03").date()] * half
                          + [pd.Timestamp("2024-06-04").date()]
                          * (len(rows) - half))
    return df


def test_phantom_inherits_parent_swing_idx_and_direction():
    """The (swing_idx, direction) pair is a usable gap<->placebo join key."""
    lines = scan_lines(_two_day(_UP_BREAK), AuditConfig(k=1))
    gap = lines[lines.kind == "gap"]
    phantom = lines[lines.kind == "phantom"]
    assert len(gap) == len(phantom) >= 1
    key = ["swing_idx", "direction"]
    assert gap[key].reset_index(drop=True).equals(
        phantom[key].reset_index(drop=True))


def test_gap_and_phantom_join_key_is_unique():
    lines = scan_lines(_two_day(_UP_BREAK), AuditConfig(k=1))
    for kind in ("gap", "phantom"):
        sub = lines[lines.kind == kind]
        assert not sub.duplicated(subset=["swing_idx", "direction"]).any()


def test_annotated_scan_lines_pairs_gap_and_phantom_labels():
    df = _two_day(_UP_BREAK)
    out = annotate_anchor_features(scan_lines(df, AuditConfig(k=1)), df)
    gap = out[out.kind == "gap"].iloc[0]
    phantom = out[out.kind == "phantom"].iloc[0]
    # anchor bar 1: open 10.0 close 11.0 -> bull, wrong colour for an up-break
    assert gap.anchor_color == "bull"
    assert gap.s1 == False                       # noqa: E712
    assert phantom.s1 == gap.s1
    assert phantom.anchor_end_shadow_ratio == pytest.approx(
        gap.anchor_end_shadow_ratio)
