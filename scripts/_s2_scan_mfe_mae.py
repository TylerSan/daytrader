"""MFE / MAE computation helper for the S2 ATR scan runner.

Kept in `scripts/` (not the strategy package) because MFE/MAE is a
scan-specific diagnostic — it is not part of the Trade wire format
consumed by Plan 3's pybroker adapter.

For long trades:
  MFE = max(high over held bars) - entry_price
  MAE = entry_price - min(low over held bars)
For short: roles swap (positive excursion = price going down).

Both are normalized by risk = |entry_price - stop_price| to produce
R-units. If risk is zero (degenerate), returns (0, 0) to avoid div-by-zero.
"""

from __future__ import annotations

import pandas as pd

from daytrader.research.bakeoff.strategies._trade import Trade


def compute_mfe_mae_r(trade: Trade, bars_1m: pd.DataFrame) -> tuple[float, float]:
    """Return (mfe_r, mae_r) for the trade. Both >= 0."""
    risk = abs(trade.entry_price - trade.stop_price)
    if risk == 0:
        return 0.0, 0.0

    entry_ts = pd.Timestamp(trade.entry_time)
    exit_ts = pd.Timestamp(trade.exit_time)

    mask = (bars_1m.index >= entry_ts) & (bars_1m.index <= exit_ts)
    held = bars_1m[mask]
    if held.empty:
        return 0.0, 0.0

    if trade.direction == "long":
        mfe_pts = float(held["high"].max()) - trade.entry_price
        mae_pts = trade.entry_price - float(held["low"].min())
    else:
        mfe_pts = trade.entry_price - float(held["low"].min())
        mae_pts = float(held["high"].max()) - trade.entry_price

    return max(0.0, mfe_pts) / risk, max(0.0, mae_pts) / risk
