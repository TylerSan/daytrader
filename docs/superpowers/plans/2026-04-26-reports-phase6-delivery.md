# Reports System — Phase 6: Telegram + PDF + Charts Delivery

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute. Steps use checkbox `- [ ]` syntax.

**Goal:** Add **Telegram push + PDF + matplotlib charts** to the premarket report delivery pipeline. After Phase 6: `daytrader reports run --type premarket` writes Obsidian markdown (Phase 2), generates 2 chart PNGs (per spec §5.3), renders a PDF (per §5.4), and pushes a multi-message + photos + PDF Telegram batch (per §5.5) — all in one orchestrator run.

**Architecture:** Strictly additive. New `reports/delivery/{telegram_pusher,pdf_renderer,chart_renderer}.py` modules. Orchestrator gains a delivery step after Obsidian write. New `--no-telegram` CLI flag for testing without sending. `python-telegram-bot` + `weasyprint` added to deps. SecretsConfig already has telegram fields (Phase 1).

**Tech Stack:** Existing + `python-telegram-bot>=21` (already in optional deps), `weasyprint>=60`, `markdown-it-py` (already transitive), matplotlib (already in deps).

**Spec reference:** `docs/superpowers/specs/2026-04-25-reports-system-design.md` §5.3 (charts), §5.4 (PDF), §5.5 (Telegram); user choices "multi-message + PDF 附件双发送" + "no lock-in suppression guardrails".

**Prerequisites:**
- Phases 1, 2, 2.5, 3, 4 complete ✅
- User to provision Telegram bot (token + chat_id) before live acceptance — runbook covers this

**Out of scope** (later phases):
- Other report types (intraday/EOD/weekly/night) → Phase 5
- launchd auto-trigger → Phase 7
- Lock-in suppress_a_section toggle (user declined) → permanently out

---

## File Structure

| File | Action | Why |
|---|---|---|
| `pyproject.toml` | Modify (add weasyprint to deps; promote python-telegram-bot from optional to core) | Phase 6 needs both |
| `src/daytrader/reports/delivery/telegram_pusher.py` | Create | Telegram bot integration |
| `tests/reports/test_telegram_pusher.py` | Create | Mocked bot tests |
| `src/daytrader/reports/delivery/pdf_renderer.py` | Create | markdown → HTML → PDF |
| `tests/reports/test_pdf_renderer.py` | Create | Render to tmp dir |
| `src/daytrader/reports/delivery/chart_renderer.py` | Create | matplotlib tf-stack + context |
| `tests/reports/test_chart_renderer.py` | Create | Verify PNGs created |
| `src/daytrader/reports/core/orchestrator.py` | Modify (add delivery step) | Wire deliveries |
| `tests/reports/test_orchestrator.py` | Modify (mock new deliverers) | Coverage |
| `src/daytrader/cli/reports.py` | Modify (--no-telegram flag) | Allow text-only test |
| `docs/ops/phase2-runbook.md` | Modify | Phase 6 acceptance steps |

---

## Task 1: Add Phase 6 dependencies

**Files:** `pyproject.toml`

- [ ] **Step 1: Promote python-telegram-bot + add weasyprint**

In `pyproject.toml`, modify the `dependencies` list. The current state has `python-telegram-bot` in `[project.optional-dependencies].notifications`. Move it to core deps; ALSO add `weasyprint>=60`.

In core `dependencies` array, add (alphabetical):

```toml
    "python-telegram-bot>=21",
    "weasyprint>=60",
```

Remove `python-telegram-bot>=21.0` from the `notifications` extras section (or leave it as a noop redundancy if simpler).

- [ ] **Step 2: Run uv sync**

Run: `uv sync`
Expected: weasyprint installs without error. May print warnings about missing system libs (cairo, pango, gobject) — these are needed for actual PDF generation. macOS users: `brew install cairo pango libffi`.

- [ ] **Step 3: Verify imports**

Run: `uv run python -c "import telegram; import weasyprint; print(telegram.__version__, weasyprint.__version__)"`
Expected: prints two version strings.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add weasyprint + promote python-telegram-bot for Phase 6"
```

---

## Task 2: ChartRenderer (matplotlib)

**Files:** Create `src/daytrader/reports/delivery/chart_renderer.py` + `tests/reports/test_chart_renderer.py`.

- [ ] **Step 1: Write failing test**

Create `tests/reports/test_chart_renderer.py`:

```python
"""Tests for ChartRenderer (matplotlib tf-stack + context)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.delivery.chart_renderer import (
    ChartRenderer,
    ChartArtifacts,
)


def _bar(t: datetime, c: float) -> OHLCV:
    return OHLCV(timestamp=t, open=c, high=c + 2, low=c - 2, close=c, volume=1000)


def test_render_tf_stack_creates_png(tmp_path):
    """tf-stack chart for one symbol creates a PNG file."""
    bars_by_tf = {
        "1W": [_bar(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240)],
        "1D": [_bar(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246)],
        "4H": [_bar(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
        "1H": [_bar(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
    }
    renderer = ChartRenderer(output_dir=tmp_path)
    path = renderer.render_tf_stack(symbol="MES", bars_by_tf=bars_by_tf, today="2026-04-26")
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 100  # non-trivial


def test_render_full_artifacts_returns_per_symbol_paths(tmp_path):
    """render_all_artifacts returns ChartArtifacts with paths per symbol."""
    bars_by_symbol = {
        "MES": {
            "1W": [_bar(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240)],
            "1D": [_bar(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246)],
            "4H": [], "1H": [],
        },
        "MGC": {
            "1W": [_bar(datetime(2026, 4, 18, tzinfo=timezone.utc), 2340)],
            "1D": [_bar(datetime(2026, 4, 24, tzinfo=timezone.utc), 2342)],
            "4H": [], "1H": [],
        },
    }
    renderer = ChartRenderer(output_dir=tmp_path)
    artifacts = renderer.render_all(
        bars_by_symbol_and_tf=bars_by_symbol,
        today="2026-04-26",
    )
    assert isinstance(artifacts, ChartArtifacts)
    assert "MES" in artifacts.tf_stack_paths
    assert "MGC" in artifacts.tf_stack_paths
    assert artifacts.tf_stack_paths["MES"].exists()


def test_chart_renderer_handles_empty_bars_gracefully(tmp_path):
    """Empty bars list for all TFs → still produces a PNG with placeholder text."""
    bars_by_tf = {tf: [] for tf in ("1W", "1D", "4H", "1H")}
    renderer = ChartRenderer(output_dir=tmp_path)
    path = renderer.render_tf_stack(symbol="MES", bars_by_tf=bars_by_tf, today="2026-04-26")
    assert path.exists()
```

- [ ] **Step 2: Run (red)**

Run: `uv run pytest tests/reports/test_chart_renderer.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/daytrader/reports/delivery/chart_renderer.py`:

```python
"""Chart renderer for premarket reports.

Generates matplotlib PNGs:
- TF stack: 4 stacked subplots (W/D/4H/1H) per symbol; line plot of close prices
- Context: current price + key levels (basic; future enhancement)

Phase 6 keeps it simple — line plots, no candlesticks (mplfinance is heavy
and hairy). When the user opens Obsidian or PDF they see a quick visual
context; precise OHLC reading still happens in MotiveWave / TradingView.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend (no GUI)
import matplotlib.pyplot as plt

from daytrader.core.ib_client import OHLCV


@dataclass(frozen=True)
class ChartArtifacts:
    """All charts rendered for a single report run."""
    tf_stack_paths: dict[str, Path] = field(default_factory=dict)


class ChartRenderer:
    """Generate premarket report chart PNGs."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_tf_stack(
        self,
        symbol: str,
        bars_by_tf: dict[str, list[OHLCV]],
        today: str,
    ) -> Path:
        """Render a 4-row figure (W/D/4H/1H) for one symbol; return PNG path."""
        fig, axes = plt.subplots(
            nrows=4, ncols=1, figsize=(10, 8), sharex=False
        )
        for ax, tf in zip(axes, ("1W", "1D", "4H", "1H")):
            bars = bars_by_tf.get(tf, [])
            if not bars:
                ax.text(0.5, 0.5, f"{tf}: no data",
                        ha="center", va="center", transform=ax.transAxes)
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                xs = list(range(len(bars)))
                ys = [b.close for b in bars]
                ax.plot(xs, ys, linewidth=1.0)
                ax.set_title(f"{tf}", fontsize=9, loc="left")
                ax.tick_params(labelsize=7)
            ax.grid(True, alpha=0.3)

        fig.suptitle(f"{symbol} — TF stack ({today})", fontsize=11)
        fig.tight_layout()

        path = self.output_dir / f"tf-stack-{symbol}-{today}.png"
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return path

    def render_all(
        self,
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
        today: str,
    ) -> ChartArtifacts:
        """Render TF-stack for every symbol; return paths."""
        paths: dict[str, Path] = {}
        for symbol, bars in bars_by_symbol_and_tf.items():
            paths[symbol] = self.render_tf_stack(
                symbol=symbol, bars_by_tf=bars, today=today
            )
        return ChartArtifacts(tf_stack_paths=paths)
```

- [ ] **Step 4: Run (green)**

Run: `uv run pytest tests/reports/test_chart_renderer.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/delivery/chart_renderer.py tests/reports/test_chart_renderer.py
git commit -m "feat(reports): ChartRenderer (matplotlib TF-stack PNGs per symbol)"
```

---

## Task 3: PDFRenderer (markdown → HTML → PDF)

**Files:** Create `src/daytrader/reports/delivery/pdf_renderer.py` + `tests/reports/test_pdf_renderer.py`.

- [ ] **Step 1: Write failing test**

Create `tests/reports/test_pdf_renderer.py`:

```python
"""Tests for PDFRenderer (markdown → HTML → PDF via weasyprint)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.delivery.pdf_renderer import PDFRenderer


def test_render_to_pdf_creates_file(tmp_path):
    """render_to_pdf converts markdown to a non-trivial PDF file."""
    markdown = (
        "# Test Report\n\n"
        "## Section A\n\n"
        "Some body text.\n\n"
        "## Section B\n\n"
        "- bullet 1\n- bullet 2\n"
    )
    renderer = PDFRenderer(output_dir=tmp_path)
    path = renderer.render_to_pdf(
        markdown_text=markdown,
        title="Premarket 2026-04-26",
        filename_stem="2026-04-26-premarket",
    )
    assert path.exists()
    assert path.suffix == ".pdf"
    # PDF magic bytes
    assert path.read_bytes().startswith(b"%PDF")


def test_render_to_pdf_handles_chinese_text(tmp_path):
    """Chinese characters render without crash."""
    markdown = "# 盘前日报\n\n中文测试内容。\n"
    renderer = PDFRenderer(output_dir=tmp_path)
    path = renderer.render_to_pdf(
        markdown_text=markdown,
        title="测试",
        filename_stem="cn-test",
    )
    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")
```

- [ ] **Step 2: Run (red)**

Run: `uv run pytest tests/reports/test_pdf_renderer.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/daytrader/reports/delivery/pdf_renderer.py`:

```python
"""PDF renderer: markdown → HTML → PDF via weasyprint.

Phase 6 keeps it simple: parse markdown with markdown-it-py (or stdlib
fallback), wrap in a minimal HTML template, render to PDF with weasyprint.
Chinese fonts: relies on weasyprint's default font fallback chain
(usually picks a CJK-capable font on macOS).

If weasyprint fails (e.g. missing system libs), we surface the original
exception — PDF is best-effort per spec §5.6 (failure → text-only push,
not pipeline abort).
"""

from __future__ import annotations

from pathlib import Path

import markdown_it
from weasyprint import HTML


_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
body {{ font-family: -apple-system, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 10pt; line-height: 1.4; }}
h1 {{ font-size: 16pt; }}
h2 {{ font-size: 13pt; margin-top: 1em; }}
h3 {{ font-size: 11pt; }}
code, pre {{ font-family: "JetBrains Mono", "Menlo", monospace; font-size: 9pt; background: #f4f4f4; padding: 2px 4px; }}
pre {{ padding: 8px; overflow-x: auto; }}
table {{ border-collapse: collapse; }}
table, th, td {{ border: 1px solid #ccc; padding: 4px 8px; font-size: 9pt; }}
ul, ol {{ padding-left: 20px; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


class PDFRenderer:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._md = markdown_it.MarkdownIt(
            "commonmark", {"breaks": True, "html": False}
        ).enable("table")

    def render_to_pdf(
        self,
        markdown_text: str,
        title: str,
        filename_stem: str,
    ) -> Path:
        body_html = self._md.render(markdown_text)
        full_html = _HTML_TEMPLATE.format(title=title, body=body_html)
        path = self.output_dir / f"{filename_stem}.pdf"
        HTML(string=full_html).write_pdf(str(path))
        return path
```

- [ ] **Step 4: Run (green)**

Run: `uv run pytest tests/reports/test_pdf_renderer.py -v`
Expected: 2 tests pass. If weasyprint complains about missing libs, install them: `brew install cairo pango libffi` and retry.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/delivery/pdf_renderer.py tests/reports/test_pdf_renderer.py
git commit -m "feat(reports): PDFRenderer (markdown → HTML → PDF via weasyprint)"
```

---

## Task 4: TelegramPusher

**Files:** Create `src/daytrader/reports/delivery/telegram_pusher.py` + `tests/reports/test_telegram_pusher.py`.

- [ ] **Step 1: Write failing test**

Create `tests/reports/test_telegram_pusher.py`:

```python
"""Tests for TelegramPusher (mocked bot)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from daytrader.reports.delivery.telegram_pusher import (
    TelegramPusher,
    PushResult,
)


@pytest.fixture
def fake_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=100))
    bot.send_photo = AsyncMock(return_value=MagicMock(message_id=101))
    bot.send_document = AsyncMock(return_value=MagicMock(message_id=102))
    return bot


@pytest.mark.asyncio
async def test_push_messages_splits_long_text(fake_bot, tmp_path):
    """A 5000-char text is split into multiple messages (each < 4096)."""
    long_text = "## Section\n" + ("a" * 4000) + "\n## Other\nbody"
    pusher = TelegramPusher(bot=fake_bot, chat_id="123")
    result = await pusher.push(
        text_messages=[long_text],
        chart_paths=[],
        pdf_path=None,
    )
    assert isinstance(result, PushResult)
    # Should have called send_message at least once
    assert fake_bot.send_message.call_count >= 1
    assert result.success is True


@pytest.mark.asyncio
async def test_push_attaches_charts_and_pdf(fake_bot, tmp_path):
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    pusher = TelegramPusher(bot=fake_bot, chat_id="123")
    await pusher.push(
        text_messages=["short"],
        chart_paths=[chart],
        pdf_path=pdf,
    )
    fake_bot.send_photo.assert_called_once()
    fake_bot.send_document.assert_called_once()


@pytest.mark.asyncio
async def test_push_handles_send_error_gracefully(fake_bot, tmp_path):
    fake_bot.send_message.side_effect = Exception("transient")
    pusher = TelegramPusher(bot=fake_bot, chat_id="123", max_retries=1)
    result = await pusher.push(
        text_messages=["x"],
        chart_paths=[],
        pdf_path=None,
    )
    assert result.success is False
    assert "transient" in (result.error or "").lower()
```

- [ ] **Step 2: Add asyncio marker config**

Verify `pyproject.toml` has `asyncio_mode = "auto"` under `[tool.pytest.ini_options]`. If not, add `pytest_asyncio` is in deps already (Phase 1) — just need the mode. Or use explicit `@pytest.mark.asyncio` decorators (already in tests above).

If pytest collection complains about asyncio:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Run (red)**

Run: `uv run pytest tests/reports/test_telegram_pusher.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement**

Create `src/daytrader/reports/delivery/telegram_pusher.py`:

```python
"""Telegram push integration.

Splits long markdown into ≤4000-char chunks (Telegram's 4096 limit minus
buffer for header/numbering), sends each as a MarkdownV2 message, then
sends each chart as a photo, then the PDF as a document.

Phase 6 keeps message structure simple: text chunks first, then charts,
then PDF — per user choice "multi-message + PDF 双发送" with PDF last.

Uses python-telegram-bot 21+ async Bot interface.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_MAX_MSG_CHARS = 4000  # Telegram limit is 4096; leave ~100 buffer
_MARKDOWN_V2_ESCAPE_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")


@dataclass(frozen=True)
class PushResult:
    success: bool
    message_count: int
    error: str | None = None


def _escape_markdown_v2(text: str) -> str:
    """Escape MarkdownV2 reserved characters."""
    return _MARKDOWN_V2_ESCAPE_RE.sub(r"\\\1", text)


def _split_text(text: str, max_chars: int = _MAX_MSG_CHARS) -> list[str]:
    """Split text at section/paragraph boundaries to fit Telegram message size."""
    if len(text) <= max_chars:
        return [text]
    # Prefer splitting at H2 boundaries
    parts = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) > max_chars:
            if current:
                chunks.append(current)
            current = part
            # If a single section itself is too large, hard-split
            while len(current) > max_chars:
                chunks.append(current[:max_chars])
                current = current[max_chars:]
        else:
            current += part
    if current:
        chunks.append(current)
    return chunks


class TelegramPusher:
    """Push markdown reports + charts + PDF to a Telegram chat."""

    def __init__(self, bot: Any, chat_id: str, max_retries: int = 3) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.max_retries = max_retries

    async def push(
        self,
        text_messages: list[str],
        chart_paths: list[Path],
        pdf_path: Path | None,
    ) -> PushResult:
        """Send everything; return a summary."""
        sent = 0
        try:
            # 1. Text chunks (each entry in text_messages may itself be split)
            for raw in text_messages:
                for chunk in _split_text(raw):
                    safe = _escape_markdown_v2(chunk)
                    await self._send_with_retry(
                        lambda c=safe: self.bot.send_message(
                            chat_id=self.chat_id,
                            text=c,
                            parse_mode="MarkdownV2",
                        )
                    )
                    sent += 1

            # 2. Charts
            for chart in chart_paths:
                await self._send_with_retry(
                    lambda p=chart: self.bot.send_photo(
                        chat_id=self.chat_id,
                        photo=p.read_bytes(),
                    )
                )
                sent += 1

            # 3. PDF
            if pdf_path is not None:
                await self._send_with_retry(
                    lambda p=pdf_path: self.bot.send_document(
                        chat_id=self.chat_id,
                        document=p.read_bytes(),
                        filename=p.name,
                    )
                )
                sent += 1

            return PushResult(success=True, message_count=sent)
        except Exception as exc:
            return PushResult(success=False, message_count=sent, error=str(exc))

    async def _send_with_retry(self, send_callable) -> None:
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                await send_callable()
                return
            except Exception as e:
                last = e
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        if last is not None:
            raise last
```

- [ ] **Step 5: Run (green)**

Run: `uv run pytest tests/reports/test_telegram_pusher.py -v`
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/reports/delivery/telegram_pusher.py tests/reports/test_telegram_pusher.py pyproject.toml
git commit -m "feat(reports): TelegramPusher (multi-message + photos + PDF, MarkdownV2)"
```

---

## Task 5: Orchestrator delivery integration

**Files:** Modify `src/daytrader/reports/core/orchestrator.py` + `tests/reports/test_orchestrator.py`.

- [ ] **Step 1: Add delivery params + step**

In `src/daytrader/reports/core/orchestrator.py`:

(a) Extend `__init__` to accept optional delivery instances:

```python
    def __init__(
        self,
        ...,
        chart_renderer=None,        # ChartRenderer | None
        pdf_renderer=None,          # PDFRenderer | None
        telegram_pusher=None,       # TelegramPusher | None
    ) -> None:
        ...
        self.chart_renderer = chart_renderer
        self.pdf_renderer = pdf_renderer
        self.telegram_pusher = telegram_pusher
```

(b) After Obsidian write succeeds and plan rows are saved, add a delivery block. Place this BEFORE the final `update_report_status` call:

```python
        # Phase 6 delivery: charts + PDF + Telegram (best-effort)
        chart_paths: list[Path] = []
        if self.chart_renderer is not None:
            try:
                # Reuse the bars we already fetched for prompt — but the
                # generator doesn't return them. For Phase 6, regenerate
                # by re-fetching is wasteful. Instead store on outcome.
                # Workaround for v1: ChartRenderer accepts the same
                # bars_by_symbol_and_tf the generator built.
                # Implementation note: if generator doesn't expose bars,
                # skip charts in Phase 6 v1 with a warning.
                if hasattr(outcome, "bars_by_symbol_and_tf"):
                    artifacts = self.chart_renderer.render_all(
                        bars_by_symbol_and_tf=outcome.bars_by_symbol_and_tf,
                        today=date_et,
                    )
                    chart_paths = list(artifacts.tf_stack_paths.values())
            except Exception as e:
                import sys
                print(f"[orchestrator] chart render failed: {e}", file=sys.stderr)

        pdf_path: Path | None = None
        if self.pdf_renderer is not None:
            try:
                pdf_path = self.pdf_renderer.render_to_pdf(
                    markdown_text=outcome.report_text,
                    title=f"Premarket {date_et}",
                    filename_stem=f"{date_et}-premarket",
                )
            except Exception as e:
                import sys
                print(f"[orchestrator] PDF render failed: {e}", file=sys.stderr)

        if self.telegram_pusher is not None:
            try:
                import asyncio
                asyncio.run(self.telegram_pusher.push(
                    text_messages=[outcome.report_text],
                    chart_paths=chart_paths,
                    pdf_path=pdf_path,
                ))
            except Exception as e:
                import sys
                print(f"[orchestrator] telegram push failed: {e}", file=sys.stderr)
```

(c) Modify `PremarketGenerator.generate` to ALSO return `bars_by_symbol_and_tf` on the outcome. Update `GenerationOutcome`:

```python
@dataclass(frozen=True)
class GenerationOutcome:
    report_text: str
    ai_result: AIResult
    validation: ValidationResult
    bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] | None = None
```

And in `generate(...)`, set `bars_by_symbol_and_tf=bars_by_symbol_and_tf` when constructing `GenerationOutcome`.

- [ ] **Step 2: Add tests for delivery integration**

Append to `tests/reports/test_orchestrator.py`:

```python
def test_orchestrator_invokes_pdf_and_telegram_when_provided(tmp_path):
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    from daytrader.core.ib_client import OpenInterest
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    fake_pdf = MagicMock()
    fake_pdf.render_to_pdf.return_value = tmp_path / "out.pdf"
    (tmp_path / "out.pdf").write_bytes(b"%PDF-1.4 fake")

    fake_charts = MagicMock()
    fake_charts.render_all.return_value = MagicMock(tf_stack_paths={"MES": tmp_path / "c.png"})
    (tmp_path / "c.png").write_bytes(b"\x89PNG fake")

    fake_telegram = MagicMock()
    async def _push(*args, **kwargs):
        return MagicMock(success=True, message_count=3)
    fake_telegram.push = _push

    state, orchestrator = _make_orchestrator(
        tmp_path, fake_ib, fake_ai,
    )
    # Re-init with deliverers
    orchestrator.pdf_renderer = fake_pdf
    orchestrator.chart_renderer = fake_charts
    orchestrator.telegram_pusher = fake_telegram

    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert result.success is True
    fake_pdf.render_to_pdf.assert_called_once()
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/reports/test_orchestrator.py -v`
Expected: all tests pass.

- [ ] **Step 4: Project sweep**

Run: `uv run pytest tests/ --ignore=tests/research -q`
Expected: 270+ pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/orchestrator.py src/daytrader/reports/types/premarket.py tests/reports/test_orchestrator.py
git commit -m "feat(reports): Orchestrator delivery (charts + PDF + Telegram, best-effort)"
```

---

## Task 6: CLI flag + bot wiring

**Files:** Modify `src/daytrader/cli/reports.py`.

- [ ] **Step 1: Wire bot init in run_cmd**

In `cli/reports.py` `run_cmd`, near the top of the body (after `shutil.which("claude")` check), conditionally instantiate the deliverers based on a new `--no-telegram` flag.

Add the flag to `run_cmd`:

```python
@reports.command("run")
@click.option("--type", "report_type", required=True, ...)
@click.option(
    "--no-telegram",
    is_flag=True,
    default=False,
    help="Skip Telegram push (still writes Obsidian + PDF + charts)."
)
@click.option(
    "--no-pdf",
    is_flag=True,
    default=False,
    help="Skip PDF rendering (faster runs for testing)."
)
@click.pass_context
def run_cmd(ctx, report_type, no_telegram, no_pdf) -> None:
    ...
```

In the body, after creating the IB connection and AI analyst, add:

```python
        from daytrader.reports.delivery.chart_renderer import ChartRenderer
        from daytrader.reports.delivery.pdf_renderer import PDFRenderer
        from daytrader.reports.delivery.telegram_pusher import TelegramPusher
        from daytrader.reports.core.secrets import load_secrets, SecretsError

        chart_renderer = ChartRenderer(
            output_dir=project_root / "data" / "exports" / "charts",
        )
        pdf_renderer = None
        if not no_pdf:
            try:
                pdf_renderer = PDFRenderer(
                    output_dir=project_root / "data" / "exports" / "pdfs",
                )
            except Exception as e:
                click.echo(f"PDF renderer unavailable: {e}", err=True)

        telegram_pusher = None
        if not no_telegram:
            try:
                secrets = load_secrets(str(project_root / "config" / "secrets.yaml"))
                from telegram import Bot
                bot = Bot(token=secrets.telegram_bot_token)
                telegram_pusher = TelegramPusher(
                    bot=bot,
                    chat_id=secrets.telegram_chat_id,
                )
            except SecretsError as e:
                click.echo(f"Telegram disabled: {e}", err=True)
            except Exception as e:
                click.echo(f"Telegram setup failed: {e}", err=True)
```

Pass these to the Orchestrator constructor:

```python
        orchestrator = Orchestrator(
            ...,
            chart_renderer=chart_renderer,
            pdf_renderer=pdf_renderer,
            telegram_pusher=telegram_pusher,
        )
```

- [ ] **Step 2: Update CLI tests if needed**

Check existing CLI tests still pass; the new flags have defaults so existing test invocations don't need changes.

Run: `uv run pytest tests/cli/test_reports_cli.py -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add src/daytrader/cli/reports.py
git commit -m "feat(reports): CLI --no-telegram / --no-pdf flags + delivery wiring"
```

---

## Task 7: Phase 6 acceptance + runbook update

**Files:** `docs/ops/phase2-runbook.md`, verification.

- [ ] **Step 1: Full test suite pass**

Run: `uv run pytest tests/ --ignore=tests/research -q`
Expected: 270+ pass.

- [ ] **Step 2: Update runbook**

In `docs/ops/phase2-runbook.md`:

(a) Add a new "Telegram bot setup" subsection under Prerequisites:

```markdown
4. **Telegram bot** (Phase 6) — to receive pushes on phone:
   - Open Telegram → search `@BotFather` → `/newbot` → follow prompts
   - Save the bot token, then message your bot with any text
   - Get your chat_id: visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `"chat":{"id": <NUMBER>`
   - Edit `config/secrets.yaml`: fill `telegram.bot_token` and `telegram.chat_id`
```

(b) Update "What this run does NOT yet do" to remove Phase 6 items:

```markdown
## What this run does NOT yet do (Phase 5+ / 7+)

- Other report types (intraday/EOD/weekly/night) → Phase 5
- Automatic launchd schedule → Phase 7
- Anthropic Web Search tool use (uses existing news collector) → Phase 4.5
```

(c) Add "Step 7 (Phase 6): Verify delivery":

```markdown
## Step 7 (Phase 6): Verify delivery

After a successful run with Phase 6 deliverers:

- A PDF appears at `data/exports/pdfs/YYYY-MM-DD-premarket.pdf`
- 3 chart PNGs at `data/exports/charts/tf-stack-{MES,MNQ,MGC}-YYYY-MM-DD.png`
- Telegram chat receives: ~3-5 text messages + 3 photos + 1 PDF document

To run without Telegram (e.g. before bot setup):

```bash
uv run daytrader reports run --type premarket --no-telegram
```

To skip PDF too (fastest dev iteration):

```bash
uv run daytrader reports run --type premarket --no-telegram --no-pdf
```
```

- [ ] **Step 3: Commit + push**

```bash
git add docs/ops/phase2-runbook.md
git commit -m "docs(reports): Phase 6 runbook (Telegram + PDF + charts)"
git push
```

- [ ] **Step 4: Print Phase 6 commit list**

Run: `git log --oneline 5d7e3a0..HEAD`
Expected: 7 Phase 6 commits.

---

## Summary

After Phase 6, `daytrader reports run --type premarket` produces:
- Obsidian markdown (Phase 2)
- 3 chart PNGs per report run (1 TF-stack per symbol)
- 1 PDF (full markdown rendered)
- Telegram batch: ~3-5 text messages + 3 photos + 1 PDF

CLI flags `--no-telegram` and `--no-pdf` allow incremental dev runs.

**Coverage vs spec §3.6 + §5:** Phase 4's 93% → Phase 6's **~98%**. Remaining gaps: launchd auto-trigger (Phase 7), other report types (Phase 5).

**Trade #1 of 30 lock-in is now technically unblocked** — the tooling is operational. User must provision Telegram bot + run a Phase 6 acceptance run before the first real lock-in trade.
