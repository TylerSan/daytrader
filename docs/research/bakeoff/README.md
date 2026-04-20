# Bake-off research module

Implementation of the W2 Setup Gate bake-off described in
[`docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md`](../../superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md).

## Current status (Plan 1 complete)

- ✅ Data layer: `daytrader.research.bakeoff.data.load_mes_1m`
- ✅ Cost model: `daytrader.research.bakeoff.costs`
- ✅ Buy-and-hold baseline: `daytrader.research.bakeoff.baseline.buy_and_hold_mes_equity`
- ⬜ Strategies (S1a/S1b/S2a/S2b) — Plan 2
- ⬜ Walk-forward + metrics + DSR — Plan 3
- ⬜ `promote` CLI + YAML v2 + Contract integration — Plan 4

## Quick test

```bash
pytest tests/research/bakeoff/ -v
```

## Fetching data

See `databento-setup.md`.

## Running baseline (sanity check)

```python
from datetime import date
from pathlib import Path
import os

from daytrader.research.bakeoff.data import load_mes_1m
from daytrader.research.bakeoff.baseline import buy_and_hold_mes_equity

ds = load_mes_1m(
    start=date(2024, 1, 2), end=date(2024, 12, 31),
    api_key=os.environ["DATABENTO_API_KEY"],
    cache_dir=Path("data/cache/ohlcv"),
)
eq = buy_and_hold_mes_equity(ds.bars, starting_capital=10_000.0)
print(f"Start: ${eq.iloc[0]:,.2f}")
print(f"End:   ${eq.iloc[-1]:,.2f}")
print(f"Return: {(eq.iloc[-1] / eq.iloc[0] - 1) * 100:+.2f}%")
```

MES 2024 should show roughly **+50% on a $10k starting capital with 1 contract**. This is ~2.5× the underlying S&P return because 1 MES contract (~$25k notional at price 5000) against a $10k cash base is leveraged ~2.5×. The scale-invariant check that actually matters is the **baseline Sharpe ≈ 0.5** (spec §5.3 M2 checkpoint) — not the return percentage. To verify, compute:

```python
import numpy as np
returns = eq.pct_change().dropna()
# Annualize: ~252 trading days × 390 minutes = 98,280 per-bar returns per year
ann_sharpe = (returns.mean() / returns.std()) * np.sqrt(252 * 390)
print(f"Annualized Sharpe: {ann_sharpe:.2f}")
```

A Sharpe dramatically different from 0.3-0.7 suggests the baseline implementation has a bug.
