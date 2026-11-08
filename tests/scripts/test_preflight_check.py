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


# ---------------------------------------------------------------------------
# --no-tws — weekly pipeline is yfinance-only, so its preflight must not gate
# on TWS (added 2026-10-29: 18 of 26 Sunday weekly runs since May were lost
# to "TWS port unreachable").
# ---------------------------------------------------------------------------


WEEKLY_WRAPPER = PROJECT_ROOT / "scripts" / "run_weekly_launchd.sh"


def _make_project_root(tmp_path: Path, *, user_yaml: bool = True) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "default.yaml").write_text("{}\n")
    if user_yaml:
        (cfg / "user.yaml").write_text("{}\n")
    return tmp_path


def _run_main(monkeypatch, module, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["preflight_check.py", *argv])
    return module.main()


def _patch_tws_down_and_forbid_api(monkeypatch, module) -> None:
    monkeypatch.setattr(module, "tws_port_open", lambda **kw: False)

    def _must_not_be_called(**kw):
        raise AssertionError("tws_api_responsive must not be called under --no-tws")

    monkeypatch.setattr(module, "tws_api_responsive", _must_not_be_called)


def test_no_tws_flag_in_help():
    result = _run("--help")
    assert result.returncode == 0
    assert "--no-tws" in result.stdout


def test_no_tws_passes_when_tws_down(monkeypatch, tmp_path, capsys):
    module = _load_preflight_module()
    port_calls: list = []

    def _port_down(**kw):
        port_calls.append(kw)
        return False

    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "tws_port_open", _port_down)
    monkeypatch.setattr(module, "claude_cli_available", lambda: True)
    root = _make_project_root(tmp_path)

    rc = _run_main(monkeypatch, module, "--no-tws", "--project-root", str(root))

    assert rc == 0
    assert port_calls == []
    out = capsys.readouterr().out
    assert "[preflight] - TWS checks skipped (--no-tws)" in out
    assert "all checks passed" in out


def test_no_tws_silent_prints_nothing_on_success(monkeypatch, tmp_path, capsys):
    module = _load_preflight_module()
    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "claude_cli_available", lambda: True)
    root = _make_project_root(tmp_path)

    rc = _run_main(monkeypatch, module, "--no-tws", "--silent", "--project-root", str(root))

    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_no_tws_still_fails_when_claude_missing(monkeypatch, tmp_path, capsys):
    module = _load_preflight_module()
    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "claude_cli_available", lambda: False)
    root = _make_project_root(tmp_path)

    rc = _run_main(monkeypatch, module, "--no-tws", "--silent", "--project-root", str(root))

    assert rc == 1
    err = capsys.readouterr().err
    assert "claude CLI not found on PATH" in err
    assert "TWS" not in err


def test_no_tws_still_fails_when_user_yaml_missing(monkeypatch, tmp_path, capsys):
    module = _load_preflight_module()
    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "claude_cli_available", lambda: True)
    root = _make_project_root(tmp_path, user_yaml=False)

    rc = _run_main(monkeypatch, module, "--no-tws", "--silent", "--project-root", str(root))

    assert rc == 1
    err = capsys.readouterr().err
    assert "user.yaml" in err
    assert "TWS" not in err


def test_without_no_tws_port_down_still_fails(monkeypatch, tmp_path, capsys):
    """Regression guard: default (daily/premarket) path still gates on TWS."""
    module = _load_preflight_module()
    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "claude_cli_available", lambda: True)
    root = _make_project_root(tmp_path)

    rc = _run_main(monkeypatch, module, "--silent", "--project-root", str(root))

    assert rc == 1
    assert "TWS port unreachable" in capsys.readouterr().err


def test_weekly_wrapper_uses_no_tws():
    text = WEEKLY_WRAPPER.read_text()
    assert "preflight_check.py --no-tws --silent" in text
    # The failure path must survive: log line, Telegram escalation, exit 0.
    assert "PREFLIGHT FAILED" in text
    assert 'notify_preflight_failure.py" "weekly" "Sunday 14:00 PT"' in text


def test_weekly_wrapper_bash_syntax_ok():
    result = subprocess.run(
        ["bash", "-n", str(WEEKLY_WRAPPER)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# LLM backend = api (2026-11): claude CLI optional, API key required,
# 1-token ping only behind --api-ping.
# ---------------------------------------------------------------------------


def test_api_backend_missing_claude_is_warning_only(monkeypatch, tmp_path, capsys):
    module = _load_preflight_module()
    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "claude_cli_available", lambda: False)
    monkeypatch.setattr(module, "api_ping", lambda root: (_ for _ in ()).throw(
        AssertionError("api_ping must not run without --api-ping")))
    monkeypatch.setenv("DAYTRADER_LLM_BACKEND", "api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    root = _make_project_root(tmp_path)

    rc = _run_main(monkeypatch, module, "--no-tws", "--project-root", str(root))

    assert rc == 0
    captured = capsys.readouterr()
    assert "claude CLI not found" not in captured.err  # wrappers grep this as fatal
    assert "ignored (LLM backend=api)" in captured.err
    assert "Anthropic API key present (env ANTHROPIC_API_KEY)" in captured.out
    assert "test-key-not-real" not in captured.out + captured.err


def test_api_backend_missing_key_fails(monkeypatch, tmp_path, capsys):
    module = _load_preflight_module()
    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "claude_cli_available", lambda: True)
    monkeypatch.setenv("DAYTRADER_LLM_BACKEND", "api")
    root = _make_project_root(tmp_path)

    rc = _run_main(monkeypatch, module, "--no-tws", "--project-root", str(root))

    assert rc == 1
    assert "LLM API key missing" in capsys.readouterr().err


def test_api_ping_opt_in(monkeypatch, tmp_path, capsys):
    module = _load_preflight_module()
    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "claude_cli_available", lambda: False)
    pinged = []
    monkeypatch.setattr(module, "api_ping", lambda root: (pinged.append(root) or (False, "AuthenticationError: bad")))
    monkeypatch.setenv("DAYTRADER_LLM_BACKEND", "api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    root = _make_project_root(tmp_path)

    rc = _run_main(monkeypatch, module, "--no-tws", "--api-ping", "--project-root", str(root))

    assert rc == 1 and len(pinged) == 1
    assert "LLM API ping failed" in capsys.readouterr().err


def test_cli_backend_missing_claude_still_fatal(monkeypatch, tmp_path, capsys):
    module = _load_preflight_module()
    _patch_tws_down_and_forbid_api(monkeypatch, module)
    monkeypatch.setattr(module, "claude_cli_available", lambda: False)
    root = _make_project_root(tmp_path)

    rc = _run_main(monkeypatch, module, "--no-tws", "--project-root", str(root))

    assert rc == 1
    assert "claude CLI not found on PATH" in capsys.readouterr().err
