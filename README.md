# Day Trading

## Trading docs (open these at the desk)

- [Pre-trade checklist](docs/trading/PRE_TRADE_CHECKLIST.md) — fill before every entry
- [Post-trade journal](docs/trading/POST_TRADE_JOURNAL.md) — fill immediately after every exit
- [Contract template](docs/trading/Contract.md.template) — risk rules, bans, cool-off
- [Setups](docs/trading/setups/) — locked setup definitions

## CLI (enforces the same gates)

Run from repo root. The `daytrader` entry point is not on `$PATH` — invoke
via `uv run`:

- `uv run daytrader journal pre-trade ...` — must `PASSED` before entry
- `uv run daytrader journal post-trade <trade_id> --exit-price ... --notes "..."`
- `uv run daytrader journal circuit status` — today's R, trade count, lock state

Optional: `alias dt='uv run daytrader'` in your shell rc, then `dt journal circuit status`.
