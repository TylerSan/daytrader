"""Unit tests for scripts/diagnose_preflight.py (no network, no TWS)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "diagnose_preflight.py"
PT = ZoneInfo("America/Los_Angeles")


def _load():
    spec = importlib.util.spec_from_file_location("diagnose_preflight", str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    sys.modules["diagnose_preflight"] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


dp = _load()


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60
    )


# ---------------------------------------------------------------------------
# Synthetic logs (line shapes copied from real production logs)
# ---------------------------------------------------------------------------

HDR = (
    "[run_{w}_launchd] start {ts}\n"
    "[run_{w}_launchd] PATH=/Users/x/.local/bin:/opt/homebrew/bin:/usr/bin:/bin\n"
    "[run_{w}_launchd] PWD=/Users/x/Projects/Day trading\n"
)


def hdr(w: str = "premarket", ts: str = "2026-10-29T06:00:05-07:00") -> str:
    return HDR.format(w=w, ts=ts)


def end(w: str = "premarket", rc: int = 0, kind: str = "reports") -> str:
    return (
        f"[run_{w}_launchd] {kind} run exit={rc}\n"
        f"[run_{w}_launchd] end 2026-10-29T06:06:00-07:00\n"
    )


NOISE = (
    "Error 321, reqId 7: Error validating request.-'bW' : cause - Invalid account code\n"
    "[futures_section] WARNING: get_open_interest(MES) failed: Insufficient OI bars for MES: got 0\n"
    "[ib_client] WARNING: requested 200 1D bars for MGC, received 139 (70%)\n"
    "findfont: Font family 'Noto Sans CJK SC' not found.\n"
    "$ES=F: possibly delisted; no price data found  (period=1d)\n"
)

TRACE_HEAD = (
    "Traceback (most recent call last):\n"
    '  File "/x/.venv/bin/daytrader", line 12, in <module>\n'
    "    sys.exit(cli())\n"
)

LOG_PORT = hdr("intraday_4h_2", "2026-10-29T11:00:05-07:00") + (
    "[preflight] ✗ TWS port unreachable at 127.0.0.1:7496\n"
    "[run_intraday_4h_2_launchd] PREFLIGHT FAILED — notify and exit 0\n"
    "[notify_preflight] Telegram OK msg_id=6331\n"
)

LOG_PORT_NO_ESC = hdr("intraday_4h_1", "2026-10-26T07:00:04-07:00") + (
    "[preflight] ✗ TWS port unreachable at 127.0.0.1:7496\n"
    "[run_intraday_4h_1_launchd] PREFLIGHT FAILED — notify and exit 0\n"
)

LOG_API = hdr("weekly", "2026-08-30T14:00:00-07:00") + (
    "positions request timed out\n"
    "open orders request timed out\n"
    "completed orders request timed out\n"
    "account updates for U11548070 request timed out\n"
    "[preflight] ✗ TWS API not responsive: API handshake failed: TimeoutError: \n"
    "[run_weekly_launchd] PREFLIGHT FAILED — send notification and exit\n"
    "[notify_preflight] Telegram OK msg_id=4138\n"
)

LOG_CLAUDE_MISSING = hdr("eod") + (
    "[preflight] ✗ claude CLI not found on PATH\n"
    "[run_eod_launchd] PREFLIGHT FAILED — notify and exit 0\n"
)

LOG_CONFIG = hdr("night") + (
    "[preflight] ✗ config: missing /x/config/user.yaml (run setup or use defaults)\n"
    "[run_night_launchd] PREFLIGHT FAILED — notify and exit 0\n"
)

LOG_SUCCESS = hdr() + "[run_premarket_launchd] preflight ok, invoking reports run\n" + NOISE + (
    "Report generated: /Users/x/Documents/DayTrader Vault/Daily/2026-10-09-premarket.md\n"
) + end()

LOG_CLAUDE_ONELINER = hdr("night", "2026-08-27T19:00:00-07:00") + (
    "[run_night_launchd] preflight ok, invoking reports run\n" + NOISE +
    "Report FAILED: RuntimeError: AI call failed: claude -p exit=1: no stderr\n"
) + end("night", 1)

LOG_CLAUDE_TRACE = hdr() + "[run_premarket_launchd] preflight ok, invoking reports run\n" + NOISE + TRACE_HEAD + (
    '  File "/x/src/daytrader/reports/core/ai_analyst.py", line 99, in call\n'
    '    raise RuntimeError(f"AI call failed: {last_error}")\n'
    "RuntimeError: AI call failed: claude -p exit=1: no stderr\n"
) + end(rc=1)

LOG_IB_RUNTIME = hdr("premarket", "2026-05-04T06:00:04-07:00") + (
    "[run_premarket_launchd] preflight ok, invoking reports run\n"
    "positions request timed out\n"
    "open orders request timed out\n"
) + TRACE_HEAD + (
    '  File "/x/src/daytrader/core/ib_client.py", line 127, in connect\n'
    "    self._ib.connect(\n"
    '  File "/x/.venv/lib/python3.12/site-packages/ib_insync/ib.py", line 1782, in connectAsync\n'
    "    await asyncio.wait_for(self.reqExecutionsAsync(), timeout)\n"
    "TimeoutError\n"
) + end(rc=1)

LOG_DISCONNECT = hdr("eod", "2026-05-07T14:00:01-07:00") + (
    "[run_eod_launchd] preflight ok, invoking reports run --type eod\n" + NOISE +
    "Report generated: /Users/x/Documents/DayTrader Vault/Daily/2026-05-07-eod.md\n"
) + TRACE_HEAD + (
    '  File "/x/src/daytrader/cli/reports.py", line 219, in run_cmd\n'
    "    ib.disconnect()\n"
    "OSError: [Errno 57] Socket is not connected\n"
) + end("eod", 1)

LOG_WEEKLY_OK = hdr("weekly", "2026-10-11T14:00:05-07:00") + (
    "[run_weekly_launchd] preflight ok, invoking weekly run --ai\n"
    "Running full weekly analysis with AI (this may take 1-3 minutes)...\n"
    "$ES=F: possibly delisted; no price data found  (period=1d)\n"
    "# 周度交易计划\n"
) + end("weekly", 0, "weekly")

LOG_WEEKLY_DEGRADED = hdr("weekly", "2026-07-05T14:00:05-07:00") + (
    "[run_weekly_launchd] preflight ok, invoking weekly run --ai\n"
    "Translation failed (rc=1)\n"
    "Claude AI analysis failed (rc=1): \n"
    "Weekly AI analysis unavailable; saving data report only\n"
) + end("weekly", 0, "weekly")

LOG_SKIP = hdr() + (
    "[run_premarket_launchd] preflight ok, invoking reports run\n"
    "Report already generated today (skipped).\n"
) + end()

LOG_VALIDATION = hdr("asia") + (
    "[run_asia_launchd] preflight ok, invoking reports run\n"
    "Report FAILED: validation: missing sections ['亚盘']\n"
) + end("asia", 1)

LOG_TELEGRAM = hdr("asia") + (
    "[run_asia_launchd] preflight ok, invoking reports run\n"
    "Report generated: /Users/x/Vault/Daily/2026-10-09-2300PT-asia.md\n"
    "[orchestrator] asia telegram failed: ConnectionError: boom\n"
) + end("asia", 0)

LOG_INTERRUPTED = hdr("eod") + (
    "[run_eod_launchd] preflight ok, invoking reports run\n" + NOISE
)

LOG_NOISE_ONLY_FAIL = hdr("eod") + (
    "[run_eod_launchd] preflight ok, invoking reports run\n" + NOISE +
    "something completely different went wrong\n"
) + end("eod", 1)


@pytest.mark.parametrize(
    "text, category, cadence",
    [
        (LOG_PORT, "PREFLIGHT_TWS_PORT", "intraday-4h-2"),
        (LOG_API, "PREFLIGHT_TWS_API", "weekly"),
        (LOG_CLAUDE_MISSING, "PREFLIGHT_CLAUDE_MISSING", "eod"),
        (LOG_CONFIG, "PREFLIGHT_CONFIG", "night"),
        (LOG_SUCCESS, "SUCCESS", "premarket"),
        (LOG_CLAUDE_ONELINER, "CLAUDE_CLI", "night"),
        (LOG_CLAUDE_TRACE, "CLAUDE_CLI", "premarket"),
        (LOG_IB_RUNTIME, "IB_RUNTIME", "premarket"),
        (LOG_DISCONNECT, "DISCONNECT_AFTER_SUCCESS", "eod"),
        (LOG_WEEKLY_OK, "SUCCESS", "weekly"),
        (LOG_WEEKLY_DEGRADED, "SUCCESS_DEGRADED", "weekly"),
        (LOG_SKIP, "IDEMPOTENT_SKIP", "premarket"),
        (LOG_VALIDATION, "VALIDATION", "asia"),
        (LOG_TELEGRAM, "TELEGRAM_DELIVERY", "asia"),
        (LOG_INTERRUPTED, "INTERRUPTED", "eod"),
        (LOG_NOISE_ONLY_FAIL, "UNKNOWN", "eod"),
    ],
)
def test_classify_categories(text, category, cadence):
    d = dp.classify_log(text)
    assert d.category == category
    assert d.cadence == cadence
    assert 0 < len(d.evidence) <= 5 or category == "INTERRUPTED"


def test_classify_fields():
    d = dp.classify_log(LOG_PORT)
    assert d.started_at == "2026-10-29T11:00:05-07:00"
    assert d.exit_code is None
    assert d.escalation_sent is True
    assert any("TWS port unreachable" in e for e in d.evidence)

    assert dp.classify_log(LOG_PORT_NO_ESC).escalation_sent is False

    s = dp.classify_log(LOG_SUCCESS)
    assert s.exit_code == 0
    assert s.report_path == "/Users/x/Documents/DayTrader Vault/Daily/2026-10-09-premarket.md"

    disc = dp.classify_log(LOG_DISCONNECT)
    assert disc.exit_code == 1
    assert disc.report_path.endswith("2026-05-07-eod.md")


def test_noise_never_in_evidence():
    for text in (LOG_SUCCESS, LOG_CLAUDE_TRACE, LOG_DISCONNECT, LOG_NOISE_ONLY_FAIL, LOG_INTERRUPTED):
        for e in dp.classify_log(text).evidence:
            assert not dp.RE_NOISE.search(e), e


def test_noise_with_exit_zero_is_success():
    text = hdr("eod") + NOISE + "Report generated: /v/2026-10-09-eod.md\n" + end("eod", 0)
    assert dp.classify_log(text).category == "SUCCESS"


def test_port_beats_other_preflight_failures():
    text = hdr() + (
        "[preflight] ✗ TWS port unreachable at 127.0.0.1:7496\n"
        "[preflight] ✗ claude CLI not found on PATH\n"
        "[run_premarket_launchd] PREFLIGHT FAILED — notify and exit 0\n"
    )
    d = dp.classify_log(text)
    assert d.category == "PREFLIGHT_TWS_PORT"
    assert any("claude CLI" in e for e in d.evidence)


def test_empty_log_is_interrupted():
    d = dp.classify_log("")
    assert d.category == "INTERRUPTED"
    assert d.cadence is None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _write(d: Path, name: str, text: str) -> Path:
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def test_find_run_logs_sorted_by_filename_ts(tmp_path):
    import os

    a = _write(tmp_path, "premarket-20261027-060000.log", LOG_SUCCESS)
    b = _write(tmp_path, "eod-20261028-140000.log", LOG_PORT)
    c = _write(tmp_path, "asia-20261026-230000.log", LOG_PORT)
    _write(tmp_path, "premarket.0600pt.out", "x")
    _write(tmp_path, "notes.log", "x")
    # mtimes deliberately inverted vs filename order
    os.utime(b, (1_000, 1_000))
    os.utime(a, (2_000, 2_000))
    os.utime(c, (3_000, 3_000))
    assert dp.find_run_logs(tmp_path) == [c, a, b]
    assert dp.find_run_logs(tmp_path, "premarket") == [a]
    assert dp.find_run_logs(tmp_path / "missing") == []
    assert dp.latest_log(tmp_path) == b
    assert dp.latest_log(tmp_path, "asia") == c


def test_latest_log_failed_only(tmp_path):
    fail = _write(tmp_path, "premarket-20261027-060000.log", LOG_PORT)
    _write(tmp_path, "premarket-20261028-060000.log", LOG_SUCCESS)
    _write(tmp_path, "eod-20261028-140000.log", LOG_DISCONNECT)  # OK category, skipped
    assert dp.latest_log(tmp_path, failed_only=True) == fail
    assert dp.latest_log(tmp_path, "eod", failed_only=True) is None


# ---------------------------------------------------------------------------
# Live context helpers
# ---------------------------------------------------------------------------


def test_probe_tws_port_closed_port_is_false():
    assert dp.probe_tws_port(port=65000, timeout=0.5) is False


def test_key_date_et_vs_pt():
    late = datetime(2026, 10, 29, 22, 0, tzinfo=PT)  # 01:00 ET next day
    assert str(dp.key_date("premarket", late)) == "2026-10-30"
    assert str(dp.key_date("night", late)) == "2026-10-29"


def test_state_db_lookup(tmp_path):
    import sqlite3

    assert dp.state_db_success(tmp_path, "premarket", datetime(2026, 10, 9).date()) is None
    (tmp_path / "data").mkdir()
    conn = sqlite3.connect(tmp_path / "data" / "state.db")
    conn.execute("CREATE TABLE reports (report_type TEXT, date TEXT, status TEXT)")
    conn.execute("INSERT INTO reports VALUES ('premarket','2026-10-09','success')")
    conn.execute("INSERT INTO reports VALUES ('eod','2026-10-09','failed')")
    conn.commit()
    conn.close()
    d = datetime(2026, 10, 9).date()
    assert dp.state_db_success(tmp_path, "premarket", d) is True
    assert dp.state_db_success(tmp_path, "eod", d) is False
    diag = dp.classify_log(hdr("premarket", "2026-10-09T06:00:05-07:00") + LOG_PORT.split("\n", 3)[3])
    assert dp.already_recovered(tmp_path, diag, datetime(2026, 10, 9, 12, tzinfo=PT)) is True


# ---------------------------------------------------------------------------
# Recommendation + rendering
# ---------------------------------------------------------------------------

NOON = datetime(2026, 10, 29, 12, 0, tzinfo=PT)
LATE = datetime(2026, 10, 29, 21, 30, tzinfo=PT)


def test_rec_tws_down():
    d = dp.classify_log(LOG_PORT)
    rec = dp.build_recommendation(d, False, False, NOON, project_root=Path("/r"))
    joined = "\n".join(rec)
    assert "TWS is still down at 127.0.0.1:7496" in joined
    assert "2FA" in joined
    assert dp.NO_FALLBACK_LINE in rec
    assert "reports run --type" not in joined


def test_rec_already_recovered():
    d = dp.classify_log(LOG_PORT)
    rec = dp.build_recommendation(d, True, True, NOON, project_root=Path("/r"))
    assert any("already recovered" in r for r in rec)
    assert not any("Catch-up" in r for r in rec)


def test_rec_weekly_no_tws_needed():
    d = dp.classify_log(LOG_API)
    rec = "\n".join(dp.build_recommendation(d, False, False, NOON, project_root=Path("/r")))
    assert "TWS is not needed" in rec
    assert "uv run daytrader weekly run --ai" in rec
    assert "still down" not in rec


def test_rec_claude_and_others():
    rec = "\n".join(dp.build_recommendation(dp.classify_log(LOG_CLAUDE_TRACE), True, False, NOON))
    assert 'claude -p "ping" --output-format text' in rec
    rec = "\n".join(dp.build_recommendation(dp.classify_log(LOG_IB_RUNTIME), True, False, NOON))
    assert "restart TWS" in rec.lower() or "Restart TWS" in rec
    rec = "\n".join(dp.build_recommendation(dp.classify_log(LOG_DISCONNECT), True, None, NOON))
    assert "Ignore exit 1" in rec
    rec = "\n".join(dp.build_recommendation(dp.classify_log(LOG_SUCCESS), True, True, NOON))
    assert "Nothing to do" in rec and "2026-10-09-premarket.md" in rec
    rec = "\n".join(dp.build_recommendation(dp.classify_log(LOG_INTERRUPTED), None, None, NOON))
    assert "human" in rec


def test_render_telegram_catchup_and_late_warning():
    d = dp.classify_log(LOG_PORT)
    root = Path("/Users/x/Projects/Day trading")
    rec = dp.build_recommendation(d, True, False, NOON, project_root=root)
    msg = dp.render_telegram(d, rec, Path("/l/intraday-4h-2-20261029-110005.log"), tws_up_now=True)
    assert msg.startswith("🩺 DayTrader diagnose")
    assert f'cd "{root}" && uv run daytrader reports run --type intraday-4h-2 --no-pdf' in msg
    assert "premarket → intraday-4h-1 → intraday-4h-2 → eod" in msg
    assert "intraday-4h-2-20261029-110005.log" in msg
    assert "PREFLIGHT_TWS_PORT" in msg
    assert "21:00 PT" not in msg
    assert len(msg) <= 1500

    late_rec = dp.build_recommendation(d, True, False, LATE, project_root=root)
    late_msg = dp.render_telegram(d, late_rec, "x.log", tws_up_now=True)
    assert "after 21:00 PT" in late_msg
    assert len(late_msg) <= 1500


def test_render_telegram_evidence_capped():
    d = dp.classify_log(LOG_API)
    msg = dp.render_telegram(d, ["a"], "x.log")
    ev = msg.split("Evidence:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert 1 <= len(ev) <= 3


def test_late_night_trap_only_for_et_keyed():
    d = dp.classify_log(LOG_CONFIG)  # night: PT-keyed
    rec = "\n".join(dp.build_recommendation(d, True, False, LATE))
    assert "after 21:00 PT" not in rec


# ---------------------------------------------------------------------------
# CLI (subprocess, --no-live)
# ---------------------------------------------------------------------------


@pytest.fixture
def log_dir(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    _write(d, "premarket-20261027-060000.log", LOG_SUCCESS)
    _write(d, "eod-20261027-140000.log", LOG_DISCONNECT)
    _write(d, "intraday-4h-2-20261028-110005.log", LOG_PORT)
    _write(d, "premarket-20261029-060000.log", LOG_SUCCESS)
    return d


def test_cli_help():
    r = _run("--help")
    assert r.returncode == 0
    for flag in ("--log-dir", "--last-failed", "--summary", "--json", "--no-live", "--send"):
        assert flag in r.stdout


def test_cli_latest_success_dry_run(log_dir):
    r = _run("--log-dir", str(log_dir), "--no-live")
    assert r.returncode == 0, r.stderr
    assert "premarket-20261029-060000.log" in r.stdout
    assert "Category: SUCCESS" in r.stdout
    assert r.stdout.rstrip().endswith("[diagnose] DRY-RUN — message not sent")


def test_cli_last_failed_json(log_dir):
    r = _run("--log-dir", str(log_dir), "--no-live", "--last-failed", "--json")
    assert r.returncode == 1, r.stderr
    data = json.loads(r.stdout)
    assert data["diagnosis"]["category"] == "PREFLIGHT_TWS_PORT"
    assert data["diagnosis"]["cadence"] == "intraday-4h-2"
    assert data["diagnosis"]["escalation_sent"] is True
    assert data["live"]["tws_up_now"] is None
    assert data["ok"] is False
    assert any("No databento/yfinance fallback" in r_ for r_ in data["recommendation"])


def test_cli_cadence_and_explicit_log(log_dir):
    r = _run("--log-dir", str(log_dir), "--no-live", "--cadence", "eod")
    assert r.returncode == 0
    assert "DISCONNECT_AFTER_SUCCESS" in r.stdout
    r = _run("--log", str(log_dir / "intraday-4h-2-20261028-110005.log"), "--no-live")
    assert r.returncode == 1
    assert "PREFLIGHT_TWS_PORT" in r.stdout


def test_cli_summary(log_dir):
    r = _run("--log-dir", str(log_dir), "--summary", "3")
    assert r.returncode == 0, r.stderr
    assert "last 3 runs" in r.stdout
    assert "PREFLIGHT_TWS_PORT" in r.stdout
    r = _run("--log-dir", str(log_dir), "--summary", "10", "--json")
    data = json.loads(r.stdout)
    assert data["runs"] == 4
    assert data["categories"] == {
        "SUCCESS": 2, "DISCONNECT_AFTER_SUCCESS": 1, "PREFLIGHT_TWS_PORT": 1
    }


def test_cli_no_log_exit_2(tmp_path):
    assert _run("--log-dir", str(tmp_path), "--no-live").returncode == 2
    assert _run("--log-dir", str(tmp_path), "--summary", "5").returncode == 2
    assert _run("--log", str(tmp_path / "nope.log"), "--no-live").returncode == 2
    d = tmp_path / "ok"
    d.mkdir()
    _write(d, "premarket-20261029-060000.log", LOG_SUCCESS)
    assert _run("--log-dir", str(d), "--no-live", "--last-failed").returncode == 2


def test_main_in_process_with_fixed_now(log_dir, capsys):
    rc = dp.main(
        ["--log-dir", str(log_dir), "--no-live", "--last-failed"],
        now=datetime(2026, 10, 29, 22, 0, tzinfo=PT),
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "TWS now: unknown" in out
    assert "after 21:00 PT" in out


def test_module_imports_without_ib_insync():
    code = (
        "import sys, importlib.util;"
        "sys.modules['ib_insync']=None; sys.modules['yaml']=None;"
        f"spec=importlib.util.spec_from_file_location('d', r'{SCRIPT}');"
        "m=importlib.util.module_from_spec(spec); sys.modules['d']=m; spec.loader.exec_module(m);"
        "print(m.probe_tws_port(port=65000, timeout=0.2))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"
