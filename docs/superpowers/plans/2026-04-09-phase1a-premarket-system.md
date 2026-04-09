# Phase 1a: Pre-Market & Weekly Preparation System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily pre-market analysis system that auto-generates structured reports (markdown + push notifications + Pine Script) and a weekly planning system, giving the trader a complete preparation workflow before each session.

**Architecture:** Plugin-style data collectors fetch market data via `yfinance` and web APIs, analyzers process it into structured insights, renderers output to multiple formats. The existing notification system handles push delivery.

**Tech Stack:** yfinance, existing core (models, db, config, notifications, registry), click CLI, Jinja2 (report templates)

---

### Task 1: Add Dependencies & Collector Interface

**Files:**
- Modify: `pyproject.toml` (add yfinance, jinja2)
- Create: `src/daytrader/premarket/__init__.py`
- Create: `src/daytrader/premarket/collectors/__init__.py`
- Create: `src/daytrader/premarket/collectors/base.py`
- Test: `tests/premarket/__init__.py`
- Test: `tests/premarket/test_collectors.py`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Add `yfinance>=0.2.36` and `jinja2>=3.1` to the `dependencies` list in `pyproject.toml`, then run:

```bash
uv pip install -e ".[dev,notifications]"
```

- [ ] **Step 2: Write failing tests for collector interface**

```python
# tests/premarket/__init__.py
# (empty)
```

```python
# tests/premarket/test_collectors.py
from datetime import datetime, timezone

import pytest

from daytrader.premarket.collectors.base import (
    Collector,
    CollectorResult,
    MarketDataCollector,
)


class FakeCollector(Collector):
    @property
    def name(self) -> str:
        return "fake"

    async def collect(self) -> CollectorResult:
        return CollectorResult(
            collector_name="fake",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={"key": "value"},
            success=True,
        )


def test_collector_result_creation():
    result = CollectorResult(
        collector_name="test",
        timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
        data={"futures": {"ES": 5400}},
        success=True,
    )
    assert result.success is True
    assert result.data["futures"]["ES"] == 5400


@pytest.mark.asyncio
async def test_fake_collector():
    c = FakeCollector()
    result = await c.collect()
    assert result.success is True
    assert result.collector_name == "fake"


@pytest.mark.asyncio
async def test_market_data_collector_runs_all():
    mdc = MarketDataCollector()
    fake = FakeCollector()
    mdc.register(fake)
    results = await mdc.collect_all()
    assert "fake" in results
    assert results["fake"].success is True
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/premarket/test_collectors.py -v
```

- [ ] **Step 4: Implement collector base**

```python
# src/daytrader/premarket/__init__.py
# (empty)
```

```python
# src/daytrader/premarket/collectors/__init__.py
# (empty)
```

```python
# src/daytrader/premarket/collectors/base.py
"""Base classes for pre-market data collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class CollectorResult(BaseModel):
    collector_name: str
    timestamp: datetime
    data: dict
    success: bool
    error: str = ""


class Collector(ABC):
    """Interface for data collector plugins."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def collect(self) -> CollectorResult: ...


class MarketDataCollector:
    """Orchestrates multiple collectors and gathers all data."""

    def __init__(self) -> None:
        self._collectors: dict[str, Collector] = {}

    def register(self, collector: Collector) -> None:
        self._collectors[collector.name] = collector

    async def collect_all(self) -> dict[str, CollectorResult]:
        results: dict[str, CollectorResult] = {}
        for name, collector in self._collectors.items():
            try:
                results[name] = await collector.collect()
            except Exception as e:
                results[name] = CollectorResult(
                    collector_name=name,
                    timestamp=datetime.now(),
                    data={},
                    success=False,
                    error=str(e),
                )
        return results
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/premarket/test_collectors.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/daytrader/premarket/ tests/premarket/
git commit -m "feat: add premarket collector interface and orchestrator"
```

---

### Task 2: Futures & VIX Collector

**Files:**
- Create: `src/daytrader/premarket/collectors/futures.py`
- Test: `tests/premarket/test_futures_collector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/premarket/test_futures_collector.py
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

from daytrader.premarket.collectors.futures import FuturesCollector


@pytest.fixture
def mock_yf_ticker():
    """Mock yfinance.Ticker to avoid real API calls in tests."""
    ticker = MagicMock()
    ticker.info = {"regularMarketPrice": 5425.50, "regularMarketChangePercent": 0.35}
    ticker.fast_info = {"last_price": 5425.50}
    return ticker


@pytest.mark.asyncio
async def test_futures_collector_returns_data():
    collector = FuturesCollector(symbols=["ES=F", "NQ=F", "^VIX"])
    with patch("daytrader.premarket.collectors.futures.yf.Ticker") as mock_ticker_cls:
        mock_t = MagicMock()
        mock_t.info = {
            "regularMarketPrice": 5425.50,
            "regularMarketChangePercent": 0.35,
            "regularMarketPreviousClose": 5400.0,
        }
        mock_ticker_cls.return_value = mock_t

        result = await collector.collect()

    assert result.success is True
    assert result.collector_name == "futures"
    assert "ES=F" in result.data
    assert result.data["ES=F"]["price"] == 5425.50


@pytest.mark.asyncio
async def test_futures_collector_handles_error():
    collector = FuturesCollector(symbols=["ES=F"])
    with patch("daytrader.premarket.collectors.futures.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.side_effect = Exception("Network error")
        result = await collector.collect()

    assert result.success is False
    assert "Network error" in result.error
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/premarket/test_futures_collector.py -v
```

- [ ] **Step 3: Implement futures collector**

```python
# src/daytrader/premarket/collectors/futures.py
"""Futures, index, and VIX data collector using yfinance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult


class FuturesCollector(Collector):
    """Collects futures (ES, NQ) and VIX data."""

    DEFAULT_SYMBOLS = ["ES=F", "NQ=F", "YM=F", "^VIX"]

    def __init__(self, symbols: list[str] | None = None) -> None:
        self._symbols = symbols or self.DEFAULT_SYMBOLS

    @property
    def name(self) -> str:
        return "futures"

    async def collect(self) -> CollectorResult:
        try:
            data = await asyncio.to_thread(self._fetch_all)
            return CollectorResult(
                collector_name=self.name,
                timestamp=datetime.now(timezone.utc),
                data=data,
                success=True,
            )
        except Exception as e:
            return CollectorResult(
                collector_name=self.name,
                timestamp=datetime.now(timezone.utc),
                data={},
                success=False,
                error=str(e),
            )

    def _fetch_all(self) -> dict:
        result = {}
        for symbol in self._symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                result[symbol] = {
                    "price": info.get("regularMarketPrice"),
                    "change_pct": info.get("regularMarketChangePercent"),
                    "prev_close": info.get("regularMarketPreviousClose"),
                }
            except Exception:
                result[symbol] = {"price": None, "change_pct": None, "prev_close": None}
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/premarket/test_futures_collector.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/premarket/collectors/futures.py tests/premarket/test_futures_collector.py
git commit -m "feat: add futures & VIX collector (yfinance)"
```

---

### Task 3: Sector & Key Levels Collector

**Files:**
- Create: `src/daytrader/premarket/collectors/sectors.py`
- Create: `src/daytrader/premarket/collectors/levels.py`
- Test: `tests/premarket/test_sectors_collector.py`
- Test: `tests/premarket/test_levels_collector.py`

- [ ] **Step 1: Write failing tests for sector collector**

```python
# tests/premarket/test_sectors_collector.py
from unittest.mock import patch, MagicMock
import pytest

from daytrader.premarket.collectors.sectors import SectorCollector


@pytest.mark.asyncio
async def test_sector_collector_returns_data():
    collector = SectorCollector()
    with patch("daytrader.premarket.collectors.sectors.yf.Ticker") as mock_cls:
        mock_t = MagicMock()
        mock_t.info = {
            "regularMarketChangePercent": 1.5,
            "shortName": "Technology Select Sector",
        }
        mock_cls.return_value = mock_t
        result = await collector.collect()

    assert result.success is True
    assert result.collector_name == "sectors"
    assert len(result.data) > 0


@pytest.mark.asyncio
async def test_sector_collector_handles_error():
    collector = SectorCollector()
    with patch("daytrader.premarket.collectors.sectors.yf.Ticker") as mock_cls:
        mock_cls.side_effect = Exception("API error")
        result = await collector.collect()

    assert result.success is False
```

- [ ] **Step 2: Write failing tests for levels collector**

```python
# tests/premarket/test_levels_collector.py
from unittest.mock import patch, MagicMock
from decimal import Decimal
import pandas as pd
import pytest

from daytrader.premarket.collectors.levels import LevelsCollector


@pytest.mark.asyncio
async def test_levels_collector_returns_key_levels():
    collector = LevelsCollector(symbols=["SPY"])
    with patch("daytrader.premarket.collectors.levels.yf.Ticker") as mock_cls:
        mock_t = MagicMock()
        mock_t.info = {
            "regularMarketDayHigh": 542.0,
            "regularMarketDayLow": 538.0,
            "regularMarketPreviousClose": 540.0,
            "regularMarketOpen": 540.5,
        }
        # Mock history for volume profile approximation
        mock_t.history.return_value = pd.DataFrame({
            "High": [542.0, 541.5],
            "Low": [538.0, 538.5],
            "Close": [540.0, 541.0],
            "Volume": [1000000, 1200000],
        })
        mock_cls.return_value = mock_t

        result = await collector.collect()

    assert result.success is True
    assert "SPY" in result.data
    levels = result.data["SPY"]
    assert "prior_day_high" in levels
    assert "prior_day_low" in levels
    assert "prior_day_close" in levels
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/premarket/test_sectors_collector.py tests/premarket/test_levels_collector.py -v
```

- [ ] **Step 4: Implement sector collector**

```python
# src/daytrader/premarket/collectors/sectors.py
"""Sector performance collector using yfinance sector ETFs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult

# Major sector ETFs
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLC": "Communication",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLB": "Materials",
}


class SectorCollector(Collector):
    def __init__(self, etfs: dict[str, str] | None = None) -> None:
        self._etfs = etfs or SECTOR_ETFS

    @property
    def name(self) -> str:
        return "sectors"

    async def collect(self) -> CollectorResult:
        try:
            data = await asyncio.to_thread(self._fetch)
            return CollectorResult(
                collector_name=self.name,
                timestamp=datetime.now(timezone.utc),
                data=data,
                success=True,
            )
        except Exception as e:
            return CollectorResult(
                collector_name=self.name,
                timestamp=datetime.now(timezone.utc),
                data={},
                success=False,
                error=str(e),
            )

    def _fetch(self) -> dict:
        sectors = {}
        for symbol, sector_name in self._etfs.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                sectors[symbol] = {
                    "name": sector_name,
                    "change_pct": info.get("regularMarketChangePercent"),
                }
            except Exception:
                sectors[symbol] = {"name": sector_name, "change_pct": None}
        return sectors
```

- [ ] **Step 5: Implement levels collector**

```python
# src/daytrader/premarket/collectors/levels.py
"""Key price levels collector using yfinance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult


class LevelsCollector(Collector):
    DEFAULT_SYMBOLS = ["SPY", "QQQ", "IWM"]

    def __init__(self, symbols: list[str] | None = None) -> None:
        self._symbols = symbols or self.DEFAULT_SYMBOLS

    @property
    def name(self) -> str:
        return "levels"

    async def collect(self) -> CollectorResult:
        try:
            data = await asyncio.to_thread(self._fetch)
            return CollectorResult(
                collector_name=self.name,
                timestamp=datetime.now(timezone.utc),
                data=data,
                success=True,
            )
        except Exception as e:
            return CollectorResult(
                collector_name=self.name,
                timestamp=datetime.now(timezone.utc),
                data={},
                success=False,
                error=str(e),
            )

    def _fetch(self) -> dict:
        result = {}
        for symbol in self._symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                hist = ticker.history(period="5d")

                levels = {
                    "prior_day_high": info.get("regularMarketDayHigh"),
                    "prior_day_low": info.get("regularMarketDayLow"),
                    "prior_day_close": info.get("regularMarketPreviousClose"),
                    "premarket_price": info.get("preMarketPrice"),
                }

                # Approximate VWAP/volume-weighted levels from recent history
                if not hist.empty and "Volume" in hist.columns:
                    vol = hist["Volume"]
                    close = hist["Close"]
                    if vol.sum() > 0:
                        vwap = (close * vol).sum() / vol.sum()
                        levels["approx_vwap_5d"] = round(float(vwap), 2)

                    # Weekly high/low from 5d history
                    levels["weekly_high"] = round(float(hist["High"].max()), 2)
                    levels["weekly_low"] = round(float(hist["Low"].min()), 2)

                result[symbol] = levels
            except Exception:
                result[symbol] = {}
        return result
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/premarket/test_sectors_collector.py tests/premarket/test_levels_collector.py -v
```

Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add src/daytrader/premarket/collectors/sectors.py src/daytrader/premarket/collectors/levels.py tests/premarket/test_sectors_collector.py tests/premarket/test_levels_collector.py
git commit -m "feat: add sector and key levels collectors (yfinance)"
```

---

### Task 4: Markdown Report Renderer

**Files:**
- Create: `src/daytrader/premarket/renderers/__init__.py`
- Create: `src/daytrader/premarket/renderers/markdown.py`
- Test: `tests/premarket/test_markdown_renderer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/premarket/test_markdown_renderer.py
from datetime import datetime, timezone

import pytest

from daytrader.premarket.collectors.base import CollectorResult
from daytrader.premarket.renderers.markdown import MarkdownRenderer


@pytest.fixture
def sample_results() -> dict[str, CollectorResult]:
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "ES=F": {"price": 5425.50, "change_pct": 0.35, "prev_close": 5400.0},
                "NQ=F": {"price": 19250.0, "change_pct": 0.45, "prev_close": 19150.0},
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
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "prior_day_high": 542.0,
                    "prior_day_low": 538.0,
                    "prior_day_close": 540.0,
                    "weekly_high": 543.0,
                    "weekly_low": 536.0,
                },
            },
            success=True,
        ),
    }


def test_markdown_renderer_produces_report(sample_results):
    renderer = MarkdownRenderer()
    report = renderer.render(sample_results, date=datetime(2026, 4, 9).date())
    assert "# Pre-Market Report" in report
    assert "2026-04-09" in report
    assert "ES=F" in report
    assert "5425.5" in report
    assert "VIX" in report or "^VIX" in report
    assert "Technology" in report
    assert "SPY" in report


def test_markdown_renderer_saves_to_file(sample_results, tmp_dir):
    renderer = MarkdownRenderer(output_dir=str(tmp_dir))
    path = renderer.render_and_save(sample_results, date=datetime(2026, 4, 9).date())
    assert path.exists()
    content = path.read_text()
    assert "Pre-Market Report" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/premarket/test_markdown_renderer.py -v
```

- [ ] **Step 3: Implement markdown renderer**

```python
# src/daytrader/premarket/renderers/__init__.py
# (empty)
```

```python
# src/daytrader/premarket/renderers/markdown.py
"""Markdown report renderer for pre-market analysis."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult


class MarkdownRenderer:
    def __init__(self, output_dir: str = "data/exports") -> None:
        self._output_dir = Path(output_dir)

    def render(self, results: dict[str, CollectorResult], date: date) -> str:
        sections = [
            f"# Pre-Market Report — {date.isoformat()}\n",
            f"*Generated at {datetime.now().strftime('%H:%M:%S')} UTC*\n",
        ]

        # Futures & VIX
        futures = results.get("futures")
        if futures and futures.success:
            sections.append("## Futures & VIX\n")
            sections.append("| Symbol | Price | Change % | Prev Close |")
            sections.append("|--------|-------|----------|------------|")
            for sym, data in futures.data.items():
                price = data.get("price", "N/A")
                change = data.get("change_pct", "N/A")
                prev = data.get("prev_close", "N/A")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else str(change)
                sections.append(f"| {sym} | {price} | {change_str} | {prev} |")
            sections.append("")

        # Sector Performance
        sectors = results.get("sectors")
        if sectors and sectors.success:
            sections.append("## Sector Performance\n")
            sorted_sectors = sorted(
                sectors.data.items(),
                key=lambda x: x[1].get("change_pct") or 0,
                reverse=True,
            )
            sections.append("| ETF | Sector | Change % |")
            sections.append("|-----|--------|----------|")
            for sym, data in sorted_sectors:
                name = data.get("name", sym)
                change = data.get("change_pct")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "N/A"
                sections.append(f"| {sym} | {name} | {change_str} |")
            sections.append("")

        # Key Levels
        levels = results.get("levels")
        if levels and levels.success:
            sections.append("## Key Levels\n")
            for sym, lvls in levels.data.items():
                sections.append(f"### {sym}\n")
                sections.append("| Level | Price |")
                sections.append("|-------|-------|")
                for level_name, price in lvls.items():
                    if price is not None:
                        label = level_name.replace("_", " ").title()
                        sections.append(f"| {label} | {price} |")
                sections.append("")

        return "\n".join(sections)

    def render_and_save(
        self, results: dict[str, CollectorResult], date: date
    ) -> Path:
        content = self.render(results, date)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"premarket-{date.isoformat()}.md"
        path.write_text(content)
        return path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/premarket/test_markdown_renderer.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/premarket/renderers/ tests/premarket/test_markdown_renderer.py
git commit -m "feat: add markdown pre-market report renderer"
```

---

### Task 5: Pine Script Renderer

**Files:**
- Create: `src/daytrader/premarket/renderers/pinescript.py`
- Test: `tests/premarket/test_pinescript_renderer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/premarket/test_pinescript_renderer.py
from datetime import datetime, timezone

import pytest

from daytrader.premarket.collectors.base import CollectorResult
from daytrader.premarket.renderers.pinescript import PineScriptRenderer


@pytest.fixture
def levels_result() -> dict[str, CollectorResult]:
    return {
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "prior_day_high": 542.0,
                    "prior_day_low": 538.0,
                    "prior_day_close": 540.0,
                },
            },
            success=True,
        ),
    }


def test_pinescript_generates_valid_code(levels_result):
    renderer = PineScriptRenderer()
    code = renderer.render(levels_result, symbol="SPY")
    assert "//@version=5" in code
    assert "indicator" in code
    assert "542.0" in code
    assert "538.0" in code
    assert "540.0" in code
    assert "hline" in code or "line.new" in code


def test_pinescript_saves_to_file(levels_result, tmp_dir):
    renderer = PineScriptRenderer(output_dir=str(tmp_dir))
    path = renderer.render_and_save(levels_result, symbol="SPY")
    assert path.exists()
    assert path.suffix == ".pine"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/premarket/test_pinescript_renderer.py -v
```

- [ ] **Step 3: Implement Pine Script renderer**

```python
# src/daytrader/premarket/renderers/pinescript.py
"""Pine Script generator for TradingView key level annotations."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult

_LEVEL_COLORS = {
    "prior_day_high": "color.red",
    "prior_day_low": "color.green",
    "prior_day_close": "color.gray",
    "premarket_price": "color.orange",
    "weekly_high": "color.new(#ff0000, 50)",
    "weekly_low": "color.new(#00ff00, 50)",
    "approx_vwap_5d": "color.purple",
}

_LEVEL_STYLES = {
    "prior_day_high": "hline.style_solid",
    "prior_day_low": "hline.style_solid",
    "prior_day_close": "hline.style_dashed",
    "premarket_price": "hline.style_dotted",
    "weekly_high": "hline.style_dashed",
    "weekly_low": "hline.style_dashed",
    "approx_vwap_5d": "hline.style_dotted",
}


class PineScriptRenderer:
    def __init__(self, output_dir: str = "scripts") -> None:
        self._output_dir = Path(output_dir)

    def render(self, results: dict[str, CollectorResult], symbol: str) -> str:
        levels_data = results.get("levels")
        if not levels_data or not levels_data.success or symbol not in levels_data.data:
            return ""

        levels = levels_data.data[symbol]
        today = date.today().isoformat()

        lines = [
            "//@version=5",
            f'indicator("DayTrader Levels — {symbol} ({today})", overlay=true)',
            "",
        ]

        for level_name, price in levels.items():
            if price is None:
                continue
            label = level_name.replace("_", " ").upper()
            color = _LEVEL_COLORS.get(level_name, "color.gray")
            style = _LEVEL_STYLES.get(level_name, "hline.style_dashed")
            lines.append(
                f'hline({price}, "{label}", {color}, {style}, 1)'
            )

        lines.append("")
        return "\n".join(lines)

    def render_and_save(
        self, results: dict[str, CollectorResult], symbol: str
    ) -> Path:
        code = self.render(results, symbol=symbol)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        path = self._output_dir / f"levels-{symbol}-{today}.pine"
        path.write_text(code)
        return path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/premarket/test_pinescript_renderer.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/premarket/renderers/pinescript.py tests/premarket/test_pinescript_renderer.py
git commit -m "feat: add Pine Script renderer for TradingView key levels"
```

---

### Task 6: Checklist Engine & Pre-Market CLI

**Files:**
- Create: `src/daytrader/premarket/checklist.py`
- Modify: `src/daytrader/cli/premarket.py` (new file, wire into main.py)
- Modify: `src/daytrader/cli/main.py` (import premarket commands)
- Test: `tests/premarket/test_checklist.py`

- [ ] **Step 1: Write failing tests for checklist engine**

```python
# tests/premarket/test_checklist.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from daytrader.premarket.checklist import PremarketChecklist
from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector
from daytrader.premarket.renderers.markdown import MarkdownRenderer


@pytest.fixture
def mock_results():
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={"ES=F": {"price": 5425.50, "change_pct": 0.35, "prev_close": 5400.0}},
            success=True,
        ),
    }


@pytest.mark.asyncio
async def test_checklist_run_collects_and_renders(tmp_dir, mock_results):
    mock_mdc = AsyncMock(spec=MarketDataCollector)
    mock_mdc.collect_all.return_value = mock_results

    checklist = PremarketChecklist(
        collector=mock_mdc,
        renderers=[MarkdownRenderer(output_dir=str(tmp_dir))],
    )

    report = await checklist.run()
    assert report is not None
    assert "ES=F" in report
    mock_mdc.collect_all.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/premarket/test_checklist.py -v
```

- [ ] **Step 3: Implement checklist engine**

```python
# src/daytrader/premarket/checklist.py
"""Pre-market checklist engine — orchestrates collection and rendering."""

from __future__ import annotations

from datetime import date, datetime

from daytrader.premarket.collectors.base import MarketDataCollector
from daytrader.premarket.renderers.markdown import MarkdownRenderer


class PremarketChecklist:
    """Runs the full pre-market analysis workflow."""

    def __init__(
        self,
        collector: MarketDataCollector,
        renderers: list | None = None,
    ) -> None:
        self._collector = collector
        self._renderers = renderers or []

    async def run(self, target_date: date | None = None) -> str:
        target_date = target_date or date.today()

        # Phase 1: Collect all data
        results = await self._collector.collect_all()

        # Phase 2: Render report
        report = ""
        for renderer in self._renderers:
            if isinstance(renderer, MarkdownRenderer):
                report = renderer.render(results, date=target_date)
                renderer.render_and_save(results, date=target_date)

        return report
```

- [ ] **Step 4: Implement CLI commands**

```python
# src/daytrader/cli/premarket.py
"""Pre-market CLI commands."""

from __future__ import annotations

import asyncio
from datetime import date

import click

from daytrader.premarket.checklist import PremarketChecklist
from daytrader.premarket.collectors.base import MarketDataCollector
from daytrader.premarket.collectors.futures import FuturesCollector
from daytrader.premarket.collectors.sectors import SectorCollector
from daytrader.premarket.collectors.levels import LevelsCollector
from daytrader.premarket.renderers.markdown import MarkdownRenderer
from daytrader.premarket.renderers.pinescript import PineScriptRenderer


def _build_checklist(output_dir: str = "data/exports") -> PremarketChecklist:
    collector = MarketDataCollector()
    collector.register(FuturesCollector())
    collector.register(SectorCollector())
    collector.register(LevelsCollector())
    renderers = [MarkdownRenderer(output_dir=output_dir)]
    return PremarketChecklist(collector=collector, renderers=renderers)


@click.command("run")
@click.option("--push", is_flag=True, help="Push report to notification channels")
@click.pass_context
def pre_run(ctx: click.Context, push: bool) -> None:
    """Run full pre-market analysis."""
    checklist = _build_checklist()
    report = asyncio.run(checklist.run())
    click.echo(report)
    if push:
        click.echo("\n[Push notifications not yet configured]")


@click.command("pine")
@click.argument("symbol", default="SPY")
@click.pass_context
def pre_pine(ctx: click.Context, symbol: str) -> None:
    """Generate Pine Script for key levels."""
    collector = MarketDataCollector()
    collector.register(LevelsCollector(symbols=[symbol]))
    results = asyncio.run(collector.collect_all())

    renderer = PineScriptRenderer()
    path = renderer.render_and_save(results, symbol=symbol)
    click.echo(f"Pine Script saved to: {path}")
```

- [ ] **Step 5: Wire CLI commands into main.py**

In `src/daytrader/cli/main.py`, add to the `pre` group:

```python
# Add after the pre group definition:
from daytrader.cli.premarket import pre_run, pre_pine

pre.add_command(pre_run)
pre.add_command(pre_pine)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/premarket/test_checklist.py -v
```

Expected: 1 passed

- [ ] **Step 7: Verify CLI works**

```bash
uv run daytrader pre --help
uv run daytrader pre run --help
uv run daytrader pre pine --help
```

- [ ] **Step 8: Commit**

```bash
git add src/daytrader/premarket/checklist.py src/daytrader/cli/premarket.py src/daytrader/cli/main.py tests/premarket/test_checklist.py
git commit -m "feat: add premarket checklist engine and CLI commands"
```

---

### Task 7: Weekly Plan Generator & CLI

**Files:**
- Create: `src/daytrader/premarket/weekly.py`
- Create: `src/daytrader/cli/weekly_cmd.py`
- Modify: `src/daytrader/cli/main.py` (wire weekly commands)
- Test: `tests/premarket/test_weekly.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/premarket/test_weekly.py
from datetime import datetime, date, timezone
from unittest.mock import AsyncMock

import pytest

from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector
from daytrader.premarket.weekly import WeeklyPlanGenerator


@pytest.fixture
def mock_results():
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 6, 18, 0, tzinfo=timezone.utc),
            data={"ES=F": {"price": 5425.50, "change_pct": 0.35, "prev_close": 5400.0}},
            success=True,
        ),
        "sectors": CollectorResult(
            collector_name="sectors",
            timestamp=datetime(2026, 4, 6, 18, 0, tzinfo=timezone.utc),
            data={"XLK": {"name": "Technology", "change_pct": 1.2}},
            success=True,
        ),
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 6, 18, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "weekly_high": 543.0,
                    "weekly_low": 536.0,
                    "prior_day_close": 540.0,
                },
            },
            success=True,
        ),
    }


@pytest.mark.asyncio
async def test_weekly_plan_generates_report(tmp_dir, mock_results):
    mock_mdc = AsyncMock(spec=MarketDataCollector)
    mock_mdc.collect_all.return_value = mock_results

    generator = WeeklyPlanGenerator(
        collector=mock_mdc,
        output_dir=str(tmp_dir),
    )

    report = await generator.generate(week_start=date(2026, 4, 6))
    assert "# Weekly Trading Plan" in report
    assert "2026-04-06" in report
    assert "ES=F" in report


@pytest.mark.asyncio
async def test_weekly_plan_saves_file(tmp_dir, mock_results):
    mock_mdc = AsyncMock(spec=MarketDataCollector)
    mock_mdc.collect_all.return_value = mock_results

    generator = WeeklyPlanGenerator(
        collector=mock_mdc,
        output_dir=str(tmp_dir),
    )

    path = await generator.generate_and_save(week_start=date(2026, 4, 6))
    assert path.exists()
    assert "weekly" in path.name
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/premarket/test_weekly.py -v
```

- [ ] **Step 3: Implement weekly plan generator**

```python
# src/daytrader/premarket/weekly.py
"""Weekly trading plan generator."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector


class WeeklyPlanGenerator:
    def __init__(
        self,
        collector: MarketDataCollector,
        output_dir: str = "data/exports",
    ) -> None:
        self._collector = collector
        self._output_dir = Path(output_dir)

    async def generate(self, week_start: date | None = None) -> str:
        week_start = week_start or date.today()
        results = await self._collector.collect_all()

        sections = [
            f"# Weekly Trading Plan — Week of {week_start.isoformat()}\n",
            f"*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC*\n",
        ]

        # Section 1: Last Week Review (placeholder — needs trade journal data)
        sections.append("## Last Week Review\n")
        sections.append("*Requires trade journal data — will be auto-populated once journal module is active.*\n")

        # Section 2: Week Ahead Macro Context
        sections.append("## Week Ahead Macro Context\n")

        # Futures overview
        futures = results.get("futures")
        if futures and futures.success:
            sections.append("### Index Futures\n")
            sections.append("| Symbol | Price | Change % |")
            sections.append("|--------|-------|----------|")
            for sym, data in futures.data.items():
                price = data.get("price", "N/A")
                change = data.get("change_pct")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "N/A"
                sections.append(f"| {sym} | {price} | {change_str} |")
            sections.append("")

        # Sector rotation
        sectors = results.get("sectors")
        if sectors and sectors.success:
            sorted_sectors = sorted(
                sectors.data.items(),
                key=lambda x: x[1].get("change_pct") or 0,
                reverse=True,
            )
            sections.append("### Sector Rotation\n")
            sections.append("**Leaders:** " + ", ".join(
                f"{d['name']} ({d['change_pct']:+.2f}%)"
                for _, d in sorted_sectors[:3]
                if d.get("change_pct") is not None
            ))
            sections.append("")
            sections.append("**Laggards:** " + ", ".join(
                f"{d['name']} ({d['change_pct']:+.2f}%)"
                for _, d in sorted_sectors[-3:]
                if d.get("change_pct") is not None
            ))
            sections.append("")

        # Section 3: Weekly Key Levels
        levels = results.get("levels")
        if levels and levels.success:
            sections.append("## Weekly Key Levels\n")
            for sym, lvls in levels.data.items():
                sections.append(f"### {sym}\n")
                sections.append("| Level | Price |")
                sections.append("|-------|-------|")
                for name, price in lvls.items():
                    if price is not None:
                        label = name.replace("_", " ").title()
                        sections.append(f"| {label} | {price} |")
                sections.append("")

        # Section 4: Weekly Trading Plan
        sections.append("## Weekly Trading Plan\n")
        sections.append("### Bias Framework\n")
        sections.append("*Review index futures + sector data above to set weekly directional bias.*\n")
        sections.append("### Event Risk Windows\n")
        sections.append("*Check economic calendar for FOMC, CPI, NFP, earnings.*\n")
        sections.append("### Focus Goals\n")
        sections.append("- [ ] Goal 1: *(set based on last week review)*\n")
        sections.append("- [ ] Goal 2: *(set based on last week review)*\n")

        return "\n".join(sections)

    async def generate_and_save(self, week_start: date | None = None) -> Path:
        week_start = week_start or date.today()
        content = await self.generate(week_start)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"weekly-{week_start.isoformat()}.md"
        path.write_text(content)
        return path
```

- [ ] **Step 4: Implement weekly CLI commands**

```python
# src/daytrader/cli/weekly_cmd.py
"""Weekly plan CLI commands."""

from __future__ import annotations

import asyncio
from datetime import date

import click

from daytrader.premarket.collectors.base import MarketDataCollector
from daytrader.premarket.collectors.futures import FuturesCollector
from daytrader.premarket.collectors.sectors import SectorCollector
from daytrader.premarket.collectors.levels import LevelsCollector
from daytrader.premarket.weekly import WeeklyPlanGenerator


def _build_weekly_generator(output_dir: str = "data/exports") -> WeeklyPlanGenerator:
    collector = MarketDataCollector()
    collector.register(FuturesCollector())
    collector.register(SectorCollector())
    collector.register(LevelsCollector())
    return WeeklyPlanGenerator(collector=collector, output_dir=output_dir)


@click.command("run")
@click.option("--push", is_flag=True, help="Push plan to notification channels")
def weekly_run(push: bool) -> None:
    """Generate full weekly trading plan."""
    generator = _build_weekly_generator()
    report = asyncio.run(generator.generate())
    click.echo(report)


@click.command("save")
def weekly_save() -> None:
    """Generate and save weekly plan to file."""
    generator = _build_weekly_generator()
    path = asyncio.run(generator.generate_and_save())
    click.echo(f"Weekly plan saved to: {path}")
```

- [ ] **Step 5: Wire weekly CLI into main.py**

In `src/daytrader/cli/main.py`, add:

```python
from daytrader.cli.weekly_cmd import weekly_run, weekly_save

weekly.add_command(weekly_run)
weekly.add_command(weekly_save)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/premarket/test_weekly.py -v
```

Expected: 2 passed

- [ ] **Step 7: Verify CLI**

```bash
uv run daytrader weekly --help
uv run daytrader weekly run --help
```

- [ ] **Step 8: Commit**

```bash
git add src/daytrader/premarket/weekly.py src/daytrader/cli/weekly_cmd.py src/daytrader/cli/main.py tests/premarket/test_weekly.py
git commit -m "feat: add weekly trading plan generator and CLI"
```

---

### Task 8: Full Pre-Market Test Suite & Verification

- [ ] **Step 1: Run all premarket tests**

```bash
uv run pytest tests/premarket/ -v
```

Expected: all tests pass (collectors: ~5, renderers: ~4, checklist: 1, weekly: 2 = ~12 tests)

- [ ] **Step 2: Run full project test suite**

```bash
uv run pytest tests/ -v
```

Expected: all ~32 tests pass

- [ ] **Step 3: Verify CLI end-to-end**

```bash
uv run daytrader pre run --help
uv run daytrader pre pine --help
uv run daytrader weekly run --help
uv run daytrader weekly save --help
```

- [ ] **Step 4: Commit and tag**

```bash
git tag v0.2.0-alpha
```
