"""Unit + end-to-end tests for scripts/verify_report.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_report.py"


@pytest.fixture(scope="module")
def vr():
    spec = importlib.util.spec_from_file_location("verify_report", str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_report"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- futures_not_etf


def test_futures_scale_passes(vr):
    assert vr.check_futures_not_etf("ES 6850 / NQ 24800").status == "PASS"


def test_etf_scale_fails(vr):
    assert vr.check_futures_not_etf("ES 685 / NQ 520").status == "FAIL"


def test_mixed_scale_warns(vr):
    text = "ES 6850 支撑\nNQ 520 阻力\n"
    assert vr.check_futures_not_etf(text).status == "WARN"


def test_no_symbol_lines_skip(vr):
    assert vr.check_futures_not_etf("VIX 18.5, DXY 104.2, 10Y 4.25%").status == "SKIP"


def test_ignores_labels_dates_percentages(vr):
    line = "NQ 4H1 2026-10-29 涨 350% 收 24800"
    assert vr.extract_price_numbers(line) == [24800.0]
    assert vr.check_futures_not_etf(line).status == "PASS"
    # only noise numbers -> nothing price-like -> SKIP
    assert vr.check_futures_not_etf("ES 4H1 2026-10-29 35%").status == "SKIP"


def test_ignores_times_distances_volumes_and_index_names(vr):
    line = "MES (Micro E-mini S&P 500) 16:00 下影 400 点 V=604 量 750 O7822 H7850"
    assert vr.extract_price_numbers(line) == [7822.0, 7850.0]


def test_heading_context_applies_to_following_lines(vr):
    text = "## 📊 MES — Multi-TF\n**4H：** O685 H690 L680\n## 📰 News\nSPY 685\n"
    assert vr.check_futures_not_etf(text).status == "FAIL"


def test_commas_and_decimals(vr):
    assert vr.extract_price_numbers("ES 7,801.25") == [7801.25]


def test_spy_token_on_level_line_flags(vr):
    res = vr.check_futures_not_etf("ES 支撑 6850 (SPY 685)")
    assert res.status == "WARN"


# --------------------------------------------------------------- session_sections


def test_session_sections_both_pass(vr):
    text = "**亚盘**：窄幅震荡\n**欧盘**：London 开盘走高"
    assert vr.check_session_sections("premarket", text).status == "PASS"


def test_session_sections_missing_warn(vr):
    text = "Breaking news (overnight Asia + Europe): 无"
    res = vr.check_session_sections("premarket", text)
    assert res.status == "WARN"
    assert "template gap" in res.detail


def test_session_sections_eod_skip(vr):
    assert vr.check_session_sections("eod", "anything").status == "SKIP"


# ---------------------------------------------------------------------- language


def test_language_chinese_pass(vr):
    text = "今日 MES 开盘急跌后 V 型反转，收盘接近高点，买盘力量强劲。" * 5
    assert vr.check_language("night", text).status == "PASS"


def test_language_english_night_fails(vr):
    text = "Today MES sold off at the open and reversed into the close. " * 10
    assert vr.check_language("night", text).status == "FAIL"


def test_language_english_intraday_warns(vr):
    text = "Today MES sold off at the open and reversed into the close. " * 10
    assert vr.check_language("intraday-4h-1", text).status == "WARN"


def test_cjk_ratio_ignores_frontmatter(vr):
    text = "---\ntags: [aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa]\n---\n中文中文"
    assert vr.cjk_ratio(text) == 1.0


# ------------------------------------------------------------------ paths / dates


@pytest.mark.parametrize(
    "report_type,expected",
    [
        ("premarket", "Daily/2026-10-29-premarket.md"),
        ("intraday-4h-1", "Daily/2026-10-29-0700PT-4H1.md"),
        ("intraday-4h-2", "Daily/2026-10-29-1100PT-4H2.md"),
        ("eod", "Daily/2026-10-29-eod.md"),
        ("night", "Daily/2026-10-29-1900PT-night.md"),
        ("asia", "Daily/2026-10-29-2300PT-asia.md"),
        ("weekly", "Weekly/weekly-2026-10-29.md"),
    ],
)
def test_expected_output_path(vr, tmp_path, report_type, expected):
    assert vr.expected_output_path(report_type, "2026-10-29", tmp_path) == tmp_path / expected


def test_default_date_et_vs_pt(vr):
    # 2026-10-29 22:30 PT == 2026-10-30 01:30 ET (the ET-date trap)
    now = datetime(2026, 10, 30, 5, 30, tzinfo=timezone.utc)
    assert vr.default_date("premarket", now) == "2026-10-30"
    assert vr.default_date("asia", now) == "2026-10-29"


def test_log_date_key_maps_late_pt_to_next_et_day(vr, tmp_path):
    (tmp_path / "premarket-20261029-213000.log").write_text("x")
    (tmp_path / "premarket-20261030-060000.log").write_text("x")
    (tmp_path / "asia-20261029-230004.log").write_text("x")
    names = [p.name for p in vr.find_run_logs("premarket", "2026-10-30", tmp_path)]
    assert names == ["premarket-20261029-213000.log", "premarket-20261030-060000.log"]
    assert [p.name for p in vr.find_run_logs("asia", "2026-10-29", tmp_path)] == ["asia-20261029-230004.log"]


# -------------------------------------------------------------------- log parsing

PREFLIGHT_FAIL_LOG = """[run_premarket_launchd] start 2026-10-29T06:00:00-07:00
[preflight] ✗ TWS port unreachable at 127.0.0.1:7496
[run_premarket_launchd] PREFLIGHT FAILED — send notification and exit
[notify_preflight] Telegram OK msg_id=6319
"""

SUCCESS_LOG = """[run_asia_launchd] start 2026-10-09T23:00:04-07:00
[run_asia_launchd] preflight ok, invoking reports run --type asia
Error 321, reqId 37: OPEN_INTEREST rejected
Report generated: /tmp/x.md
[run_asia_launchd] reports run exit=0
[run_asia_launchd] end 2026-10-09T23:01:44-07:00
"""

AI_FAIL_LOG = """[run_night_launchd] preflight ok, invoking reports run --type night
Report FAILED: RuntimeError: AI call failed: claude -p exit=1: no stderr
[run_night_launchd] reports run exit=1
"""


def test_classify_logs(vr):
    outcome, reason = vr.classify_log(PREFLIGHT_FAIL_LOG)
    assert outcome == "failed" and "TWS port unreachable" in reason and "msg_id=6319" in reason
    assert vr.classify_log(SUCCESS_LOG) == ("success", "exit=0")
    outcome, reason = vr.classify_log(AI_FAIL_LOG)
    assert outcome == "failed" and "AI call failed" in reason


def test_latest_run_log_fail_and_pass(vr, tmp_path):
    d = tmp_path / "data" / "logs" / "launchd"
    d.mkdir(parents=True)
    (d / "premarket-20261029-060000.log").write_text(PREFLIGHT_FAIL_LOG)
    chk, _ = vr.check_latest_run_log("premarket", "2026-10-29", tmp_path)
    assert chk.status == "FAIL"
    (d / "premarket-20261029-123000.log").write_text(SUCCESS_LOG)
    chk, _ = vr.check_latest_run_log("premarket", "2026-10-29", tmp_path)
    assert chk.status == "PASS"


def test_telegram_checks(vr):
    assert vr.check_telegram("night", "").status == "SKIP"
    assert vr.check_telegram("premarket", SUCCESS_LOG).status == "WARN"
    bad = "[orchestrator] telegram push failed: boom"
    assert vr.check_telegram("premarket", bad).status == "FAIL"


def test_state_db_row(vr, tmp_path):
    import sqlite3

    (tmp_path / "data").mkdir()
    conn = sqlite3.connect(tmp_path / "data" / "state.db")
    conn.execute(
        "CREATE TABLE reports (id INTEGER PRIMARY KEY, report_type TEXT, date TEXT, time_pt TEXT, "
        "time_et TEXT, obsidian_path TEXT, pdf_path TEXT, telegram_msg_ids TEXT, status TEXT, "
        "failure_reason TEXT, duration_seconds REAL, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO reports (report_type, date, time_pt, time_et, obsidian_path, status, "
        "duration_seconds, created_at) VALUES ('asia','2026-10-09','23:00','02:00','/v/a.md',"
        "'success',97.1,'2026-10-10T06:00:07+00:00')"
    )
    conn.commit()
    conn.close()
    chk, path, created = vr.check_state_db_row("asia", "2026-10-09", tmp_path)
    assert chk.status == "PASS" and path == "/v/a.md" and created is not None
    chk, _, _ = vr.check_state_db_row("night", "2026-10-09", tmp_path)
    assert chk.status == "FAIL"
    chk, _, _ = vr.check_state_db_row("weekly", "2026-10-09", tmp_path)
    assert chk.status == "SKIP"


def test_required_sections_uses_validator(vr):
    good = "Lock-in MES MNQ MGC F. 期货结构 📰 D. 数据快照"
    assert vr.check_required_sections("asia", good, PROJECT_ROOT).status == "PASS"
    assert vr.check_required_sections("asia", "nothing", PROJECT_ROOT).status == "FAIL"
    assert vr.check_required_sections("weekly", "", PROJECT_ROOT).status == "SKIP"


# --------------------------------------------------------------------- end-to-end

CHINESE_ASIA = """---
date: 2026-10-09
cadence: asia
---

# Asia D-Archive — 2026-10-09 23:00 PT

## 🔒 Lock-in Metadata
- trades_done: 0/30

## 📊 MES — Multi-TF
**4H：** O7822 H7850 L7783 C7817，下影 34 点，午盘抛售后被买回，低点抬高、高点抬高的阶梯式上行。

## 📊 MNQ — Multi-TF
**1H：** 开盘抛售后在 30982 至 30992 形成双底，反弹收复约一半跌幅，相对弱势。

## 📊 MGC — Multi-TF
亚洲时段强势拉升，4169 涨至 4233.5，随后回落整理。

## F. 期货结构
未平仓量数据不可用，结构判断以价格行为为主。

## 📰 Breaking News
无重大新闻，市场情绪平稳，等待下周数据。

## D. Pattern Archive
开盘急跌后 V 型反转，收盘位于价值区上沿附近。

## 数据快照
数据来源为盘后快照，仅供复盘学习使用。
"""


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60
    )


def test_end_to_end_file_mode(tmp_path):
    md = tmp_path / "2026-10-09-2300PT-asia.md"
    md.write_text(CHINESE_ASIA, encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    res = _run("--type", "asia", "--date", "2026-10-09", "--file", str(md), "--project-root", str(root))
    assert res.returncode == 0, res.stdout + res.stderr
    assert "VERDICT: WARN" in res.stdout

    res = _run(
        "--type", "asia", "--date", "2026-10-09", "--file", str(md), "--project-root", str(root), "--json"
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert set(data) >= {"type", "date", "file", "checks", "verdict", "exit_code"}
    assert data["verdict"] == "WARN" and data["exit_code"] == 0
    by_name = {c["name"]: c["status"] for c in data["checks"]}
    assert len(data["checks"]) == 9
    assert by_name == {
        "state_db_row": "SKIP",
        "output_file": "PASS",
        "latest_run_log": "WARN",
        "telegram": "SKIP",
        "futures_not_etf": "PASS",
        "session_sections": "SKIP",
        "language": "PASS",
        "required_sections": "PASS",
        "data_source": "PASS",
    }

    res = _run(
        "--type", "asia", "--date", "2026-10-09", "--file", str(md), "--project-root", str(root), "--strict"
    )
    assert res.returncode == 1


def test_end_to_end_missing_report_exit_2(tmp_path):
    res = _run(
        "--type", "night", "--date", "2026-10-09", "--project-root", str(tmp_path), "--vault", str(tmp_path / "v")
    )
    assert res.returncode == 2
    assert "VERDICT: FAIL" in res.stdout


def test_end_to_end_english_night_fails(tmp_path):
    md = tmp_path / "n.md"
    md.write_text(CHINESE_ASIA.replace("cadence: asia", "cadence: night") + "\n" + ("English only text. " * 400))
    res = _run("--type", "night", "--date", "2026-10-09", "--file", str(md), "--project-root", str(tmp_path), "--json")
    data = json.loads(res.stdout)
    assert res.returncode == 1
    assert {c["name"]: c["status"] for c in data["checks"]}["language"] == "FAIL"


# -------------------------------------------------------------------- data_source

YF_NOTE = "数据源：yfinance（延迟约 15 分钟；OI 与合约链不可用）"


def _make_reports_db(root, *, with_column: bool, data_source=None, report_type="asia",
                     date_str="2026-10-09", status="success"):
    import sqlite3

    (root / "data").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / "data" / "state.db")
    extra = ", data_source TEXT" if with_column else ""
    conn.execute(
        "CREATE TABLE reports (id INTEGER PRIMARY KEY, report_type TEXT, date TEXT, time_pt TEXT, "
        "time_et TEXT, obsidian_path TEXT, pdf_path TEXT, telegram_msg_ids TEXT, status TEXT, "
        f"failure_reason TEXT, duration_seconds REAL, created_at TEXT{extra})"
    )
    cols = "report_type, date, time_pt, time_et, status, duration_seconds, created_at"
    vals = [report_type, date_str, "23:00", "02:00", status, 90.0, "2026-10-10T06:00:07+00:00"]
    if with_column:
        cols += ", data_source"
        vals.append(data_source)
    conn.execute(f"INSERT INTO reports ({cols}) VALUES ({', '.join('?' * len(vals))})", vals)
    conn.commit()
    conn.close()


def test_data_source_yfinance_text_and_db_pass(vr):
    chk = vr.check_data_source("body\n\n---\n" + YF_NOTE + "\n", "yfinance")
    assert chk.status == "PASS"
    assert chk.detail == (
        'data_source: yfinance (report text contains "数据源：yfinance"; '
        "state.db data_source=yfinance)"
    )


def test_data_source_ib_pass(vr):
    chk = vr.check_data_source("纯 IB 报告", "ib")
    assert chk.status == "PASS"
    assert chk.detail.startswith("data_source: ib")
    assert "state.db data_source=ib" in chk.detail
    # unknown DB value (old schema) + no marker -> ib
    chk = vr.check_data_source("纯 IB 报告", None)
    assert chk.status == "PASS" and chk.detail.startswith("data_source: ib")


def test_data_source_text_only_or_db_only_yfinance_passes_with_marker(vr):
    chk = vr.check_data_source(YF_NOTE, None)
    assert chk.status == "PASS" and "数据源：yfinance" in chk.detail
    chk = vr.check_data_source(None, "yfinance")
    assert chk.status == "PASS" and "数据源：yfinance" in chk.detail


def test_data_source_disagreement_warns(vr):
    assert vr.check_data_source(YF_NOTE, "ib").status == "WARN"
    chk = vr.check_data_source("无标记", "yfinance")
    assert chk.status == "WARN" and "数据源：yfinance" in chk.detail


def test_data_source_nothing_known_skips(vr):
    assert vr.check_data_source(None, None).status == "SKIP"


def test_read_db_data_source_handles_old_schema(vr, tmp_path):
    old = tmp_path / "old"
    _make_reports_db(old, with_column=False)
    assert vr.read_db_data_source("asia", "2026-10-09", old) is None
    new = tmp_path / "new"
    _make_reports_db(new, with_column=True, data_source="yfinance")
    assert vr.read_db_data_source("asia", "2026-10-09", new) == "yfinance"
    assert vr.read_db_data_source("night", "2026-10-09", new) is None
    assert vr.read_db_data_source("asia", "2026-10-09", tmp_path / "missing") is None


def test_end_to_end_yfinance_report_prints_marker(tmp_path):
    md = tmp_path / "2026-10-09-2300PT-asia.md"
    md.write_text(CHINESE_ASIA + "\n---\n" + YF_NOTE + "\n", encoding="utf-8")
    root = tmp_path / "root"
    _make_reports_db(root, with_column=True, data_source="yfinance")
    res = _run("--type", "asia", "--date", "2026-10-09", "--file", str(md), "--project-root", str(root))
    assert res.returncode == 0, res.stdout + res.stderr
    line = next(l for l in res.stdout.splitlines() if l.startswith("data_source"))
    assert "PASS" in line and "数据源：yfinance" in line
