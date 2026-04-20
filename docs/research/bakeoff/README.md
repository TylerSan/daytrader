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

MES 2024 should show roughly +20–25% before cost (S&P 500 total return), minus ~$80 in rollover costs (4 rolls × $2.50 × $5/contract adjustment, exact value depends on roll levels). A significant deviation means the baseline code has a bug — do not proceed to Plan 2 until that's resolved.
