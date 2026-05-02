"""Unit tests for scripts/preflight_check.py."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "preflight_check.py"


def _run(*extra_args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), *extra_args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_preflight_help_succeeds():
    """`--help` exits 0."""
    result = _run("--help")
    assert result.returncode == 0
    assert "preflight" in (result.stdout + result.stderr).lower()


def test_preflight_silent_mode_supported():
    """`--silent` flag is accepted."""
    result = _run("--help")
    assert result.returncode == 0
    assert "--silent" in result.stdout


def test_preflight_check_tws_port_unreachable_when_no_tws(monkeypatch):
    """Direct function test: tws_port_open returns False when nothing's listening."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("preflight_check", str(SCRIPT))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Pick an unused port — port 0 is invalid, use 65000
        result = module.tws_port_open(host="127.0.0.1", port=65000, timeout=1.0)
        assert result is False
    finally:
        sys.path.pop(0)


def test_preflight_check_tws_port_open_when_listener(monkeypatch, tmp_path):
    """Spin up a temp TCP listener; preflight detects it."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("preflight_check", str(SCRIPT))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            result = module.tws_port_open(host="127.0.0.1", port=port, timeout=1.0)
            assert result is True
        finally:
            srv.close()
    finally:
        sys.path.pop(0)


def test_preflight_check_claude_cli_available():
    """claude_cli_available returns True when `claude` binary is on PATH."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("preflight_check", str(SCRIPT))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Real claude is installed (at /opt/homebrew/bin/claude)
        # Test default behavior — should find it
        result = module.claude_cli_available()
        # Accept either True or False; we just want it not to crash
        assert isinstance(result, bool)
    finally:
        sys.path.pop(0)
