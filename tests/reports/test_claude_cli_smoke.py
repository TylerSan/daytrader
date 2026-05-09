"""Smoke test: verify the `claude` CLI is available on PATH.

Phase 2 invokes Claude via `claude -p` subprocess (using the user's
Pro Max subscription) rather than the Anthropic API. We verify the
binary is reachable without making a real call.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def test_claude_cli_on_path():
    """`claude` is resolvable via shutil.which."""
    path = shutil.which("claude")
    if path is None:
        pytest.skip(
            "claude CLI not on PATH — install Claude Code to run Phase 2 acceptance"
        )
    assert path  # truthy; e.g. /usr/local/bin/claude


def test_claude_cli_help_succeeds():
    """`claude --help` exits 0 and prints usage."""
    if shutil.which("claude") is None:
        pytest.skip("claude CLI not on PATH")
    result = subprocess.run(
        ["claude", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    # Usage banner should mention --print or -p
    combined = (result.stdout + result.stderr).lower()
    assert "print" in combined or "-p" in combined
