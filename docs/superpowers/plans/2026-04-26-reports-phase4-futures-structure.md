# Reports System — Phase 4: F. 期货结构 + News Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute. Steps use checkbox `- [ ]` syntax.

**Goal:** Add the **F. 期货结构** section to the multi-instrument premarket report (per spec §3.6). For each symbol (MES + MNQ + MGC), include: Open Interest delta, Basis (futures vs underlying), Term Structure (front/back month spread), and Volume Profile (POC/VAH/VAL). Wire the existing `premarket/collectors/news.py` NewsCollector into the prompt context (replacing the empty `news_items=[]` Phase 2 stopgap). After Phase 4: the premarket report includes Section F per instrument with rich positioning data, and a real news block from the existing collector.

**Architecture:** Strictly additive. New `reports/futures_data/` submodule with one file per data type (OI, basis, term, volume profile). New `FuturesSection` aggregator. PromptBuilder accepts an optional `futures_data_by_symbol` dict. PremarketGenerator orchestrates the data fetch in parallel with bar fetching. OutputValidator gains an F-section requirement. The existing NewsCollector (Phase 1a) is invoked from PremarketGenerator and its results passed through to PromptBuilder.

**Tech Stack:** Same as Phase 3 + `yfinance` (already in deps, used for SPX index quote for basis), no new external deps.

**Spec reference:** `docs/superpowers/specs/2026-04-25-reports-system-design.md` §3.6 F section, §4.2 news, §4.6 instruments → COT mapping.

**Prerequisites:**
- Phases 1, 2, 2.5, 3 complete ✅
- IB Gateway / TWS API supports OI via `reqHistoricalData(whatToShow="OPEN_INTEREST")` and multi-contract month queries

**Out of scope** (later phases):
- COT weekly report integration → Phase 5 (Sunday weekly report)
- Anthropic Web Search tool use → Phase 4.5 (requires claude -p tool support investigation)
- Settlement price as separate data point → already covered by `prior_day_close` in Phase 2.5 levels
- AI interpretation as separate algorithm → AI does this naturally from raw F-section data in prompt
- Telegram / PDF / charts → Phase 6
- launchd schedule → Phase 7

---

## File Structure

| File | Action | Why |
|---|---|---|
| `src/daytrader/core/ib_client.py` | Modify (add `get_open_interest`, `get_term_structure_prices`) | OI + multi-contract data |
| `tests/reports/test_ib_client.py` | Modify | Coverage for new methods |
| `src/daytrader/reports/futures_data/__init__.py` | Create | New submodule marker |
| `src/daytrader/reports/futures_data/volume_profile.py` | Create | POC/VAH/VAL from 1m bars |
| `tests/reports/test_volume_profile.py` | Create | Unit tests |
| `src/daytrader/reports/futures_data/basis.py` | Create | Futures - underlying spread |
| `tests/reports/test_basis.py` | Create | Unit tests |
| `src/daytrader/reports/futures_data/term_structure.py` | Create | Front/back month structure |
| `tests/reports/test_term_structure.py` | Create | Unit tests |
| `src/daytrader/reports/futures_data/futures_section.py` | Create | Aggregator: builds F-section dict per symbol |
| `tests/reports/test_futures_section.py` | Create | Integration of all 4 data types |
| `src/daytrader/reports/core/prompt_builder.py` | Modify (add `futures_data_by_symbol` param) | Pipe F data to prompt |
| `tests/reports/test_prompt_builder.py` | Modify | Coverage |
| `src/daytrader/reports/templates/premarket.md` | Modify (add F section instructions) | Template v3 |
| `src/daytrader/reports/core/output_validator.py` | Modify (require F section) | Verification |
| `tests/reports/test_output_validator.py` | Modify | Coverage |
| `src/daytrader/reports/types/premarket.py` | Modify (invoke FuturesSection + NewsCollector) | Pipeline integration |
| `tests/reports/test_premarket_type.py` | Modify | Coverage |
| `src/daytrader/reports/core/orchestrator.py` | No change | Generator handles new fetches internally |

---

## Task 1: IBClient — get_open_interest

**Files:** Modify `src/daytrader/core/ib_client.py` + `tests/reports/test_ib_client.py`.

- [ ] **Step 1: Add failing test**

Append to `tests/reports/test_ib_client.py`:

```python
def test_ibclient_get_open_interest_returns_recent_oi(monkeypatch):
    """get_open_interest fetches OPEN_INTEREST bars and returns most recent values."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    # Build fake bars with `volume` field carrying OI value (IB convention)
    bar_today = MagicMock()
    bar_today.date = datetime(2026, 4, 25, tzinfo=timezone.utc)
    bar_today.close = 2143820.0   # OI value
    bar_today.volume = 0.0
    bar_yesterday = MagicMock()
    bar_yesterday.date = datetime(2026, 4, 24, tzinfo=timezone.utc)
    bar_yesterday.close = 2131390.0
    bar_yesterday.volume = 0.0

    fake_ib.reqHistoricalData.return_value = [bar_yesterday, bar_today]
    fake_ib.qualifyContracts.return_value = [MagicMock(conId=12345)]

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    oi = client.get_open_interest(symbol="MES")

    assert oi.today == pytest.approx(2143820.0)
    assert oi.yesterday == pytest.approx(2131390.0)
    assert oi.delta == pytest.approx(12430.0)
    assert oi.delta_pct == pytest.approx(12430.0 / 2131390.0)
```

- [ ] **Step 2: Run (red)**

Run: `uv run pytest tests/reports/test_ib_client.py::test_ibclient_get_open_interest_returns_recent_oi -v`
Expected: FAIL — `get_open_interest` not defined.

- [ ] **Step 3: Implement**

Append to `src/daytrader/core/ib_client.py` (after `get_snapshot`):

```python
@dataclass(frozen=True)
class OpenInterest:
    """Open interest snapshot — today vs yesterday."""
    today: float
    yesterday: float
    delta: float       # today - yesterday
    delta_pct: float   # delta / yesterday
```

Then add the method on `IBClient`:

```python
    def get_open_interest(self, symbol: str) -> OpenInterest:
        """Fetch most recent OPEN_INTEREST values (today + yesterday)."""
        if self._ib is None or not self._ib.isConnected():
            raise RuntimeError("IBClient is not connected; call connect() first")

        from ib_insync import ContFuture
        contract = ContFuture(symbol, _exchange_for(symbol))
        try:
            qualified = self._ib.qualifyContracts(contract)
            if qualified and hasattr(qualified[0], "conId") and qualified[0].conId:
                contract = qualified[0]
        except Exception:
            pass

        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="3 D",
            barSizeSetting="1 day",
            whatToShow="OPEN_INTEREST",
            useRTH=False,
            formatDate=2,
            timeout=60,
        )
        if len(bars) < 2:
            raise RuntimeError(f"Insufficient OI bars for {symbol}: got {len(bars)}")

        today = float(bars[-1].close)
        yesterday = float(bars[-2].close)
        delta = today - yesterday
        delta_pct = delta / yesterday if yesterday else 0.0
        return OpenInterest(
            today=today,
            yesterday=yesterday,
            delta=delta,
            delta_pct=delta_pct,
        )
```

- [ ] **Step 4: Run (green)**

Run: `uv run pytest tests/reports/test_ib_client.py -v`
Expected: 14 tests pass (13 prior + 1 new).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/ib_client.py tests/reports/test_ib_client.py
git commit -m "feat(reports): IBClient.get_open_interest (today vs yesterday delta)"
```

---

## Task 2: Volume Profile (POC / VAH / VAL)

**Files:** Create `src/daytrader/reports/futures_data/__init__.py`, `volume_profile.py`, and `tests/reports/test_volume_profile.py`.

- [ ] **Step 1: Create marker**

Create `src/daytrader/reports/futures_data/__init__.py`:

```python
"""Futures-specific data extractors for the F. 期货结构 section.

Phase 4 modules: OI delta, basis, term structure, volume profile.
"""
```

- [ ] **Step 2: Write failing test**

Create `tests/reports/test_volume_profile.py`:

```python
"""Tests for volume profile (POC, VAH, VAL)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.futures_data.volume_profile import (
    VolumeProfile,
    compute_volume_profile,
)


def _bar(t: datetime, o: float, h: float, l: float, c: float, v: float) -> OHLCV:
    return OHLCV(timestamp=t, open=o, high=h, low=l, close=c, volume=v)


def test_compute_volume_profile_basic():
    """Single bar should yield POC at (h+l)/2, VAH=h, VAL=l for that bar."""
    bars = [
        _bar(datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc), 5240, 5246, 5238, 5244, 1000),
    ]
    vp = compute_volume_profile(bars, tick_size=0.25, value_area_pct=0.7)
    assert isinstance(vp, VolumeProfile)
    assert 5238 <= vp.poc <= 5246
    assert vp.val <= vp.poc <= vp.vah
    assert vp.total_volume == pytest.approx(1000.0)


def test_compute_volume_profile_aggregates_multiple_bars():
    """Multiple bars at same price range concentrate volume on overlap."""
    bars = [
        _bar(datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc), 5240, 5246, 5238, 5244, 1000),
        _bar(datetime(2026, 4, 25, 14, 1, tzinfo=timezone.utc), 5244, 5248, 5242, 5246, 2000),
        _bar(datetime(2026, 4, 25, 14, 2, tzinfo=timezone.utc), 5246, 5250, 5244, 5248, 1500),
    ]
    vp = compute_volume_profile(bars, tick_size=0.25, value_area_pct=0.7)
    # POC should be in the overlap zone where all 3 bars share price
    assert 5244 <= vp.poc <= 5246
    assert vp.total_volume == pytest.approx(4500.0)
    assert vp.val < vp.vah


def test_compute_volume_profile_empty_bars_raises():
    with pytest.raises(ValueError, match="empty"):
        compute_volume_profile([], tick_size=0.25)
```

- [ ] **Step 3: Run (red)**

Run: `uv run pytest tests/reports/test_volume_profile.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement**

Create `src/daytrader/reports/futures_data/volume_profile.py`:

```python
"""Volume profile computation (POC, VAH, VAL).

Distributes each bar's volume uniformly across its price range (high to low),
then identifies:
- POC (Point of Control): price level with the most volume
- Value Area: contiguous range around POC containing `value_area_pct` of total volume
- VAH (Value Area High): top of value area
- VAL (Value Area Low): bottom of value area

Standard convention: value_area_pct = 70% (auction market theory).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from daytrader.core.ib_client import OHLCV


@dataclass(frozen=True)
class VolumeProfile:
    poc: float          # Point of Control (price with most volume)
    vah: float          # Value Area High
    val: float          # Value Area Low
    total_volume: float
    tick_size: float


def compute_volume_profile(
    bars: list[OHLCV],
    tick_size: float = 0.25,
    value_area_pct: float = 0.7,
) -> VolumeProfile:
    """Compute volume profile from a list of intraday bars."""
    if not bars:
        raise ValueError("compute_volume_profile: empty bars list")

    # 1. Distribute each bar's volume across its price range
    volume_at_price: dict[float, float] = defaultdict(float)
    for bar in bars:
        if bar.high < bar.low:
            continue  # malformed
        price_levels = []
        p = bar.low
        while p <= bar.high + 1e-9:  # tolerance for float
            price_levels.append(round(p, 6))
            p += tick_size
        if not price_levels:
            price_levels = [bar.close]
        per_level_volume = bar.volume / len(price_levels)
        for level in price_levels:
            volume_at_price[level] += per_level_volume

    if not volume_at_price:
        raise ValueError("compute_volume_profile: no price levels accumulated")

    # 2. POC = price with max volume
    poc = max(volume_at_price.keys(), key=lambda p: volume_at_price[p])
    total_volume = sum(volume_at_price.values())
    target_volume = total_volume * value_area_pct

    # 3. Build value area: expand from POC outward, picking the higher-volume side
    sorted_levels = sorted(volume_at_price.keys())
    poc_idx = sorted_levels.index(poc)
    val_idx, vah_idx = poc_idx, poc_idx
    accumulated = volume_at_price[poc]

    while accumulated < target_volume:
        below_idx = val_idx - 1
        above_idx = vah_idx + 1
        below_vol = (
            volume_at_price[sorted_levels[below_idx]] if below_idx >= 0 else -1
        )
        above_vol = (
            volume_at_price[sorted_levels[above_idx]]
            if above_idx < len(sorted_levels) else -1
        )
        if below_vol < 0 and above_vol < 0:
            break  # exhausted both sides
        if above_vol >= below_vol:
            vah_idx = above_idx
            accumulated += above_vol
        else:
            val_idx = below_idx
            accumulated += below_vol

    return VolumeProfile(
        poc=poc,
        vah=sorted_levels[vah_idx],
        val=sorted_levels[val_idx],
        total_volume=total_volume,
        tick_size=tick_size,
    )
```

- [ ] **Step 5: Run (green)**

Run: `uv run pytest tests/reports/test_volume_profile.py -v`
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/reports/futures_data/__init__.py src/daytrader/reports/futures_data/volume_profile.py tests/reports/test_volume_profile.py
git commit -m "feat(reports): volume profile (POC/VAH/VAL) computation"
```

---

## Task 3: Basis (futures - underlying)

**Files:** Create `src/daytrader/reports/futures_data/basis.py` + `tests/reports/test_basis.py`.

- [ ] **Step 1: Write failing test**

Create `tests/reports/test_basis.py`:

```python
"""Tests for basis (futures - underlying)."""

from __future__ import annotations

import pytest

from daytrader.reports.futures_data.basis import compute_basis, BasisResult


def test_compute_basis_simple():
    """Basis = future_price - underlying_price."""
    result = compute_basis(future_price=5246.75, underlying_price=5244.50)
    assert isinstance(result, BasisResult)
    assert result.basis == pytest.approx(2.25)
    assert result.future_price == pytest.approx(5246.75)
    assert result.underlying_price == pytest.approx(5244.50)


def test_compute_basis_negative():
    """Basis can be negative (futures trading below cash)."""
    result = compute_basis(future_price=5240.00, underlying_price=5245.00)
    assert result.basis == pytest.approx(-5.00)
```

- [ ] **Step 2: Run (red)**

Run: `uv run pytest tests/reports/test_basis.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/daytrader/reports/futures_data/basis.py`:

```python
"""Basis computation: futures price - underlying index/spot price.

Phase 4 keeps it simple: the caller passes both prices; this module just
computes the spread and provides a typed result. Fetching underlying prices
(SPX, NDX, gold spot/GLD) is the caller's responsibility — typically via
yfinance or a separate IBClient call to an index symbol.

Future Phase 4.5 may add a unified fetcher that knows symbol→underlying
mapping and orchestrates both fetches.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BasisResult:
    future_price: float
    underlying_price: float
    basis: float            # future_price - underlying_price


def compute_basis(future_price: float, underlying_price: float) -> BasisResult:
    """Return the futures-to-underlying spread."""
    return BasisResult(
        future_price=future_price,
        underlying_price=underlying_price,
        basis=future_price - underlying_price,
    )
```

- [ ] **Step 4: Run (green)**

Run: `uv run pytest tests/reports/test_basis.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/futures_data/basis.py tests/reports/test_basis.py
git commit -m "feat(reports): basis (futures - underlying) compute helper"
```

---

## Task 4: Term Structure (front / back month)

**Files:** Create `src/daytrader/reports/futures_data/term_structure.py` + `tests/reports/test_term_structure.py`.

- [ ] **Step 1: Write failing test**

Create `tests/reports/test_term_structure.py`:

```python
"""Tests for term structure (front/back month)."""

from __future__ import annotations

import pytest

from daytrader.reports.futures_data.term_structure import (
    TermStructure,
    compute_term_structure,
)


def test_compute_term_structure_contango():
    """When back > front, structure is contango."""
    ts = compute_term_structure(
        front_price=5246.75,
        next_price=5252.00,
        far_price=5258.50,
    )
    assert isinstance(ts, TermStructure)
    assert ts.front == pytest.approx(5246.75)
    assert ts.next == pytest.approx(5252.00)
    assert ts.far == pytest.approx(5258.50)
    assert ts.contango is True
    assert ts.spread_front_next == pytest.approx(5.25)
    assert ts.spread_next_far == pytest.approx(6.50)


def test_compute_term_structure_backwardation():
    """When back < front, structure is backwardation."""
    ts = compute_term_structure(
        front_price=2350.00,
        next_price=2348.00,
        far_price=2345.00,
    )
    assert ts.contango is False
    assert ts.spread_front_next == pytest.approx(-2.00)
```

- [ ] **Step 2: Run (red)**

Run: `uv run pytest tests/reports/test_term_structure.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/daytrader/reports/futures_data/term_structure.py`:

```python
"""Term structure computation: front, next, far month spreads.

Phase 4 keeps it simple: the caller passes 3 prices (front, next, far);
this module computes spreads and labels contango / backwardation.
Fetching the 3 prices is the caller's responsibility (multi-contract IB
queries with explicit lastTradeDateOrContractMonth).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TermStructure:
    front: float                 # front-month price
    next: float                  # next-quarter price
    far: float                   # far-quarter (Q+2) price
    spread_front_next: float     # next - front
    spread_next_far: float       # far - next
    contango: bool               # spread_front_next > 0


def compute_term_structure(
    front_price: float, next_price: float, far_price: float
) -> TermStructure:
    spread_front_next = next_price - front_price
    spread_next_far = far_price - next_price
    return TermStructure(
        front=front_price,
        next=next_price,
        far=far_price,
        spread_front_next=spread_front_next,
        spread_next_far=spread_next_far,
        contango=spread_front_next > 0,
    )
```

- [ ] **Step 4: Run (green)**

Run: `uv run pytest tests/reports/test_term_structure.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/futures_data/term_structure.py tests/reports/test_term_structure.py
git commit -m "feat(reports): term structure (front/next/far) compute helper"
```

---

## Task 5: FuturesSection aggregator

**Files:** Create `src/daytrader/reports/futures_data/futures_section.py` + `tests/reports/test_futures_section.py`.

- [ ] **Step 1: Write failing test**

Create `tests/reports/test_futures_section.py`:

```python
"""Tests for FuturesSection aggregator (per-symbol F-section data bundle)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.futures_data.futures_section import (
    FuturesSection,
    SymbolFuturesData,
    build_futures_section,
)


def _bar(c: float, v: float = 1000) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 4, 25, 14, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=v,
    )


def test_build_futures_section_assembles_per_symbol_data():
    """build_futures_section calls IB + computes VP / basis / term and returns dict."""
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True

    # Mock OI calls
    fake_ib.get_open_interest.return_value = OpenInterest(
        today=2143820.0, yesterday=2131390.0, delta=12430.0, delta_pct=0.006
    )

    # Mock 1m bars for VP
    fake_ib.get_bars.return_value = [
        _bar(5240.0, 1000), _bar(5244.0, 2000), _bar(5246.0, 1500),
    ]

    # Underlying prices for basis (caller supplies dict)
    underlying_prices = {"MES": 5244.50, "MNQ": 18495.0, "MGC": 2342.5}

    # Term structure prices (caller supplies dict)
    term_prices = {
        "MES": (5246.75, 5252.00, 5258.50),
        "MNQ": (18500.0, 18560.0, 18620.0),
        "MGC": (2350.00, 2348.00, 2345.00),
    }

    section = build_futures_section(
        ib_client=fake_ib,
        symbols=["MES", "MNQ", "MGC"],
        underlying_prices=underlying_prices,
        term_prices=term_prices,
        tick_sizes={"MES": 0.25, "MNQ": 0.25, "MGC": 0.10},
    )

    assert isinstance(section, FuturesSection)
    assert set(section.per_symbol.keys()) == {"MES", "MNQ", "MGC"}
    mes = section.per_symbol["MES"]
    assert isinstance(mes, SymbolFuturesData)
    assert mes.open_interest.delta == pytest.approx(12430.0)
    assert mes.basis.basis == pytest.approx(5246.75 - 5244.50)
    assert mes.term_structure.contango is True
    assert mes.volume_profile.total_volume == pytest.approx(4500.0)


def test_build_futures_section_handles_oi_failure_gracefully():
    """If get_open_interest raises, that symbol's OI = None but others succeed."""
    from daytrader.core.ib_client import OpenInterest

    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_bar(5240.0)]
    # First call raises, second succeeds
    fake_ib.get_open_interest.side_effect = [
        RuntimeError("Insufficient OI bars"),
        OpenInterest(today=900000, yesterday=890000, delta=10000, delta_pct=0.011),
    ]

    section = build_futures_section(
        ib_client=fake_ib,
        symbols=["MES", "MGC"],
        underlying_prices={"MES": 5244.5, "MGC": 2342.5},
        term_prices={"MES": (5246.75, 5252, 5258), "MGC": (2350, 2348, 2345)},
        tick_sizes={"MES": 0.25, "MGC": 0.10},
    )

    assert section.per_symbol["MES"].open_interest is None
    assert section.per_symbol["MGC"].open_interest is not None
```

- [ ] **Step 2: Run (red)**

Run: `uv run pytest tests/reports/test_futures_section.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/daytrader/reports/futures_data/futures_section.py`:

```python
"""FuturesSection aggregator.

Builds the F. 期货结构 section data bundle for use in PromptBuilder.
For each symbol: OI delta, volume profile, basis, term structure.

Caller provides:
- IBClient (for OI and 1m bars)
- underlying_prices dict (computed/fetched separately, e.g. via yfinance)
- term_prices dict (front/next/far prices, fetched separately)
- tick_sizes dict (per symbol; affects VP granularity)

The aggregator handles per-data-type failures gracefully — each field becomes
None if its fetch/compute fails, and a warning is printed to stderr. The
overall structure is still returned so the prompt always has something to
include in the F section.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from daytrader.core.ib_client import IBClient, OpenInterest
from daytrader.reports.futures_data.basis import BasisResult, compute_basis
from daytrader.reports.futures_data.term_structure import (
    TermStructure,
    compute_term_structure,
)
from daytrader.reports.futures_data.volume_profile import (
    VolumeProfile,
    compute_volume_profile,
)


@dataclass(frozen=True)
class SymbolFuturesData:
    """Per-symbol F-section data."""
    symbol: str
    open_interest: OpenInterest | None
    basis: BasisResult | None
    term_structure: TermStructure | None
    volume_profile: VolumeProfile | None


@dataclass(frozen=True)
class FuturesSection:
    """All-symbols F-section bundle."""
    per_symbol: dict[str, SymbolFuturesData]


def build_futures_section(
    ib_client: IBClient,
    symbols: list[str],
    underlying_prices: dict[str, float],
    term_prices: dict[str, tuple[float, float, float]],
    tick_sizes: dict[str, float],
) -> FuturesSection:
    """Aggregate F-section data for all symbols."""
    per_symbol: dict[str, SymbolFuturesData] = {}

    for symbol in symbols:
        # OI
        oi: OpenInterest | None
        try:
            oi = ib_client.get_open_interest(symbol=symbol)
        except Exception as e:
            print(
                f"[futures_section] WARNING: get_open_interest({symbol}) failed: {e}",
                file=sys.stderr,
            )
            oi = None

        # Basis
        basis: BasisResult | None = None
        if symbol in underlying_prices:
            try:
                # We need the front-month price as future_price; use term_prices first slot
                front_price = term_prices[symbol][0] if symbol in term_prices else None
                if front_price is not None:
                    basis = compute_basis(
                        future_price=front_price,
                        underlying_price=underlying_prices[symbol],
                    )
            except Exception as e:
                print(
                    f"[futures_section] WARNING: basis({symbol}) failed: {e}",
                    file=sys.stderr,
                )
                basis = None

        # Term structure
        term: TermStructure | None = None
        if symbol in term_prices:
            try:
                front, mid, far = term_prices[symbol]
                term = compute_term_structure(front, mid, far)
            except Exception as e:
                print(
                    f"[futures_section] WARNING: term_structure({symbol}) failed: {e}",
                    file=sys.stderr,
                )
                term = None

        # Volume profile from 1m bars (last RTH session, ~390 bars at most)
        vp: VolumeProfile | None
        try:
            bars_1m = ib_client.get_bars(symbol=symbol, timeframe="1m", bars=390)
            if bars_1m:
                vp = compute_volume_profile(
                    bars=bars_1m,
                    tick_size=tick_sizes.get(symbol, 0.25),
                    value_area_pct=0.7,
                )
            else:
                vp = None
        except Exception as e:
            print(
                f"[futures_section] WARNING: volume_profile({symbol}) failed: {e}",
                file=sys.stderr,
            )
            vp = None

        per_symbol[symbol] = SymbolFuturesData(
            symbol=symbol,
            open_interest=oi,
            basis=basis,
            term_structure=term,
            volume_profile=vp,
        )

    return FuturesSection(per_symbol=per_symbol)
```

- [ ] **Step 4: Run (green)**

Run: `uv run pytest tests/reports/test_futures_section.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/futures_data/futures_section.py tests/reports/test_futures_section.py
git commit -m "feat(reports): FuturesSection aggregator (per-symbol F data bundle)"
```

---

## Task 6: PromptBuilder — accept futures_data_by_symbol

**Files:** Modify `src/daytrader/reports/core/prompt_builder.py` + `tests/reports/test_prompt_builder.py`.

- [ ] **Step 1: Update signature + add F-section block builder**

In `src/daytrader/reports/core/prompt_builder.py`, modify `build_premarket` to accept an optional `futures_data` param:

```python
    def build_premarket(
        self,
        context: ReportContext,
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
        tradable_symbols: list[str],
        news_items: list[dict[str, Any]],
        run_timestamp_pt: str,
        run_timestamp_et: str,
        futures_data: "FuturesSection | None" = None,  # Phase 4 addition
    ) -> list[dict[str, Any]]:
```

Add a new method `_build_futures_section_block`:

```python
    @staticmethod
    def _build_futures_section_block(
        futures_data: "FuturesSection | None",
    ) -> str:
        """Format F-section data for the prompt user message."""
        if futures_data is None:
            return "## F. 期货结构 (futures positioning)\n\n(no F-section data available)"
        lines = ["## F. 期货结构 (futures positioning) — raw data per symbol"]
        for symbol, data in futures_data.per_symbol.items():
            lines.append(f"\n### {symbol}")
            if data.open_interest:
                oi = data.open_interest
                lines.append(
                    f"- OI: today={oi.today:.0f}, yesterday={oi.yesterday:.0f}, "
                    f"delta={oi.delta:+.0f} ({oi.delta_pct:+.2%})"
                )
            else:
                lines.append("- OI: unavailable")
            if data.basis:
                lines.append(
                    f"- Basis: future={data.basis.future_price:.2f}, "
                    f"underlying={data.basis.underlying_price:.2f}, "
                    f"spread={data.basis.basis:+.2f}"
                )
            else:
                lines.append("- Basis: unavailable")
            if data.term_structure:
                ts = data.term_structure
                structure_label = "contango" if ts.contango else "backwardation"
                lines.append(
                    f"- Term structure: front={ts.front:.2f}, next={ts.next:.2f}, "
                    f"far={ts.far:.2f} → {structure_label} "
                    f"(spread front→next: {ts.spread_front_next:+.2f})"
                )
            else:
                lines.append("- Term structure: unavailable")
            if data.volume_profile:
                vp = data.volume_profile
                lines.append(
                    f"- Volume profile (today, RTH): POC={vp.poc:.2f}, "
                    f"VAH={vp.vah:.2f}, VAL={vp.val:.2f} "
                    f"(total volume {vp.total_volume:.0f})"
                )
            else:
                lines.append("- Volume profile: unavailable")
        lines.append(
            "\nGenerate the F. 期货结构 section in the report by interpreting "
            "the above raw data into bullish/bearish positioning paragraphs per symbol."
        )
        return "\n".join(lines)
```

In the `build_premarket` body, add the F-block to `user_text`:

```python
        futures_block = self._build_futures_section_block(futures_data)
        # Insert futures_block after bars_block, before news_block
        user_text = (
            f"# Premarket Daily Report — generation context\n\n"
            f"**Run time**: {run_timestamp_pt} ({run_timestamp_et})\n\n"
            f"{lock_in_block}\n\n"
            f"{tradable_block}\n\n"
            f"{bars_block}\n\n"
            f"{futures_block}\n\n"
            f"{news_block}\n\n"
            f"Please generate the full multi-instrument premarket report following "
            f"the system prompt template. Output in Chinese."
        )
```

Add the import at the top (forward reference; place it after existing imports):

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from daytrader.reports.futures_data.futures_section import FuturesSection
```

- [ ] **Step 2: Add tests**

Append to `tests/reports/test_prompt_builder.py`:

```python
def test_prompt_builder_includes_f_section_when_futures_data_provided():
    from daytrader.reports.futures_data.futures_section import (
        FuturesSection, SymbolFuturesData,
    )
    from daytrader.reports.futures_data.basis import BasisResult
    from daytrader.reports.futures_data.term_structure import TermStructure
    from daytrader.reports.futures_data.volume_profile import VolumeProfile
    from daytrader.core.ib_client import OpenInterest

    ctx = ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n",
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    fs = FuturesSection(per_symbol={
        "MES": SymbolFuturesData(
            symbol="MES",
            open_interest=OpenInterest(2143820, 2131390, 12430, 0.006),
            basis=BasisResult(5246.75, 5244.50, 2.25),
            term_structure=TermStructure(5246.75, 5252.00, 5258.50, 5.25, 6.50, True),
            volume_profile=VolumeProfile(5244.0, 5249.0, 5240.0, 1500000.0, 0.25),
        ),
    })
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
        futures_data=fs,
    )
    user_text = msgs[1]["content"]
    assert "F. 期货结构" in user_text
    assert "12430" in user_text  # OI delta
    assert "contango" in user_text
    assert "POC=5244" in user_text


def test_prompt_builder_omits_f_section_when_no_futures_data():
    ctx = ReportContext(
        contract_status=ContractStatus.NOT_CREATED,
        contract_text=None,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
        futures_data=None,  # explicit
    )
    user_text = msgs[1]["content"]
    assert "no F-section data available" in user_text
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/reports/test_prompt_builder.py -v`
Expected: all tests pass (5 prior + 2 new = 7).

- [ ] **Step 4: Commit**

```bash
git add src/daytrader/reports/core/prompt_builder.py tests/reports/test_prompt_builder.py
git commit -m "feat(reports): PromptBuilder F-section block (futures positioning data)"
```

---

## Task 7: Premarket template v3 — add F section

**Files:** Modify `src/daytrader/reports/templates/premarket.md`.

- [ ] **Step 1: Update template**

In `src/daytrader/reports/templates/premarket.md`, in the "Required Sections (in order)" list, INSERT a new item between current item 4 (Breaking news) and current item 5 (C. 计划复核):

```markdown
5. **F. 期货结构 / Futures Positioning** — per-symbol paragraphs interpreting the raw OI / basis / term / VP data into bullish/bearish positioning narrative
```

Renumber subsequent items (now 6, 7, 8, 9 instead of 5, 6, 7, 8).

Then, ADD a new "F. Section Format" subsection after the per-instrument template:

```markdown
## F. Futures Positioning Format

For each symbol (MES, MNQ, MGC), generate a paragraph that integrates the raw data into a positioning narrative. Use this structure:

### F-{SYMBOL}

- **Settlement / OI**: [today's settlement, OI delta value + direction interpretation, e.g. "价涨 OI 涨 → 真多头资金流入" or "价跌 OI 涨 → 新空头进场"]
- **Basis**: [spread value + interpretation, e.g. "+0.5 pt within normal range -2 to +3 → 中性"]
- **Term structure**: [contango/backwardation + spreads + carry interpretation]
- **Volume profile**: [POC/VAH/VAL + current price relationship, e.g. "当前价 5246.75 在 POC 上方、VAH 下方 → 公允区上沿"]
- **综合定性 / Overall posture**: [bullish positioning (强度: 强/中/弱) | neutral | bearish positioning (强度: ...)]

For MNQ (context-only): keep the F-MNQ block short — focus on whether MNQ posture confirms or contradicts MES posture.
```

Update the "Length Limit" section:

```markdown
## Length Limit

Max ~12,000 characters with F section. If approaching limit, compress B (use bullets), preserve all multi-TF + F-* + C-MES + C-MGC + A.
```

- [ ] **Step 2: Verify template loads**

Run: `uv run python -c "from daytrader.reports.templates import load_template; t = load_template('premarket'); print(len(t), 'chars'); assert 'F. 期货结构' in t or 'F-{SYMBOL}' in t"`

Expected: prints char count, no AssertionError.

- [ ] **Step 3: Commit**

```bash
git add src/daytrader/reports/templates/premarket.md
git commit -m "feat(reports): premarket template v3 (add F. 期货结构 section)"
```

---

## Task 8: OutputValidator — require F section

**Files:** Modify `src/daytrader/reports/core/output_validator.py` + `tests/reports/test_output_validator.py`.

- [ ] **Step 1: Add F-section requirement**

In `REQUIRED_SECTIONS["premarket"]`, INSERT the F-section labels between "新闻" alternatives and the C-MES/C-MGC entries:

```python
        ["新闻", "News", "Breaking"],
        # F. 期货结构 — at least one F-{symbol} or general F header must appear
        ["F. 期货结构", "F-MES", "F-MNQ", "F-MGC", "Futures Positioning", "期货结构"],
        # Plan blocks for tradable instruments
        ["C-MES", "### C-MES", "C. MES", "MES Plan"],
        ...
```

- [ ] **Step 2: Update fixtures**

In `tests/reports/test_output_validator.py`, the `PREMARKET_SAMPLE_VALID` fixture currently lacks an F section. INSERT it after `## Breaking news / 突发新闻` block:

```
## F. 期货结构

### F-MES
- Settlement: ok
- OI: ok
- Overall: bullish

### F-MGC
- Settlement: ok
- Overall: neutral
```

Same for `PREMARKET_SAMPLE_LIVE_FORMAT`.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/reports/test_output_validator.py -v`
Expected: all tests pass with the updated fixtures including F-section.

- [ ] **Step 4: Commit**

```bash
git add src/daytrader/reports/core/output_validator.py tests/reports/test_output_validator.py
git commit -m "feat(reports): OutputValidator F-section requirement"
```

---

## Task 9: PremarketGenerator — invoke FuturesSection + News

**Files:** Modify `src/daytrader/reports/types/premarket.py` + `tests/reports/test_premarket_type.py`.

- [ ] **Step 1: Update generator**

In `src/daytrader/reports/types/premarket.py`, add to imports:

```python
from daytrader.reports.futures_data.futures_section import (
    FuturesSection, build_futures_section,
)
```

In `PremarketGenerator.__init__`, add optional callable params:

```python
    def __init__(
        self,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbols: list[str],
        tradable_symbols: list[str],
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
        underlying_price_fetcher: callable | None = None,
        term_price_fetcher: callable | None = None,
        tick_sizes: dict[str, float] | None = None,
        news_collector: callable | None = None,
    ) -> None:
```

(Keep all existing assignments; assign the new params to `self.*`.)

In `generate(...)`, BEFORE calling `prompt_builder.build_premarket`:

```python
        # Build F-section data (best-effort)
        futures_data: FuturesSection | None = None
        try:
            tick_sizes = self.tick_sizes or {s: 0.25 for s in self.symbols}
            underlying_prices = (
                self.underlying_price_fetcher(self.symbols)
                if self.underlying_price_fetcher else {}
            )
            term_prices = (
                self.term_price_fetcher(self.symbols)
                if self.term_price_fetcher else {}
            )
            futures_data = build_futures_section(
                ib_client=self.ib_client,
                symbols=self.symbols,
                underlying_prices=underlying_prices,
                term_prices=term_prices,
                tick_sizes=tick_sizes,
            )
        except Exception as exc:
            import sys
            print(
                f"[premarket_generator] WARNING: F-section build failed: {exc}",
                file=sys.stderr,
            )
            futures_data = None

        # Fetch news (best-effort)
        if news_items is None:
            news_items = []
            if self.news_collector is not None:
                try:
                    news_items = self.news_collector()
                except Exception as exc:
                    import sys
                    print(
                        f"[premarket_generator] WARNING: news fetch failed: {exc}",
                        file=sys.stderr,
                    )
                    news_items = []
```

Then pass `futures_data=futures_data` and `news_items=news_items` to `build_premarket`.

- [ ] **Step 2: Add tests**

Append to `tests/reports/test_premarket_type.py`:

```python
def test_premarket_generator_invokes_futures_section_when_fetchers_provided():
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]
    from daytrader.core.ib_client import OpenInterest
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = (
        "## Lock-in\nstatus\n## Multi-TF\n### 📊 MES\n#### W\nx\n#### D\nx\n"
        "#### 4H\nx\n#### 1H\nx\n## 突发新闻\nnews\n"
        "## F. 期货结构\n### F-MES\nbullish\n"
        "## C. 计划复核\n### C-MES\nplan\n"
        "## B. 市场叙事\nb\n## A. 建议\nx\n## 数据快照\nok"
    )
    fake_ai_result.input_tokens = 1
    fake_ai_result.output_tokens = 1
    fake_ai_result.cache_creation_tokens = 0
    fake_ai_result.cache_read_tokens = 0
    fake_ai_result.model = "claude-opus-4-7"
    fake_ai_result.stop_reason = "end_turn"
    fake_ai.call.return_value = fake_ai_result

    underlying_fetcher = MagicMock(return_value={"MES": 5244.5})
    term_fetcher = MagicMock(return_value={"MES": (5246.75, 5252.0, 5258.5)})

    generator = PremarketGenerator(
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES"],
        tradable_symbols=["MES"],
        underlying_price_fetcher=underlying_fetcher,
        term_price_fetcher=term_fetcher,
        tick_sizes={"MES": 0.25},
    )
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )
    underlying_fetcher.assert_called_once_with(["MES"])
    term_fetcher.assert_called_once_with(["MES"])
    fake_ib.get_open_interest.assert_called_with(symbol="MES")
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/reports/test_premarket_type.py -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/daytrader/reports/types/premarket.py tests/reports/test_premarket_type.py
git commit -m "feat(reports): PremarketGenerator invokes FuturesSection + news (Phase 4)"
```

---

## Task 10: Phase 4 acceptance + runbook update

**Files:** Verification + `docs/ops/phase2-runbook.md`.

- [ ] **Step 1: Full project test pass**

Run: `uv run pytest tests/ --ignore=tests/research -q`
Expected: 260+ tests pass.

- [ ] **Step 2: Update runbook**

In `docs/ops/phase2-runbook.md`, "What this run does NOT yet do (Phase 4+)" → rename to "Phase 5+" and remove F-section + news items:

```markdown
## What this run does NOT yet do (Phase 5+)

- Other report types (intraday/EOD/weekly/night) → Phase 5
- Telegram push (only Obsidian today) → Phase 6
- PDF / chart rendering → Phase 6
- Automatic launchd schedule → Phase 7
- Anthropic Web Search tool use (Phase 4 uses existing news collector only) → Phase 4.5
```

Add a new "Step 6 (Phase 4)" section:

```markdown
## Step 6 (Phase 4): Verify F. 期货结构 in report

After a successful Phase 4 run, the markdown should contain:

- "## F. 期货结构" header
- "### F-MES" subsection with OI, Basis, Term structure, Volume profile fields
- "### F-MNQ" and "### F-MGC" similarly
- AI-generated 综合定性 (overall posture) per symbol

Quick verification:

```bash
grep -c "F-MES\|F-MNQ\|F-MGC" "$HOME/Documents/DayTrader Vault/Daily/$(date +%Y-%m-%d)-premarket.md"
# Expected: 3
```
```

- [ ] **Step 3: Commit + push**

```bash
git add docs/ops/phase2-runbook.md
git commit -m "docs(reports): Phase 4 runbook update (F section + news coverage)"
git push
```

- [ ] **Step 4: Print Phase 4 commit summary**

Run: `git log --oneline 86bc1d6..HEAD`
Expected: 10 Phase 4 commits.

---

## Summary

After Phase 4, the premarket report includes the **F. 期货结构** section per symbol with OI delta + Basis + Term structure + Volume profile. News is wired in from the existing premarket collector (replacing Phase 2's empty stub).

**Coverage vs spec §3.6:** Phase 3's 85% → Phase 4's **~93%**. Remaining gaps: charts/PDF/Telegram (Phase 6), other report types (Phase 5), launchd (Phase 7).

**Next:** Phase 6 plan (Telegram + PDF + matplotlib charts) — separate file.
