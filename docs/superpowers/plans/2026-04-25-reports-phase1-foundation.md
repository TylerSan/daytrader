# Reports System — Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the foundation for the multi-cadence reports system: IBKR connection layer, SQLite state DB, multi-instrument config, CLI scaffolding, and IB Gateway operational setup. After Phase 1: `daytrader reports dry-run --type premarket` runs end-to-end with mocked AI/delivery, fetching real MES bars from IB.

**Architecture:** Strictly additive. New `core/ib_client.py`, new `core/state.py` (separate from existing `core/db.py`), new `reports/` module sibling to `premarket/` and `journal/`. Existing modules untouched. ib_insync connects to a locally-run IB Gateway managed by IBC.

**Tech Stack:** Python 3.12+, ib_insync, sqlite3 (stdlib), pydantic v2, click, pytest, pyyaml, IBC (operational, manual install).

**Spec reference:** `docs/superpowers/specs/2026-04-25-reports-system-design.md` §6.1 module structure, §4.4 SQLite schema, §4.6 instruments config, §6.6 first-run checklist.

**Out of scope for Phase 1** (covered by later phases):
- AI prompt building / Anthropic SDK integration → Phase 2
- Multi-TF report generation logic → Phase 3
- Futures structure (OI/COT/basis/term/VP) → Phase 4
- All 6 report types beyond premarket skeleton → Phase 5
- Obsidian write / PDF render / Telegram push → Phase 6
- launchd plists → Phase 7

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `pyproject.toml` | Dependency declarations | Modify |
| `tests/reports/__init__.py` | Test package marker | Create |
| `tests/reports/conftest.py` | Reports-specific fixtures | Create |
| `src/daytrader/core/ib_client.py` | ib_insync wrapper, generic market-data only | Create |
| `tests/reports/test_ib_client.py` | IBClient unit tests (mocked ib_insync) | Create |
| `src/daytrader/core/state.py` | SQLite state DB for reports system | Create |
| `tests/reports/test_state.py` | State DB unit tests | Create |
| `config/instruments.yaml` | MES/MNQ/MGC parameters | Create |
| `src/daytrader/reports/__init__.py` | Reports module marker | Create |
| `src/daytrader/reports/instruments/__init__.py` | Instruments submodule marker | Create |
| `src/daytrader/reports/instruments/definitions.py` | Instrument config loader | Create |
| `tests/reports/test_instruments.py` | Instruments loader tests | Create |
| `src/daytrader/core/config.py` | Add ReportsConfig (additive) | Modify (one block append) |
| `config/default.yaml` | Add reports section (additive) | Modify (append) |
| `config/secrets.yaml.example` | Template for secrets | Create |
| `.gitignore` | Add config/secrets.yaml | Modify |
| `src/daytrader/reports/core/__init__.py` | Reports core submodule | Create |
| `src/daytrader/reports/core/secrets.py` | Secrets loader (Anthropic key, Telegram token) | Create |
| `tests/reports/test_secrets.py` | Secrets loader tests | Create |
| `src/daytrader/cli/reports.py` | New CLI command group (dry-run subcommand) | Create |
| `src/daytrader/cli/main.py` | Register reports command group | Modify (one block append) |
| `tests/cli/test_reports_cli.py` | CLI smoke test | Create |
| `scripts/run_report.py` | launchd entry point script | Create |
| `tests/scripts/test_run_report.py` | Script entry tests | Create |
| `docs/ops/ib-gateway-setup.md` | IB Gateway + IBC install guide | Create |

---

## Task 1: Add Phase 1 dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `ib_insync` to core dependencies**

Open `pyproject.toml` and locate the `dependencies` array (lines 6-22). Add `ib_insync>=0.9.86` to the list (alphabetical insertion between `httpx` and `jinja2` is fine).

The dependencies array should look like:

```toml
dependencies = [
    "click>=8.1",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "ib_insync>=0.9.86",
    "pandas>=2.2",
    "numpy>=1.26",
    "plotly>=5.18",
    "yfinance>=0.2.36",
    "jinja2>=3.1",
    "anthropic>=0.40",
    "matplotlib>=3.8",
    "pyarrow>=14.0",
    "databento>=0.42",
    "lib-pybroker>=1.0",
    "quantstats>=0.0.62",
]
```

- [ ] **Step 2: Run `uv sync` to install**

Run: `uv sync`
Expected: ib_insync resolves and installs without conflict.

- [ ] **Step 3: Verify installation**

Run: `uv run python -c "import ib_insync; print(ib_insync.__version__)"`
Expected: prints a version string like `0.9.86`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add ib_insync for IBKR market data"
```

---

## Task 2: Create reports test package

**Files:**
- Create: `tests/reports/__init__.py`
- Create: `tests/reports/conftest.py`

- [ ] **Step 1: Create empty `__init__.py`**

Create `tests/reports/__init__.py` with content:

```python
"""Tests for daytrader.reports module and reports CLI."""
```

- [ ] **Step 2: Create `conftest.py` with shared fixtures**

Create `tests/reports/conftest.py` with content:

```python
"""Shared fixtures for reports tests."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest


@pytest.fixture
def tmp_state_db(tmp_path: Path) -> Path:
    """Provide an isolated SQLite DB path for state tests."""
    return tmp_path / "state.db"


@pytest.fixture
def fixture_instruments_yaml(tmp_path: Path) -> Path:
    """Minimal instruments.yaml fixture mirroring spec §4.6."""
    content = """
instruments:
  MES:
    full_name: "Micro E-mini S&P 500"
    underlying_index: SPX
    cme_symbol: MES
    typical_atr_pts: 14
    typical_stop_pts: 8
    typical_target_pts: 16
    cot_commodity: "S&P 500 STOCK INDEX"
  MNQ:
    full_name: "Micro E-mini Nasdaq 100"
    underlying_index: NDX
    cme_symbol: MNQ
    typical_atr_pts: 60
    typical_stop_pts: 30
    typical_target_pts: 60
    cot_commodity: "NASDAQ MINI"
  MGC:
    full_name: "Micro Gold"
    underlying_index: null
    cme_symbol: MGC
    typical_atr_pts: 8
    typical_stop_pts: 5
    typical_target_pts: 10
    cot_commodity: "GOLD"
"""
    path = tmp_path / "instruments.yaml"
    path.write_text(content)
    return path
```

- [ ] **Step 3: Run pytest to verify package detected**

Run: `uv run pytest tests/reports/ -v --collect-only`
Expected: 0 tests collected, no import errors.

- [ ] **Step 4: Commit**

```bash
git add tests/reports/__init__.py tests/reports/conftest.py
git commit -m "test(reports): scaffold reports test package + fixtures"
```

---

## Task 3: IBClient — class skeleton + connection state

**Files:**
- Create: `src/daytrader/core/ib_client.py`
- Create: `tests/reports/test_ib_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/reports/test_ib_client.py` with:

```python
"""Unit tests for daytrader.core.ib_client.IBClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from daytrader.core.ib_client import IBClient


def test_ibclient_instantiates_with_defaults():
    """IBClient can be created with default host/port."""
    client = IBClient()
    assert client.host == "127.0.0.1"
    assert client.port == 4002  # IB Gateway live default
    assert client.client_id == 1
    assert client.is_healthy() is False  # not connected yet


def test_ibclient_custom_host_port():
    """IBClient accepts custom host/port/client_id."""
    client = IBClient(host="10.0.0.5", port=7497, client_id=42)
    assert client.host == "10.0.0.5"
    assert client.port == 7497
    assert client.client_id == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reports/test_ib_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daytrader.core.ib_client'`

- [ ] **Step 3: Write minimal implementation**

Create `src/daytrader/core/ib_client.py`:

```python
"""IBKR ib_insync wrapper.

Generic market-data only: bars, snapshots, connection lifecycle.
Futures-specific helpers (OI, term structure, settlement) live in
`reports/futures_data/ib_extensions.py` and accept an IBClient instance.

See spec §4.1 for full design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ib_insync import IB


class IBClient:
    """Singleton ib_insync wrapper, reused across reports."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib: IB | None = None

    def is_healthy(self) -> bool:
        """Return True iff connected to IB Gateway."""
        return self._ib is not None and self._ib.isConnected()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/reports/test_ib_client.py -v`
Expected: PASS — both tests green.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/ib_client.py tests/reports/test_ib_client.py
git commit -m "feat(reports): IBClient skeleton with connection state"
```

---

## Task 4: IBClient — connect / disconnect lifecycle

**Files:**
- Modify: `src/daytrader/core/ib_client.py`
- Modify: `tests/reports/test_ib_client.py`

- [ ] **Step 1: Add failing test for connect / disconnect**

Append to `tests/reports/test_ib_client.py`:

```python
def test_ibclient_connect_calls_ib_insync(monkeypatch):
    """connect() invokes ib_insync.IB().connect with our params."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    fake_ib_class = MagicMock(return_value=fake_ib)
    monkeypatch.setattr("daytrader.core.ib_client.IB", fake_ib_class)

    client = IBClient(host="1.2.3.4", port=9999, client_id=7)
    client.connect()

    fake_ib_class.assert_called_once()
    fake_ib.connect.assert_called_once_with(
        host="1.2.3.4", port=9999, clientId=7, timeout=10
    )
    assert client.is_healthy() is True


def test_ibclient_disconnect_closes_connection(monkeypatch):
    """disconnect() calls ib_insync.IB.disconnect and resets state."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    client.disconnect()

    fake_ib.disconnect.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/reports/test_ib_client.py -v`
Expected: FAIL — `connect`/`disconnect` not yet defined.

- [ ] **Step 3: Implement connect / disconnect**

Modify `src/daytrader/core/ib_client.py`. Replace the file contents with:

```python
"""IBKR ib_insync wrapper.

Generic market-data only: bars, snapshots, connection lifecycle.
Futures-specific helpers (OI, term structure, settlement) live in
`reports/futures_data/ib_extensions.py` and accept an IBClient instance.

See spec §4.1 for full design.
"""

from __future__ import annotations

from ib_insync import IB


class IBClient:
    """Singleton ib_insync wrapper, reused across reports."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib: IB | None = None

    def connect(self, timeout: int = 10) -> None:
        """Establish connection to IB Gateway. Idempotent."""
        if self._ib is None:
            self._ib = IB()
        if not self._ib.isConnected():
            self._ib.connect(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                timeout=timeout,
            )

    def disconnect(self) -> None:
        """Close connection. Idempotent."""
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()

    def reconnect(self) -> None:
        """Disconnect then reconnect. Idempotent."""
        self.disconnect()
        self.connect()

    def is_healthy(self) -> bool:
        """Return True iff connected to IB Gateway."""
        return self._ib is not None and self._ib.isConnected()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_ib_client.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/ib_client.py tests/reports/test_ib_client.py
git commit -m "feat(reports): IBClient connect/disconnect/reconnect"
```

---

## Task 5: IBClient — get_bars()

**Files:**
- Modify: `src/daytrader/core/ib_client.py`
- Modify: `tests/reports/test_ib_client.py`

- [ ] **Step 1: Add failing test**

Append to `tests/reports/test_ib_client.py`:

```python
from datetime import datetime, timezone


def test_ibclient_get_bars_returns_ohlcv(monkeypatch):
    """get_bars() returns list of OHLCV from ib_insync."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    fake_bar = MagicMock()
    fake_bar.date = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    fake_bar.open = 5240.00
    fake_bar.high = 5252.50
    fake_bar.low = 5238.25
    fake_bar.close = 5246.75
    fake_bar.volume = 142830

    fake_ib.reqHistoricalData.return_value = [fake_bar]

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    bars = client.get_bars(symbol="MES", timeframe="4H", bars=50)

    assert len(bars) == 1
    assert bars[0].open == 5240.00
    assert bars[0].close == 5246.75
    assert bars[0].volume == 142830

    # Verify the IB call
    fake_ib.reqHistoricalData.assert_called_once()
    call_kwargs = fake_ib.reqHistoricalData.call_args.kwargs
    assert call_kwargs["barSizeSetting"] == "4 hours"
    assert call_kwargs["durationStr"] == "8 D"  # 50 × 4H ≈ 8 days


def test_ibclient_get_bars_unsupported_timeframe_raises():
    """Unsupported timeframe raises ValueError."""
    client = IBClient()
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        client.get_bars(symbol="MES", timeframe="3H", bars=10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reports/test_ib_client.py -v`
Expected: FAIL — `get_bars` not defined.

- [ ] **Step 3: Implement `get_bars` and OHLCV dataclass**

Modify `src/daytrader/core/ib_client.py`. Add at top of file (after imports):

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class OHLCV:
    """One OHLCV bar."""
    timestamp: datetime  # bar end time, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


_TIMEFRAME_TO_IB_BAR_SIZE: dict[str, str] = {
    "1m": "1 min",
    "15m": "15 mins",
    "1H": "1 hour",
    "4H": "4 hours",
    "1D": "1 day",
    "1W": "1 week",
    "1M": "1 month",
}


def _duration_str(timeframe: str, bars: int) -> str:
    """Compute IB durationStr from desired (timeframe, bars).

    IB requires duration like '50 D' or '52 W'. We approximate.
    """
    if timeframe == "1m":
        return f"{bars * 60} S"
    if timeframe == "15m":
        return f"{bars * 15} S" if bars * 15 < 86400 else f"{(bars * 15) // 1440 + 1} D"
    if timeframe == "1H":
        return f"{(bars + 23) // 24 + 1} D"
    if timeframe == "4H":
        return f"{(bars * 4 + 23) // 24 + 1} D"
    if timeframe == "1D":
        return f"{bars} D"
    if timeframe == "1W":
        return f"{bars} W"
    if timeframe == "1M":
        return f"{bars} M"
    raise ValueError(f"Unsupported timeframe: {timeframe}")
```

Then add the `get_bars` method to `IBClient`:

```python
    def get_bars(
        self,
        symbol: str,
        timeframe: Literal["1m", "15m", "1H", "4H", "1D", "1W", "1M"] = "4H",
        bars: int = 50,
        end_time: datetime | None = None,
    ) -> list[OHLCV]:
        """Fetch historical bars from IB Gateway.

        Returns OHLCV list with timestamps in UTC (bar end times).
        """
        if timeframe not in _TIMEFRAME_TO_IB_BAR_SIZE:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if self._ib is None or not self._ib.isConnected():
            raise RuntimeError("IBClient is not connected; call connect() first")

        from ib_insync import ContFuture
        contract = ContFuture(symbol, "CME")  # MES/MNQ on CME, MGC on COMEX
        # COMEX vs CME exchange resolution handled by ContFuture for MGC too.
        ib_bars = self._ib.reqHistoricalData(
            contract,
            endDateTime=end_time or "",
            durationStr=_duration_str(timeframe, bars),
            barSizeSetting=_TIMEFRAME_TO_IB_BAR_SIZE[timeframe],
            whatToShow="TRADES",
            useRTH=False,
            formatDate=2,  # UTC seconds
        )
        return [
            OHLCV(
                timestamp=b.date,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in ib_bars
        ]
```

Update the import at the top to also import `Literal` from `typing` (already there) and add `from datetime import datetime` if missing. The full file imports should now be:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ib_insync import IB
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/reports/test_ib_client.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/ib_client.py tests/reports/test_ib_client.py
git commit -m "feat(reports): IBClient.get_bars + OHLCV dataclass"
```

---

## Task 6: IBClient — get_snapshot()

**Files:**
- Modify: `src/daytrader/core/ib_client.py`
- Modify: `tests/reports/test_ib_client.py`

- [ ] **Step 1: Add failing test**

Append to `tests/reports/test_ib_client.py`:

```python
def test_ibclient_get_snapshot_returns_current_quote(monkeypatch):
    """get_snapshot() returns current bid/ask/last."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    fake_ticker = MagicMock()
    fake_ticker.bid = 5246.50
    fake_ticker.ask = 5246.75
    fake_ticker.last = 5246.75
    fake_ticker.time = datetime(2026, 4, 25, 14, 30, tzinfo=timezone.utc)

    fake_ib.reqMktData.return_value = fake_ticker
    fake_ib.sleep = MagicMock()

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    snap = client.get_snapshot(symbol="MES")

    assert snap.bid == 5246.50
    assert snap.ask == 5246.75
    assert snap.last == 5246.75
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reports/test_ib_client.py::test_ibclient_get_snapshot_returns_current_quote -v`
Expected: FAIL — `get_snapshot` not defined.

- [ ] **Step 3: Implement Snapshot dataclass + get_snapshot**

In `src/daytrader/core/ib_client.py`, add the Snapshot dataclass after OHLCV:

```python
@dataclass(frozen=True)
class Snapshot:
    """Real-time market snapshot."""
    timestamp: datetime  # UTC
    bid: float
    ask: float
    last: float
```

Add `get_snapshot` method to `IBClient`:

```python
    def get_snapshot(self, symbol: str) -> Snapshot:
        """Fetch current bid/ask/last for the front-month continuous contract."""
        if self._ib is None or not self._ib.isConnected():
            raise RuntimeError("IBClient is not connected; call connect() first")

        from ib_insync import ContFuture
        contract = ContFuture(symbol, "CME")
        ticker = self._ib.reqMktData(contract, "", False, False)
        self._ib.sleep(1)  # wait for data tick
        return Snapshot(
            timestamp=ticker.time or datetime.now(),
            bid=float(ticker.bid) if ticker.bid else 0.0,
            ask=float(ticker.ask) if ticker.ask else 0.0,
            last=float(ticker.last) if ticker.last else 0.0,
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_ib_client.py -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/ib_client.py tests/reports/test_ib_client.py
git commit -m "feat(reports): IBClient.get_snapshot + Snapshot dataclass"
```

---

## Task 7: StateDB — schema initialization

**Files:**
- Create: `src/daytrader/core/state.py`
- Create: `tests/reports/test_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/reports/test_state.py`:

```python
"""Unit tests for daytrader.core.state.StateDB."""

from __future__ import annotations

import sqlite3

import pytest

from daytrader.core.state import StateDB


def test_statedb_initializes_schema(tmp_state_db):
    """StateDB.initialize() creates all required tables."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    conn = sqlite3.connect(str(tmp_state_db))
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    conn.close()

    expected = {
        "plans",
        "reports",
        "news_seen",
        "failures",
        "lock_in_status",
        "bar_cache",
    }
    assert expected.issubset(tables)


def test_statedb_initialize_idempotent(tmp_state_db):
    """Calling initialize() twice does not error."""
    db = StateDB(str(tmp_state_db))
    db.initialize()
    db.initialize()  # second call must not raise


def test_statedb_creates_parent_directory(tmp_path):
    """StateDB creates parent directory if missing."""
    nested = tmp_path / "subdir" / "state.db"
    db = StateDB(str(nested))
    db.initialize()
    assert nested.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: FAIL — `daytrader.core.state` does not exist.

- [ ] **Step 3: Implement StateDB**

Create `src/daytrader/core/state.py`:

```python
"""SQLite state DB for the reports system.

Stores: today's plans, report generation history, news dedup,
failure log, lock-in status snapshots, bar cache.

Separate from `core/db.py` (signals/trades) to avoid coupling.

See spec §4.4 for full schema.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    date TEXT NOT NULL,
    instrument TEXT NOT NULL,
    setup_name TEXT,
    direction TEXT,
    entry REAL,
    stop REAL,
    target REAL,
    r_unit_dollars REAL,
    invalidations TEXT,
    raw_plan_text TEXT,
    created_at TEXT NOT NULL,
    source_report_path TEXT,
    PRIMARY KEY (date, instrument)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    date TEXT NOT NULL,
    time_pt TEXT NOT NULL,
    time_et TEXT NOT NULL,
    obsidian_path TEXT,
    pdf_path TEXT,
    telegram_msg_ids TEXT,
    status TEXT NOT NULL,
    failure_reason TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cache_hit_rate REAL,
    duration_seconds REAL,
    estimated_cost_usd REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_date_type ON reports(date, report_type);

CREATE TABLE IF NOT EXISTS news_seen (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT,
    title TEXT,
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    impact_tag TEXT,
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    failure_stage TEXT NOT NULL,
    failure_reason TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS lock_in_status (
    snapshot_at TEXT PRIMARY KEY,
    trades_done INTEGER NOT NULL,
    trades_target INTEGER NOT NULL,
    cumulative_r REAL,
    last_trade_date TEXT,
    last_trade_r REAL,
    streak TEXT,
    breakdown_mes INTEGER,
    breakdown_mnq INTEGER,
    breakdown_mgc INTEGER
);

CREATE TABLE IF NOT EXISTS bar_cache (
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (instrument, timeframe, bar_time)
);
"""


class StateDB:
    """SQLite wrapper for reports system state."""

    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create all tables. Idempotent (uses IF NOT EXISTS)."""
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/state.py tests/reports/test_state.py
git commit -m "feat(reports): StateDB schema initialization (6 tables)"
```

---

## Task 8: StateDB — reports CRUD

**Files:**
- Modify: `src/daytrader/core/state.py`
- Modify: `tests/reports/test_state.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/reports/test_state.py`:

```python
from datetime import datetime, timezone


def test_statedb_insert_report_and_get(tmp_state_db):
    """insert_report() stores a row, get_report_by_id() retrieves it."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    rid = db.insert_report(
        report_type="premarket",
        date_et="2026-04-25",
        time_pt="06:00",
        time_et="09:00",
        status="pending",
        created_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
    )
    assert isinstance(rid, int)
    assert rid > 0

    row = db.get_report_by_id(rid)
    assert row["report_type"] == "premarket"
    assert row["date"] == "2026-04-25"
    assert row["status"] == "pending"


def test_statedb_update_report_status(tmp_state_db):
    """update_report_status() records final state and metrics."""
    db = StateDB(str(tmp_state_db))
    db.initialize()
    rid = db.insert_report(
        report_type="premarket",
        date_et="2026-04-25",
        time_pt="06:00",
        time_et="09:00",
        status="pending",
        created_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
    )

    db.update_report_status(
        rid,
        status="success",
        obsidian_path="/path/to/file.md",
        tokens_input=14000,
        tokens_output=5000,
        duration_seconds=18.4,
        estimated_cost_usd=0.55,
    )

    row = db.get_report_by_id(rid)
    assert row["status"] == "success"
    assert row["obsidian_path"] == "/path/to/file.md"
    assert row["tokens_input"] == 14000
    assert row["duration_seconds"] == pytest.approx(18.4)


def test_statedb_already_generated_today(tmp_state_db):
    """already_generated_today() supports idempotency check."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    assert db.already_generated_today("premarket", "2026-04-25") is False

    db.insert_report(
        report_type="premarket",
        date_et="2026-04-25",
        time_pt="06:00",
        time_et="09:00",
        status="success",
        created_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
    )

    assert db.already_generated_today("premarket", "2026-04-25") is True
    assert db.already_generated_today("eod", "2026-04-25") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: FAIL — methods don't exist yet.

- [ ] **Step 3: Implement reports CRUD**

Append to `src/daytrader/core/state.py` (inside the `StateDB` class):

```python
    # --- reports table ---

    def insert_report(
        self,
        report_type: str,
        date_et: str,
        time_pt: str,
        time_et: str,
        status: str,
        created_at: datetime,
    ) -> int:
        """Insert a pending/in-progress report row, return its id."""
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO reports
               (report_type, date, time_pt, time_et, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (report_type, date_et, time_pt, time_et, status,
             created_at.isoformat()),
        )
        conn.commit()
        return cur.lastrowid

    def get_report_by_id(self, report_id: int) -> sqlite3.Row | None:
        conn = self._get_conn()
        return conn.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()

    def update_report_status(
        self,
        report_id: int,
        status: str,
        obsidian_path: str | None = None,
        pdf_path: str | None = None,
        telegram_msg_ids: str | None = None,
        failure_reason: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
        cache_hit_rate: float | None = None,
        duration_seconds: float | None = None,
        estimated_cost_usd: float | None = None,
    ) -> None:
        """Update status and metrics for an existing report row."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE reports SET
                 status = ?,
                 obsidian_path = COALESCE(?, obsidian_path),
                 pdf_path = COALESCE(?, pdf_path),
                 telegram_msg_ids = COALESCE(?, telegram_msg_ids),
                 failure_reason = COALESCE(?, failure_reason),
                 tokens_input = COALESCE(?, tokens_input),
                 tokens_output = COALESCE(?, tokens_output),
                 cache_hit_rate = COALESCE(?, cache_hit_rate),
                 duration_seconds = COALESCE(?, duration_seconds),
                 estimated_cost_usd = COALESCE(?, estimated_cost_usd)
               WHERE id = ?""",
            (status, obsidian_path, pdf_path, telegram_msg_ids,
             failure_reason, tokens_input, tokens_output, cache_hit_rate,
             duration_seconds, estimated_cost_usd, report_id),
        )
        conn.commit()

    def already_generated_today(self, report_type: str, date_et: str) -> bool:
        """Idempotency check: did a successful report of this type run today?"""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT 1 FROM reports
               WHERE report_type = ? AND date = ? AND status = 'success'
               LIMIT 1""",
            (report_type, date_et),
        ).fetchone()
        return row is not None
```

You'll also need to add `from datetime import datetime` at the top of `state.py` if it's not already there. Update the imports:

```python
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/state.py tests/reports/test_state.py
git commit -m "feat(reports): StateDB reports CRUD (insert/get/update/idempotent check)"
```

---

## Task 9: StateDB — plans CRUD

**Files:**
- Modify: `src/daytrader/core/state.py`
- Modify: `tests/reports/test_state.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/reports/test_state.py`:

```python
import json


def test_statedb_save_and_get_plan(tmp_state_db):
    """save_plan + get_plan_for_date round-trip."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    db.save_plan(
        date_et="2026-04-25",
        instrument="MES",
        setup_name="ORB long",
        direction="long",
        entry=5240.0,
        stop=5232.0,
        target=5256.0,
        r_unit_dollars=8.0,
        invalidations=["price < 5232", "SPY < 580", "VIX > 18"],
        raw_plan_text="Long MES at 5240, stop 5232, target 5256.",
        source_report_path="/path/to/premarket.md",
        created_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
    )

    plan = db.get_plan_for_date("2026-04-25", "MES")
    assert plan is not None
    assert plan["setup_name"] == "ORB long"
    assert plan["entry"] == pytest.approx(5240.0)
    assert json.loads(plan["invalidations"]) == [
        "price < 5232", "SPY < 580", "VIX > 18"
    ]


def test_statedb_get_plan_returns_none_for_missing(tmp_state_db):
    db = StateDB(str(tmp_state_db))
    db.initialize()

    assert db.get_plan_for_date("2026-04-25", "MES") is None


def test_statedb_save_plan_replaces_on_same_key(tmp_state_db):
    """Saving same (date, instrument) twice keeps only latest."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    base_args = dict(
        date_et="2026-04-25",
        instrument="MES",
        direction="long",
        r_unit_dollars=8.0,
        invalidations=[],
        raw_plan_text="",
        source_report_path="",
        created_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
    )
    db.save_plan(setup_name="V1", entry=5240.0, stop=5232.0, target=5256.0, **base_args)
    db.save_plan(setup_name="V2", entry=5245.0, stop=5237.0, target=5261.0, **base_args)

    plan = db.get_plan_for_date("2026-04-25", "MES")
    assert plan["setup_name"] == "V2"
    assert plan["entry"] == pytest.approx(5245.0)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: 3 new tests FAIL — `save_plan`, `get_plan_for_date` not defined.

- [ ] **Step 3: Implement plans CRUD**

Add to `StateDB` class in `src/daytrader/core/state.py`. Also add `import json` at the top of the file (next to existing imports). Then add these methods:

```python
    # --- plans table ---

    def save_plan(
        self,
        date_et: str,
        instrument: str,
        setup_name: str,
        direction: str,
        entry: float,
        stop: float,
        target: float,
        r_unit_dollars: float,
        invalidations: list[str],
        raw_plan_text: str,
        source_report_path: str,
        created_at: datetime,
    ) -> None:
        """Insert or replace a plan for (date, instrument)."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO plans
               (date, instrument, setup_name, direction, entry, stop, target,
                r_unit_dollars, invalidations, raw_plan_text,
                created_at, source_report_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date_et, instrument, setup_name, direction,
             entry, stop, target, r_unit_dollars,
             json.dumps(invalidations), raw_plan_text,
             created_at.isoformat(), source_report_path),
        )
        conn.commit()

    def get_plan_for_date(
        self, date_et: str, instrument: str
    ) -> sqlite3.Row | None:
        conn = self._get_conn()
        return conn.execute(
            "SELECT * FROM plans WHERE date = ? AND instrument = ?",
            (date_et, instrument),
        ).fetchone()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/state.py tests/reports/test_state.py
git commit -m "feat(reports): StateDB plans CRUD (per (date, instrument))"
```

---

## Task 10: StateDB — news_seen dedup

**Files:**
- Modify: `src/daytrader/core/state.py`
- Modify: `tests/reports/test_state.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/reports/test_state.py`:

```python
def test_statedb_news_seen_dedup(tmp_state_db):
    """add_news returns True for new, False for already-seen."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    assert db.add_news(
        source="anthropic-web",
        external_id="abc123",
        url="https://example.com/a",
        title="FOMC raises rates",
        published_at=datetime(2026, 4, 25, 18, 0, tzinfo=timezone.utc),
        impact_tag="material",
        first_seen_at=datetime(2026, 4, 25, 19, 0, tzinfo=timezone.utc),
    ) is True

    # Same news again
    assert db.add_news(
        source="anthropic-web",
        external_id="abc123",
        url="https://example.com/a",
        title="FOMC raises rates",
        published_at=datetime(2026, 4, 25, 18, 0, tzinfo=timezone.utc),
        impact_tag="material",
        first_seen_at=datetime(2026, 4, 25, 20, 0, tzinfo=timezone.utc),
    ) is False
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: FAIL — `add_news` not defined.

- [ ] **Step 3: Implement add_news**

Add to `StateDB` in `src/daytrader/core/state.py`:

```python
    # --- news_seen table ---

    def add_news(
        self,
        source: str,
        external_id: str,
        url: str | None,
        title: str | None,
        published_at: datetime | None,
        first_seen_at: datetime,
        impact_tag: str | None = None,
    ) -> bool:
        """Insert news row. Returns True if new, False if (source, external_id)
        already present."""
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT 1 FROM news_seen WHERE source = ? AND external_id = ? LIMIT 1",
            (source, external_id),
        ).fetchone()
        if existing is not None:
            return False
        conn.execute(
            """INSERT INTO news_seen
               (source, external_id, url, title, published_at,
                first_seen_at, impact_tag)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source, external_id, url, title,
             published_at.isoformat() if published_at else None,
             first_seen_at.isoformat(), impact_tag),
        )
        conn.commit()
        return True
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/state.py tests/reports/test_state.py
git commit -m "feat(reports): StateDB news_seen dedup"
```

---

## Task 11: StateDB — failures CRUD

**Files:**
- Modify: `src/daytrader/core/state.py`
- Modify: `tests/reports/test_state.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/reports/test_state.py`:

```python
def test_statedb_log_failure_and_resolve(tmp_state_db):
    """log_failure stores; resolve_failure marks resolved_at."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    fid = db.log_failure(
        report_type="premarket",
        scheduled_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
        failure_stage="ai",
        failure_reason="anthropic timeout after 3 retries",
        retry_count=3,
    )
    assert fid > 0

    unresolved = db.list_unresolved_failures()
    assert len(unresolved) == 1
    assert unresolved[0]["failure_stage"] == "ai"

    db.resolve_failure(fid, resolved_at=datetime(2026, 4, 25, 13, 30, tzinfo=timezone.utc))
    assert db.list_unresolved_failures() == []
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: FAIL — failure methods missing.

- [ ] **Step 3: Implement**

Add to `StateDB`:

```python
    # --- failures table ---

    def log_failure(
        self,
        report_type: str,
        scheduled_at: datetime,
        failure_stage: str,
        failure_reason: str,
        retry_count: int,
    ) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO failures
               (report_type, scheduled_at, failure_stage,
                failure_reason, retry_count)
               VALUES (?, ?, ?, ?, ?)""",
            (report_type, scheduled_at.isoformat(),
             failure_stage, failure_reason, retry_count),
        )
        conn.commit()
        return cur.lastrowid

    def list_unresolved_failures(self) -> list[sqlite3.Row]:
        conn = self._get_conn()
        return list(conn.execute(
            "SELECT * FROM failures WHERE resolved_at IS NULL ORDER BY id"
        ).fetchall())

    def resolve_failure(self, failure_id: int, resolved_at: datetime) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE failures SET resolved_at = ? WHERE id = ?",
            (resolved_at.isoformat(), failure_id),
        )
        conn.commit()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/state.py tests/reports/test_state.py
git commit -m "feat(reports): StateDB failure log + resolve"
```

---

## Task 12: StateDB — lock_in_status snapshot

**Files:**
- Modify: `src/daytrader/core/state.py`
- Modify: `tests/reports/test_state.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/reports/test_state.py`:

```python
def test_statedb_save_lock_in_snapshot_and_latest(tmp_state_db):
    db = StateDB(str(tmp_state_db))
    db.initialize()

    db.save_lock_in_snapshot(
        snapshot_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
        trades_done=7,
        trades_target=30,
        cumulative_r=1.5,
        last_trade_date="2026-04-23",
        last_trade_r=-0.5,
        streak="2L1W",
        breakdown={"MES": 4, "MNQ": 2, "MGC": 1},
    )

    latest = db.latest_lock_in_snapshot()
    assert latest is not None
    assert latest["trades_done"] == 7
    assert latest["breakdown_mes"] == 4
    assert latest["breakdown_mnq"] == 2
    assert latest["breakdown_mgc"] == 1
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: FAIL — methods missing.

- [ ] **Step 3: Implement**

Add to `StateDB`:

```python
    # --- lock_in_status table ---

    def save_lock_in_snapshot(
        self,
        snapshot_at: datetime,
        trades_done: int,
        trades_target: int,
        cumulative_r: float | None,
        last_trade_date: str | None,
        last_trade_r: float | None,
        streak: str | None,
        breakdown: dict[str, int],
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO lock_in_status
               (snapshot_at, trades_done, trades_target, cumulative_r,
                last_trade_date, last_trade_r, streak,
                breakdown_mes, breakdown_mnq, breakdown_mgc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_at.isoformat(),
                trades_done,
                trades_target,
                cumulative_r,
                last_trade_date,
                last_trade_r,
                streak,
                breakdown.get("MES", 0),
                breakdown.get("MNQ", 0),
                breakdown.get("MGC", 0),
            ),
        )
        conn.commit()

    def latest_lock_in_snapshot(self) -> sqlite3.Row | None:
        conn = self._get_conn()
        return conn.execute(
            "SELECT * FROM lock_in_status ORDER BY snapshot_at DESC LIMIT 1"
        ).fetchone()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/state.py tests/reports/test_state.py
git commit -m "feat(reports): StateDB lock-in snapshot per-instrument breakdown"
```

---

## Task 13: StateDB — bar_cache CRUD

**Files:**
- Modify: `src/daytrader/core/state.py`
- Modify: `tests/reports/test_state.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/reports/test_state.py`:

```python
def test_statedb_cache_and_load_bars(tmp_state_db):
    db = StateDB(str(tmp_state_db))
    db.initialize()

    bars_in = [
        ("MES", "1D", "2026-04-23T22:00:00+00:00", 5240.0, 5252.0, 5238.0, 5246.0, 142000.0),
        ("MES", "1D", "2026-04-24T22:00:00+00:00", 5246.0, 5260.0, 5244.0, 5258.0, 138000.0),
    ]
    db.cache_bars(bars_in)

    out = db.load_cached_bars("MES", "1D")
    assert len(out) == 2
    assert out[0]["close"] == pytest.approx(5246.0)
    assert out[1]["close"] == pytest.approx(5258.0)


def test_statedb_cache_replaces_on_same_key(tmp_state_db):
    db = StateDB(str(tmp_state_db))
    db.initialize()

    db.cache_bars([
        ("MES", "1D", "2026-04-23T22:00:00+00:00", 5240.0, 5252.0, 5238.0, 5246.0, 142000.0),
    ])
    # Replace with corrected close
    db.cache_bars([
        ("MES", "1D", "2026-04-23T22:00:00+00:00", 5240.0, 5252.0, 5238.0, 5247.0, 145000.0),
    ])

    out = db.load_cached_bars("MES", "1D")
    assert len(out) == 1
    assert out[0]["close"] == pytest.approx(5247.0)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: FAIL — bar_cache methods missing.

- [ ] **Step 3: Implement**

Add to `StateDB`:

```python
    # --- bar_cache table ---

    def cache_bars(
        self,
        bars: list[tuple[str, str, str, float, float, float, float, float]],
    ) -> None:
        """Insert/replace cached bars. Each tuple:
        (instrument, timeframe, bar_time_iso, open, high, low, close, volume)
        """
        conn = self._get_conn()
        conn.executemany(
            """INSERT OR REPLACE INTO bar_cache
               (instrument, timeframe, bar_time, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            bars,
        )
        conn.commit()

    def load_cached_bars(
        self, instrument: str, timeframe: str
    ) -> list[sqlite3.Row]:
        conn = self._get_conn()
        return list(conn.execute(
            """SELECT * FROM bar_cache
               WHERE instrument = ? AND timeframe = ?
               ORDER BY bar_time ASC""",
            (instrument, timeframe),
        ).fetchall())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_state.py -v`
Expected: 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/state.py tests/reports/test_state.py
git commit -m "feat(reports): StateDB bar cache (instrument × timeframe)"
```

---

## Task 14: instruments.yaml + InstrumentConfig loader

**Files:**
- Create: `config/instruments.yaml`
- Create: `src/daytrader/reports/__init__.py`
- Create: `src/daytrader/reports/instruments/__init__.py`
- Create: `src/daytrader/reports/instruments/definitions.py`
- Create: `tests/reports/test_instruments.py`

- [ ] **Step 1: Create instruments.yaml**

Create `config/instruments.yaml`:

```yaml
# Multi-instrument futures definitions for the reports system.
# See spec §4.6.

instruments:
  MES:
    full_name: "Micro E-mini S&P 500"
    underlying_index: SPX
    cme_symbol: MES
    typical_atr_pts: 14
    typical_stop_pts: 8
    typical_target_pts: 16
    cot_commodity: "S&P 500 STOCK INDEX"

  MNQ:
    full_name: "Micro E-mini Nasdaq 100"
    underlying_index: NDX
    cme_symbol: MNQ
    typical_atr_pts: 60
    typical_stop_pts: 30
    typical_target_pts: 60
    cot_commodity: "NASDAQ MINI"

  MGC:
    full_name: "Micro Gold"
    underlying_index: null
    cme_symbol: MGC
    typical_atr_pts: 8
    typical_stop_pts: 5
    typical_target_pts: 10
    cot_commodity: "GOLD"
```

- [ ] **Step 2: Create reports module markers**

Create `src/daytrader/reports/__init__.py`:

```python
"""Reports subsystem: multi-cadence multi-instrument trading reports.

See docs/superpowers/specs/2026-04-25-reports-system-design.md.
"""
```

Create `src/daytrader/reports/instruments/__init__.py`:

```python
"""Instrument configuration loader."""
```

- [ ] **Step 3: Write failing test**

Create `tests/reports/test_instruments.py`:

```python
"""Tests for instruments config loader."""

from __future__ import annotations

import pytest

from daytrader.reports.instruments.definitions import (
    InstrumentConfig,
    load_instruments,
)


def test_load_instruments_returns_three_known_symbols(fixture_instruments_yaml):
    cfg = load_instruments(str(fixture_instruments_yaml))
    assert set(cfg.keys()) == {"MES", "MNQ", "MGC"}


def test_load_instruments_parses_mes_correctly(fixture_instruments_yaml):
    cfg = load_instruments(str(fixture_instruments_yaml))
    mes = cfg["MES"]
    assert isinstance(mes, InstrumentConfig)
    assert mes.full_name == "Micro E-mini S&P 500"
    assert mes.underlying_index == "SPX"
    assert mes.cme_symbol == "MES"
    assert mes.typical_atr_pts == 14
    assert mes.cot_commodity == "S&P 500 STOCK INDEX"


def test_load_instruments_handles_null_underlying(fixture_instruments_yaml):
    cfg = load_instruments(str(fixture_instruments_yaml))
    mgc = cfg["MGC"]
    assert mgc.underlying_index is None


def test_load_instruments_missing_file_raises(tmp_path):
    missing = tmp_path / "nonexistent.yaml"
    with pytest.raises(FileNotFoundError):
        load_instruments(str(missing))
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/reports/test_instruments.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 5: Implement**

Create `src/daytrader/reports/instruments/definitions.py`:

```python
"""Instrument configuration loader.

Reads `config/instruments.yaml` (or another path) into `InstrumentConfig`
pydantic models keyed by symbol (MES, MNQ, MGC).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class InstrumentConfig(BaseModel):
    """Per-instrument futures parameters."""
    full_name: str
    underlying_index: str | None
    cme_symbol: str
    typical_atr_pts: float
    typical_stop_pts: float
    typical_target_pts: float
    cot_commodity: str


def load_instruments(path: str) -> dict[str, InstrumentConfig]:
    """Load instruments.yaml into a dict of symbol -> InstrumentConfig.

    Raises FileNotFoundError if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Instruments config not found: {path}")
    raw = yaml.safe_load(p.read_text())
    instruments_raw = raw.get("instruments", {})
    return {
        symbol: InstrumentConfig(**params)
        for symbol, params in instruments_raw.items()
    }
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/reports/test_instruments.py -v`
Expected: 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add config/instruments.yaml src/daytrader/reports/__init__.py src/daytrader/reports/instruments/__init__.py src/daytrader/reports/instruments/definitions.py tests/reports/test_instruments.py
git commit -m "feat(reports): instruments.yaml + InstrumentConfig loader (MES/MNQ/MGC)"
```

---

## Task 15: ReportsConfig added to core/config.py (additive)

**Files:**
- Modify: `src/daytrader/core/config.py` (additive — no existing code changes)
- Modify: `config/default.yaml` (additive)

- [ ] **Step 1: Inspect current config.py to know where to append**

Run: `uv run grep -n 'class DayTraderConfig' src/daytrader/core/config.py`
Expected: shows the line where DayTraderConfig is defined (around line 72).

- [ ] **Step 2: Append ReportsConfig pydantic model**

Open `src/daytrader/core/config.py`. Locate the `DayTraderConfig` class definition (the merged top-level config). Add a new `ReportsConfig` class **above** it, then add a `reports` field to `DayTraderConfig`.

Add **after** `JournalConfig` (around line 70) and **before** `DayTraderConfig`:

```python
class ReportsObsidianConfig(BaseModel):
    intraday_folder: str = "Daily/Intraday"
    eod_folder: str = "Daily/EOD"
    night_folder: str = "Daily/Night"


class ReportsIBConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4002  # IB Gateway live default; paper is 4001
    client_id: int = 1


class ReportsConfig(BaseModel):
    enabled: bool = False  # off by default until Phase 7 wiring
    state_db_path: str = "data/state.db"
    instruments_yaml: str = "config/instruments.yaml"
    obsidian: ReportsObsidianConfig = ReportsObsidianConfig()
    ib: ReportsIBConfig = ReportsIBConfig()
```

Then add to `DayTraderConfig` class **at the end of its field list**:

```python
    reports: ReportsConfig = ReportsConfig()
```

So the resulting class body is:

```python
class DayTraderConfig(BaseModel):
    database: DatabaseConfig = DatabaseConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    obsidian: ObsidianConfig = ObsidianConfig()
    premarket: PremarketConfig = PremarketConfig()
    backtest: BacktestConfig = BacktestConfig()
    journal: JournalConfig = JournalConfig()
    reports: ReportsConfig = ReportsConfig()
```

- [ ] **Step 3: Append to config/default.yaml**

Append to the end of `config/default.yaml`:

```yaml

reports:
  enabled: false
  state_db_path: data/state.db
  instruments_yaml: config/instruments.yaml
  obsidian:
    intraday_folder: Daily/Intraday
    eod_folder: Daily/EOD
    night_folder: Daily/Night
  ib:
    host: 127.0.0.1
    port: 4002
    client_id: 1
```

- [ ] **Step 4: Run all tests to ensure no regression**

Run: `uv run pytest tests/ -x --ignore=tests/research`
Expected: existing tests still pass; reports tests still pass.

- [ ] **Step 5: Verify config loads**

Run: `uv run python -c "from daytrader.core.config import load_config; from pathlib import Path; cfg = load_config(default_config=Path('config/default.yaml'), user_config=Path('config/user.yaml')); print(cfg.reports.ib.port)"`
Expected: prints `4002` without error.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/core/config.py config/default.yaml
git commit -m "feat(reports): add ReportsConfig pydantic model + default.yaml entries"
```

---

## Task 16: Secrets loader (Anthropic key + Telegram token)

**Files:**
- Create: `config/secrets.yaml.example`
- Modify: `.gitignore`
- Create: `src/daytrader/reports/core/__init__.py`
- Create: `src/daytrader/reports/core/secrets.py`
- Create: `tests/reports/test_secrets.py`

- [ ] **Step 1: Create secrets template**

Create `config/secrets.yaml.example`:

```yaml
# Copy this file to config/secrets.yaml and fill in values.
# config/secrets.yaml is gitignored.

anthropic:
  api_key: "sk-ant-XXXXXXXXXXXXXXXXX"

telegram:
  bot_token: "123456789:ABCDEF..."  # @BotFather
  chat_id: "12345678"               # your private chat with the bot
```

- [ ] **Step 2: Add to .gitignore**

Run this command to verify .gitignore exists:

Run: `cat .gitignore | head -5`

Append to `.gitignore`:

```
# Secrets — never commit
config/secrets.yaml
```

- [ ] **Step 3: Create reports/core marker**

Create `src/daytrader/reports/core/__init__.py`:

```python
"""Reports core: shared utilities (AI, secrets, context, prompt)."""
```

- [ ] **Step 4: Write failing tests**

Create `tests/reports/test_secrets.py`:

```python
"""Tests for secrets loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.core.secrets import (
    SecretsConfig,
    load_secrets,
    SecretsError,
)


def test_load_secrets_full_file(tmp_path):
    p = tmp_path / "secrets.yaml"
    p.write_text("""
anthropic:
  api_key: "sk-ant-test"
telegram:
  bot_token: "123:abc"
  chat_id: "456"
""")
    s = load_secrets(str(p))
    assert isinstance(s, SecretsConfig)
    assert s.anthropic_api_key == "sk-ant-test"
    assert s.telegram_bot_token == "123:abc"
    assert s.telegram_chat_id == "456"


def test_load_secrets_missing_file_raises(tmp_path):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(SecretsError, match="not found"):
        load_secrets(str(missing))


def test_load_secrets_missing_anthropic_key_raises(tmp_path):
    p = tmp_path / "secrets.yaml"
    p.write_text("""
telegram:
  bot_token: "123:abc"
  chat_id: "456"
""")
    with pytest.raises(SecretsError, match="anthropic"):
        load_secrets(str(p))


def test_load_secrets_missing_telegram_raises(tmp_path):
    p = tmp_path / "secrets.yaml"
    p.write_text("""
anthropic:
  api_key: "sk-ant-test"
""")
    with pytest.raises(SecretsError, match="telegram"):
        load_secrets(str(p))
```

- [ ] **Step 5: Run tests to verify failure**

Run: `uv run pytest tests/reports/test_secrets.py -v`
Expected: FAIL — module not implemented.

- [ ] **Step 6: Implement secrets loader**

Create `src/daytrader/reports/core/secrets.py`:

```python
"""Secrets loader for the reports system.

Reads `config/secrets.yaml` (gitignored). Fails loudly on missing fields
to avoid silent fallback to broken state at runtime.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class SecretsError(Exception):
    """Raised when secrets cannot be loaded or are incomplete."""


class SecretsConfig(BaseModel):
    """All secrets needed by the reports system."""
    anthropic_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str


def load_secrets(path: str) -> SecretsConfig:
    p = Path(path)
    if not p.exists():
        raise SecretsError(f"Secrets file not found: {path}")
    raw = yaml.safe_load(p.read_text()) or {}

    anthropic = raw.get("anthropic", {})
    if not anthropic.get("api_key"):
        raise SecretsError("Missing anthropic.api_key in secrets.yaml")

    telegram = raw.get("telegram", {})
    if not telegram.get("bot_token") or not telegram.get("chat_id"):
        raise SecretsError("Missing telegram.bot_token or telegram.chat_id")

    return SecretsConfig(
        anthropic_api_key=anthropic["api_key"],
        telegram_bot_token=telegram["bot_token"],
        telegram_chat_id=str(telegram["chat_id"]),
    )
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/reports/test_secrets.py -v`
Expected: 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add .gitignore config/secrets.yaml.example src/daytrader/reports/core/__init__.py src/daytrader/reports/core/secrets.py tests/reports/test_secrets.py
git commit -m "feat(reports): SecretsConfig loader (Anthropic + Telegram)"
```

---

## Task 17: CLI scaffolding — `daytrader reports dry-run`

**Files:**
- Create: `src/daytrader/cli/reports.py`
- Modify: `src/daytrader/cli/main.py`
- Create: `tests/cli/__init__.py` (if not present)
- Create: `tests/cli/test_reports_cli.py`

- [ ] **Step 1: Verify tests/cli/ marker**

Run: `ls tests/cli/__init__.py 2>/dev/null || echo missing`

If output is `missing`, create `tests/cli/__init__.py`:

```python
"""Tests for daytrader.cli command groups."""
```

- [ ] **Step 2: Write failing CLI test**

Create `tests/cli/test_reports_cli.py`:

```python
"""Smoke tests for the `daytrader reports` CLI group."""

from __future__ import annotations

from click.testing import CliRunner

from daytrader.cli.main import cli


def test_reports_group_registered():
    """`daytrader reports --help` lists the dry-run subcommand."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "--help"])
    assert result.exit_code == 0
    assert "dry-run" in result.output


def test_reports_dry_run_premarket_executes():
    """dry-run --type premarket runs without touching network/disk side effects."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "dry-run", "--type", "premarket"])
    assert result.exit_code == 0
    assert "premarket" in result.output.lower()
    assert "dry-run complete" in result.output.lower()


def test_reports_dry_run_unknown_type_fails():
    """Unknown --type returns non-zero exit and lists valid types."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "dry-run", "--type", "bogus"])
    assert result.exit_code != 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_reports_cli.py -v`
Expected: FAIL — `daytrader reports` group not registered.

- [ ] **Step 4: Create cli/reports.py**

Create `src/daytrader/cli/reports.py`:

```python
"""CLI command group `daytrader reports`.

Phase 1 provides a dry-run subcommand that exercises the foundation:
config load + IB connection (or skip in dry-run) + state DB init.

Generation logic (Phase 2+) will plug into report-type handlers later.
"""

from __future__ import annotations

import click


VALID_TYPES = (
    "premarket",
    "intraday-4h-1",
    "intraday-4h-2",
    "eod",
    "night",
    "asia",
    "weekly",
)


@click.group()
def reports() -> None:
    """Multi-cadence trading reports system."""


@reports.command("dry-run")
@click.option(
    "--type",
    "report_type",
    required=True,
    type=click.Choice(VALID_TYPES, case_sensitive=False),
    help="Report type to dry-run.",
)
def dry_run(report_type: str) -> None:
    """Dry-run a report-type pipeline (no network / file side effects).

    Phase 1 scope: prints the report type and exits successfully.
    Later phases plug in real fetch/AI/delivery steps with --no-side-effects flag.
    """
    click.echo(f"[dry-run] report_type={report_type}")
    click.echo("[dry-run] config load: OK (Phase 1 stub)")
    click.echo("[dry-run] state DB init: OK (Phase 1 stub)")
    click.echo("[dry-run] IB connection: skipped (Phase 1 stub)")
    click.echo("[dry-run] AI generation: skipped (Phase 1 stub)")
    click.echo("[dry-run] delivery: skipped (Phase 1 stub)")
    click.echo("[dry-run] dry-run complete")
```

- [ ] **Step 5: Register the group in cli/main.py**

Open `src/daytrader/cli/main.py`. At the bottom of the file (after the existing `journal.add_command(...)` registrations), add:

```python


from daytrader.cli.reports import reports as reports_group  # noqa: E402

cli.add_command(reports_group)
```

This is **strictly additive** — no existing lines change.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/cli/test_reports_cli.py -v`
Expected: 3 tests PASS.

- [ ] **Step 7: Verify CLI works manually**

Run: `uv run daytrader reports --help`
Expected: shows `dry-run` subcommand.

Run: `uv run daytrader reports dry-run --type premarket`
Expected: 6 lines of `[dry-run] ...` ending in `dry-run complete`.

- [ ] **Step 8: Commit**

```bash
git add src/daytrader/cli/reports.py src/daytrader/cli/main.py tests/cli/__init__.py tests/cli/test_reports_cli.py
git commit -m "feat(reports): CLI scaffolding daytrader reports dry-run"
```

---

## Task 18: scripts/run_report.py — launchd entry point skeleton

**Files:**
- Create: `scripts/run_report.py`
- Create: `tests/scripts/__init__.py`
- Create: `tests/scripts/test_run_report.py`

- [ ] **Step 1: Create tests/scripts marker**

Run: `ls tests/scripts/__init__.py 2>/dev/null || echo missing`

If missing, create `tests/scripts/__init__.py`:

```python
"""Tests for top-level scripts/ entry points."""
```

- [ ] **Step 2: Write failing test**

Create `tests/scripts/test_run_report.py`:

```python
"""Tests for scripts/run_report.py — launchd entry point."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "run_report.py"


def test_run_report_help_succeeds():
    """run_report.py --help prints usage and exits 0."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--type" in result.stdout


def test_run_report_missing_type_fails():
    """No --type argument → non-zero exit."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_run_report_unknown_type_fails():
    """Unknown --type → non-zero exit."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--type", "bogus"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_run_report_premarket_dry_succeeds(tmp_path):
    """Phase 1: --type premarket --dry exits 0 and prints expected lines."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--type", "premarket", "--dry"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "report_type=premarket" in result.stdout
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/scripts/test_run_report.py -v`
Expected: FAIL — `scripts/run_report.py` does not exist.

- [ ] **Step 4: Create the script**

Create `scripts/run_report.py`:

```python
#!/usr/bin/env python3
"""launchd entry point for report generation.

Phase 1: argparse + lock acquisition + delegation to CLI dry-run.
Later phases plug in the real pipeline (IB → AI → Obsidian → Telegram).

Usage:
    scripts/run_report.py --type premarket
    scripts/run_report.py --type premarket --dry   # Phase 1 stub mode
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_DIR = PROJECT_ROOT / "data" / "locks"

VALID_TYPES = (
    "premarket",
    "intraday-4h-1",
    "intraday-4h-2",
    "eod",
    "night",
    "asia",
    "weekly",
)


def _acquire_lock(report_type: str) -> int:
    """Acquire an exclusive lock for this report type.

    Returns the file descriptor; caller must keep it open until done.
    Raises SystemExit if another instance is running.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"{report_type}.lock"
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        print(
            f"[run_report] another instance of {report_type} is running; exit",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return fd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a scheduled report.")
    parser.add_argument(
        "--type",
        required=True,
        choices=VALID_TYPES,
        help="Report type to generate.",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Phase 1 dry-run: skip IB / AI / delivery, print stub progress.",
    )
    args = parser.parse_args()

    lock_fd = _acquire_lock(args.type)
    try:
        if args.dry:
            print(f"[run_report] report_type={args.type}")
            print("[run_report] (Phase 1 stub) all stages skipped")
            print("[run_report] complete")
            return 0
        # Phase 2+ wiring lands here.
        print(f"[run_report] report_type={args.type}")
        print("[run_report] full pipeline not yet implemented (Phase 2+)")
        return 0
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
```

Make it executable:

Run: `chmod +x scripts/run_report.py`

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/scripts/test_run_report.py -v`
Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_report.py tests/scripts/__init__.py tests/scripts/test_run_report.py
git commit -m "feat(reports): scripts/run_report.py launchd entry skeleton + lock"
```

---

## Task 19: IB Gateway operational setup documentation

**Files:**
- Create: `docs/ops/ib-gateway-setup.md`

- [ ] **Step 1: Create the doc**

Create `docs/ops/ib-gateway-setup.md`:

```markdown
# IB Gateway + IBC Operational Setup

This doc covers the manual one-time setup needed to run the Phase 1+ reports system. Once complete, the system can fetch market data without human intervention 24/7.

## Prerequisites

- IBKR account (paper or live)
- CME Real-time Market Data subscription (for MES/MNQ; user already has)
- COMEX Real-time Market Data subscription (for MGC) — verify under Account → Market Data Subscriptions
- macOS 12+ (other platforms work but ops docs assume macOS)
- Java 8 or 17 (IB Gateway requirement; install via Homebrew if missing)

## Step 1: Install IB Gateway

1. Download "IB Gateway — Stable" from <https://www.interactivebrokers.com/en/trading/ibgateway-stable.php>
2. Install to `/Applications/IB Gateway/<version>/`
3. Launch once manually:
   - Choose "IB Gateway" mode (not TWS)
   - Mode: Live (port 4002) or Paper (port 4001) — pick based on your trading account
   - Sign in with your IBKR username/password
   - Accept terms; let the Gateway initialize
4. Quit IB Gateway.

## Step 2: Install IBC (IB Controller)

IBC handles the IB Gateway's daily logout/reconnect, 2FA prompts, and crash recovery. It's the standard solution for headless 24/7 IB Gateway operation.

1. Download from <https://github.com/IbcAlpha/IBC/releases> (latest stable release)
2. Extract to `~/IBC/`
3. Edit `~/IBC/config.ini`:
   - Set `IbLoginId=<your-username>`
   - Set `IbPassword=<your-password>` (or use the alternate keychain method below)
   - Set `TradingMode=live` (or `paper`)
   - Set `IbDir=/Applications/IB Gateway/<version>` (path to your install)
   - Enable `ReadOnlyApi=no` (Phase 1 reads only, but later phases may need full access for OI/COT)
4. (Recommended) Use macOS Keychain for password instead of plaintext:
   - Set `PasswordEncryption=yes` and use `~/IBC/scripts/keychain.sh` to store the password securely.

## Step 3: Test the launch script

1. Run IBC with a dry-run flag to verify config:

   ```bash
   ~/IBC/scripts/displaybannerandlaunch.sh
   ```

2. Wait ~30 seconds. The Gateway window should appear and auto-login.
3. Verify the Gateway is listening on port 4002 (live) or 4001 (paper):

   ```bash
   nc -zv 127.0.0.1 4002
   ```

   Expected: `Connection to 127.0.0.1 port 4002 [tcp/*] succeeded!`

4. From this repo, test the connection:

   ```bash
   uv run python -c "from daytrader.core.ib_client import IBClient; c = IBClient(); c.connect(); print('healthy:', c.is_healthy()); c.disconnect()"
   ```

   Expected: `healthy: True`

## Step 4: launchd plist (Phase 7 will add this; documenting the path here)

When Phase 7 lands, a launchd plist at `scripts/launchd/com.daytrader.ibgateway.plist` will:
- Launch IBC at boot
- KeepAlive=true (auto-restart on crash)
- Redirect stdout/stderr to `data/logs/launchd/ibgateway.{out,err}`

For Phase 1, you can manually run IBC during dev sessions and quit when done.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Login failed: 2FA required" | IBC config missing 2FA setup | See IBC README for SMS/IBKey/Mobile config |
| Connection refused on port 4002 | Gateway not running | Re-run IBC launch script |
| `IB Gateway requires re-authentication` daily | Default behavior | IBC's `RestartTime` setting handles this; defaults to 03:00 |
| `Pacing violation` errors | Too many IB requests too fast | Reduce concurrency in `core/ib_client.py` (Phase 2+) |
| MGC bars empty | COMEX subscription missing | Add COMEX Top of Book ($1.50/mo) in Account → Market Data |

## References

- IBC documentation: <https://github.com/IbcAlpha/IBC/blob/master/userguide.md>
- ib_insync docs: <https://ib-insync.readthedocs.io/>
- IB Gateway port reference: 4001 (paper), 4002 (live), 7496 (TWS live), 7497 (TWS paper)
```

- [ ] **Step 2: Verify markdown renders cleanly**

Run: `head -20 docs/ops/ib-gateway-setup.md`
Expected: clean markdown, no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add docs/ops/ib-gateway-setup.md
git commit -m "docs(reports): IB Gateway + IBC operational setup guide"
```

---

## Task 20: Final integration smoke test

**Files:**
- Modify: `tests/cli/test_reports_cli.py`
- Verify: full test suite passes

- [ ] **Step 1: Add an end-to-end smoke test**

Append to `tests/cli/test_reports_cli.py`:

```python
def test_reports_dry_run_all_types_succeed():
    """Each valid --type runs dry-run successfully."""
    runner = CliRunner()
    valid_types = [
        "premarket",
        "intraday-4h-1",
        "intraday-4h-2",
        "eod",
        "night",
        "asia",
        "weekly",
    ]
    for t in valid_types:
        result = runner.invoke(cli, ["reports", "dry-run", "--type", t])
        assert result.exit_code == 0, f"failed for type={t}: {result.output}"
        assert "dry-run complete" in result.output.lower()
```

- [ ] **Step 2: Run the full reports test suite**

Run: `uv run pytest tests/reports/ tests/cli/test_reports_cli.py tests/scripts/test_run_report.py -v`
Expected: all tests PASS.

- [ ] **Step 3: Run the entire project test suite to verify no regression**

Run: `uv run pytest tests/ -x --ignore=tests/research`
Expected: existing premarket / journal / core tests still pass; new reports tests pass.

- [ ] **Step 4: Verify the dry-run CLI manually**

Run: `uv run daytrader reports dry-run --type weekly`
Expected:
```
[dry-run] report_type=weekly
[dry-run] config load: OK (Phase 1 stub)
[dry-run] state DB init: OK (Phase 1 stub)
[dry-run] IB connection: skipped (Phase 1 stub)
[dry-run] AI generation: skipped (Phase 1 stub)
[dry-run] delivery: skipped (Phase 1 stub)
[dry-run] dry-run complete
```

- [ ] **Step 5: Commit**

```bash
git add tests/cli/test_reports_cli.py
git commit -m "test(reports): smoke-test all 7 report types via dry-run"
```

---

## Task 21: Phase 1 completion — verify acceptance criteria

**Files:**
- None (verification only)

- [ ] **Step 1: Verify Phase 1 acceptance criteria from spec §9 Phase 1**

Phase 1 deliverable per spec §9:
> Foundation (`core/ib_client.py`, `core/state.py`, IB Gateway + IBC setup, dry-run scaffolding)

Verify each:

1. `core/ib_client.py` exists with connect/disconnect/get_bars/get_snapshot/is_healthy/reconnect:
   - Run: `uv run python -c "from daytrader.core.ib_client import IBClient; c = IBClient(); print(dir(c))"`
   - Expected: lists `connect`, `disconnect`, `get_bars`, `get_snapshot`, `is_healthy`, `reconnect`

2. `core/state.py` exists with all 6 tables:
   - Run: `uv run python -c "import tempfile, sqlite3; from daytrader.core.state import StateDB; t = tempfile.mktemp(); db = StateDB(t); db.initialize(); conn = sqlite3.connect(t); print(sorted([r[0] for r in conn.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')]))"`
   - Expected: lists `bar_cache, failures, lock_in_status, news_seen, plans, reports`

3. IB Gateway + IBC setup doc exists:
   - Run: `ls -la docs/ops/ib-gateway-setup.md`
   - Expected: file exists

4. Dry-run scaffolding works:
   - Run: `uv run daytrader reports dry-run --type premarket`
   - Expected: 6 lines of stub output ending in `dry-run complete`

- [ ] **Step 2: Confirm test count**

Run: `uv run pytest tests/reports/ tests/cli/test_reports_cli.py tests/scripts/test_run_report.py --co -q | tail -5`
Expected: total of 25+ tests collected.

- [ ] **Step 3: Confirm git history is clean and topical**

Run: `git log --oneline | head -25`
Expected: ~20 commits, each scoped to one task, all prefixed with `feat(reports):`, `chore(deps):`, `docs(reports):`, or `test(reports):`.

- [ ] **Step 4: No commit needed — Phase 1 is verification only**

If any of the above checks fail, return to the offending task and fix.

---

## Summary

After completing all 21 tasks, Phase 1 produces:

1. **Foundation modules**:
   - `core/ib_client.py` — generic IBKR market-data wrapper (connect, get_bars, get_snapshot)
   - `core/state.py` — SQLite state DB with 6 tables and CRUD helpers
2. **Configuration**:
   - `config/instruments.yaml` — MES/MNQ/MGC parameters
   - `config/secrets.yaml.example` — template for Anthropic + Telegram secrets
   - `core/config.py::ReportsConfig` — additive pydantic model
3. **CLI surface**:
   - `daytrader reports dry-run --type <T>` — Phase 1 stub for all 7 types
4. **Operational entry point**:
   - `scripts/run_report.py` — launchd-callable script with lock + arg parsing
5. **Operational docs**:
   - `docs/ops/ib-gateway-setup.md` — IB Gateway + IBC install guide

**Tests**: ~25 tests across `tests/reports/`, `tests/cli/`, `tests/scripts/`, all passing alongside existing project tests.

**Existing modules** (`premarket/`, `journal/`, `core/db.py`, etc.) — **unchanged**.

**Next**: Phase 2 plan (single-instrument single-report-type proof-of-concept: MES premarket end-to-end with real Anthropic call + Obsidian write, no Telegram yet). Will be written as a separate plan file referencing this Phase 1 foundation.
