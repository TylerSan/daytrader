"""Anchor-bar shape features and the pre-registered subgroups (spec 修订 (四)).

The v1 audit scored *every* body-broken swing extreme. z说's own teaching is
narrower: his breakaway-gap lines are anchored on a bald-top bear candle's high,
a bald-bottom bull candle's low, or a long-wick pin's extreme — and the anchor's
colour opposes the break direction. If an edge lives only in that textbook
subset, pooling it with the rest dilutes it toward zero. This module labels each
line with the shape of its anchor bar so the subset can be scored on its own.

Definitions (frozen by spec 修订 (四), do not re-tune after seeing results)
-------------------------------------------------------------------------
Anchor bar = ``bars.iloc[swing_idx]`` — the swing bar whose extremum became the
line, **not** the bar that broke it.

``anchor_range``             ``high - low``.
``anchor_color``             ``"bull"`` if ``close > open``, ``"bear"`` if
                             ``close < open``, else ``None`` (doji: no colour,
                             so it can never satisfy S1).
``anchor_end_shadow``        the shadow at the end the *line price* sits on:
                             ``high - max(open, close)`` for ``direction=+1``
                             (a broken swing H), ``min(open, close) - low`` for
                             ``direction=-1``. Mirrored, never the far end.
``anchor_end_shadow_ratio``  shadow / range, **NaN when range == 0** — a
                             zero-range bar has no shape, so it is excluded
                             from every ratio statistic rather than counted as
                             ratio 0.
``anchor_body_price``        the body edge on the line side: ``max(open, close)``
                             for +1, ``min(open, close)`` for -1. This is the
                             alternative line price of the 修订 (四)
                             line-placement sensitivity ("大体积K看实体").

Subgroups (boolean, Kleene logic over the nullable dtype)
``s1``  colour agreement: an up-break (+1, anchor swing H) anchored on a bear
        bar; a down-break on a bull bar.
``s2``  ``s1`` and ``ratio <= s2_max`` (default 0.20) — bald end.
``s3``  ``s1`` and ``ratio >= s3_min`` (default 0.50) — long-wick pin.
``s4``  ``s2 | s3`` — the textbook anchor.

Both thresholds are inclusive at the boundary, and both are parameters so the
修订 (四) sensitivity sweep (S2 over {0.10, 0.20, 0.30}, S3 over
{0.40, 0.50, 0.60}) re-runs the same code rather than a second implementation.

Kind handling
-------------
``gap``     labelled from its own anchor bar.
``phantom`` the C1 placebo carries its parent gap's ``swing_idx`` and
            ``direction`` verbatim (:func:`gaps.scan_lines` writes them at
            creation), so reading the anchor bar off ``swing_idx`` *is* the
            inheritance the spec asks for — no parent link needs to be added.
            ``(swing_idx, direction)`` is therefore also a unique 1:1 join key
            between a gap and its placebo.
``plain``   the C2 control is not a broken level and takes no subgroup: every
            feature is NaN and every label ``pd.NA``. Its ``swing_idx`` points
            at a swing whose direction convention is inverted relative to a
            gap's, so labelling it would be meaningless as well as out of spec.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: Columns appended by :func:`annotate_anchor_features`, in order.
ANCHOR_COLUMNS = ("anchor_color", "anchor_range", "anchor_end_shadow",
                  "anchor_end_shadow_ratio", "anchor_body_price",
                  "s1", "s2", "s3", "s4")

SUBGROUPS = ("s1", "s2", "s3", "s4")

#: Frozen defaults of spec 修订 (四).
S2_MAX = 0.20
S3_MIN = 0.50

#: The sensitivity sweep the revision pre-registers.
S2_GRID = (0.10, 0.20, 0.30)
S3_GRID = (0.40, 0.50, 0.60)

#: Kinds that carry an anchor shape at all.
_ANCHORED = ("gap", "phantom")


def annotate_anchor_features(lines_df: pd.DataFrame, bars_df: pd.DataFrame, *,
                             s2_max: float = S2_MAX,
                             s3_min: float = S3_MIN) -> pd.DataFrame:
    """Return ``lines_df`` plus :data:`ANCHOR_COLUMNS`. Purely additive."""
    out = lines_df.copy()
    if not len(out):
        out["anchor_color"] = pd.Series(dtype=object)
        for col in ("anchor_range", "anchor_end_shadow",
                    "anchor_end_shadow_ratio", "anchor_body_price"):
            out[col] = pd.Series(dtype=float)
        for col in SUBGROUPS:
            out[col] = pd.Series(dtype="boolean")
        return out

    o = bars_df["open"].to_numpy(dtype=float)
    h = bars_df["high"].to_numpy(dtype=float)
    l = bars_df["low"].to_numpy(dtype=float)  # noqa: E741
    c = bars_df["close"].to_numpy(dtype=float)

    idx = out["swing_idx"].to_numpy(dtype=int)
    up = out["direction"].to_numpy(dtype=int) > 0
    keep = out["kind"].isin(_ANCHORED).to_numpy()

    a_o, a_h, a_l, a_c = o[idx], h[idx], l[idx], c[idx]
    body_hi = np.maximum(a_o, a_c)
    body_lo = np.minimum(a_o, a_c)

    rng = a_h - a_l
    shadow = np.where(up, a_h - body_hi, body_lo - a_l)
    # range == 0 -> no shape to speak of: NaN, excluded from ratio statistics.
    ratio = np.divide(shadow, rng, out=np.full(len(out), np.nan),
                      where=rng > 0)
    body_price = np.where(up, body_hi, body_lo)

    color = np.where(a_c > a_o, "bull", np.where(a_c < a_o, "bear", None))
    color = np.asarray(color, dtype=object)

    s1 = np.where(up, color == "bear", color == "bull") & keep
    with np.errstate(invalid="ignore"):
        s2 = s1 & (ratio <= s2_max)
        s3 = s1 & (ratio >= s3_min)

    nan = np.full(len(out), np.nan)
    out["anchor_color"] = np.where(keep, color, None)
    out["anchor_range"] = np.where(keep, rng, nan)
    out["anchor_end_shadow"] = np.where(keep, shadow, nan)
    out["anchor_end_shadow_ratio"] = np.where(keep, ratio, nan)
    out["anchor_body_price"] = np.where(keep, body_price, nan)
    for name, vals in (("s1", s1), ("s2", s2), ("s3", s3), ("s4", s2 | s3)):
        arr = pd.array(vals, dtype="boolean")
        arr[~keep] = pd.NA        # plain rows carry no label at all
        out[name] = arr
    return out


def subgroup_mask(lines_df: pd.DataFrame, label: str, *,
                  complement: bool = False) -> pd.Series:
    """Boolean selector for one subgroup (or its complement).

    ``pd.NA`` — the unlabelled ``plain`` rows — is False on both sides, so a
    subgroup and its complement partition only the anchored kinds.
    """
    if label not in SUBGROUPS:
        raise ValueError(f"unknown subgroup {label!r}; expected one of "
                         f"{SUBGROUPS}")
    col = lines_df[label]
    return (~col.fillna(True) if complement else col.fillna(False)).astype(bool)
