#!/usr/bin/env python3
"""Diagnose a launchd report run from its per-run log and say what to do next.

Reads `data/logs/launchd/<cadence>-YYYYMMDD-HHMMSS.log` (written by the
`scripts/run_*_launchd.sh` wrappers), classifies the outcome into a fixed
failure taxonomy, optionally probes live state (TWS port now, state.db
success row), and prints a compact Telegram-ready message with the exact
recovery command. Default is dry-run; `--send` pushes it via Telegram.

Why this exists: the wrappers `exit 0` on preflight failure, so launchctl
never sees a failure; the only durable evidence is the per-run log. This
script turns that log into a verdict + action an agent (or human) can
branch on via the exit code.

Since 2026-10-29 the weekday wrappers degrade a TWS-only preflight failure
to `reports run --source yfinance` (log line `PREFLIGHT FAILED (TWS only) —
degrading to --source yfinance`). Those runs classify as
SUCCESS_DEGRADED_YFINANCE / DEGRADED_YFINANCE_FAILED, never as a
PREFLIGHT_TWS_* failure (which now only comes from older wrappers / weekly).

Stdlib only. pyyaml is imported only on the `--send` path; ib_insync is
never imported (preflight_check.tws_port_open is a plain TCP probe).

Exit codes:
    0  category is SUCCESS / SUCCESS_DEGRADED / SUCCESS_DEGRADED_YFINANCE /
       DISCONNECT_AFTER_SUCCESS / IDEMPOTENT_SKIP (nothing lost)
    1  any other category (a cadence was lost or needs a human)
    2  no matching log found

Usage:
    uv run python scripts/diagnose_preflight.py                  # latest run
    uv run python scripts/diagnose_preflight.py --last-failed    # latest non-success
    uv run python scripts/diagnose_preflight.py --cadence eod --json
    uv run python scripts/diagnose_preflight.py --summary 20
    uv run python scripts/diagnose_preflight.py --log path/to/run.log --no-live
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent

TWS_HOST = "127.0.0.1"
TWS_PORT = 7496  # hard-coded in preflight_check.py / wrappers, not read from config

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

SUCCESS = "SUCCESS"
SUCCESS_DEGRADED = "SUCCESS_DEGRADED"
SUCCESS_DEGRADED_YFINANCE = "SUCCESS_DEGRADED_YFINANCE"
DEGRADED_YFINANCE_FAILED = "DEGRADED_YFINANCE_FAILED"
PREFLIGHT_TWS_PORT = "PREFLIGHT_TWS_PORT"
PREFLIGHT_TWS_API = "PREFLIGHT_TWS_API"
PREFLIGHT_CLAUDE_MISSING = "PREFLIGHT_CLAUDE_MISSING"
PREFLIGHT_CONFIG = "PREFLIGHT_CONFIG"
CLAUDE_CLI = "CLAUDE_CLI"
IB_RUNTIME = "IB_RUNTIME"
VALIDATION = "VALIDATION"
TELEGRAM_DELIVERY = "TELEGRAM_DELIVERY"
DISCONNECT_AFTER_SUCCESS = "DISCONNECT_AFTER_SUCCESS"
IDEMPOTENT_SKIP = "IDEMPOTENT_SKIP"
INTERRUPTED = "INTERRUPTED"
UNKNOWN = "UNKNOWN"

CATEGORIES = (
    SUCCESS,
    SUCCESS_DEGRADED,
    SUCCESS_DEGRADED_YFINANCE,
    DEGRADED_YFINANCE_FAILED,
    PREFLIGHT_TWS_PORT,
    PREFLIGHT_TWS_API,
    PREFLIGHT_CLAUDE_MISSING,
    PREFLIGHT_CONFIG,
    CLAUDE_CLI,
    IB_RUNTIME,
    VALIDATION,
    TELEGRAM_DELIVERY,
    DISCONNECT_AFTER_SUCCESS,
    IDEMPOTENT_SKIP,
    INTERRUPTED,
    UNKNOWN,
)

OK_CATEGORIES = frozenset(
    {
        SUCCESS,
        SUCCESS_DEGRADED,
        SUCCESS_DEGRADED_YFINANCE,
        DISCONNECT_AFTER_SUCCESS,
        IDEMPOTENT_SKIP,
    }
)
PREFLIGHT_TWS_CATEGORIES = frozenset({PREFLIGHT_TWS_PORT, PREFLIGHT_TWS_API})

# Cadences whose state.db date key is the ET date (others: PT date).
ET_KEYED = frozenset({"premarket", "intraday-4h-1", "intraday-4h-2", "eod"})
# Same-day chain; later cadences read earlier output (4h reads premarket).
SAME_DAY_CHAIN = ("premarket", "intraday-4h-1", "intraday-4h-2", "eod")
# Scheduled PT slot (hour, minute) per weekday cadence.
SCHEDULE_PT = {
    "premarket": (6, 0),
    "intraday-4h-1": (7, 0),
    "intraday-4h-2": (11, 0),
    "eod": (14, 0),
    "night": (19, 0),
    "asia": (23, 0),
}

YFINANCE_FALLBACK_LINE = (
    "A yfinance fallback exists: `reports run --source yfinance` (data delayed "
    "~15 min, no OI / contract chain). Current weekday wrappers degrade to it "
    "automatically on a TWS-only preflight failure, so a PREFLIGHT_TWS_* log "
    "comes from an older wrapper (or weekly)."
)


def yfinance_command(cadence: str | None, project_root: Path) -> str:
    return (
        f'cd "{project_root}" && uv run daytrader reports run '
        f'--type {cadence or "<cadence>"} --no-pdf --source yfinance'
    )

# ---------------------------------------------------------------------------
# Literal log signatures (see wrappers, preflight_check.py, cli/reports.py)
# ---------------------------------------------------------------------------

RE_START = re.compile(r"^\[run_(\w+)_launchd\] start (\S+)")
RE_PREFLIGHT_FAILED = re.compile(r"\] PREFLIGHT FAILED")
RE_DEGRADED_YF = re.compile(r"\] PREFLIGHT FAILED \(TWS only\) — degrading to --source yfinance")
RE_PF_PORT = re.compile(r"\[preflight\] ✗ TWS port unreachable")
RE_PF_API = re.compile(r"\[preflight\] ✗ TWS API not responsive")
RE_PF_CLAUDE = re.compile(r"\[preflight\] ✗ claude CLI not found on PATH")
RE_PF_CONFIG = re.compile(r"\[preflight\] ✗ config:")
RE_PF_ANY = re.compile(r"\[preflight\] ✗ ")
RE_NOTIFY_OK = re.compile(r"\[notify_preflight\] Telegram OK msg_id=\d+")
RE_EXIT = re.compile(r"\] (?:reports|weekly) run exit=(\d+)")
RE_REPORT_GENERATED = re.compile(r"^Report generated: (.+?)\s*$")
RE_SKIPPED = re.compile(r"^Report already generated today \(skipped\)\.")
RE_REPORT_FAILED = re.compile(r"^Report FAILED: ")
RE_CLAUDE_FAIL = re.compile(r"AI call failed: claude -p (?:exit=\d+|timeout)")
RE_VALIDATION = re.compile(r"validation: missing sections \[")
RE_TELEGRAM_FAIL = re.compile(r"\[orchestrator\] .*telegram (?:push )?failed:", re.I)
RE_WEEKLY_DEGRADED = re.compile(r"Weekly AI analysis unavailable")
RE_WEEKLY_AI_FAIL = re.compile(r"Claude AI analysis failed \(rc=\d+\)")
RE_DISCONNECT = re.compile(r"OSError: \[Errno 57\]")
RE_IB_CONNECT = re.compile(r"connectAsync|ib_client\.py\", line \d+, in connect\b")
RE_FINAL_EXC = re.compile(
    r"^(?:[\w.]+\.)?(TimeoutError|ConnectionRefusedError|ConnectionResetError|"
    r"ConnectionError|CancelledError)\b"
)
RE_TIMED_OUT = re.compile(r"request timed out$")

# Benign noise: never evidence, never drives a category.
RE_NOISE = re.compile(
    r"Error 321, reqId|get_open_interest|findfont:|\[ib_client\] WARNING|"
    r"possibly delisted"
)

RE_LOG_NAME = re.compile(r"^(?P<cadence>[a-z0-9-]+)-(?P<ts>\d{8}-\d{6})\.log$")

MAX_EVIDENCE = 5


@dataclass
class Diagnosis:
    category: str = UNKNOWN
    cadence: str | None = None
    started_at: str | None = None
    exit_code: int | None = None
    escalation_sent: bool = False
    evidence: list[str] = field(default_factory=list)
    report_path: str | None = None
    degraded: bool = False  # wrapper fell back to `--source yfinance`


def _clip(line: str, n: int = 200) -> str:
    line = line.rstrip()
    return line if len(line) <= n else line[: n - 1] + "…"


def classify_log(text: str) -> Diagnosis:
    """Classify a single wrapper run log. Pure function.

    A yfinance-degraded run (TWS-only preflight failure, then
    `reports run --source yfinance`) is classified like a normal pipeline run
    and then remapped: exit 0 → SUCCESS_DEGRADED_YFINANCE, a failed pipeline
    → DEGRADED_YFINANCE_FAILED (the inner cause stays in the evidence).
    Skip / Telegram-delivery / interrupted outcomes keep their category with
    `degraded=True`.
    """
    diag = _classify(text)
    if not diag.degraded:
        return diag
    if diag.category == SUCCESS:
        diag.category = SUCCESS_DEGRADED_YFINANCE
    elif diag.category in (CLAUDE_CLI, VALIDATION, IB_RUNTIME, UNKNOWN):
        diag.category = DEGRADED_YFINANCE_FAILED
    return diag


def _classify(text: str) -> Diagnosis:
    lines = text.splitlines()
    diag = Diagnosis()

    def find(rx: re.Pattern, *, last: bool = False) -> tuple[int, str] | None:
        hits = [(i, ln) for i, ln in enumerate(lines) if rx.search(ln) and not RE_NOISE.search(ln)]
        if not hits:
            return None
        return hits[-1] if last else hits[0]

    def find_all(rx: re.Pattern) -> list[str]:
        return [ln for ln in lines if rx.search(ln) and not RE_NOISE.search(ln)]

    evidence: list[str] = []

    def add(*items: str | None) -> None:
        for it in items:
            if it and _clip(it) not in evidence and len(evidence) < MAX_EVIDENCE:
                evidence.append(_clip(it))

    start = find(RE_START)
    if start:
        m = RE_START.search(start[1])
        diag.cadence = m.group(1).replace("_", "-")
        diag.started_at = m.group(2)

    exit_hit = find(RE_EXIT, last=True)
    if exit_hit:
        diag.exit_code = int(RE_EXIT.search(exit_hit[1]).group(1))

    diag.escalation_sent = find(RE_NOTIFY_OK) is not None

    gen = find(RE_REPORT_GENERATED, last=True)
    if gen:
        diag.report_path = RE_REPORT_GENERATED.search(gen[1]).group(1)

    pf = find(RE_PREFLIGHT_FAILED)
    notify = find(RE_NOTIFY_OK)
    degraded = find(RE_DEGRADED_YF)
    if degraded:
        # TWS-only preflight failure, wrapper went on with --source yfinance:
        # not a lost cadence; classify the yfinance pipeline run below.
        diag.degraded = True
        add(degraded[1])
        pf = None

    # 1. Preflight failures (wrapper exits 0 with no exit= line).
    if pf:
        for rx, cat in (
            (RE_PF_PORT, PREFLIGHT_TWS_PORT),
            (RE_PF_API, PREFLIGHT_TWS_API),
            (RE_PF_CLAUDE, PREFLIGHT_CLAUDE_MISSING),
            (RE_PF_CONFIG, PREFLIGHT_CONFIG),
        ):
            hit = find(rx)
            if hit:
                diag.category = cat
                add(hit[1])
                break
        else:
            diag.category = UNKNOWN
        add(*find_all(RE_PF_ANY))
        add(pf[1], notify[1] if notify else None)
        diag.evidence = evidence
        return diag

    # 2. Idempotent skip.
    skip = find(RE_SKIPPED)
    if skip:
        diag.category = IDEMPOTENT_SKIP
        add(skip[1], exit_hit[1] if exit_hit else None)
        diag.evidence = evidence
        return diag

    # 3. No exit line: wrapper never finished (killed, sleep, still running).
    if exit_hit is None:
        diag.category = INTERRUPTED
        add(gen[1] if gen else None)
        tail = [ln for ln in lines if ln.strip() and not RE_NOISE.search(ln)][-3:]
        add(*tail)
        diag.evidence = evidence
        return diag

    exit_code = diag.exit_code

    # 4. Report written, then a non-zero exit (e.g. ib.disconnect() OSError).
    if gen and exit_code != 0:
        disc = find(RE_DISCONNECT, last=True)
        if disc or any("disconnect()" in ln for ln in lines[gen[0]:]):
            diag.category = DISCONNECT_AFTER_SUCCESS
            add(gen[1], disc[1] if disc else None, exit_hit[1])
            diag.evidence = evidence
            return diag

    # 5. Telegram push failure (report written, push raised).
    tg = find(RE_TELEGRAM_FAIL)
    if tg:
        diag.category = TELEGRAM_DELIVERY
        add(tg[1], gen[1] if gen else None, exit_hit[1])
        diag.evidence = evidence
        return diag

    if exit_code == 0:
        # 6. Weekly degraded: AI failed but data report saved, exit 0.
        deg = find(RE_WEEKLY_DEGRADED)
        if deg:
            diag.category = SUCCESS_DEGRADED
            ai = find(RE_WEEKLY_AI_FAIL)
            add(ai[1] if ai else None, deg[1], exit_hit[1])
        else:
            diag.category = SUCCESS
            add(gen[1] if gen else None, exit_hit[1])
        diag.evidence = evidence
        return diag

    # 7. Non-zero exit: pick the cause.
    failed = find(RE_REPORT_FAILED)
    val = find(RE_VALIDATION)
    claude = find(RE_CLAUDE_FAIL, last=True)
    if val:
        diag.category = VALIDATION
        add(val[1])
    elif claude:
        diag.category = CLAUDE_CLI
        add(claude[1])
    else:
        final_exc = None
        for ln in reversed(lines):
            if RE_FINAL_EXC.search(ln.strip()):
                final_exc = ln.strip()
                break
        ib_connect = find(RE_IB_CONNECT)
        timed_out = find_all(RE_TIMED_OUT)
        if ib_connect or (final_exc and timed_out):
            diag.category = IB_RUNTIME
            add(*(timed_out[:1]), ib_connect[1].strip() if ib_connect else None, final_exc)
        else:
            diag.category = UNKNOWN
            add(failed[1] if failed else None)
            tail = [
                ln for ln in lines[: exit_hit[0]] if ln.strip() and not RE_NOISE.search(ln)
            ][-2:]
            add(*tail)
    add(exit_hit[1])
    diag.evidence = evidence
    return diag


# ---------------------------------------------------------------------------
# Log discovery
# ---------------------------------------------------------------------------


def _log_ts(path: Path) -> datetime | None:
    m = RE_LOG_NAME.match(path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("ts"), "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def find_run_logs(log_dir: Path, cadence: str | None = None) -> list[Path]:
    """Per-run logs `<cadence>-YYYYMMDD-HHMMSS.log`, oldest first by filename ts."""
    log_dir = Path(log_dir)
    if not log_dir.is_dir():
        return []
    out: list[tuple[datetime, str, Path]] = []
    for p in log_dir.iterdir():
        m = RE_LOG_NAME.match(p.name)
        if not m or not p.is_file():
            continue
        if cadence and m.group("cadence") != cadence:
            continue
        ts = _log_ts(p)
        if ts is None:
            continue
        out.append((ts, p.name, p))
    out.sort(key=lambda t: (t[0], t[1]))
    return [p for _, _, p in out]


def _read(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def latest_log(
    log_dir: Path, cadence: str | None = None, failed_only: bool = False
) -> Path | None:
    """Most recent run log; with failed_only, most recent run whose category is not OK."""
    logs = find_run_logs(log_dir, cadence)
    if not failed_only:
        return logs[-1] if logs else None
    for p in reversed(logs):
        if classify_log(_read(p)).category not in OK_CATEGORIES:
            return p
    return None


# ---------------------------------------------------------------------------
# Live context
# ---------------------------------------------------------------------------


def probe_tws_port(host: str = TWS_HOST, port: int = TWS_PORT, timeout: float = 1.0) -> bool | None:
    """True/False from preflight_check.tws_port_open; None if the probe itself broke."""
    try:
        spec = importlib.util.spec_from_file_location(
            "_diag_preflight_check", str(SCRIPT_DIR / "preflight_check.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return bool(module.tws_port_open(host=host, port=port, timeout=timeout))
    except Exception:
        return None


def key_date(cadence: str | None, when: datetime) -> date:
    """state.db idempotency date: ET date for premarket/4h/eod, PT date otherwise."""
    tz = ET if cadence in ET_KEYED else PT
    if when.tzinfo is None:
        when = when.replace(tzinfo=PT)
    return when.astimezone(tz).date()


def _parse_started(started_at: str | None) -> datetime | None:
    if not started_at:
        return None
    try:
        dt = datetime.fromisoformat(started_at)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=PT)


def state_db_success(project_root: Path, cadence: str, on_date: date) -> bool | None:
    """Does a status='success' row exist? None if the DB is missing/unreadable."""
    db = Path(project_root) / "data" / "state.db"
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            row = conn.execute(
                "SELECT 1 FROM reports WHERE report_type=? AND date=? "
                "AND status='success' LIMIT 1",
                (cadence, on_date.isoformat()),
            ).fetchone()
        finally:
            conn.close()
        return row is not None
    except sqlite3.Error:
        return None


def already_recovered(project_root: Path, diag: Diagnosis, now: datetime) -> bool | None:
    """Was the cadence of this run generated successfully for its date since?"""
    if not diag.cadence:
        return None
    when = _parse_started(diag.started_at) or now
    if diag.cadence == "weekly":
        # Legacy weekly path is not in state.db; it always writes this export.
        p = Path(project_root) / "data" / "exports" / f"weekly-{key_date('weekly', when)}.md"
        return p.is_file() and p.stat().st_size > 0
    return state_db_success(project_root, diag.cadence, key_date(diag.cadence, when))


def missed_same_day(project_root: Path, now_pt: datetime) -> list[str] | None:
    """Chain cadences whose slot has passed today with no success row (weekday only)."""
    if now_pt.weekday() >= 5 or now_pt.hour >= 21:
        return None
    today = key_date("premarket", now_pt)
    missed = []
    for cad in SAME_DAY_CHAIN:
        h, m = SCHEDULE_PT[cad]
        if (now_pt.hour, now_pt.minute) < (h, m):
            continue
        ok = state_db_success(project_root, cad, today)
        if ok is None:
            return None
        if not ok:
            missed.append(cad)
    return missed


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


def catchup_command(cadence: str | None, project_root: Path) -> str:
    if cadence == "weekly":
        return f'cd "{project_root}" && uv run daytrader weekly run --ai'
    return f'cd "{project_root}" && uv run daytrader reports run --type {cadence or "<cadence>"} --no-pdf'


def build_recommendation(
    diag: Diagnosis,
    tws_up_now: bool | None,
    already_recovered: bool | None,
    now_pt: datetime,
    *,
    project_root: Path = DEFAULT_PROJECT_ROOT,
    missed_today: list[str] | None = None,
) -> list[str]:
    """Plain-text action lines for this diagnosis."""
    cat = diag.cadence
    cmd = catchup_command(cat, project_root)
    now_pt = now_pt.astimezone(PT) if now_pt.tzinfo else now_pt.replace(tzinfo=PT)
    lines: list[str] = []

    def et_trap() -> None:
        if cat in ET_KEYED and now_pt.hour >= 21:
            lines.append(
                "WARNING: it is after 21:00 PT, so ET is already tomorrow. Running "
                f"{cat} now keys to tomorrow's ET date and will BLOCK tomorrow's "
                "scheduled run (idempotency: only a state.db row delete undoes it). "
                "Do not catch up tonight; let the next scheduled run fire."
            )

    def stale_date() -> None:
        started = _parse_started(diag.started_at)
        if not started or not cat:
            return
        run_key, now_key = key_date(cat, started), key_date(cat, now_pt)
        if run_key != now_key:
            lines.append(
                f"Note: the missed run was keyed to {run_key}; running now keys to "
                f"{now_key}. `reports run` cannot backfill a past date (no --date "
                "flag); a past-date regeneration needs Orchestrator.run_<cadence>"
                "(run_at=...) by hand (not in repo)."
            )

    if diag.category in PREFLIGHT_TWS_CATEGORIES:
        what = "port unreachable" if diag.category == PREFLIGHT_TWS_PORT else "API handshake timed out"
        if cat == "weekly":
            lines.append(
                f"Weekly preflight failed ({what}), but weekly uses yfinance only and "
                "TWS is not needed: run `uv run daytrader weekly run --ai` directly now."
            )
        if already_recovered:
            lines.append(f"{cat} already recovered (success recorded for its date), nothing to do.")
        elif cat == "weekly":
            lines.append(f"Catch-up: {cmd}")
        elif tws_up_now:
            lines.append(f"TWS is up now at {TWS_HOST}:{TWS_PORT}. Catch-up: {cmd}")
            if missed_today:
                chain = " → ".join(missed_today)
                lines.append(f"Missed today, run in this order: {chain}")
            else:
                lines.append(
                    "If several cadences were missed today, run them in order: "
                    "premarket → intraday-4h-1 → intraday-4h-2 → eod."
                )
            stale_date()
            et_trap()
        elif tws_up_now is None:
            lines.append(
                f"TWS state unknown (live probe skipped). Once TWS is up at "
                f"{TWS_HOST}:{TWS_PORT}, catch-up: {cmd}"
            )
            et_trap()
        else:
            if diag.category == PREFLIGHT_TWS_API:
                lines.append(
                    f"TWS port is down now at {TWS_HOST}:{TWS_PORT} (run saw a hung API): "
                    "restart TWS and log in (IBKR 2FA is manual), then re-run this diagnosis."
                )
            else:
                lines.append(
                    f"TWS is still down at {TWS_HOST}:{TWS_PORT}: start/log in to TWS "
                    "(IBKR 2FA is manual), then re-run this diagnosis."
                )
        if diag.category == PREFLIGHT_TWS_API and tws_up_now:
            lines.append(
                "Port is open but the run saw an API timeout: if the catch-up hangs "
                "too, restart TWS (re-auth loop / HMDS disconnect)."
            )
        if not diag.escalation_sent:
            lines.append(
                "Escalation was NOT sent for this run (no `Telegram OK` line; the "
                "notifier's stderr goes to /dev/null)."
            )
        if cat != "weekly" and not already_recovered and not tws_up_now:
            lines.append(
                "Or catch up now without TWS (yfinance, degraded): "
                + yfinance_command(cat, project_root)
            )
            if tws_up_now is False:
                et_trap()
        lines.append(YFINANCE_FALLBACK_LINE)
    elif diag.category == PREFLIGHT_CLAUDE_MISSING:
        lines.append(
            "`claude` was not on the wrapper PATH (/opt/homebrew/bin, /usr/local/bin, "
            "~/.local/bin). Fix the install/PATH, then re-run: " + cmd
        )
        et_trap()
    elif diag.category == PREFLIGHT_CONFIG:
        lines.append(
            "config/default.yaml or config/user.yaml missing in the project root. "
            "Restore it, then re-run: " + cmd
        )
        et_trap()
    elif diag.category == CLAUDE_CLI:
        lines.append(
            "`claude -p` failed with stdout discarded (ai_analyst records stderr only). "
            'Run `claude -p "ping" --output-format text` manually to see the real error '
            "(auth / usage limit), then re-run the cadence: " + cmd
        )
        if already_recovered:
            lines.append(f"{cat} already recovered (success recorded for its date), nothing to do.")
        et_trap()
    elif diag.category == IB_RUNTIME:
        lines.append(
            "TWS accepted the socket but hung during connect/requests. Restart TWS "
            "(log in; 2FA is manual), then re-run: " + cmd
        )
        if already_recovered:
            lines.append(f"{cat} already recovered (success recorded for its date), nothing to do.")
        et_trap()
    elif diag.category == DISCONNECT_AFTER_SUCCESS:
        lines.append(
            "Report was delivered (Report generated line precedes the error); the "
            "exit 1 comes from ib.disconnect() on a dead socket. Ignore exit 1."
        )
        if diag.report_path:
            lines.append(f"Report: {diag.report_path}")
    elif diag.category == SUCCESS:
        lines.append("Nothing to do.")
        if diag.report_path:
            lines.append(f"Report: {diag.report_path}")
    elif diag.category == SUCCESS_DEGRADED_YFINANCE:
        lines.append(
            "TWS was unreachable at preflight, so the report was generated from "
            "yfinance (data delayed ~15 min, no OI / contract chain). Nothing lost."
        )
        if diag.report_path:
            lines.append(f"Report: {diag.report_path}")
        lines.append(
            "Optional IB-quality re-run once TWS is up: the degraded run already "
            "wrote the success row, so it must be deleted first (destructive, ask "
            "the user), then: " + cmd
        )
    elif diag.category == DEGRADED_YFINANCE_FAILED:
        lines.append(
            f"TWS was unreachable and the yfinance fallback run also failed "
            f"(exit {diag.exit_code}). Read the evidence (claude -p / validation / "
            "yfinance error) before re-running."
        )
        if already_recovered:
            lines.append(f"{cat} already recovered (success recorded for its date), nothing to do.")
        elif tws_up_now:
            lines.append(f"TWS is up now at {TWS_HOST}:{TWS_PORT}. Catch-up: {cmd}")
        else:
            lines.append(f"Retry without TWS: {yfinance_command(cat, project_root)}")
        et_trap()
    elif diag.category == SUCCESS_DEGRADED:
        lines.append(
            "Weekly data report saved but the AI analysis failed (exit 0). Optional: "
            'check `claude -p "ping" --output-format text`, then re-run: ' + cmd
        )
    elif diag.category == IDEMPOTENT_SKIP:
        lines.append(
            "A success row already existed for this cadence/date, so the run was "
            "skipped. Nothing to do (to regenerate, delete that row in data/state.db)."
        )
    elif diag.category == VALIDATION:
        lines.append(
            "AI output failed section validation (missing sections). Re-run once: "
            + cmd
            + " ; if it repeats, inspect the template/prompt."
        )
        et_trap()
    elif diag.category == TELEGRAM_DELIVERY:
        lines.append(
            "Report was written but the Telegram push raised. Read it in the vault"
            + (f" ({diag.report_path})" if diag.report_path else "")
            + "; check config/secrets.yaml bot token / network."
        )
    else:  # INTERRUPTED / UNKNOWN
        if diag.category == INTERRUPTED:
            lines.append(
                "Run never reached its exit line (killed, machine slept, or still "
                "running). Evidence above; a human should check before re-running."
            )
        else:
            lines.append("Unrecognised outcome. Evidence above; ask a human before acting.")
        if already_recovered:
            lines.append(f"{cat} already recovered (success recorded for its date), nothing to do.")
    return lines


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

MAX_TELEGRAM = 1500


def _tws_label(v: bool | None) -> str:
    return "up" if v else ("unknown" if v is None else "down")


def render_telegram(
    diag: Diagnosis,
    recommendation: list[str],
    log_path: Path | str | None,
    *,
    tws_up_now: bool | None = None,
    already_recovered: bool | None = None,
) -> str:
    name = Path(log_path).name if log_path else "(none)"
    parts = [
        "🩺 DayTrader diagnose",
        "",
        f"Cadence: {diag.cadence or '?'}",
        f"Log: {name}",
        f"Started: {diag.started_at or '?'}",
        f"Category: {diag.category}",
        f"Exit: {diag.exit_code if diag.exit_code is not None else '-'}",
        f"Escalation sent: {'yes' if diag.escalation_sent else 'NO'}",
        f"TWS now: {_tws_label(tws_up_now)}",
    ]
    if already_recovered is not None:
        parts.append(f"Recovered since: {'yes' if already_recovered else 'no'}")
    if diag.evidence:
        parts.append("")
        parts.append("Evidence:")
        parts.extend(f"  {_clip(e, 160)}" for e in diag.evidence[:3])
    if recommendation:
        parts.append("")
        parts.append("Action:")
        parts.extend(f"- {r}" for r in recommendation)
    text = "\n".join(parts)
    if len(text) > MAX_TELEGRAM:
        text = text[: MAX_TELEGRAM - 1] + "…"
    return text


def summarize(logs: list[Path]) -> tuple[Counter, dict[str, Counter], int]:
    total: Counter = Counter()
    per_cadence: dict[str, Counter] = {}
    no_escalation = 0
    for p in logs:
        d = classify_log(_read(p))
        cad = d.cadence or RE_LOG_NAME.match(p.name).group("cadence")
        total[d.category] += 1
        per_cadence.setdefault(cad, Counter())[d.category] += 1
        if d.category.startswith("PREFLIGHT_") and not d.escalation_sent:
            no_escalation += 1
    return total, per_cadence, no_escalation


def render_summary(logs: list[Path]) -> str:
    total, per_cadence, no_esc = summarize(logs)
    first, last = logs[0].name, logs[-1].name
    out = [f"[diagnose] summary of last {len(logs)} runs ({first} .. {last})", ""]
    width = max(len(c) for c in CATEGORIES)
    out.append(f"{'category':<{width}}  count")
    out.append(f"{'-' * width}  -----")
    for cat in CATEGORIES:
        if total[cat]:
            out.append(f"{cat:<{width}}  {total[cat]:>5}")
    out.append(f"{'TOTAL':<{width}}  {sum(total.values()):>5}")
    out.append("")
    out.append("by cadence:")
    for cad in sorted(per_cadence):
        cells = ", ".join(f"{k}={v}" for k, v in per_cadence[cad].most_common())
        out.append(f"  {cad}: {cells}")
    out.append("")
    out.append(f"preflight failures with no Telegram escalation: {no_esc}")
    n_deg = total[SUCCESS_DEGRADED_YFINANCE] + total[DEGRADED_YFINANCE_FAILED]
    if n_deg:
        out.append(
            f"yfinance-degraded runs (TWS down, not lost): {n_deg} "
            f"(ok={total[SUCCESS_DEGRADED_YFINANCE]}, failed={total[DEGRADED_YFINANCE_FAILED]})"
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Telegram send (only path that needs pyyaml)
# ---------------------------------------------------------------------------


def send_telegram(project_root: Path, text: str) -> str:
    import yaml  # noqa: PLC0415 — only needed for --send

    spec = importlib.util.spec_from_file_location(
        "_diag_notify_preflight", str(SCRIPT_DIR / "notify_preflight_failure.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    secrets_path = Path(project_root) / "config" / "secrets.yaml"
    with open(secrets_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    token = data["telegram"]["bot_token"]
    chat_id = str(data["telegram"]["chat_id"])
    result = module._send_telegram(token, chat_id, text)
    if result and result.get("ok"):
        return f"[diagnose] Telegram OK msg_id={result.get('result', {}).get('message_id')}"
    return f"[diagnose] Telegram returned not-ok: {result}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="diagnose a launchd report run (preflight / pipeline) from its log",
    )
    p.add_argument("--project-root", default=str(DEFAULT_PROJECT_ROOT),
                   help="project root (default: parent of scripts/)")
    p.add_argument("--log-dir", default=None,
                   help="per-run log dir (default: <project-root>/data/logs/launchd)")
    p.add_argument("--cadence", default=None,
                   help="restrict to one cadence (premarket, intraday-4h-1, ..., weekly)")
    p.add_argument("--log", default=None, help="explicit log file (skips discovery)")
    p.add_argument("--last-failed", action="store_true",
                   help="pick the most recent failed run (category outside the exit-0 set) instead of the most recent run")
    p.add_argument("--summary", type=int, metavar="N", default=None,
                   help="print a category count table over the last N runs, then exit")
    p.add_argument("--json", action="store_true",
                   help="print Diagnosis + recommendation as JSON")
    p.add_argument("--no-live", action="store_true",
                   help="skip the TWS port probe and state.db lookup")
    p.add_argument("--send", action="store_true",
                   help="actually send the message via Telegram (default: dry-run)")
    return p


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = Path(args.project_root).expanduser()
    log_dir = Path(args.log_dir).expanduser() if args.log_dir else project_root / "data" / "logs" / "launchd"
    now_pt = (now or datetime.now(timezone.utc)).astimezone(PT)

    if args.summary is not None:
        logs = find_run_logs(log_dir, args.cadence)
        if args.summary > 0:
            logs = logs[-args.summary:]
        if not logs:
            print(f"[diagnose] no run logs found in {log_dir}", file=sys.stderr)
            return 2
        if args.json:
            total, per_cad, no_esc = summarize(logs)
            print(json.dumps({
                "runs": len(logs),
                "first": logs[0].name,
                "last": logs[-1].name,
                "categories": dict(total),
                "by_cadence": {k: dict(v) for k, v in per_cad.items()},
                "preflight_failures_without_escalation": no_esc,
            }, indent=2, ensure_ascii=False))
        else:
            print(render_summary(logs))
        return 0

    if args.log:
        log_path = Path(args.log).expanduser()
        if not log_path.is_file():
            print(f"[diagnose] log not found: {log_path}", file=sys.stderr)
            return 2
    else:
        log_path = latest_log(log_dir, args.cadence, failed_only=args.last_failed)
        if log_path is None:
            what = "failed run" if args.last_failed else "run log"
            print(f"[diagnose] no {what} found in {log_dir}", file=sys.stderr)
            return 2

    diag = classify_log(_read(log_path))
    if diag.cadence is None:
        m = RE_LOG_NAME.match(log_path.name)
        if m:
            diag.cadence = m.group("cadence")

    tws_up: bool | None = None
    recovered: bool | None = None
    missed: list[str] | None = None
    if not args.no_live:
        tws_up = probe_tws_port()
        recovered = already_recovered(project_root, diag, now_pt)
        if diag.category in PREFLIGHT_TWS_CATEGORIES and diag.cadence in ET_KEYED:
            missed = missed_same_day(project_root, now_pt)

    rec = build_recommendation(
        diag, tws_up, recovered, now_pt, project_root=project_root, missed_today=missed
    )

    if args.json:
        print(json.dumps({
            "log": str(log_path),
            "diagnosis": asdict(diag),
            "live": {
                "tws_up_now": tws_up,
                "already_recovered": recovered,
                "missed_today": missed,
                "now_pt": now_pt.isoformat(timespec="seconds"),
            },
            "recommendation": rec,
            "ok": diag.category in OK_CATEGORIES,
        }, indent=2, ensure_ascii=False))
    else:
        text = render_telegram(diag, rec, log_path, tws_up_now=tws_up, already_recovered=recovered)
        print(text)
        if args.send:
            try:
                print(send_telegram(project_root, text))
            except Exception as e:  # never crash on delivery
                print(f"[diagnose] Telegram send failed: {type(e).__name__}: {e}", file=sys.stderr)
        else:
            print("[diagnose] DRY-RUN — message not sent")

    return 0 if diag.category in OK_CATEGORIES else 1


if __name__ == "__main__":
    raise SystemExit(main())
