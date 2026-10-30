"""Tests for the weekday launchd wrappers' TWS-only yfinance degrade path.

The wrappers are run for real under bash with fake `uv` / `osascript`
executables (no network, no TWS, no Telegram). The fakes live in
`$HOME/.local/bin`, which every wrapper prepends to PATH last, so they win
over /opt/homebrew/bin etc.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT_ROOT / "scripts"

# wrapper stem -> (cadence, scheduled time string)
WRAPPERS = {
    "premarket": ("premarket", "06:00 PT"),
    "intraday_4h_1": ("intraday-4h-1", "07:00 PT"),
    "intraday_4h_2": ("intraday-4h-2", "11:00 PT"),
    "eod": ("eod", "14:00 PT"),
    "night": ("night", "19:00 PT"),
    "asia": ("asia", "23:00 PT"),
}

PF_PORT = "[preflight] ✗ TWS port unreachable at 127.0.0.1:7496"
PF_API = "[preflight] ✗ TWS API not responsive: API handshake failed: TimeoutError: "
PF_CLAUDE = "[preflight] ✗ claude CLI not found on PATH"
PF_CONFIG = "[preflight] ✗ config: missing /x/config/user.yaml (run setup or use defaults)"

# Fake uv: dispatches on its argv, records calls, driven by env vars.
FAKE_UV = r"""#!/usr/bin/env bash
if [[ "$1" == "run" && "$2" == "python" && "$3" == "scripts/preflight_check.py" ]]; then
    if [[ -n "${FAKE_PREFLIGHT_STDERR:-}" ]]; then
        printf '%s\n' "$FAKE_PREFLIGHT_STDERR" >&2
    fi
    exit "${FAKE_PREFLIGHT_RC:-0}"
fi
if [[ "$1" == "run" && "$2" == "python" && "$3" == *notify_preflight_failure.py ]]; then
    shift 3
    echo "$*" >> "$FAKE_NOTIFY_LOG"
    echo "[notify_preflight] Telegram OK msg_id=1"
    exit 0
fi
if [[ "$1" == "run" && "$2" == "daytrader" && "$3" == "reports" && "$4" == "run" ]]; then
    shift 2
    echo "$*" >> "$FAKE_REPORTS_LOG"
    echo "Report generated: /tmp/fake-report.md"
    exit "${FAKE_REPORT_RC:-0}"
fi
echo "fake uv: unexpected args: $*" >&2
exit 97
"""

FAKE_OSASCRIPT = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_OSASCRIPT_LOG"
exit 0
"""


def _wrapper(stem: str) -> Path:
    return SCRIPTS / f"run_{stem}_launchd.sh"


# ---------------------------------------------------------------------------
# Static checks (all six)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stem", sorted(WRAPPERS))
def test_bash_syntax_ok(stem):
    r = subprocess.run(["bash", "-n", str(_wrapper(stem))], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("stem", sorted(WRAPPERS))
def test_wrapper_contains_degrade_path(stem):
    cadence, sched = WRAPPERS[stem]
    text = _wrapper(stem).read_text(encoding="utf-8")
    assert "--source yfinance" in text
    assert "--degraded" in text
    assert "PREFLIGHT FAILED" in text
    assert "PREFLIGHT FAILED (TWS only) — degrading to --source yfinance" in text
    assert f"reports run --type {cadence} --no-pdf --source yfinance" in text
    assert f'"{cadence}" "{sched}" --degraded' in text
    assert "set -uo pipefail" in text
    assert 'rm -f "$PREFLIGHT_ERR"' in text


# ---------------------------------------------------------------------------
# Functional (fake uv / osascript)
# ---------------------------------------------------------------------------


class Run:
    def __init__(self, proc: subprocess.CompletedProcess, root: Path):
        self.proc = proc
        self.root = root

    def _lines(self, name: str) -> list[str]:
        p = self.root / name
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    @property
    def reports_calls(self) -> list[str]:
        return self._lines("reports_calls.txt")

    @property
    def notify_calls(self) -> list[str]:
        return self._lines("notify_calls.txt")

    @property
    def osascript_calls(self) -> list[str]:
        return self._lines("osascript_calls.txt")

    @property
    def run_log(self) -> str:
        logs = sorted((self.root / "data" / "logs" / "launchd").glob("*.log"))
        assert len(logs) == 1, logs
        return logs[0].read_text(encoding="utf-8")


def run_wrapper(tmp_path: Path, stem: str, *, preflight_rc: int, preflight_stderr: str = "",
                report_rc: int = 0) -> Run:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    wrapper = scripts / f"run_{stem}_launchd.sh"
    shutil.copy2(_wrapper(stem), wrapper)

    home = tmp_path / "home"
    shim = home / ".local" / "bin"
    shim.mkdir(parents=True)
    for name, body in (("uv", FAKE_UV), ("osascript", FAKE_OSASCRIPT)):
        f = shim / name
        f.write_text(body, encoding="utf-8")
        f.chmod(0o755)

    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    env = {
        "HOME": str(home),
        "PATH": f"{shim}:/usr/bin:/bin",
        "TMPDIR": str(tmpdir),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "FAKE_PREFLIGHT_RC": str(preflight_rc),
        "FAKE_PREFLIGHT_STDERR": preflight_stderr,
        "FAKE_REPORT_RC": str(report_rc),
        "FAKE_REPORTS_LOG": str(tmp_path / "reports_calls.txt"),
        "FAKE_NOTIFY_LOG": str(tmp_path / "notify_calls.txt"),
        "FAKE_OSASCRIPT_LOG": str(tmp_path / "osascript_calls.txt"),
    }
    proc = subprocess.run(["bash", str(wrapper)], env=env, capture_output=True, timeout=30)
    run = Run(proc, tmp_path)
    # mktemp file must be cleaned up on every path
    assert list(tmpdir.iterdir()) == []
    return run


CASES = ["asia", "premarket", "intraday_4h_2"]


@pytest.mark.parametrize("stem", CASES)
@pytest.mark.parametrize("report_rc", [0, 1])
def test_tws_only_failure_degrades_to_yfinance(tmp_path, stem, report_rc):
    cadence, sched = WRAPPERS[stem]
    r = run_wrapper(tmp_path, stem, preflight_rc=1, preflight_stderr=PF_PORT, report_rc=report_rc)

    assert r.proc.returncode == report_rc
    assert r.reports_calls == [f"reports run --type {cadence} --no-pdf --source yfinance"]
    assert r.notify_calls == [f"{cadence} {sched} --degraded"]
    assert len(r.osascript_calls) == 1 and "yfinance" in r.osascript_calls[0]

    log = r.run_log
    assert PF_PORT in log
    assert f"[run_{stem}_launchd] PREFLIGHT FAILED (TWS only) — degrading to --source yfinance" in log
    assert "notify and exit 0" not in log and "send notification and exit" not in log
    assert f"[run_{stem}_launchd] reports run exit={report_rc}" in log
    assert f"[run_{stem}_launchd] end " in log
    # [preflight] ✗ lines precede the degrade line (diagnose / humans grep them in order)
    assert log.index(PF_PORT) < log.index("degrading to --source yfinance")


@pytest.mark.parametrize("stem", CASES)
def test_tws_api_and_port_failure_degrades(tmp_path, stem):
    cadence, _ = WRAPPERS[stem]
    r = run_wrapper(tmp_path, stem, preflight_rc=1, preflight_stderr=f"{PF_PORT}\n{PF_API}")
    assert r.proc.returncode == 0
    assert r.reports_calls == [f"reports run --type {cadence} --no-pdf --source yfinance"]
    assert PF_PORT in r.run_log and PF_API in r.run_log


@pytest.mark.parametrize("stem", CASES)
@pytest.mark.parametrize(
    "stderr",
    [PF_CLAUDE, PF_CONFIG, f"{PF_PORT}\n{PF_CLAUDE}", "[preflight] ✗ something new"],
    ids=["claude", "config", "tws+claude", "unknown"],
)
def test_non_tws_failure_notifies_and_exits_0(tmp_path, stem, stderr):
    cadence, sched = WRAPPERS[stem]
    r = run_wrapper(tmp_path, stem, preflight_rc=1, preflight_stderr=stderr, report_rc=5)

    assert r.proc.returncode == 0
    assert r.reports_calls == []
    assert r.notify_calls == [f"{cadence} {sched}"]
    assert len(r.osascript_calls) == 1

    log = r.run_log
    assert stderr.splitlines()[-1] in log
    assert f"[run_{stem}_launchd] PREFLIGHT FAILED" in log
    assert "degrading to --source yfinance" not in log
    assert "reports run exit=" not in log


@pytest.mark.parametrize("stem", CASES)
@pytest.mark.parametrize("report_rc", [0, 1])
def test_preflight_ok_runs_ib_report(tmp_path, stem, report_rc):
    cadence, _ = WRAPPERS[stem]
    r = run_wrapper(tmp_path, stem, preflight_rc=0, report_rc=report_rc)

    assert r.proc.returncode == report_rc
    assert r.reports_calls == [f"reports run --type {cadence} --no-pdf"]
    assert r.notify_calls == []
    assert r.osascript_calls == []

    log = r.run_log
    assert f"[run_{stem}_launchd] preflight ok, invoking reports run" in log
    assert "PREFLIGHT FAILED" not in log
    assert f"[run_{stem}_launchd] reports run exit={report_rc}" in log


# ---------------------------------------------------------------------------
# notify_preflight_failure.build_message (never sends; no network)
# ---------------------------------------------------------------------------


def _load_notifier():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_test_notify_preflight", str(SCRIPTS / "notify_preflight_failure.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _now():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime(2026, 10, 29, 23, 0, 7, tzinfo=ZoneInfo("America/Los_Angeles"))


def test_notifier_degraded_message():
    m = _load_notifier()
    text = m.build_message("asia", "23:00 PT", True, _now())
    assert text.startswith("ℹ️ DayTrader: TWS 不可达，已用 yfinance 降级生成")
    assert "Cadence: asia" in text
    assert "Scheduled: 23:00 PT" in text
    assert "Detected: 2026-10-29 23:00 PDT" in text
    assert "数据延迟约 15 分钟；OI 与合约链不可用。" in text
    assert "TWS 恢复后可手动重跑：uv run daytrader reports run --type asia --no-pdf" in text
    assert "LOST" not in text and "⚠️" not in text


def test_notifier_default_message_unchanged():
    m = _load_notifier()
    text = m.build_message("premarket", "06:00 PT", False, _now())
    assert text == (
        "⚠️ DayTrader preflight FAILED\n"
        "\n"
        "Cadence: premarket\n"
        "Scheduled: 06:00 PT\n"
        "Detected: 2026-10-29 23:00 PDT\n"
        "\n"
        "Likely cause: TWS API unreachable "
        "(IBKR mobile login can kick desktop session) / "
        "claude CLI missing / config corrupted.\n"
        "\n"
        "Action: restart TWS, then re-run cadence manually:\n"
        "  cd <repo>\n"
        "  uv run daytrader reports run --type premarket --no-pdf\n"
        "\n"
        "This cadence is LOST until manually re-run."
    )


def test_notifier_degraded_flag_parsed_without_sending(tmp_path, monkeypatch):
    """main() picks up --degraded from argv[3:]; secrets are missing so it never sends."""
    m = _load_notifier()
    sent: list[str] = []
    monkeypatch.setattr(m, "_send_telegram", lambda *a: sent.append(a[2]) or {"ok": True})
    monkeypatch.setattr(m, "__file__", str(tmp_path / "scripts" / "notify_preflight_failure.py"))
    monkeypatch.setattr("sys.argv", ["x", "asia", "23:00 PT", "--degraded"])
    assert m.main() == 0
    assert sent == []  # no config/secrets.yaml under tmp_path → returns before sending

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "secrets.yaml").write_text(
        "telegram:\n  bot_token: t\n  chat_id: 1\n", encoding="utf-8"
    )
    assert m.main() == 0
    assert len(sent) == 1 and sent[0].startswith("ℹ️ DayTrader: TWS 不可达")
    monkeypatch.setattr("sys.argv", ["x", "asia", "23:00 PT"])
    assert m.main() == 0
    assert sent[1].startswith("⚠️ DayTrader preflight FAILED")
