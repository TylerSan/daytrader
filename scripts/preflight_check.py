#!/usr/bin/env python3
"""Pre-run sanity check for `daytrader reports run` automation.

Returns exit 0 if all checks pass, exit non-zero if any check fails.
With `--silent`, suppresses stdout (errors still go to stderr).

Checks:
- TWS / IB Gateway port reachable
- `claude` CLI present on PATH
- `config/default.yaml` and `config/user.yaml` readable
"""

from __future__ import annotations

import argparse
import shutil
import socket
import sys
from pathlib import Path


def tws_port_open(host: str = "127.0.0.1", port: int = 7496, timeout: float = 2.0) -> bool:
    """Return True iff TCP connect to host:port succeeds within timeout."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        sock.close()
        return True
    except (OSError, socket.timeout):
        return False


def claude_cli_available() -> bool:
    """Return True iff `claude` is on PATH."""
    return shutil.which("claude") is not None


def config_files_readable(project_root: Path) -> tuple[bool, str]:
    """Return (ok, msg). ok=True if both config files readable."""
    default = project_root / "config" / "default.yaml"
    user = project_root / "config" / "user.yaml"
    if not default.exists():
        return False, f"missing {default}"
    if not user.exists():
        return False, f"missing {user} (run setup or use defaults)"
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="preflight check for daytrader reports automation")
    parser.add_argument("--silent", action="store_true", help="suppress stdout on success")
    parser.add_argument("--tws-host", default="127.0.0.1")
    parser.add_argument("--tws-port", type=int, default=7496)
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    project_root = Path(args.project_root)
    failures: list[str] = []

    # 1. TWS port
    if tws_port_open(host=args.tws_host, port=args.tws_port):
        if not args.silent:
            print(f"[preflight] ✓ TWS reachable at {args.tws_host}:{args.tws_port}")
    else:
        failures.append(f"TWS unreachable at {args.tws_host}:{args.tws_port}")

    # 2. claude CLI
    if claude_cli_available():
        if not args.silent:
            print("[preflight] ✓ claude CLI on PATH")
    else:
        failures.append("claude CLI not found on PATH")

    # 3. config files
    ok, msg = config_files_readable(project_root)
    if ok:
        if not args.silent:
            print("[preflight] ✓ config files readable")
    else:
        failures.append(f"config: {msg}")

    if failures:
        for f in failures:
            print(f"[preflight] ✗ {f}", file=sys.stderr)
        return 1
    if not args.silent:
        print("[preflight] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
