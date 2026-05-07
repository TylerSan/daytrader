"""Send a Telegram notification when launchd preflight fails.

Why this exists: macOS notification (osascript) is easy to miss when
the user is asleep / phone-only. preflight failures (TWS API timeout,
claude CLI missing, config corrupted) silently lose entire cadences.
Telegram pushes through to phone.

Designed for invocation from run_*_launchd.sh wrappers. Stand-alone
(no daytrader package import → ~150ms startup), urllib + pyyaml only.

Best-effort: any exception → silent exit 0. NEVER block the wrapper.

Usage:
    uv run python scripts/notify_preflight_failure.py <cadence> <scheduled_time_pt>

Example:
    uv run python scripts/notify_preflight_failure.py premarket "06:00 PT"
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml


def _send_telegram(token: str, chat_id: str, text: str) -> dict | None:
    """Send a single message via Telegram Bot API. Returns response dict or None."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def main() -> int:
    # Argument parse — never block on bad args
    if len(sys.argv) < 3:
        print(
            "[notify_preflight] usage: notify_preflight_failure.py "
            "<cadence> <scheduled_time_pt>",
            file=sys.stderr,
        )
        return 0

    cadence = sys.argv[1]
    scheduled = sys.argv[2]

    # Locate secrets relative to this script (scripts/ → ../config/)
    project_root = Path(__file__).resolve().parents[1]
    secrets_path = project_root / "config" / "secrets.yaml"

    # Load secrets
    try:
        with open(secrets_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        token = data["telegram"]["bot_token"]
        chat_id = str(data["telegram"]["chat_id"])
    except Exception as e:
        print(
            f"[notify_preflight] secrets load failed ({secrets_path}): {e}",
            file=sys.stderr,
        )
        return 0

    # Build message
    now_local = datetime.now().astimezone()
    text = (
        f"⚠️ DayTrader preflight FAILED\n"
        f"\n"
        f"Cadence: {cadence}\n"
        f"Scheduled: {scheduled}\n"
        f"Detected: {now_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
        f"\n"
        f"Likely cause: TWS API unreachable "
        f"(IBKR mobile login can kick desktop session) / "
        f"claude CLI missing / config corrupted.\n"
        f"\n"
        f"Action: restart TWS, then re-run cadence manually:\n"
        f"  cd <repo>\n"
        f"  uv run daytrader reports run --type {cadence} --no-pdf\n"
        f"\n"
        f"This cadence is LOST until manually re-run."
    )

    # Send
    try:
        result = _send_telegram(token, chat_id, text)
        if result and result.get("ok"):
            msg_id = result.get("result", {}).get("message_id")
            print(f"[notify_preflight] Telegram OK msg_id={msg_id}")
        else:
            print(
                f"[notify_preflight] Telegram returned not-ok: {result}",
                file=sys.stderr,
            )
    except Exception as e:
        print(
            f"[notify_preflight] Telegram send failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )

    return 0  # ALWAYS exit 0 — never block wrapper


if __name__ == "__main__":
    sys.exit(main())
