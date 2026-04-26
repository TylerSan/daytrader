"""Tests for scripts/run_report.py — launchd entry point."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "run_report.py"


def test_run_report_help_succeeds():
    """run_report.py --help prints usage and exits 0."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--type" in result.stdout


def test_run_report_missing_type_fails():
    """No --type argument → non-zero exit."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_run_report_unknown_type_fails():
    """Unknown --type → non-zero exit."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--type", "bogus"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_run_report_premarket_dry_succeeds(tmp_path):
    """Phase 1: --type premarket --dry exits 0 and prints expected lines."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--type", "premarket", "--dry"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "report_type=premarket" in result.stdout
