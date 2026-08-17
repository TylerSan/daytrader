# Report Format Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add info-card image generation (via baoyu-image-cards) and Markdown layout improvements to daily pre-market and weekly reports.

**Architecture:** New `CardGenerator` class produces card prompts from `CollectorResult` data and invokes `claude -p` with the `baoyu-image-cards` skill to generate WebP images. `MarkdownRenderer` and `WeeklyPlanGenerator` gain a "data snapshot" section with embedded images and collapsible detail tables. Cron scripts call card generation after AI analysis, with 120s timeout and graceful fallback.

**Tech Stack:** Python 3.12, Click CLI, Claude Code CLI (`claude -p`), baoyu-image-cards skill, Obsidian-compatible Markdown, WebP images.

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/daytrader/premarket/renderers/cards.py` | `CardGenerator` — builds card prompts, invokes claude CLI, returns image paths |
| Create | `tests/premarket/test_cards.py` | Tests for `CardGenerator` |
| Modify | `src/daytrader/premarket/renderers/markdown.py` | Add card image embedding, callout folding, news summary removal |
| Modify | `tests/premarket/test_markdown_renderer.py` | Tests for new render modes (with/without cards) |
| Modify | `src/daytrader/premarket/weekly.py` | Add card image embedding, callout folding in `_render_data` |
| Modify | `tests/premarket/test_weekly.py` | Tests for weekly render with/without cards |
| Modify | `src/daytrader/cli/premarket.py` | Add `pre cards` CLI command |
| Modify | `src/daytrader/cli/weekly_cmd.py` | Add `weekly cards` CLI command |
| Modify | `scripts/premarket-cron.sh` | Add card generation step + image sync to Obsidian |
| Modify | `scripts/weekly-cron.sh` | Add card generation step + image sync to Obsidian |

---

### Task 1: CardGenerator — prompt building

**Files:**
- Create: `src/daytrader/premarket/renderers/cards.py`
- Create: `tests/premarket/test_cards.py`

- [ ] **Step 1: Write the failing test for prompt building**

```python
# tests/premarket/test_cards.py
from datetime import date, datetime, timezone

import pytest

from daytrader.premarket.collectors.base import CollectorResult
from daytrader.premarket.renderers.cards import CardGenerator


@pytest.fixture
def sample_results() -> dict[str, CollectorResult]:
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "ES=F": {
                    "price": 5425.50,
                    "change_pct": 0.35,
                    "prev_close": 5400.0,
                    "day_high": 5440.0,
                    "day_low": 5390.0,
                    "overnight_high": 5435.0,
                    "overnight_low": 5395.0,
                    "overnight_range": 40.0,
                    "asia_high": 5420.0,
                    "asia_low": 5400.0,
                    "europe_high": 5435.0,
                    "europe_low": 5395.0,
                },
                "NQ=F": {
                    "price": 19250.0,
                    "change_pct": 0.45,
                    "prev_close": 19150.0,
                    "day_high": 19300.0,
                    "day_low": 19100.0,
                },
                "^VIX": {"price": 18.5, "change_pct": -2.1, "prev_close": 18.9},
            },
            success=True,
        ),
        "sectors": CollectorResult(
            collector_name="sectors",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "XLK": {"name": "Technology", "change_pct": 1.2},
                "XLF": {"name": "Financials", "change_pct": -0.3},
            },
            success=True,
        ),
        "movers": CollectorResult(
            collector_name="movers",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "movers": [
                    {"symbol": "PLTR", "name": "Palantir", "price": 129.55, "gap_pct": -7.96, "vol_ratio": 2.14},
                    {"symbol": "AMZN", "name": "Amazon", "price": 233.09, "gap_pct": 5.35, "vol_ratio": 1.23},
                ]
            },
            success=True,
        ),
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "prior_day_high": 681.15,
                    "prior_day_low": 673.77,
                    "prior_day_close": 676.01,
                    "approx_vwap_5d": 666.54,
                    "weekly_high": 681.15,
                    "weekly_low": 645.11,
                },
            },
            success=True,
        ),
    }


def test_build_overview_prompt(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    prompt = gen.build_overview_prompt(sample_results, date(2026, 4, 9))
    assert "ES=F" in prompt
    assert "5425.5" in prompt
    assert "VIX" in prompt
    assert "18.5" in prompt


def test_build_sectors_prompt(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    prompt = gen.build_sectors_prompt(sample_results)
    assert "Technology" in prompt
    assert "+1.20%" in prompt
    assert "Financials" in prompt


def test_build_movers_prompt(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    prompt = gen.build_movers_prompt(sample_results)
    assert "PLTR" in prompt
    assert "-7.96%" in prompt
    assert "AMZN" in prompt


def test_build_levels_prompt(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    prompt = gen.build_levels_prompt(sample_results)
    assert "SPY" in prompt
    assert "681.15" in prompt
    assert "VWAP" in prompt or "vwap" in prompt.lower()


def test_build_prompts_returns_empty_on_missing_data():
    gen = CardGenerator(output_dir="/tmp/test-cards")
    empty = {}
    assert gen.build_overview_prompt(empty, date(2026, 4, 9)) == ""
    assert gen.build_sectors_prompt(empty) == ""
    assert gen.build_movers_prompt(empty) == ""
    assert gen.build_levels_prompt(empty) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/test_cards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daytrader.premarket.renderers.cards'`

- [ ] **Step 3: Implement CardGenerator prompt builders**

```python
# src/daytrader/premarket/renderers/cards.py
"""Info-card image generator using baoyu-image-cards skill."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult

_STYLE_INSTRUCTIONS = """\
风格要求：
- 简洁现代风（Apple 风格）
- 白底 + 浅灰卡片背景
- 涨跌色：绿色（涨）/ 红色（跌）/ 灰色（平）
- 字体：无衬线、数字加粗突出
- 宽高比：1:1（方形）
- 语言：中文"""


class CardGenerator:
    def __init__(self, output_dir: str = "data/exports/images") -> None:
        self._output_dir = Path(output_dir)

    def build_overview_prompt(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> str:
        futures = results.get("futures")
        if not futures or not futures.success:
            return ""

        lines = [f"# 市场总览 — {target_date.isoformat()}\n"]
        for sym, data in futures.data.items():
            if not isinstance(data, dict):
                continue
            price = data.get("price", "—")
            change = data.get("change_pct")
            change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
            oh = data.get("overnight_high", "")
            ol = data.get("overnight_low", "")
            overnight = f"  隔夜区间: {ol}–{oh}" if oh and ol else ""
            lines.append(f"- **{sym}**: {price} ({change_str}){overnight}")

        lines.append(f"\n{_STYLE_INSTRUCTIONS}")
        lines.append("\n布局：仪表盘网格，每个品种一个数据块，涨绿跌红，箭头指示方向。")
        return "\n".join(lines)

    def build_sectors_prompt(self, results: dict[str, CollectorResult]) -> str:
        sectors = results.get("sectors")
        if not sectors or not sectors.success:
            return ""

        sorted_sectors = sorted(
            sectors.data.items(),
            key=lambda x: x[1].get("change_pct") or 0,
            reverse=True,
        )

        lines = ["# 板块强弱\n"]
        for sym, data in sorted_sectors:
            name = data.get("name", sym)
            change = data.get("change_pct")
            change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
            lines.append(f"- {sym} ({name}): {change_str}")

        lines.append(f"\n{_STYLE_INSTRUCTIONS}")
        lines.append("\n布局：水平柱状图/热力条，从强到弱渐变色排列。")
        return "\n".join(lines)

    def build_movers_prompt(self, results: dict[str, CollectorResult]) -> str:
        movers = results.get("movers")
        if not movers or not movers.success or not movers.data.get("movers"):
            return ""

        lines = ["# 盘前异动\n"]
        for m in movers.data["movers"]:
            gap_str = f"{m['gap_pct']:+.2f}%"
            lines.append(
                f"- **{m['symbol']}** ({m['name']}): 缺口 {gap_str}, 量比 {m['vol_ratio']}x"
            )

        lines.append(f"\n{_STYLE_INSTRUCTIONS}")
        lines.append("\n布局：列表卡片，大号 gap 百分比突出显示，涨绿跌红。")
        return "\n".join(lines)

    def build_levels_prompt(self, results: dict[str, CollectorResult]) -> str:
        levels = results.get("levels")
        if not levels or not levels.success:
            return ""

        lines = ["# 关键价位\n"]
        for sym, lvls in levels.data.items():
            lines.append(f"\n**{sym}:**")
            for name, price in lvls.items():
                if price is not None:
                    label = name.replace("_", " ").title()
                    lines.append(f"- {label}: {price}")

        lines.append(f"\n{_STYLE_INSTRUCTIONS}")
        lines.append("\n布局：每个品种一行，价格标注在数轴示意上，支撑阻力清晰标注。")
        return "\n".join(lines)

    def image_paths(self, prefix: str, target_date: date) -> dict[str, Path]:
        """Return expected image paths for a given report date."""
        d = target_date.isoformat()
        return {
            "overview": self._output_dir / f"{prefix}-{d}-overview.webp",
            "sectors": self._output_dir / f"{prefix}-{d}-sectors.webp",
            "movers": self._output_dir / f"{prefix}-{d}-movers.webp",
            "levels": self._output_dir / f"{prefix}-{d}-levels.webp",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/test_cards.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd "/Users/tylersan/Projects/Day trading"
git add src/daytrader/premarket/renderers/cards.py tests/premarket/test_cards.py
git commit -m "feat: add CardGenerator with prompt builders for info-card images"
```

---

### Task 2: CardGenerator — image generation via Claude CLI

**Files:**
- Modify: `src/daytrader/premarket/renderers/cards.py`
- Modify: `tests/premarket/test_cards.py`

- [ ] **Step 1: Write the failing test for image generation**

```python
# Append to tests/premarket/test_cards.py
from unittest.mock import patch, MagicMock
import subprocess


def test_generate_card_calls_claude_cli(sample_results, tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Image generated successfully"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        path = gen.generate_card(
            prompt="test prompt",
            output_path=tmp_dir / "test.webp",
        )
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "claude" in call_args[0][0][0] or "claude" in str(call_args)


def test_generate_card_returns_none_on_failure(tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120)):
        path = gen.generate_card(
            prompt="test prompt",
            output_path=tmp_dir / "test.webp",
        )
        assert path is None


def test_generate_all_premarket(sample_results, tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""

    with patch.object(gen, "generate_card", return_value=tmp_dir / "fake.webp") as mock_gen:
        paths = gen.generate_premarket_cards(sample_results, date(2026, 4, 9))
        assert mock_gen.call_count == 4  # overview, sectors, movers, levels


def test_generate_all_premarket_skips_missing_data(tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    empty_results = {}

    with patch.object(gen, "generate_card") as mock_gen:
        paths = gen.generate_premarket_cards(empty_results, date(2026, 4, 9))
        assert mock_gen.call_count == 0
        assert paths == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/test_cards.py::test_generate_card_calls_claude_cli -v`
Expected: FAIL with `AttributeError: 'CardGenerator' object has no attribute 'generate_card'`

- [ ] **Step 3: Implement generate_card and generate_premarket_cards**

Add the following methods to the `CardGenerator` class in `src/daytrader/premarket/renderers/cards.py`:

```python
    # Add these imports at the top of the file:
    # import subprocess
    # import logging
    #
    # _log = logging.getLogger(__name__)
    # _CLAUDE_BIN = "/opt/homebrew/bin/claude"
    # _TIMEOUT = 120

    def generate_card(self, prompt: str, output_path: Path) -> Path | None:
        """Invoke claude CLI with baoyu-image-cards skill to generate a card image.

        Returns the output path on success, None on failure.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        full_prompt = (
            f"/image-cards\n\n"
            f"生成单张信息图卡片，保存为 WebP 格式到 {output_path}\n\n"
            f"{prompt}"
        )
        try:
            result = subprocess.run(
                [_CLAUDE_BIN, "-p", full_prompt, "--output-format", "text"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                cwd=str(Path(__file__).resolve().parents[4]),
            )
            if result.returncode == 0 and output_path.exists():
                return output_path
            _log.warning("Card generation failed (rc=%d): %s", result.returncode, result.stderr[:200])
            return None
        except subprocess.TimeoutExpired:
            _log.warning("Card generation timed out after %ds", _TIMEOUT)
            return None
        except Exception as e:
            _log.warning("Card generation error: %s", e)
            return None

    def generate_premarket_cards(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> list[Path]:
        """Generate all pre-market info cards. Returns list of successfully created paths."""
        paths = self.image_paths("premarket", target_date)
        generated: list[Path] = []

        prompt_builders = [
            ("overview", self.build_overview_prompt, {"results": results, "target_date": target_date}),
            ("sectors", self.build_sectors_prompt, {"results": results}),
            ("movers", self.build_movers_prompt, {"results": results}),
            ("levels", self.build_levels_prompt, {"results": results}),
        ]

        for card_name, builder, kwargs in prompt_builders:
            prompt = builder(**kwargs)
            if not prompt:
                continue
            result = self.generate_card(prompt, paths[card_name])
            if result:
                generated.append(result)

        return generated

    def generate_weekly_cards(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> list[Path]:
        """Generate all weekly info cards. Returns list of successfully created paths."""
        paths = self.image_paths("weekly", target_date)
        generated: list[Path] = []

        # Weekly uses overview, levels, and sectors (3 cards).
        # Note: the spec's "event risk calendar" card is deferred — that data
        # comes from AI analysis text, not CollectorResult, so it can't be
        # generated at this stage. Can be added later as a follow-up.
        prompt_builders = [
            ("overview", self.build_overview_prompt, {"results": results, "target_date": target_date}),
            ("levels", self.build_levels_prompt, {"results": results}),
            ("sectors", self.build_sectors_prompt, {"results": results}),
        ]

        for card_name, builder, kwargs in prompt_builders:
            prompt = builder(**kwargs)
            if not prompt:
                continue
            result = self.generate_card(prompt, paths[card_name])
            if result:
                generated.append(result)

        return generated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/test_cards.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
cd "/Users/tylersan/Projects/Day trading"
git add src/daytrader/premarket/renderers/cards.py tests/premarket/test_cards.py
git commit -m "feat: add CardGenerator image generation via claude CLI"
```

---

### Task 3: MarkdownRenderer — card embedding and callout folding

**Files:**
- Modify: `src/daytrader/premarket/renderers/markdown.py`
- Modify: `tests/premarket/test_markdown_renderer.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/premarket/test_markdown_renderer.py
from pathlib import Path


def test_render_with_card_images_shows_snapshot_section(sample_results):
    renderer = MarkdownRenderer()
    card_images = [
        Path("data/exports/images/premarket-2026-04-09-overview.webp"),
        Path("data/exports/images/premarket-2026-04-09-sectors.webp"),
    ]
    report = renderer.render(
        sample_results,
        date=datetime(2026, 4, 9).date(),
        card_images=card_images,
    )
    assert "数据速览" in report
    assert "premarket-2026-04-09-overview.webp" in report
    assert "premarket-2026-04-09-sectors.webp" in report


def test_render_with_card_images_folds_tables(sample_results):
    renderer = MarkdownRenderer()
    card_images = [Path("data/exports/images/premarket-2026-04-09-overview.webp")]
    report = renderer.render(
        sample_results,
        date=datetime(2026, 4, 9).date(),
        card_images=card_images,
    )
    assert "> [!info]- 详细数据" in report


def test_render_without_card_images_no_folding(sample_results):
    renderer = MarkdownRenderer()
    report = renderer.render(sample_results, date=datetime(2026, 4, 9).date())
    assert "> [!info]-" not in report
    assert "数据速览" not in report


def test_render_news_without_summary(sample_results):
    sample_results["news"] = CollectorResult(
        collector_name="news",
        timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
        data={
            "headlines": [
                {"title": "S&P 500 Surges", "publisher": "Reuters", "summary": "The index rose..."},
            ]
        },
        success=True,
    )
    renderer = MarkdownRenderer()
    report = renderer.render(sample_results, date=datetime(2026, 4, 9).date())
    # Summary quote block should not appear
    assert "> The index rose" not in report
    # Title and publisher should still appear
    assert "S&P 500 Surges" in report
    assert "Reuters" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/test_markdown_renderer.py::test_render_with_card_images_shows_snapshot_section -v`
Expected: FAIL with `TypeError: MarkdownRenderer.render() got an unexpected keyword argument 'card_images'`

- [ ] **Step 3: Implement the changes to MarkdownRenderer**

Modify `src/daytrader/premarket/renderers/markdown.py`:

1. Add `card_images: list[Path] | None = None` parameter to `render()`
2. After the title, insert "数据速览" section if `card_images` is non-empty
3. Wrap data tables in `> [!info]-` callout blocks when `card_images` is non-empty
4. Remove summary quote blocks from news section

The full updated `render` method:

```python
    def render(
        self,
        results: dict[str, CollectorResult],
        date: date,
        ai_analysis: str = "",
        card_images: list[Path] | None = None,
    ) -> str:
        sections: list[str] = []
        now = datetime.now()
        has_cards = bool(card_images)

        # Obsidian-compatible YAML frontmatter
        sections.append("---")
        sections.append(f"date: {date.isoformat()}")
        sections.append(f"generated: {now.strftime('%Y-%m-%dT%H:%M:%S')}")
        sections.append("type: premarket")
        sections.append("tags: [trading, premarket, daily]")
        sections.append("---\n")

        sections.append(f"# 盘前分析报告 — {date.isoformat()}")
        sections.append(f"*生成时间: {now.strftime('%H:%M:%S')} UTC*\n")

        # ═══════════════════════════════════════
        # Data Snapshot (card images)
        # ═══════════════════════════════════════
        if has_cards:
            sections.append("---")
            sections.append("## 数据速览\n")
            for img in card_images:
                label = img.stem.split("-", 4)[-1] if "-" in img.stem else img.stem
                sections.append(f"![{label}](images/{img.name})")
            sections.append("")

        # ═══════════════════════════════════════
        # Section 1: 宏观环境
        # ═══════════════════════════════════════
        sections.append("---")
        sections.append("## 一、宏观环境\n")

        # 1.1 期货总览
        futures = results.get("futures")
        if futures and futures.success:
            table_lines = []
            table_lines.append("### 1.1 指数期货 & VIX\n")
            table_lines.append("| 品种 | 现价 | 涨跌幅 | 前收 | 日高 | 日低 |")
            table_lines.append("|------|------|--------|------|------|------|")
            for sym, data in futures.data.items():
                if not isinstance(data, dict):
                    continue
                price = data.get("price", "—")
                change = data.get("change_pct")
                prev = data.get("prev_close", "—")
                high = data.get("day_high", "—")
                low = data.get("day_low", "—")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
                table_lines.append(f"| {sym} | {price} | {change_str} | {prev} | {high} | {low} |")
            table_lines.append("")

            if has_cards:
                sections.append("> [!info]- 详细数据：指数期货 & VIX")
                for line in table_lines:
                    sections.append(f"> {line}")
            else:
                sections.extend(table_lines)

        # 1.2 隔夜走势 (same pattern: wrap in callout if has_cards)
        # ... (apply same wrapping pattern to overnight and sectors tables)

        # 1.3 板块强弱
        # ... (apply same wrapping pattern)

        # ═══════════════════════════════════════
        # Section 2: 消息面 — no summary quotes
        # ═══════════════════════════════════════
        news = results.get("news")
        if news and news.success and news.data.get("headlines"):
            sections.append("---")
            sections.append("## 二、消息面\n")
            for item in news.data["headlines"]:
                title = item.get("title", "")
                publisher = item.get("publisher", "")
                pub_info = f" — *{publisher}*" if publisher else ""
                sections.append(f"- **{title}**{pub_info}")
            sections.append("")

        # Remaining sections (movers, levels, AI) follow same pattern...
```

The key changes are:
- New `card_images` parameter
- "数据速览" section at top when cards exist
- `_wrap_callout(title, lines)` helper that prefixes each line with `> ` inside a `> [!info]-` block
- News section no longer emits `> {summary}` lines

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/test_markdown_renderer.py -v`
Expected: All tests PASS (both old and new)

- [ ] **Step 5: Commit**

```bash
cd "/Users/tylersan/Projects/Day trading"
git add src/daytrader/premarket/renderers/markdown.py tests/premarket/test_markdown_renderer.py
git commit -m "feat: add card image embedding and callout folding to MarkdownRenderer"
```

---

### Task 4: WeeklyPlanGenerator — card embedding and callout folding

**Files:**
- Modify: `src/daytrader/premarket/weekly.py`
- Modify: `tests/premarket/test_weekly.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/premarket/test_weekly.py
from pathlib import Path


def test_weekly_render_with_cards_shows_snapshot(sample_results):
    """_render_data should include 数据速览 when card_images provided."""
    from daytrader.premarket.weekly import WeeklyPlanGenerator
    from unittest.mock import AsyncMock, MagicMock

    collector = MagicMock()
    gen = WeeklyPlanGenerator(collector=collector, output_dir="/tmp/test")
    card_images = [Path("data/exports/images/weekly-2026-04-09-overview.webp")]
    report = gen._render_data(sample_results, date(2026, 4, 9), card_images=card_images)
    assert "数据速览" in report
    assert "weekly-2026-04-09-overview.webp" in report
    assert "> [!info]- 详细数据" in report


def test_weekly_render_without_cards_no_folding(sample_results):
    from daytrader.premarket.weekly import WeeklyPlanGenerator
    from unittest.mock import MagicMock

    collector = MagicMock()
    gen = WeeklyPlanGenerator(collector=collector, output_dir="/tmp/test")
    report = gen._render_data(sample_results, date(2026, 4, 9))
    assert "> [!info]-" not in report
    assert "数据速览" not in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/test_weekly.py::test_weekly_render_with_cards_shows_snapshot -v`
Expected: FAIL with `TypeError: _render_data() got an unexpected keyword argument 'card_images'`

- [ ] **Step 3: Implement the changes to WeeklyPlanGenerator._render_data**

Modify `src/daytrader/premarket/weekly.py`:

1. Add `card_images: list[Path] | None = None` parameter to `_render_data()`
2. After the title, insert "数据速览" section if `card_images` is non-empty
3. Wrap data tables in `> [!info]-` callout blocks when `card_images` is non-empty

Apply the same pattern as MarkdownRenderer: add the "数据速览" section, wrap each table block in a collapsible callout when `has_cards` is True.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/test_weekly.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd "/Users/tylersan/Projects/Day trading"
git add src/daytrader/premarket/weekly.py tests/premarket/test_weekly.py
git commit -m "feat: add card image embedding and callout folding to WeeklyPlanGenerator"
```

---

### Task 5: CLI commands — `daytrader pre cards` and `daytrader weekly cards`

**Files:**
- Modify: `src/daytrader/cli/premarket.py`
- Modify: `src/daytrader/cli/weekly_cmd.py`

- [ ] **Step 1: Add `pre cards` command**

Add to `src/daytrader/cli/premarket.py`:

```python
@click.command("cards")
@click.option("--date", "target_date", default=None, help="Date in YYYY-MM-DD format")
@click.pass_context
def pre_cards(ctx: click.Context, target_date: str | None) -> None:
    """Generate info-card images for a pre-market report."""
    from datetime import date as date_cls
    from daytrader.premarket.renderers.cards import CardGenerator

    d = date_cls.fromisoformat(target_date) if target_date else date_cls.today()
    checklist = _build_checklist()
    results = asyncio.run(checklist._collector.collect_all())

    gen = CardGenerator()
    paths = gen.generate_premarket_cards(results, d)
    if paths:
        click.echo(f"Generated {len(paths)} card(s):")
        for p in paths:
            click.echo(f"  {p}")
    else:
        click.echo("No cards generated (data may be unavailable or generation failed).")
```

- [ ] **Step 2: Add `weekly cards` command**

Add to `src/daytrader/cli/weekly_cmd.py`:

```python
@click.command("cards")
@click.option("--date", "target_date", default=None, help="Date in YYYY-MM-DD format")
def weekly_cards(target_date: str | None) -> None:
    """Generate info-card images for a weekly report."""
    from datetime import date as date_cls
    from daytrader.premarket.renderers.cards import CardGenerator

    d = date_cls.fromisoformat(target_date) if target_date else date_cls.today()
    generator = _build_weekly_generator()
    results = asyncio.run(generator._collector.collect_all())

    gen = CardGenerator()
    paths = gen.generate_weekly_cards(results, d)
    if paths:
        click.echo(f"Generated {len(paths)} card(s):")
        for p in paths:
            click.echo(f"  {p}")
    else:
        click.echo("No cards generated (data may be unavailable or generation failed).")
```

- [ ] **Step 3: Verify CLI commands are registered**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m daytrader pre cards --help && python -m daytrader weekly cards --help`
Expected: Both show help text with `--date` option

- [ ] **Step 4: Commit**

```bash
cd "/Users/tylersan/Projects/Day trading"
git add src/daytrader/cli/premarket.py src/daytrader/cli/weekly_cmd.py
git commit -m "feat: add 'daytrader pre cards' and 'daytrader weekly cards' CLI commands"
```

---

### Task 6: Cron script integration

**Files:**
- Modify: `scripts/premarket-cron.sh`
- Modify: `scripts/weekly-cron.sh`

- [ ] **Step 1: Update premarket-cron.sh**

Insert between Step 3 (merge) and Step 4 (pine scripts):

```bash
# Step 3.5: Generate info-card images (non-blocking, 120s timeout)
log "Step 3.5: Generating info-card images..."
IMAGES_DIR="$EXPORT_DIR/images"
mkdir -p "$IMAGES_DIR"

if timeout 120 "$DAYTRADER" pre cards --date "$TODAY" >> "$LOG_FILE" 2>&1; then
    log "Info cards generated successfully"

    # Re-render final report with card image references
    # The MarkdownRenderer will detect images in IMAGES_DIR and embed them
    CARD_FLAG="--with-cards"
else
    log "WARNING: Info card generation failed or timed out, continuing without cards"
    CARD_FLAG=""
fi

# Update Obsidian sync to include images
if [ -d "$IMAGES_DIR" ] && [ "$(ls -A "$IMAGES_DIR" 2>/dev/null)" ]; then
    OBSIDIAN_IMAGES="$OBSIDIAN_DAILY/images"
    mkdir -p "$OBSIDIAN_IMAGES"
    cp "$IMAGES_DIR"/premarket-"$TODAY"-*.webp "$OBSIDIAN_IMAGES/" 2>/dev/null || true
    log "Card images synced to Obsidian"
fi
```

- [ ] **Step 2: Update weekly-cron.sh**

Insert after Step 3 (merge), same pattern:

```bash
# Step 3.5: Generate info-card images (non-blocking, 120s timeout)
log "Step 3.5: Generating weekly info-card images..."
IMAGES_DIR="$EXPORT_DIR/images"
mkdir -p "$IMAGES_DIR"

if timeout 120 "$DAYTRADER" weekly cards --date "$TODAY" >> "$LOG_FILE" 2>&1; then
    log "Weekly info cards generated successfully"
else
    log "WARNING: Weekly info card generation failed or timed out, continuing without cards"
fi

# Update Obsidian sync to include images
if [ -d "$IMAGES_DIR" ] && [ "$(ls -A "$IMAGES_DIR" 2>/dev/null)" ]; then
    OBSIDIAN_IMAGES="$OBSIDIAN_WEEKLY/images"
    mkdir -p "$OBSIDIAN_IMAGES"
    cp "$IMAGES_DIR"/weekly-"$TODAY"-*.webp "$OBSIDIAN_IMAGES/" 2>/dev/null || true
    log "Weekly card images synced to Obsidian"
fi
```

- [ ] **Step 3: Verify scripts are syntactically valid**

Run: `bash -n "/Users/tylersan/Projects/Day trading/scripts/premarket-cron.sh" && bash -n "/Users/tylersan/Projects/Day trading/scripts/weekly-cron.sh" && echo "OK"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd "/Users/tylersan/Projects/Day trading"
git add scripts/premarket-cron.sh scripts/weekly-cron.sh
git commit -m "feat: integrate card generation into cron scripts with timeout and Obsidian sync"
```

---

### Task 7: End-to-end test — generate cards for today's report

- [ ] **Step 1: Run card generation for today's premarket data**

Run: `cd "/Users/tylersan/Projects/Day trading" && .venv/bin/daytrader pre cards --date 2026-04-09`
Expected: 4 cards generated in `data/exports/images/`

- [ ] **Step 2: Verify generated images exist**

Run: `ls -la "/Users/tylersan/Projects/Day trading/data/exports/images/premarket-2026-04-09-"*.webp`
Expected: 4 WebP files listed

- [ ] **Step 3: Regenerate today's report with card images embedded**

Run: `cd "/Users/tylersan/Projects/Day trading" && .venv/bin/daytrader pre run`
Verify the output contains "数据速览" section and `![...](images/...)` references.

- [ ] **Step 4: Run full test suite**

Run: `cd "/Users/tylersan/Projects/Day trading" && python -m pytest tests/premarket/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit any final adjustments**

```bash
cd "/Users/tylersan/Projects/Day trading"
git add -A
git commit -m "feat: complete report format optimization with info-card images"
```
