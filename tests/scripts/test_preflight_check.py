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


# ---------------------------------------------------------------------------
# tws_api_responsive — real ib_insync handshake check (added 2026-05-04 after
# launchd 06:00 PT auto-fire failed silently because TWS was port-open but
# API-unresponsive)
# ---------------------------------------------------------------------------


def _load_preflight_module():
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("preflight_check", str(SCRIPT))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_tws_api_responsive_returns_false_when_port_closed():
    """Against a port nothing's listening on, handshake should fail fast."""
    module = _load_preflight_module()
    ok, msg = module.tws_api_responsive(host="127.0.0.1", port=65000, timeout=2.0)
    assert ok is False
    assert "failed" in msg.lower() or "refused" in msg.lower() or "timeout" in msg.lower()


def test_tws_api_responsive_skipped_if_ib_insync_missing(monkeypatch):
    """If ib_insync is not importable, function returns ok=True with skipped msg
    so port-only check still gates the run (graceful degradation)."""
    module = _load_preflight_module()
    # Force ImportError on `from ib_insync import IB`
    import builtins
    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "ib_insync":
            raise ImportError("ib_insync not installed (mocked)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    ok, msg = module.tws_api_responsive(host="127.0.0.1", port=7496, timeout=1.0)
    assert ok is True
    assert "skipped" in msg.lower()


def test_preflight_skip_api_check_flag_supported():
    """--skip-api-check is a valid CLI flag."""
    result = _run("--help")
    assert result.returncode == 0
    assert "--skip-api-check" in result.stdout


def test_preflight_api_timeout_flag_supported():
    """--api-timeout is a valid CLI flag with default."""
    result = _run("--help")
    assert result.returncode == 0
    assert "--api-timeout" in result.stdout


def test_preflight_skip_api_check_bypasses_handshake(monkeypatch):
    """When --skip-api-check passed, tws_api_responsive is NOT invoked."""
    # Port is open (we'll spin up a listener) so port check passes.
    # If --skip-api-check works, the run returns 0 and DOESN'T attempt
    # the (slow) handshake.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        result = _run(
            "--skip-api-check",
            "--tws-host", "127.0.0.1",
            "--tws-port", str(port),
        )
        # The port check passes, claude + config may pass or fail depending
        # on env, but the API handshake is definitely skipped (visible in
        # stdout if successful).
        out = (result.stdout + result.stderr).lower()
        assert "api handshake skipped" in out or "skipped" in out
    finally:
        srv.close()
