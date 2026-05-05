#!/usr/bin/env python3
"""launchd entry point for report generation.

Phase 1: argparse + lock acquisition + delegation to CLI dry-run.
Later phases plug in the real pipeline (IB → AI → Obsidian → Telegram).

Usage:
    scripts/run_report.py --type premarket
    scripts/run_report.py --type premarket --dry   # Phase 1 stub mode
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_DIR = PROJECT_ROOT / "data" / "locks"

VALID_TYPES = (
    "premarket",
    "intraday-4h-1",
    "intraday-4h-2",
    "eod",
    "night",
    "asia",
    "weekly",
)


def _acquire_lock(report_type: str) -> int:
    """Acquire an exclusive lock for this report type.

    Returns the file descriptor; caller must keep it open until done.
    Raises SystemExit if another instance is running.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"{report_type}.lock"
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        print(
            f"[run_report] another instance of {report_type} is running; exit",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return fd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a scheduled report.")
    parser.add_argument(
        "--type",
        required=True,
        choices=VALID_TYPES,
        help="Report type to generate.",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Phase 1 dry-run: skip IB / AI / delivery, print stub progress.",
    )
    args = parser.parse_args()

    lock_fd = _acquire_lock(args.type)
    try:
        if args.dry:
            print(f"[run_report] report_type={args.type}")
            print("[run_report] (Phase 1 stub) all stages skipped")
            print("[run_report] complete")
            return 0

        # Phase 2: delegate to CLI run subcommand for premarket; other types
        # surface a NotImplementedError-style exit until later phases.
        if args.type != "premarket":
            print(
                f"[run_report] {args.type!r} not yet implemented (Phase 2 supports premarket only)",
                file=sys.stderr,
            )
            return 4

        # Use the CLI runner so the path matches `daytrader reports run`
        import subprocess
        cmd = [
            sys.executable, "-m", "daytrader.cli.main",
            "reports", "run", "--type", "premarket",
        ]
        completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        return completed.returncode
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
