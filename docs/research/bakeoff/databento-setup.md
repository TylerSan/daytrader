# Databento Setup for W2 Setup Gate Bake-off

## What you're buying

MES front-month continuous 1-minute OHLCV from 2022-01-01 to 2025-12-31.

Schema: `ohlcv-1m`
Dataset: `GLBX.MDP3`
Symbol: `MES.c.0` (continuous, front-month by open interest)
Size: ~500 MB compressed parquet
Expected cost: $5–$20 one-time (Databento historical billing is per-byte; OHLCV-1m is the cheapest schema)

## Steps

1. Create an account at https://databento.com/signup if you don't have one.
2. Confirm your default billing method has funds / a PO covers the ~$20 expected charge.
3. Generate an API key at https://databento.com/portal/keys.
4. Store it locally — **do not commit**:
   ```bash
   # option A: env var
   export DATABENTO_API_KEY="db-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

   # option B: config/user.yaml (already gitignored)
   echo "databento_api_key: db-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" >> config/user.yaml
   ```
5. Run the single-day smoke test FIRST (Task 9 step 4). **Only proceed past this if it passes.**

## Pulling the full 4-year dataset

After the smoke test passes:
```bash
python -c "
from datetime import date
from pathlib import Path
import os

from daytrader.research.bakeoff.data import load_mes_1m

ds = load_mes_1m(
    start=date(2022, 1, 3),
    end=date(2025, 12, 31),
    api_key=os.environ['DATABENTO_API_KEY'],
    cache_dir=Path('data/cache/ohlcv'),
)
print(f'Bars: {len(ds.bars):,}')
print(f'Rollover skip dates: {len(ds.rollover_skip_dates)}')
print(f'Low-coverage days: {int(ds.quality_report[\"flag_low_coverage\"].sum())}')
"
```

Expected output roughly:
- Bars: ~370,000–390,000 (≈ 1000 trading days × 390 bars, minus low-coverage days)
- Rollover skip dates: ~32 (4 quarterly rollovers/year × 4 years × 2 days each)
- Low-coverage days: typically < 15 (holidays, partial sessions, outages)

## Troubleshooting

- **`databento.common.error.BentoHttpError: 401`**: API key wrong or expired.
- **`401: insufficient permissions`**: your Databento plan doesn't include GLBX.MDP3 historical; contact Databento support to add futures.
- **DataFrame returned but `instrument_id` missing**: symbology wrong. Double-check `stype_in="continuous"` and `symbols=["MES.c.0"]`.
- **Bill shock (>$100)**: you almost certainly downloaded a non-OHLCV schema by accident. Cancel, get a refund, verify `schema="ohlcv-1m"`.
