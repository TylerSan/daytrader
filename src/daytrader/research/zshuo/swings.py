"""Confirmed fractal swing points (spec §2.1). No lookahead: a swing at i is
usable only from bar confirmed_idx = i + k onward."""
from __future__ import annotations

import pandas as pd


def find_swings(high: pd.Series, low: pd.Series, k: int) -> pd.DataFrame:
    h, l = high.to_numpy(), low.to_numpy()
    rows = []
    for i in range(k, len(h) - k):
        wh = h[i - k:i + k + 1]
        if h[i] == wh.max() and (wh == h[i]).sum() == 1:
            rows.append((i, float(h[i]), "H", i + k))
        wl = l[i - k:i + k + 1]
        if l[i] == wl.min() and (wl == l[i]).sum() == 1:
            rows.append((i, float(l[i]), "L", i + k))
    return pd.DataFrame(rows, columns=["idx", "price", "kind", "confirmed_idx"])
