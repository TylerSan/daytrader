#!/usr/bin/env python3
"""Pre-run sanity check for `daytrader reports run` automation.

Returns exit 0 if all checks pass, exit non-zero if any check fails.
With `--silent`, suppresses stdout (errors still go to stderr).

Checks:
- TWS / IB Gateway port reachable (TCP-level)
- TWS / IB Gateway API responsive (real ib_insync handshake)
- LLM backend (env DAYTRADER_LLM_BACKEND → config ai.backend → cli):
  - cli: `claude` CLI present on PATH (fatal if missing)
  - api: Anthropic API key present (env ANTHROPIC_API_KEY or
    anthropic.api_key in config/secrets.yaml); a missing `claude` CLI is
    only a warning. `--api-ping` additionally sends a 1-token request
    (opt-in: it spends API credits, so routine preflights skip it).
- `config/default.yaml` and `config/user.yaml` readable

With `--no-tws`, the two TWS checks (port + API handshake) are skipped
entirely; only the claude CLI and config checks run and gate the exit
code. Use it for pipelines that do not talk to TWS at all — e.g. the
weekly report (`daytrader weekly run --ai`, yfinance only), which was
losing most Sunday runs to "TWS port unreachable" before this switch.
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


def tws_api_responsive(
    host: str = "127.0.0.1", port: int = 7496, timeout: float = 8.0
) -> tuple[bool, str]:
    """Real IB API handshake test. Returns (ok, msg).

    Catches the "port open but API unresponsive" state — observed
    2026-05-04 06:00 PT when TWS was in a re-auth loop / HMDS disconnect:
    `tws_port_open()` returned True (TCP socket accepted) but every
    subsequent ib_insync request timed out, including positions / open
    orders / completed orders / account updates. The launchd job ran
    for 22 seconds and exited 1 with no report generated.

    This check does what the actual report pipeline will do — open a
    real ib_insync.IB() connection on a sentinel client_id and confirm
    isConnected() — so a half-connected TWS now fails fast at preflight
    instead of wasting a launchd fire and failing 22s later.

    ib_insync is lazy-imported so preflight stays usable in environments
    where it's not installed (returns ok=True with a "skipped" message —
    the port-level check still gates the run).

    client_id=999 is a sentinel chosen to avoid clashing with the real
    report run which uses client_id=1 (default per IBClient).
    """
    try:
        from ib_insync import IB
    except ImportError:
        return True, "ib_insync not installed; API handshake check skipped"

    ib = IB()
    try:
        ib.connect(host=host, port=port, clientId=999, timeout=timeout)
        connected = ib.isConnected()
        ib.disconnect()
        if not connected:
            return False, "connect() returned but isConnected() is False"
        return True, "ok"
    except Exception as e:
        return False, f"API handshake failed: {type(e).__name__}: {str(e)[:120]}"
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def claude_cli_available() -> bool:
    """Return True iff `claude` is on PATH."""
    return shutil.which("claude") is not None


def resolve_llm_backend(project_root: Path) -> tuple[str, str | None]:
    """Return (backend, error). backend is "cli" or "api".

    Falls back to "cli" if the daytrader package is not importable (keeps
    preflight usable outside the uv env, matching the historical check).
    """
    try:
        from daytrader.core.llm import LLMError, load_llm_settings
    except ImportError:
        return "cli", None
    try:
        return load_llm_settings(project_root).backend, None
    except LLMError as e:
        return "cli", str(e)


def api_key_present(project_root: Path) -> tuple[bool, str]:
    """Return (present, source). Never returns or prints the key."""
    try:
        from daytrader.core.llm import resolve_api_key
    except ImportError:
        return False, "daytrader package not importable"
    key, source = resolve_api_key(project_root)
    return key is not None, source


def api_ping(project_root: Path, timeout: float = 30.0) -> tuple[bool, str]:
    """1-token Messages API request with the resolved key + model.

    Opt-in only (--api-ping): costs a fraction of a cent per run.
    """
    try:
        import anthropic

        from daytrader.core.llm import load_llm_settings, resolve_api_key
    except ImportError as e:
        return False, f"import failed: {e}"
    key, _ = resolve_api_key(project_root)
    if not key:
        return False, "no API key"
    model = load_llm_settings(project_root).model
    try:
        client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=timeout)
        client.messages.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True, f"ok (model={model})"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:160]}"


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
    parser.add_argument(
        "--skip-api-check",
        action="store_true",
        help="skip the ib_insync API handshake (only check TCP port). Useful "
        "for debugging preflight without TWS, or in CI.",
    )
    parser.add_argument(
        "--api-timeout",
        type=float,
        default=8.0,
        help="seconds to wait for ib_insync handshake (default 8s)",
    )
    parser.add_argument(
        "--no-tws",
        action="store_true",
        help="skip both TWS checks (TCP port + API handshake). For pipelines "
        "that don't use TWS, e.g. the weekly report (yfinance only).",
    )
    parser.add_argument(
        "--api-ping",
        action="store_true",
        help="when the LLM backend is api, also send a 1-token request to "
        "verify key + model (spends API credits; off by default).",
    )
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    project_root = Path(args.project_root)
    failures: list[str] = []

    if args.no_tws:
        if not args.silent:
            print("[preflight] - TWS checks skipped (--no-tws)")
    else:
        # 1. TWS port (TCP level — fast, ~ms)
        if tws_port_open(host=args.tws_host, port=args.tws_port):
            if not args.silent:
                print(f"[preflight] ✓ TWS port reachable at {args.tws_host}:{args.tws_port}")
        else:
            failures.append(f"TWS port unreachable at {args.tws_host}:{args.tws_port}")

        # 2. TWS API handshake (real ib_insync connect — ~3-8s)
        # Skip if --skip-api-check OR if port already failed (no point handshaking
        # against a port that isn't open).
        if args.skip_api_check:
            if not args.silent:
                print("[preflight] - TWS API handshake skipped (--skip-api-check)")
        elif failures:  # port unreachable already
            if not args.silent:
                print("[preflight] - TWS API handshake skipped (port unreachable)")
        else:
            ok, msg = tws_api_responsive(
                host=args.tws_host, port=args.tws_port, timeout=args.api_timeout
            )
            if ok:
                if not args.silent:
                    print(f"[preflight] ✓ TWS API responsive ({msg})")
            else:
                failures.append(f"TWS API not responsive: {msg}")

    # 3. LLM backend: claude CLI (cli) or Anthropic API key (api)
    backend, backend_err = resolve_llm_backend(project_root)
    if backend_err:
        failures.append(f"config: {backend_err}")
    elif backend == "api":
        if not args.silent:
            print("[preflight] - LLM backend: api")
        if claude_cli_available():
            if not args.silent:
                print("[preflight] ✓ claude CLI on PATH (unused: LLM backend=api)")
        else:
            # Warning only. Worded to avoid the wrappers' fatal grep for
            # "claude CLI not found".
            print(
                "[preflight] ! claude CLI not on PATH — ignored (LLM backend=api)",
                file=sys.stderr,
            )
        present, source = api_key_present(project_root)
        if present:
            if not args.silent:
                print(f"[preflight] ✓ Anthropic API key present ({source})")
            if args.api_ping:
                ok, msg = api_ping(project_root)
                if ok:
                    if not args.silent:
                        print(f"[preflight] ✓ Anthropic API ping {msg}")
                else:
                    failures.append(f"LLM API ping failed: {msg}")
        else:
            failures.append(
                "LLM API key missing: set ANTHROPIC_API_KEY or "
                "anthropic.api_key in config/secrets.yaml"
            )
    elif claude_cli_available():
        if not args.silent:
            print("[preflight] ✓ claude CLI on PATH")
    else:
        failures.append("claude CLI not found on PATH")

    # 4. config files
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
