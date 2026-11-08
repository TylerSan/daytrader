"""Static checks for .claude/skills/verify-report/SKILL.md."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL = PROJECT_ROOT / ".claude" / "skills" / "verify-report" / "SKILL.md"

REPORT_TYPES = (
    "premarket",
    "intraday-4h-1",
    "intraday-4h-2",
    "eod",
    "night",
    "asia",
    "weekly",
)
FILENAME_PATTERNS = (
    "{date}-premarket.md",
    "{date}-0700PT-4H1.md",
    "{date}-1100PT-4H2.md",
    "{date}-eod.md",
    "{date}-1900PT-night.md",
    "{date}-2300PT-asia.md",
    "Weekly/weekly-{date}.md",
)


def _split() -> tuple[dict[str, str], str]:
    text = SKILL.read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
    assert m, "SKILL.md must start with a --- YAML frontmatter block"
    front: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        key, sep, val = line.partition(":")
        assert sep, f"unparseable frontmatter line: {line!r}"
        front[key.strip()] = val.strip()
    return front, m.group(2)


def test_skill_file_exists():
    assert SKILL.is_file()


def test_frontmatter_name_and_description():
    front, _ = _split()
    assert front.get("name") == "verify-report"
    desc = front.get("description", "")
    assert desc
    assert len(desc) < 1024
    assert "\n" not in desc


def test_frontmatter_parses_with_yaml_if_available():
    yaml = pytest.importorskip("yaml")
    text = SKILL.read_text(encoding="utf-8")
    fm = text.split("---\n", 2)[1]
    data = yaml.safe_load(fm)
    assert data["name"] == "verify-report"
    assert isinstance(data["description"], str) and data["description"]


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_body_mentions_every_type(report_type):
    _, body = _split()
    assert report_type in body


@pytest.mark.parametrize(
    "command",
    ["reports dry-run", "scripts/verify_report.py", "scripts/diagnose_preflight.py"],
)
def test_body_mentions_commands(command):
    _, body = _split()
    assert command in body


@pytest.mark.parametrize("pattern", FILENAME_PATTERNS)
def test_body_mentions_output_filenames(pattern):
    _, body = _split()
    assert pattern in body


@pytest.mark.parametrize("signature", ["PREFLIGHT FAILED", "TWS port unreachable", "AI call failed"])
def test_body_mentions_failure_signatures(signature):
    _, body = _split()
    assert signature in body


@pytest.mark.parametrize(
    "signature",
    [
        "PREFLIGHT FAILED (TWS only) — degrading to --source yfinance",
        "[reports] data source: yfinance (IB unreachable)",
        "[reports] data source: yfinance (--source yfinance)",
        "数据源：yfinance（延迟约 15 分钟；OI 与合约链不可用）",
        "[yfinance 降级]",
        "SUCCESS_DEGRADED_YFINANCE",
    ],
)
def test_body_mentions_yfinance_degrade_signatures(signature):
    _, body = _split()
    assert signature in body
