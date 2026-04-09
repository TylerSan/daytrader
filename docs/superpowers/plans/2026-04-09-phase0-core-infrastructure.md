# Phase 0: Core Infrastructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the foundational infrastructure — project scaffold, domain models, database layer, plugin registry, config system, CLI framework, and notification system — so all subsequent module plans can build on a stable base.

**Architecture:** Python 3.12+ package (`daytrader`) using `uv` for dependency management, `click` for CLI, SQLite via repository pattern for persistence, YAML for config, and a plugin registry for extensibility.

**Tech Stack:** Python 3.12+, uv, click, pyyaml, SQLite (stdlib sqlite3), pydantic (data models), pytest, httpx, python-telegram-bot

---

## File Structure

```
Day trading/
├── pyproject.toml                          # Project metadata + dependencies
├── .gitignore
├── config/
│   └── default.yaml                        # Default configuration
├── src/daytrader/
│   ├── __init__.py                         # Package init with version
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py                       # Domain models (pydantic)
│   │   ├── db.py                           # Database layer (SQLite + repository pattern)
│   │   ├── config.py                       # Config loader (YAML merge: default + user)
│   │   └── registry.py                     # Plugin registry
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── base.py                         # Notifier ABC interface
│   │   ├── telegram.py                     # Telegram Bot notifier
│   │   ├── imessage.py                     # iMessage notifier (AppleScript)
│   │   └── discord.py                      # Discord webhook notifier
│   └── cli/
│       ├── __init__.py
│       └── main.py                         # CLI entry point with click groups
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         # Shared fixtures (tmp db, config)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   ├── test_db.py
│   │   ├── test_config.py
│   │   └── test_registry.py
│   └── notifications/
│       ├── __init__.py
│       └── test_notifications.py
└── data/
    ├── db/
    ├── tick/
    ├── imports/
    └── exports/
```

---

### Task 1: Project Scaffold & Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/daytrader/__init__.py`

- [ ] **Step 1: Initialize git repo**

```bash
cd "/Users/tylersan/Projects/Day trading"
git init
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "daytrader"
version = "0.1.0"
description = "Self-evolving day trading platform for order flow scalping"
requires-python = ">=3.12"
dependencies = [
    "click>=8.1",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "pandas>=2.2",
    "numpy>=1.26",
    "plotly>=5.18",
]

[project.optional-dependencies]
notifications = [
    "python-telegram-bot>=21.0",
    "discord.py>=2.3",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
daytrader = "daytrader.cli.main:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/daytrader"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
build/
config/user.yaml
data/db/*.db
data/tick/
data/imports/
data/exports/
.pytest_cache/
```

- [ ] **Step 4: Create package init**

```python
# src/daytrader/__init__.py
"""DayTrader — self-evolving day trading platform."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Create data directories**

```bash
mkdir -p data/{db,tick,imports,exports}
touch data/db/.gitkeep data/tick/.gitkeep data/imports/.gitkeep data/exports/.gitkeep
```

- [ ] **Step 6: Install with uv**

```bash
cd "/Users/tylersan/Projects/Day trading"
uv venv
uv pip install -e ".[dev,notifications]"
```

Expected: clean install, no errors.

- [ ] **Step 7: Verify installation**

```bash
uv run python -c "import daytrader; print(daytrader.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore src/daytrader/__init__.py data/
git commit -m "chore: initialize daytrader project scaffold"
```

---

### Task 2: Configuration System

**Files:**
- Create: `src/daytrader/core/__init__.py`
- Create: `src/daytrader/core/config.py`
- Create: `config/default.yaml`
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Create test directory and conftest**

```python
# tests/__init__.py
# (empty)
```

```python
# tests/conftest.py
import pytest
from pathlib import Path
import tempfile
import yaml


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def default_config(tmp_dir: Path) -> Path:
    cfg = {
        "database": {"path": "data/db/daytrader.db"},
        "notifications": {
            "enabled": False,
            "channels": {
                "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
                "discord": {"enabled": False, "webhook_url": ""},
                "imessage": {"enabled": False, "recipient": ""},
            },
        },
        "premarket": {"push_on_complete": False},
        "backtest": {"default_config": "stacked_imbalance.yaml"},
    }
    path = tmp_dir / "default.yaml"
    path.write_text(yaml.dump(cfg))
    return path
```

```python
# tests/core/__init__.py
# (empty)
```

- [ ] **Step 2: Write failing tests for config**

```python
# tests/core/test_config.py
from pathlib import Path
import yaml

from daytrader.core.config import load_config, DayTraderConfig


def test_load_default_config(default_config: Path):
    cfg = load_config(default_config=default_config)
    assert cfg.database.path == "data/db/daytrader.db"
    assert cfg.notifications.enabled is False


def test_user_config_overrides_default(tmp_dir: Path, default_config: Path):
    user_cfg = {"notifications": {"enabled": True}}
    user_path = tmp_dir / "user.yaml"
    user_path.write_text(yaml.dump(user_cfg))

    cfg = load_config(default_config=default_config, user_config=user_path)
    assert cfg.notifications.enabled is True
    # default values preserved
    assert cfg.database.path == "data/db/daytrader.db"


def test_missing_user_config_uses_defaults(default_config: Path):
    cfg = load_config(
        default_config=default_config,
        user_config=Path("/nonexistent/user.yaml"),
    )
    assert cfg.database.path == "data/db/daytrader.db"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/core/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'daytrader.core.config'`

- [ ] **Step 4: Implement config module**

```python
# src/daytrader/core/__init__.py
# (empty)
```

```python
# src/daytrader/core/config.py
"""Configuration loader — merges default.yaml + user.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class DatabaseConfig(BaseModel):
    path: str = "data/db/daytrader.db"


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class DiscordConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""


class IMessageConfig(BaseModel):
    enabled: bool = False
    recipient: str = ""


class NotificationChannels(BaseModel):
    telegram: TelegramConfig = TelegramConfig()
    discord: DiscordConfig = DiscordConfig()
    imessage: IMessageConfig = IMessageConfig()


class NotificationsConfig(BaseModel):
    enabled: bool = False
    channels: NotificationChannels = NotificationChannels()


class PremarketConfig(BaseModel):
    push_on_complete: bool = False


class BacktestConfig(BaseModel):
    default_config: str = "stacked_imbalance.yaml"


class DayTraderConfig(BaseModel):
    database: DatabaseConfig = DatabaseConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    premarket: PremarketConfig = PremarketConfig()
    backtest: BacktestConfig = BacktestConfig()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(
    default_config: Path | None = None,
    user_config: Path | None = None,
) -> DayTraderConfig:
    """Load config by merging default + user YAML files."""
    data: dict[str, Any] = {}

    if default_config and default_config.exists():
        data = yaml.safe_load(default_config.read_text()) or {}

    if user_config and user_config.exists():
        user_data = yaml.safe_load(user_config.read_text()) or {}
        data = _deep_merge(data, user_data)

    return DayTraderConfig.model_validate(data)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/core/test_config.py -v
```

Expected: 3 passed

- [ ] **Step 6: Create default.yaml**

```yaml
# config/default.yaml
database:
  path: data/db/daytrader.db

notifications:
  enabled: false
  channels:
    telegram:
      enabled: false
      bot_token: ""
      chat_id: ""
    discord:
      enabled: false
      webhook_url: ""
    imessage:
      enabled: false
      recipient: ""

premarket:
  push_on_complete: false

backtest:
  default_config: stacked_imbalance.yaml
```

- [ ] **Step 7: Commit**

```bash
git add src/daytrader/core/ config/default.yaml tests/
git commit -m "feat: add configuration system with YAML merge support"
```

---

### Task 3: Domain Models

**Files:**
- Create: `src/daytrader/core/models.py`
- Test: `tests/core/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_models.py
from datetime import datetime, timezone
from decimal import Decimal

from daytrader.core.models import (
    Signal,
    SignalDirection,
    Trade,
    TradeSide,
    Level,
    LevelSource,
    MarketContext,
    MarketRegime,
)


def test_signal_creation():
    s = Signal(
        symbol="ES",
        direction=SignalDirection.BULLISH,
        strength=3,
        price=Decimal("5400.50"),
        timestamp=datetime(2026, 4, 9, 9, 35, tzinfo=timezone.utc),
        imbalance_layers=3,
        delta_ratio=Decimal("3.5"),
    )
    assert s.symbol == "ES"
    assert s.direction == SignalDirection.BULLISH
    assert s.strength == 3
    assert s.id is not None  # auto-generated UUID


def test_trade_pnl_in_r():
    t = Trade(
        symbol="ES",
        side=TradeSide.LONG,
        entry_price=Decimal("5400.00"),
        exit_price=Decimal("5406.00"),
        stop_price=Decimal("5398.00"),
        size=1,
        entry_time=datetime(2026, 4, 9, 9, 35, tzinfo=timezone.utc),
        exit_time=datetime(2026, 4, 9, 9, 42, tzinfo=timezone.utc),
    )
    assert t.risk == Decimal("2.00")  # entry - stop
    assert t.pnl == Decimal("6.00")  # exit - entry
    assert t.r_multiple == Decimal("3.00")  # pnl / risk


def test_level_creation():
    lvl = Level(
        symbol="SPY",
        price=Decimal("540.25"),
        source=LevelSource.PRIOR_DAY_HIGH,
        label="PDH",
    )
    assert lvl.source == LevelSource.PRIOR_DAY_HIGH


def test_market_context():
    ctx = MarketContext(
        timestamp=datetime(2026, 4, 9, 9, 30, tzinfo=timezone.utc),
        regime=MarketRegime.TRENDING,
        vix=Decimal("18.5"),
        es_change_pct=Decimal("0.35"),
    )
    assert ctx.regime == MarketRegime.TRENDING
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/core/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement domain models**

```python
# src/daytrader/core/models.py
"""Core domain models for the DayTrader platform."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# --- Enums ---

class SignalDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class TradeSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class LevelSource(str, Enum):
    PRIOR_DAY_HIGH = "prior_day_high"
    PRIOR_DAY_LOW = "prior_day_low"
    PRIOR_DAY_CLOSE = "prior_day_close"
    PREMARKET_HIGH = "premarket_high"
    PREMARKET_LOW = "premarket_low"
    VOLUME_PROFILE_POC = "vp_poc"
    VOLUME_PROFILE_VAH = "vp_vah"
    VOLUME_PROFILE_VAL = "vp_val"
    WEEKLY_HIGH = "weekly_high"
    WEEKLY_LOW = "weekly_low"
    CUSTOM = "custom"


class MarketRegime(str, Enum):
    TRENDING = "trending"
    RANGE_BOUND = "range_bound"
    VOLATILE = "volatile"
    LOW_VOLATILITY = "low_volatility"


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --- Models ---

class Signal(BaseModel):
    id: str = Field(default_factory=_new_id)
    symbol: str
    direction: SignalDirection
    strength: int  # number of stacked imbalance layers
    price: Decimal
    timestamp: datetime
    imbalance_layers: int
    delta_ratio: Decimal
    context_regime: MarketRegime | None = None
    confidence: Confidence = Confidence.MEDIUM


class Trade(BaseModel):
    id: str = Field(default_factory=_new_id)
    symbol: str
    side: TradeSide
    entry_price: Decimal
    exit_price: Decimal
    stop_price: Decimal
    size: int
    entry_time: datetime
    exit_time: datetime
    signal_id: str | None = None
    source: str = ""  # "motivewave", "broker", etc.
    prop_firm: str | None = None
    tags: list[str] = Field(default_factory=list)

    @property
    def risk(self) -> Decimal:
        return abs(self.entry_price - self.stop_price)

    @property
    def pnl(self) -> Decimal:
        if self.side == TradeSide.LONG:
            return self.exit_price - self.entry_price
        return self.entry_price - self.exit_price

    @property
    def r_multiple(self) -> Decimal:
        if self.risk == 0:
            return Decimal("0")
        return self.pnl / self.risk


class Level(BaseModel):
    id: str = Field(default_factory=_new_id)
    symbol: str
    price: Decimal
    source: LevelSource
    label: str = ""
    date: datetime | None = None


class MarketContext(BaseModel):
    timestamp: datetime
    regime: MarketRegime
    vix: Decimal | None = None
    es_change_pct: Decimal | None = None
    nq_change_pct: Decimal | None = None
    sector_leaders: list[str] = Field(default_factory=list)
    sector_laggards: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    id: str = Field(default_factory=_new_id)
    title: str
    description: str
    status: HypothesisStatus = HypothesisStatus.PENDING
    confidence: Confidence = Confidence.LOW
    evidence: str = ""
    recommendation: str = ""
    created_at: datetime | None = None
    validated_at: datetime | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/core/test_models.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/models.py tests/core/test_models.py
git commit -m "feat: add core domain models (Signal, Trade, Level, MarketContext, Hypothesis)"
```

---

### Task 4: Database Layer

**Files:**
- Create: `src/daytrader/core/db.py`
- Test: `tests/core/test_db.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_db.py
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.core.db import Database
from daytrader.core.models import (
    Signal,
    SignalDirection,
    Trade,
    TradeSide,
    Confidence,
)


@pytest.fixture
def db(tmp_dir: Path) -> Database:
    db_path = tmp_dir / "test.db"
    database = Database(str(db_path))
    database.initialize()
    return database


def _sample_signal() -> Signal:
    return Signal(
        symbol="ES",
        direction=SignalDirection.BULLISH,
        strength=3,
        price=Decimal("5400.50"),
        timestamp=datetime(2026, 4, 9, 9, 35, tzinfo=timezone.utc),
        imbalance_layers=3,
        delta_ratio=Decimal("3.5"),
    )


def _sample_trade() -> Trade:
    return Trade(
        symbol="ES",
        side=TradeSide.LONG,
        entry_price=Decimal("5400.00"),
        exit_price=Decimal("5406.00"),
        stop_price=Decimal("5398.00"),
        size=1,
        entry_time=datetime(2026, 4, 9, 9, 35, tzinfo=timezone.utc),
        exit_time=datetime(2026, 4, 9, 9, 42, tzinfo=timezone.utc),
    )


def test_save_and_get_signal(db: Database):
    signal = _sample_signal()
    db.save_signal(signal)
    loaded = db.get_signal(signal.id)
    assert loaded is not None
    assert loaded.symbol == "ES"
    assert loaded.price == Decimal("5400.50")


def test_list_signals_by_symbol(db: Database):
    s1 = _sample_signal()
    s2 = Signal(
        symbol="NQ",
        direction=SignalDirection.BEARISH,
        strength=2,
        price=Decimal("19200.00"),
        timestamp=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        imbalance_layers=2,
        delta_ratio=Decimal("2.8"),
    )
    db.save_signal(s1)
    db.save_signal(s2)
    es_signals = db.list_signals(symbol="ES")
    assert len(es_signals) == 1
    assert es_signals[0].symbol == "ES"


def test_save_and_get_trade(db: Database):
    trade = _sample_trade()
    db.save_trade(trade)
    loaded = db.get_trade(trade.id)
    assert loaded is not None
    assert loaded.symbol == "ES"
    assert loaded.pnl == Decimal("6.00")


def test_list_trades_by_date(db: Database):
    trade = _sample_trade()
    db.save_trade(trade)
    trades = db.list_trades(date=datetime(2026, 4, 9).date())
    assert len(trades) == 1


def test_empty_results(db: Database):
    assert db.get_signal("nonexistent") is None
    assert db.list_signals(symbol="AAPL") == []
    assert db.list_trades() == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/core/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement database layer**

```python
# src/daytrader/core/db.py
"""SQLite database layer with repository pattern."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from daytrader.core.models import (
    Confidence,
    Signal,
    SignalDirection,
    MarketRegime,
    Trade,
    TradeSide,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    strength INTEGER NOT NULL,
    price TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    imbalance_layers INTEGER NOT NULL,
    delta_ratio TEXT NOT NULL,
    context_regime TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    extra TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    exit_price TEXT NOT NULL,
    stop_price TEXT NOT NULL,
    size INTEGER NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT NOT NULL,
    signal_id TEXT,
    source TEXT DEFAULT '',
    prop_firm TEXT,
    tags TEXT DEFAULT '[]',
    extra TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
"""


class Database:
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
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Signals ---

    def save_signal(self, signal: Signal) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO signals
               (id, symbol, direction, strength, price, timestamp,
                imbalance_layers, delta_ratio, context_regime, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.id,
                signal.symbol,
                signal.direction.value,
                signal.strength,
                str(signal.price),
                signal.timestamp.isoformat(),
                signal.imbalance_layers,
                str(signal.delta_ratio),
                signal.context_regime.value if signal.context_regime else None,
                signal.confidence.value,
            ),
        )
        conn.commit()

    def get_signal(self, signal_id: str) -> Signal | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_signal(row)

    def list_signals(self, symbol: str | None = None) -> list[Signal]:
        conn = self._get_conn()
        if symbol:
            rows = conn.execute(
                "SELECT * FROM signals WHERE symbol = ? ORDER BY timestamp DESC",
                (symbol,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_signal(r) for r in rows]

    @staticmethod
    def _row_to_signal(row: sqlite3.Row) -> Signal:
        return Signal(
            id=row["id"],
            symbol=row["symbol"],
            direction=SignalDirection(row["direction"]),
            strength=row["strength"],
            price=Decimal(row["price"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            imbalance_layers=row["imbalance_layers"],
            delta_ratio=Decimal(row["delta_ratio"]),
            context_regime=MarketRegime(row["context_regime"]) if row["context_regime"] else None,
            confidence=Confidence(row["confidence"]),
        )

    # --- Trades ---

    def save_trade(self, trade: Trade) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO trades
               (id, symbol, side, entry_price, exit_price, stop_price, size,
                entry_time, exit_time, signal_id, source, prop_firm, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.id,
                trade.symbol,
                trade.side.value,
                str(trade.entry_price),
                str(trade.exit_price),
                str(trade.stop_price),
                trade.size,
                trade.entry_time.isoformat(),
                trade.exit_time.isoformat(),
                trade.signal_id,
                trade.source,
                trade.prop_firm,
                json.dumps(trade.tags),
            ),
        )
        conn.commit()

    def get_trade(self, trade_id: str) -> Trade | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_trade(row)

    def list_trades(self, date: date | None = None, symbol: str | None = None) -> list[Trade]:
        conn = self._get_conn()
        query = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        if date:
            query += " AND entry_time LIKE ?"
            params.append(f"{date.isoformat()}%")
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY entry_time DESC"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_trade(r) for r in rows]

    @staticmethod
    def _row_to_trade(row: sqlite3.Row) -> Trade:
        return Trade(
            id=row["id"],
            symbol=row["symbol"],
            side=TradeSide(row["side"]),
            entry_price=Decimal(row["entry_price"]),
            exit_price=Decimal(row["exit_price"]),
            stop_price=Decimal(row["stop_price"]),
            size=row["size"],
            entry_time=datetime.fromisoformat(row["entry_time"]),
            exit_time=datetime.fromisoformat(row["exit_time"]),
            signal_id=row["signal_id"],
            source=row["source"],
            prop_firm=row["prop_firm"],
            tags=json.loads(row["tags"]),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/core/test_db.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/db.py tests/core/test_db.py
git commit -m "feat: add SQLite database layer with Signal and Trade repositories"
```

---

### Task 5: Plugin Registry

**Files:**
- Create: `src/daytrader/core/registry.py`
- Test: `tests/core/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_registry.py
import pytest

from daytrader.core.registry import PluginRegistry


class DummyCollector:
    name = "dummy"

    def collect(self) -> str:
        return "data"


class AnotherCollector:
    name = "another"

    def collect(self) -> str:
        return "more data"


def test_register_and_get():
    registry = PluginRegistry[DummyCollector]()
    plugin = DummyCollector()
    registry.register("dummy", plugin)
    assert registry.get("dummy") is plugin


def test_get_unknown_returns_none():
    registry = PluginRegistry()
    assert registry.get("nonexistent") is None


def test_list_registered():
    registry = PluginRegistry()
    registry.register("a", DummyCollector())
    registry.register("b", AnotherCollector())
    names = registry.list_names()
    assert sorted(names) == ["a", "b"]


def test_register_duplicate_raises():
    registry = PluginRegistry()
    registry.register("dup", DummyCollector())
    with pytest.raises(ValueError, match="already registered"):
        registry.register("dup", AnotherCollector())
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/core/test_registry.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement plugin registry**

```python
# src/daytrader/core/registry.py
"""Generic plugin registry for extensible components."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class PluginRegistry(Generic[T]):
    """Type-safe registry for plugin components."""

    def __init__(self) -> None:
        self._plugins: dict[str, T] = {}

    def register(self, name: str, plugin: T) -> None:
        if name in self._plugins:
            raise ValueError(f"Plugin '{name}' already registered")
        self._plugins[name] = plugin

    def get(self, name: str) -> T | None:
        return self._plugins.get(name)

    def list_names(self) -> list[str]:
        return list(self._plugins.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/core/test_registry.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/core/registry.py tests/core/test_registry.py
git commit -m "feat: add generic plugin registry"
```

---

### Task 6: Notification System

**Files:**
- Create: `src/daytrader/notifications/__init__.py`
- Create: `src/daytrader/notifications/base.py`
- Create: `src/daytrader/notifications/telegram.py`
- Create: `src/daytrader/notifications/discord.py`
- Create: `src/daytrader/notifications/imessage.py`
- Test: `tests/notifications/test_notifications.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/notifications/__init__.py
# (empty)
```

```python
# tests/notifications/test_notifications.py
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from daytrader.notifications.base import Notifier, NotificationMessage, NotificationManager
from daytrader.notifications.telegram import TelegramNotifier
from daytrader.notifications.discord import DiscordNotifier
from daytrader.notifications.imessage import IMessageNotifier


class FakeNotifier(Notifier):
    def __init__(self):
        self.sent: list[NotificationMessage] = []

    @property
    def name(self) -> str:
        return "fake"

    async def send(self, message: NotificationMessage) -> bool:
        self.sent.append(message)
        return True


def test_notification_message():
    msg = NotificationMessage(title="Test", body="Hello world", channel="test")
    assert msg.title == "Test"
    assert msg.body == "Hello world"


@pytest.mark.asyncio
async def test_fake_notifier():
    notifier = FakeNotifier()
    msg = NotificationMessage(title="T", body="B", channel="fake")
    result = await notifier.send(msg)
    assert result is True
    assert len(notifier.sent) == 1


@pytest.mark.asyncio
async def test_notification_manager_dispatches():
    fake = FakeNotifier()
    manager = NotificationManager()
    manager.register(fake)

    msg = NotificationMessage(title="T", body="B", channel="fake")
    results = await manager.notify(msg)
    assert results == {"fake": True}
    assert len(fake.sent) == 1


@pytest.mark.asyncio
async def test_notification_manager_skip_disabled():
    fake = FakeNotifier()
    manager = NotificationManager()
    manager.register(fake)

    msg = NotificationMessage(title="T", body="B", channel="nonexistent")
    results = await manager.notify(msg)
    assert results == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/notifications/test_notifications.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement notification base and manager**

```python
# src/daytrader/notifications/__init__.py
from daytrader.notifications.base import Notifier, NotificationMessage, NotificationManager

__all__ = ["Notifier", "NotificationMessage", "NotificationManager"]
```

```python
# src/daytrader/notifications/base.py
"""Notification system base classes and manager."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class NotificationMessage(BaseModel):
    title: str
    body: str
    channel: str  # target channel name, or "all"
    priority: str = "normal"  # "normal", "high"
    metadata: dict = {}


class Notifier(ABC):
    """Interface for notification channel plugins."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool: ...


class NotificationManager:
    """Dispatches notifications to registered channels."""

    def __init__(self) -> None:
        self._notifiers: dict[str, Notifier] = {}

    def register(self, notifier: Notifier) -> None:
        self._notifiers[notifier.name] = notifier

    async def notify(
        self, message: NotificationMessage
    ) -> dict[str, bool]:
        results: dict[str, bool] = {}
        if message.channel == "all":
            targets = self._notifiers.values()
        else:
            n = self._notifiers.get(message.channel)
            targets = [n] if n else []
        for notifier in targets:
            results[notifier.name] = await notifier.send(message)
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/notifications/test_notifications.py -v
```

Expected: 4 passed

- [ ] **Step 5: Implement Telegram notifier**

```python
# src/daytrader/notifications/telegram.py
"""Telegram Bot notification channel."""

from __future__ import annotations

import httpx

from daytrader.notifications.base import Notifier, NotificationMessage


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    @property
    def name(self) -> str:
        return "telegram"

    async def send(self, message: NotificationMessage) -> bool:
        text = f"*{message.title}*\n\n{message.body}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/sendMessage",
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
        return resp.status_code == 200
```

- [ ] **Step 6: Implement Discord notifier**

```python
# src/daytrader/notifications/discord.py
"""Discord webhook notification channel."""

from __future__ import annotations

import httpx

from daytrader.notifications.base import Notifier, NotificationMessage


class DiscordNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "discord"

    async def send(self, message: NotificationMessage) -> bool:
        payload = {
            "embeds": [
                {
                    "title": message.title,
                    "description": message.body,
                    "color": 0x00FF00 if message.priority == "normal" else 0xFF0000,
                }
            ]
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self._webhook_url, json=payload)
        return resp.status_code in (200, 204)
```

- [ ] **Step 7: Implement iMessage notifier**

```python
# src/daytrader/notifications/imessage.py
"""iMessage notification channel via macOS AppleScript."""

from __future__ import annotations

import asyncio
import subprocess

from daytrader.notifications.base import Notifier, NotificationMessage


class IMessageNotifier(Notifier):
    def __init__(self, recipient: str) -> None:
        self._recipient = recipient

    @property
    def name(self) -> str:
        return "imessage"

    async def send(self, message: NotificationMessage) -> bool:
        text = f"{message.title}: {message.body}"
        script = (
            f'tell application "Messages"\n'
            f'  set targetService to 1st account whose service type = iMessage\n'
            f'  set targetBuddy to participant "{self._recipient}" of targetService\n'
            f'  send "{text}" to targetBuddy\n'
            f'end tell'
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except OSError:
            return False
```

- [ ] **Step 8: Commit**

```bash
git add src/daytrader/notifications/ tests/notifications/
git commit -m "feat: add notification system (Telegram, Discord, iMessage)"
```

---

### Task 7: CLI Framework

**Files:**
- Create: `src/daytrader/cli/__init__.py`
- Create: `src/daytrader/cli/main.py`

- [ ] **Step 1: Implement CLI entry point with all command groups**

```python
# src/daytrader/cli/__init__.py
# (empty)
```

```python
# src/daytrader/cli/main.py
"""DayTrader CLI — unified entry point."""

from __future__ import annotations

from pathlib import Path

import click

from daytrader import __version__
from daytrader.core.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/daytrader/cli -> project root


@click.group()
@click.version_option(__version__, prog_name="daytrader")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """DayTrader — self-evolving day trading platform."""
    ctx.ensure_object(dict)
    cfg = load_config(
        default_config=PROJECT_ROOT / "config" / "default.yaml",
        user_config=PROJECT_ROOT / "config" / "user.yaml",
    )
    ctx.obj["config"] = cfg
    ctx.obj["project_root"] = PROJECT_ROOT


# Placeholder groups — each will be fleshed out in their module's plan

@cli.group()
def pre() -> None:
    """Pre-market daily analysis."""


@cli.group()
def weekly() -> None:
    """Weekly trading plan."""


@cli.group()
def bt() -> None:
    """Strategy backtesting."""


@cli.group()
def evo() -> None:
    """Autonomous evolution engine."""


@cli.group()
def prop() -> None:
    """Prop firm account management."""


@cli.group()
def psych() -> None:
    """Trading psychology system."""


@cli.group()
def learn() -> None:
    """Learning & content curation."""


@cli.group()
def stats() -> None:
    """Instrument statistical edge."""


@cli.group()
def kb() -> None:
    """Knowledge base management."""


@cli.group()
def publish() -> None:
    """Content publishing pipeline."""


@cli.group()
def book() -> None:
    """Book manuscript builder."""


@cli.group()
def journal() -> None:
    """Trade journal & import."""
```

- [ ] **Step 2: Test CLI loads**

```bash
uv run daytrader --version
```

Expected: `daytrader, version 0.1.0`

```bash
uv run daytrader --help
```

Expected: shows all command groups (pre, weekly, bt, evo, prop, psych, learn, stats, kb, publish, book, journal)

- [ ] **Step 3: Commit**

```bash
git add src/daytrader/cli/
git commit -m "feat: add CLI framework with all command group stubs"
```

---

### Task 8: Full Test Suite & Final Verification

- [ ] **Step 1: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: all 16+ tests pass (config: 3, models: 4, db: 5, registry: 4, notifications: 4)

- [ ] **Step 2: Verify CLI end-to-end**

```bash
uv run daytrader --version
uv run daytrader --help
uv run daytrader pre --help
uv run daytrader bt --help
```

Expected: all commands respond correctly

- [ ] **Step 3: Commit any remaining files**

```bash
git status
# If any untracked test/init files, add them
git add -A
git commit -m "chore: finalize phase 0 core infrastructure"
```

- [ ] **Step 4: Tag release**

```bash
git tag v0.1.0-alpha
```
