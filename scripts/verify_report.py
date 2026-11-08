#!/usr/bin/env python3
"""Verify whether a DayTrader scheduled report really succeeded.

Pure stdlib (sqlite3 + zoneinfo); never imports ib_insync or connects to TWS.
Safe to run at any time, including while TWS is down.

Checks (each -> PASS / WARN / FAIL / SKIP):
  1. state_db_row      data/state.db `reports` has status='success' for (type, date)
  2. output_file       vault Daily/<file>.md (or data/exports fallback) exists, > 500 bytes
  3. latest_run_log    newest data/logs/launchd/<type>-*.log for the date ended `run exit=0`
  4. telegram          report delivery is UNVERIFIABLE today (documented gap)
  5. futures_not_etf   heuristic: ES/NQ levels look like futures (6000s/20000s), not SPY/QQQ (600s/500s)
  6. session_sections  premarket only: 亚盘 / 欧盘 paragraphs present (template gap -> WARN)
  7. language          CJK ratio of non-whitespace chars
  8. required_sections reuse output_validator.REQUIRED_SECTIONS
  9. data_source       informational: ib vs yfinance fallback (report-text marker + state.db
                       reports.data_source); never FAIL, WARN only if the two disagree

Exit codes: 0 PASS (or WARN without --strict), 1 FAIL (or WARN with --strict),
2 report file could not be located at all.

Usage:
  uv run python scripts/verify_report.py --type asia --date 2026-10-09 \
      --project-root "/Users/tylersan/Projects/Day trading/.claude/worktrees/nice-varahamihira-9d6142"
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

REPORT_TYPES = (
    "premarket",
    "intraday-4h-1",
    "intraday-4h-2",
    "eod",
    "night",
    "asia",
    "weekly",
)
ET_DATE_TYPES = ("premarket", "intraday-4h-1", "intraday-4h-2", "eod")
PT_DATE_TYPES = ("night", "asia")
TELEGRAM_TYPES = ET_DATE_TYPES  # night/asia/weekly have no Telegram by design

FILENAME_PATTERNS = {
    "premarket": "{date}-premarket.md",
    "intraday-4h-1": "{date}-0700PT-4H1.md",
    "intraday-4h-2": "{date}-1100PT-4H2.md",
    "eod": "{date}-eod.md",
    "night": "{date}-1900PT-night.md",
    "asia": "{date}-2300PT-asia.md",
    "weekly": "weekly-{date}.md",
}

VALIDATOR_KEYS = {
    "premarket": "premarket",
    "intraday-4h-1": "intraday-4h",
    "intraday-4h-2": "intraday-4h",
    "eod": "eod",
    "night": "night",
    "asia": "asia",
}

# Extra prefixes used by hand-named recovery logs in data/logs/manual.
MANUAL_LOG_ALIASES = {
    "intraday-4h-1": ("intraday-4h-1-", "4h1-"),
    "intraday-4h-2": ("intraday-4h-2-", "4h2-"),
}

MIN_FILE_BYTES = 500
CJK_THRESHOLD = 0.15
DEFAULT_VAULT = "~/Documents/DayTrader Vault"


@dataclass
class Check:
    name: str
    status: str
    detail: str


# ---------------------------------------------------------------------------
# Dates / paths
# ---------------------------------------------------------------------------


def default_date(report_type: str, now: datetime | None = None) -> str:
    """Date key the orchestrator would use for a run happening `now`.

    ET date for premarket/4h/eod, PT date for night/asia. Weekly files are
    named after the run day (launchd fires Sunday 14:00 PT), so default to the
    most recent Sunday in local time.
    """
    now = now or datetime.now().astimezone()
    if report_type in ET_DATE_TYPES:
        return now.astimezone(ET).date().isoformat()
    if report_type in PT_DATE_TYPES:
        return now.astimezone(PT).date().isoformat()
    local = now.date()
    return (local - timedelta(days=(local.weekday() + 1) % 7)).isoformat()


def expected_filename(report_type: str, date_str: str) -> str:
    return FILENAME_PATTERNS[report_type].format(date=date_str)


def expected_output_path(
    report_type: str,
    date_str: str,
    vault: Path,
    daily_folder: str = "Daily",
    weekly_folder: str = "Weekly",
) -> Path:
    folder = weekly_folder if report_type == "weekly" else daily_folder
    return Path(vault).expanduser() / folder / expected_filename(report_type, date_str)


def _yaml_scalar(text: str, key: str) -> str | None:
    """Tiny yaml-free lookup: first `key: value` line (any indentation)."""
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    if not m:
        return None
    val = m.group(1)
    if val[:1] in ("'", '"'):
        val = val[1:].split(val[0], 1)[0]
    else:
        val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
    return val or None


def config_value(project_root: Path, key: str) -> str | None:
    """config/user.yaml wins over config/default.yaml (regex, not a YAML parser)."""
    for name in ("user.yaml", "default.yaml"):
        p = project_root / "config" / name
        try:
            val = _yaml_scalar(p.read_text(encoding="utf-8"), key)
        except OSError:
            continue
        if val:
            return val
    return None


# ---------------------------------------------------------------------------
# Check 1: state.db
# ---------------------------------------------------------------------------


def check_state_db_row(
    report_type: str, date_str: str, project_root: Path
) -> tuple[Check, str | None, datetime | None]:
    """Returns (check, obsidian_path, created_at) of the latest success row."""
    if report_type == "weekly":
        return Check("state_db_row", SKIP, "weekly uses the legacy path and writes no state.db row"), None, None
    db = project_root / "data" / "state.db"
    if not db.exists():
        return Check("state_db_row", SKIP, f"{db} not found (wrong --project-root?)"), None, None
    try:
        conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT id, status, obsidian_path, duration_seconds, failure_reason, "
                "time_pt, telegram_msg_ids, created_at FROM reports WHERE report_type=? AND date=? "
                "ORDER BY id DESC",
                (report_type, date_str),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return Check("state_db_row", FAIL, f"cannot read {db}: {e}"), None, None
    if not rows:
        return Check(
            "state_db_row",
            FAIL,
            f"no row for ({report_type}, {date_str}); preflight failures never reach the DB",
        ), None, None
    latest = rows[0]
    success = [r for r in rows if r[1] == "success"]
    dur = f"{latest[3]:.0f}s" if latest[3] is not None else "n/a"
    desc = (
        f"latest id={latest[0]} status={latest[1]} time_pt={latest[5]} "
        f"duration={dur} obsidian_path={latest[2] or '-'}"
    )
    if latest[4]:
        desc += f" failure_reason={latest[4]}"
    desc += f"; telegram_msg_ids={latest[6] or 'NULL (never written by code)'}"
    if success:
        extra = "" if latest[1] == "success" else f" (an earlier row id={success[0][0]} is success)"
        try:
            created = datetime.fromisoformat(success[0][7])
            if created.tzinfo is None:
                created = created.replace(tzinfo=PT)
        except (TypeError, ValueError):
            created = None
        return Check("state_db_row", PASS, f"{len(rows)} row(s); {desc}{extra}"), success[0][2], created
    return Check("state_db_row", FAIL, f"{len(rows)} row(s), none success; {desc}"), None, None


# ---------------------------------------------------------------------------
# Check 2: output file
# ---------------------------------------------------------------------------


def locate_output(
    report_type: str,
    date_str: str,
    project_root: Path,
    vault: Path,
    daily_folder: str,
    weekly_folder: str,
    db_path: str | None,
) -> list[Path]:
    cands: list[Path] = []
    if db_path:
        cands.append(Path(db_path).expanduser())
    cands.append(expected_output_path(report_type, date_str, vault, daily_folder, weekly_folder))
    cands.append(project_root / "data" / "exports" / expected_filename(report_type, date_str))
    seen: list[Path] = []
    for c in cands:
        if c not in seen:
            seen.append(c)
    return seen


def check_output_file(candidates: list[Path]) -> tuple[Check, Path | None]:
    for c in candidates:
        if c.is_file():
            size = c.stat().st_size
            if size > MIN_FILE_BYTES:
                return Check("output_file", PASS, f"{c} ({size} bytes)"), c
            return Check("output_file", FAIL, f"{c} is only {size} bytes (<= {MIN_FILE_BYTES})"), c
    return Check("output_file", FAIL, "not found; looked in: " + " | ".join(str(c) for c in candidates)), None


# ---------------------------------------------------------------------------
# Check 3: wrapper run logs
# ---------------------------------------------------------------------------

RE_PREFLIGHT_OK = re.compile(r"\] preflight ok, invoking")
RE_RUN_EXIT = re.compile(r"\] (?:reports|weekly) run exit=(\d+)")
RE_END = re.compile(r"^\[run_\w+_launchd\] end ", re.MULTILINE)
RE_PREFLIGHT_FAILED = re.compile(r"\] PREFLIGHT FAILED")
RE_REPORT_FAILED = re.compile(r"^Report FAILED: (.+)$", re.MULTILINE)
RE_REASON = re.compile(
    r"^(\[preflight\] ✗ .+|Report FAILED: .+|RuntimeError: AI call failed: .+|"
    r"OSError: .+|TimeoutError.*|Claude AI analysis failed .+)$",
    re.MULTILINE,
)
RE_NOTIFY_OK = re.compile(r"\[notify_preflight\] Telegram OK msg_id=(\d+)")
RE_TELEGRAM_FAIL = re.compile(
    r"(\[orchestrator\] .*telegram (?:push )?failed:.*|^Telegram disabled: .*|^Telegram setup failed: .*)",
    re.IGNORECASE | re.MULTILINE,
)
RE_WEEKLY_DEGRADED = re.compile(r"Weekly AI analysis unavailable; saving data report only")


def _log_date_key(report_type: str, ts: datetime) -> str:
    """Map a wrapper log timestamp (machine-local, PT) to the report date key."""
    aware = ts.replace(tzinfo=PT)
    if report_type in ET_DATE_TYPES:
        return aware.astimezone(ET).date().isoformat()
    return aware.date().isoformat()


def find_run_logs(report_type: str, date_str: str, log_dir: Path) -> list[Path]:
    pat = re.compile(rf"^{re.escape(report_type)}-(\d{{8}}-\d{{6}})\.log$")
    hits: list[tuple[datetime, Path]] = []
    if not log_dir.is_dir():
        return []
    for p in log_dir.iterdir():
        m = pat.match(p.name)
        if not m:
            continue
        ts = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
        if _log_date_key(report_type, ts) == date_str:
            hits.append((ts, p))
    return [p for _, p in sorted(hits)]


def find_manual_logs(report_type: str, date_str: str, manual_dir: Path) -> list[Path]:
    if not manual_dir.is_dir():
        return []
    prefixes = MANUAL_LOG_ALIASES.get(report_type, (f"{report_type}-",))
    d = date.fromisoformat(date_str)
    wanted = {d.strftime("%Y%m%d"), (d + timedelta(days=1)).strftime("%Y%m%d")}
    out = []
    for p in sorted(manual_dir.iterdir()):
        if not p.name.startswith(prefixes):
            continue
        stamps = set(re.findall(r"(\d{8})-\d{6}", p.name))
        if not stamps or stamps & wanted:
            out.append(p)
    return out


def classify_log(text: str) -> tuple[str, str]:
    """Return (outcome, reason) where outcome in success/failed/incomplete."""
    reason_m = RE_REASON.search(text)
    reason = reason_m.group(1).strip() if reason_m else ""
    if RE_PREFLIGHT_FAILED.search(text):
        notify = RE_NOTIFY_OK.search(text)
        esc = f"; escalation Telegram OK msg_id={notify.group(1)}" if notify else "; NO escalation Telegram OK line"
        return "failed", f"PREFLIGHT FAILED: {reason or 'reason not logged'}{esc}"
    exit_m = RE_RUN_EXIT.search(text)
    if RE_REPORT_FAILED.search(text):
        return "failed", reason or RE_REPORT_FAILED.search(text).group(0)
    if exit_m is None:
        if not RE_PREFLIGHT_OK.search(text):
            return "incomplete", "no preflight result logged (still running or killed?)"
        return "incomplete", "preflight ok but no `run exit=` line (still running or killed?)"
    rc = int(exit_m.group(1))
    if rc != 0:
        if "Report generated:" in text:
            return "failed", f"exit={rc} AFTER `Report generated:` ({reason or 'see log'}) - file may still be fine"
        return "failed", f"exit={rc}: {reason or 'see log'}"
    if RE_WEEKLY_DEGRADED.search(text):
        return "degraded", "exit=0 but weekly AI analysis failed (data-only report)"
    if "Report already generated today (skipped)." in text:
        return "success", "exit=0 (idempotent skip: an earlier success row exists)"
    return "success", "exit=0"


def _log_ts(p: Path) -> datetime | None:
    m = re.search(r"-(\d{8}-\d{6})\.log$", p.name)
    return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=PT) if m else None


def check_latest_run_log(
    report_type: str,
    date_str: str,
    project_root: Path,
    db_success_at: datetime | None = None,
) -> tuple[Check, str]:
    """Returns (check, concatenated text of the date's logs for later checks).

    A failed latest launchd log is downgraded to WARN when state.db holds a
    success row created after it (i.e. a manual recovery run succeeded).
    """
    log_dir = project_root / "data" / "logs" / "launchd"
    logs = find_run_logs(report_type, date_str, log_dir)
    manual = find_manual_logs(report_type, date_str, project_root / "data" / "logs" / "manual")
    manual_note = f"; manual logs: {', '.join(p.name for p in manual)}" if manual else ""
    if not logs:
        return Check(
            "latest_run_log",
            WARN,
            f"no {report_type}-*.log in {log_dir} for {date_str} (manual run or launchd did not fire){manual_note}",
        ), ""
    texts = []
    results = []
    for p in logs:
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            t = f"<unreadable: {e}>"
        texts.append(t)
        results.append((p, *classify_log(t)))
    latest_p, outcome, reason = results[-1]
    earlier_ok = [p for p, o, _ in results[:-1] if o == "success"]
    head = f"{latest_p.name} ({len(logs)} log(s) for {date_str}): {reason}"
    if outcome == "success":
        status = PASS
    elif outcome == "degraded":
        status = WARN
    elif outcome == "incomplete":
        status = WARN
    elif db_success_at is not None and (_log_ts(latest_p) or db_success_at) <= db_success_at:
        status = WARN
        head += (
            f"; but state.db success row created {db_success_at.astimezone(PT):%Y-%m-%d %H:%M} PT "
            "(later manual recovery, no wrapper log)"
        )
    elif earlier_ok:
        status = WARN
        head += f"; earlier success in {earlier_ok[-1].name}"
    else:
        status = FAIL
    return Check("latest_run_log", status, head + manual_note), "\n".join(texts)


# ---------------------------------------------------------------------------
# Check 4: telegram
# ---------------------------------------------------------------------------


def check_telegram(report_type: str, log_text: str) -> Check:
    if report_type not in TELEGRAM_TYPES:
        return Check("telegram", SKIP, f"{report_type} has no Telegram delivery by design")
    m = RE_TELEGRAM_FAIL.search(log_text or "")
    if m:
        return Check("telegram", FAIL, f"log shows: {m.group(1).strip()}")
    return Check(
        "telegram",
        WARN,
        "UNVERIFIABLE: TelegramPusher.push swallows errors and returns PushResult(success=False), "
        "the orchestrator discards it, reports.telegram_msg_ids is never written; only exceptions "
        "raised outside push() are logged ([orchestrator] ... telegram failed:) - none found. "
        "Check the Telegram chat by eye.",
    )


# ---------------------------------------------------------------------------
# Check 5: futures vs ETF price scale (heuristic)
# ---------------------------------------------------------------------------

SYMBOL_PATTERNS = {
    "ES": re.compile(r"(?<![A-Za-z0-9])M?ES(?![A-Za-z0-9])|标普"),
    "NQ": re.compile(r"(?<![A-Za-z0-9])M?NQ(?![A-Za-z0-9])|纳指"),
    "GC": re.compile(r"(?<![A-Za-z0-9])M?GC(?![A-Za-z0-9])"),
}
FUTURES_BANDS = {"ES": (3000, 12000), "NQ": (10000, 40000), "GC": (1500, 8000)}
ETF_BAND = (300, 800)
ETF_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(SPY|QQQ)(?![A-Za-z0-9])")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
# Dates / times stripped before number scanning.
DATE_TIME_RE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}|\d{4}/\d{1,2}/\d{1,2}|(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)"
    r"|(?<![\d.])\d{1,2}[-/]\d{1,2}(?![\d.])|\d{8}-\d{6}"
)
# Index names whose number is not a price ("S&P 500", "Nasdaq-100", "Russell 2000").
INDEX_NAME_RE = re.compile(
    r"S&P\s?500|SP\s?500|SPX\s?500|标普\s?500|Nasdaq[- ]?100|纳斯达克\s?100|纳指\s?100|Russell\s?2000|罗素\s?2000",
    re.IGNORECASE,
)
NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
DISTANCE_SUFFIX_RE = re.compile(r"\s*(点|pts?\b|points?\b|ticks?\b|bps?\b|美元/点)", re.IGNORECASE)
OHLC_PREFIX = set("OHLC")
VOLUME_PREFIX_RE = re.compile(r"(?:(?<![A-Za-z])V|Vol|Volume|量|成交量)\s*[=:：]?\s*$", re.IGNORECASE)
LEVEL_LABEL_RE = re.compile(
    r"支撑|阻力|关键位|关键价位|价位|levels?\b|support|resistance|PDH|PDL|ONH|ONL|VAH|VAL|POC|VWAP",
    re.IGNORECASE,
)


def extract_price_numbers(line: str) -> list[float]:
    """Numbers with 3-6 integer digits that look like price levels.

    Excludes: dates, clock times, percentages, numbers glued to letters
    (4H1, 1100PT, 18.5k), signed changes (+32, -250), point distances
    (250 点 / 40 pts), index names (S&P 500, Nasdaq-100). A single O/H/L/C
    prefix (O7822 H7850) is allowed.
    """
    s = DATE_TIME_RE.sub(" ", INDEX_NAME_RE.sub(" ", line))
    out: list[float] = []
    for m in NUM_RE.finditer(s):
        start, end = m.span()
        prev = s[start - 1] if start > 0 else ""
        prev2 = s[start - 2] if start > 1 else ""
        nxt = s[end] if end < len(s) else ""
        if prev and (prev.isdigit() or prev in ".,"):
            continue
        if prev.isascii() and prev.isalpha():
            if not (prev in OHLC_PREFIX and not (prev2.isascii() and prev2.isalnum())):
                continue
        if prev in "+±−" or (prev == "-" and not prev2.isdigit()):
            continue
        if nxt and ((nxt.isascii() and nxt.isalpha()) or nxt in "%％"):
            continue
        if DISTANCE_SUFFIX_RE.match(s, end):
            continue
        if VOLUME_PREFIX_RE.search(s[max(0, start - 12):start]):
            continue
        raw = m.group(0)
        int_digits = len(raw.split(".")[0].replace(",", ""))
        if not 3 <= int_digits <= 6:
            continue
        out.append(float(raw.replace(",", "")))
    return out


def check_futures_not_etf(text: str) -> Check:
    name = "futures_not_etf"
    heading_syms: set[str] = set()
    futures_hits: list[str] = []
    etf_hits: list[str] = []
    sym_lines = 0
    for raw in text.splitlines():
        line_syms = {k for k, rx in SYMBOL_PATTERNS.items() if rx.search(raw)}
        if HEADING_RE.match(raw):
            heading_syms = line_syms
        syms = line_syms | heading_syms
        if not syms:
            continue
        sym_lines += 1
        has_index = bool(syms & {"ES", "NQ"})
        nums = extract_price_numbers(raw)
        # SPY/QQQ named on an ES/NQ line labelled as levels (支撑/阻力/POC/...).
        if nums and has_index and line_syms & {"ES", "NQ"} and LEVEL_LABEL_RE.search(raw):
            for tok in ETF_TOKEN_RE.findall(raw):
                etf_hits.append(f"{tok} token")
        for v in nums:
            in_band = [s for s in syms if FUTURES_BANDS[s][0] <= v <= FUTURES_BANDS[s][1]]
            if in_band:
                futures_hits.append(f"{'/'.join(sorted(in_band))}:{v:g}")
            elif has_index and ETF_BAND[0] <= v <= ETF_BAND[1]:
                etf_hits.append(f"{v:g}")
    note = "heuristic: numbers on ES/NQ/GC lines or under their headings"
    if sym_lines == 0:
        return Check(name, SKIP, f"no ES/MES/NQ/MNQ/GC/MGC lines ({note})")
    if not futures_hits and not etf_hits:
        return Check(name, SKIP, f"{sym_lines} symbol line(s) but no price-like numbers ({note})")
    sample_f = ", ".join(futures_hits[:4])
    sample_e = ", ".join(etf_hits[:6])
    if etf_hits and not futures_hits:
        return Check(name, FAIL, f"only ETF-scale values on ES/NQ lines: {sample_e} - looks like SPY/QQQ, not futures ({note})")
    if etf_hits:
        return Check(
            name,
            WARN,
            f"mixed: {len(futures_hits)} futures-scale (e.g. {sample_f}) and {len(etf_hits)} ETF-scale "
            f"({sample_e}) - read those lines ({note})",
        )
    return Check(name, PASS, f"{len(futures_hits)} futures-scale values, 0 ETF-scale (e.g. {sample_f}) ({note})")


# ---------------------------------------------------------------------------
# Check 6: 亚盘 / 欧盘 sections
# ---------------------------------------------------------------------------

ASIA_RE = re.compile(r"亚盘|亚欧盘|亚洲盘|亚洲时段|Asia session|Asian session", re.IGNORECASE)
EUROPE_RE = re.compile(r"欧盘|欧洲盘|欧洲时段|Europe session|European session|London", re.IGNORECASE)


def check_session_sections(report_type: str, text: str) -> Check:
    name = "session_sections"
    if report_type != "premarket":
        return Check(name, SKIP, f"not expected for {report_type}")
    asia, europe = bool(ASIA_RE.search(text)), bool(EUROPE_RE.search(text))
    if asia and europe:
        return Check(name, PASS, "亚盘 and 欧盘 coverage both present")
    missing = [n for n, ok in (("亚盘/Asia", asia), ("欧盘/Europe", europe)) if not ok]
    return Check(
        name,
        WARN,
        f"missing {', '.join(missing)}; known template gap (premarket.md only asks for a combined "
        "'Breaking news (overnight Asia + Europe)' section), not a run failure",
    )


# ---------------------------------------------------------------------------
# Check 7: language
# ---------------------------------------------------------------------------

CJK_RE = re.compile(r"[一-鿿]")
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def cjk_ratio(text: str) -> float:
    body = FRONTMATTER_RE.sub("", text, count=1)
    chars = [c for c in body if not c.isspace()]
    if not chars:
        return 0.0
    return sum(1 for c in chars if CJK_RE.match(c)) / len(chars)


def check_language(report_type: str, text: str) -> Check:
    ratio = cjk_ratio(text)
    hard = report_type in ("night", "asia", "premarket", "eod")
    msg = f"CJK ratio {ratio:.2f} (threshold {CJK_THRESHOLD})"
    if ratio >= CJK_THRESHOLD:
        return Check("language", PASS, msg)
    if hard:
        return Check("language", FAIL, f"{msg}; {report_type} has a Chinese-output directive")
    return Check("language", WARN, f"{msg}; {report_type} only weakly asks for Chinese")


# ---------------------------------------------------------------------------
# Check 8: required sections (reuse output_validator)
# ---------------------------------------------------------------------------


def load_required_sections(project_root: Path):
    rel = Path("src/daytrader/reports/core/output_validator.py")
    for root in (project_root, Path(__file__).resolve().parents[1]):
        path = root / rel
        if not path.is_file():
            continue
        mod_name = "_verify_report_output_validator"
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
            return module.REQUIRED_SECTIONS, path
        except Exception:
            sys.modules.pop(mod_name, None)
            continue
    return None, None


def check_required_sections(report_type: str, text: str, project_root: Path) -> Check:
    name = "required_sections"
    if report_type == "weekly":
        return Check(name, SKIP, "weekly has no validator entry")
    table, path = load_required_sections(project_root)
    key = VALIDATOR_KEYS[report_type]
    if table is None or key not in table:
        return Check(name, SKIP, "output_validator.REQUIRED_SECTIONS not importable")
    missing = []
    for slot in table[key]:
        alts = [slot] if isinstance(slot, str) else list(slot)
        if not any(a in text for a in alts):
            missing.append(alts[0] if len(alts) == 1 else f"any of {alts}")
    if missing:
        return Check(name, FAIL, f"missing {len(missing)}/{len(table[key])} slots for '{key}': {missing}")
    return Check(name, PASS, f"all {len(table[key])} '{key}' slots present (substring check only)")


# ---------------------------------------------------------------------------
# Check 9: data source (ib vs yfinance fallback) - informational, never FAIL
# ---------------------------------------------------------------------------

YF_MARKER = "数据源：yfinance"
YF_MARKER_RE = re.compile(r"数据源\s*[：:]\s*yfinance", re.IGNORECASE)


def read_db_data_source(report_type: str, date_str: str, project_root: Path) -> str | None:
    """`reports.data_source` of the latest success row (else latest row).

    None when unknown: no DB, no row, NULL value, or an old DB whose
    `reports` table predates the data_source column.
    """
    db = project_root / "data" / "state.db"
    if report_type == "weekly" or not db.exists():
        return None
    try:
        conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(reports)")}
            if "data_source" not in cols:
                return None
            row = conn.execute(
                "SELECT data_source FROM reports WHERE report_type=? AND date=? "
                "ORDER BY (status='success') DESC, id DESC LIMIT 1",
                (report_type, date_str),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    return str(row[0]).strip().lower() or None


def check_data_source(text: str | None, db_source: str | None) -> Check:
    """Which market-data client fed the report. Non-failing by design."""
    name = "data_source"
    text_yf = None if text is None else bool(YF_MARKER_RE.search(text))
    db_yf = None if db_source is None else db_source == "yfinance"
    if text_yf is None and db_yf is None:
        return Check(name, SKIP, "no report text and no state.db data_source (column absent/NULL)")
    if text_yf is None:
        text_part = "report text unavailable"
    elif text_yf:
        text_part = f'report text contains "{YF_MARKER}"'
    else:
        text_part = f'report text has no "{YF_MARKER}" marker'
    db_part = (
        f"state.db data_source={db_source}" if db_source is not None
        else "state.db data_source unknown (column absent/NULL)"
    )
    evidence = f"{text_part}; {db_part}"
    if text_yf is not None and db_yf is not None and text_yf != db_yf:
        return Check(
            name,
            WARN,
            f"mismatch ({YF_MARKER} per {'report text' if text_yf else 'state.db'} only): {evidence}",
        )
    if text_yf or db_yf:
        detail = f"data_source: yfinance ({evidence})"
        if YF_MARKER not in detail:
            detail += f" [{YF_MARKER}]"
        return Check(name, PASS, detail)
    return Check(name, PASS, f"data_source: ib ({evidence})")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def verdict_of(checks: list[Check]) -> str:
    statuses = {c.status for c in checks}
    if FAIL in statuses:
        return FAIL
    if WARN in statuses:
        return WARN
    return PASS


def run_checks(args) -> dict:
    project_root = Path(args.project_root).expanduser().resolve()
    report_type = args.type
    date_str = args.date or default_date(report_type)
    vault = Path(args.vault or config_value(project_root, "vault_path") or DEFAULT_VAULT).expanduser()
    daily_folder = config_value(project_root, "daily_folder") or "Daily"
    weekly_folder = config_value(project_root, "weekly_folder") or "Weekly"

    checks: list[Check] = []
    db_check, db_path, db_success_at = check_state_db_row(report_type, date_str, project_root)
    checks.append(db_check)

    if args.file:
        candidates = [Path(args.file).expanduser()]
    else:
        candidates = locate_output(report_type, date_str, project_root, vault, daily_folder, weekly_folder, db_path)
    file_check, found = check_output_file(candidates)
    checks.append(file_check)

    log_check, log_text = check_latest_run_log(report_type, date_str, project_root, db_success_at)
    checks.append(log_check)
    checks.append(check_telegram(report_type, log_text))

    text: str | None = None
    if found is not None:
        text = found.read_text(encoding="utf-8", errors="replace")
        checks.append(check_futures_not_etf(text))
        checks.append(check_session_sections(report_type, text))
        checks.append(check_language(report_type, text))
        checks.append(check_required_sections(report_type, text, project_root))
    else:
        for n in ("futures_not_etf", "session_sections", "language", "required_sections"):
            checks.append(Check(n, SKIP, "no report file to read"))
    checks.append(check_data_source(text, read_db_data_source(report_type, date_str, project_root)))

    verdict = verdict_of(checks)
    if found is None:
        exit_code = 2
    elif verdict == FAIL or (verdict == WARN and args.strict):
        exit_code = 1
    else:
        exit_code = 0
    return {
        "type": report_type,
        "date": date_str,
        "project_root": str(project_root),
        "vault": str(vault),
        "file": str(found) if found else None,
        "checks": [asdict(c) for c in checks],
        "verdict": verdict,
        "strict": bool(args.strict),
        "exit_code": exit_code,
    }


def render_table(result: dict) -> str:
    lines = [
        f"verify-report  type={result['type']}  date={result['date']}",
        f"project_root={result['project_root']}",
        f"file={result['file'] or '(not found)'}",
        "",
    ]
    w = max(len(c["name"]) for c in result["checks"])
    lines.append(f"{'CHECK'.ljust(w)}  STATUS  DETAIL")
    lines.append(f"{'-' * w}  ------  {'-' * 40}")
    for c in result["checks"]:
        lines.append(f"{c['name'].ljust(w)}  {c['status'].ljust(6)}  {c['detail']}")
    lines.append("")
    suffix = " (report file not located, exit 2)" if result["exit_code"] == 2 else ""
    lines.append(f"VERDICT: {result['verdict']}{suffix}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Verify a DayTrader scheduled report (state.db + vault file + launchd log + content heuristics). "
        "Stdlib only; does not touch TWS."
    )
    p.add_argument("--type", required=True, choices=REPORT_TYPES)
    p.add_argument("--date", help="YYYY-MM-DD report date key (default: ET today for premarket/4h/eod, "
                   "PT today for night/asia, most recent Sunday for weekly)")
    p.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]),
                   help="repo root holding data/state.db and data/logs (production: the nice-varahamihira worktree)")
    p.add_argument("--vault", help="Obsidian vault (default: obsidian.vault_path from config, else ~/Documents/DayTrader Vault)")
    p.add_argument("--file", help="verify this markdown file instead of locating it")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--strict", action="store_true", help="WARN counts as failure for the exit code")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.date:
        try:
            date.fromisoformat(args.date)
        except ValueError:
            print(f"--date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
            return 2
    result = run_checks(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_table(result))
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
