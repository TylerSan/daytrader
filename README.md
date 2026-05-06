# Day Trading

## Trading docs (open these at the desk)

- [Pre-trade checklist](docs/trading/PRE_TRADE_CHECKLIST.md) — fill before every entry
- [Post-trade journal](docs/trading/POST_TRADE_JOURNAL.md) — fill immediately after every exit
- [Contract template](docs/trading/Contract.md.template) — risk rules, bans, cool-off
- [Setups](docs/trading/setups/) — locked setup definitions

## CLI (enforces the same gates)

- `daytrader journal pre-trade ...` — must `PASSED` before entry
- `daytrader journal post-trade <trade_id> --exit-price ... --notes "..."`
- `daytrader journal circuit status` — today's R, trade count, lock state
