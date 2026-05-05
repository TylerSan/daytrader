# IB Gateway + IBC Operational Setup

This doc covers the manual one-time setup needed to run the Phase 1+ reports system. Once complete, the system can fetch market data without human intervention 24/7.

## Prerequisites

- IBKR account (paper or live)
- CME Real-time Market Data subscription (for MES/MNQ; user already has)
- COMEX Real-time Market Data subscription (for MGC) — verify under Account → Market Data Subscriptions
- macOS 12+ (other platforms work but ops docs assume macOS)
- Java 8 or 17 (IB Gateway requirement; install via Homebrew if missing)

## Step 1: Install IB Gateway

1. Download "IB Gateway — Stable" from <https://www.interactivebrokers.com/en/trading/ibgateway-stable.php>
2. Install to `/Applications/IB Gateway/<version>/`
3. Launch once manually:
   - Choose "IB Gateway" mode (not TWS)
   - Mode: Live (port 4002) or Paper (port 4001) — pick based on your trading account
   - Sign in with your IBKR username/password
   - Accept terms; let the Gateway initialize
4. Quit IB Gateway.

## Step 2: Install IBC (IB Controller)

IBC handles the IB Gateway's daily logout/reconnect, 2FA prompts, and crash recovery. It's the standard solution for headless 24/7 IB Gateway operation.

1. Download from <https://github.com/IbcAlpha/IBC/releases> (latest stable release)
2. Extract to `~/IBC/`
3. Edit `~/IBC/config.ini`:
   - Set `IbLoginId=<your-username>`
   - Set `IbPassword=<your-password>` (or use the alternate keychain method below)
   - Set `TradingMode=live` (or `paper`)
   - Set `IbDir=/Applications/IB Gateway/<version>` (path to your install)
   - Enable `ReadOnlyApi=no` (Phase 1 reads only, but later phases may need full access for OI/COT)
4. (Recommended) Use macOS Keychain for password instead of plaintext:
   - Set `PasswordEncryption=yes` and use `~/IBC/scripts/keychain.sh` to store the password securely.

## Step 3: Test the launch script

1. Run IBC with a dry-run flag to verify config:

   ```bash
   ~/IBC/scripts/displaybannerandlaunch.sh
   ```

2. Wait ~30 seconds. The Gateway window should appear and auto-login.
3. Verify the Gateway is listening on port 4002 (live) or 4001 (paper):

   ```bash
   nc -zv 127.0.0.1 4002
   ```

   Expected: `Connection to 127.0.0.1 port 4002 [tcp/*] succeeded!`

4. From this repo, test the connection:

   ```bash
   uv run python -c "from daytrader.core.ib_client import IBClient; c = IBClient(); c.connect(); print('healthy:', c.is_healthy()); c.disconnect()"
   ```

   Expected: `healthy: True`

## Step 4: launchd plist (Phase 7 will add this; documenting the path here)

When Phase 7 lands, a launchd plist at `scripts/launchd/com.daytrader.ibgateway.plist` will:
- Launch IBC at boot
- KeepAlive=true (auto-restart on crash)
- Redirect stdout/stderr to `data/logs/launchd/ibgateway.{out,err}`

For Phase 1, you can manually run IBC during dev sessions and quit when done.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Login failed: 2FA required" | IBC config missing 2FA setup | See IBC README for SMS/IBKey/Mobile config |
| Connection refused on port 4002 | Gateway not running | Re-run IBC launch script |
| `IB Gateway requires re-authentication` daily | Default behavior | IBC's `RestartTime` setting handles this; defaults to 03:00 |
| `Pacing violation` errors | Too many IB requests too fast | Reduce concurrency in `core/ib_client.py` (Phase 2+) |
| MGC bars empty | COMEX subscription missing | Add COMEX Top of Book ($1.50/mo) in Account → Market Data |

## References

- IBC documentation: <https://github.com/IbcAlpha/IBC/blob/master/userguide.md>
- ib_insync docs: <https://ib-insync.readthedocs.io/>
- IB Gateway port reference: 4001 (paper), 4002 (live), 7496 (TWS live), 7497 (TWS paper)
