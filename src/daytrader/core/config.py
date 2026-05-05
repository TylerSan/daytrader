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


class ObsidianConfig(BaseModel):
    enabled: bool = True
    vault_path: str = "~/Documents/DayTrader Vault"
    daily_folder: str = "Daily"
    weekly_folder: str = "Weekly"


class PremarketConfig(BaseModel):
    push_on_complete: bool = False


class BacktestConfig(BaseModel):
    default_config: str = "stacked_imbalance.yaml"


class JournalObsidianConfig(BaseModel):
    trades_folder: str = "DayTrader/Trades"
    dry_runs_folder: str = "DayTrader/DryRuns"
    checklists_folder: str = "DayTrader/Daily"


class JournalConfig(BaseModel):
    db_path: str = "data/db/journal.db"
    contract_path: str = "docs/trading/Contract.md"
    setups_dir: str = "docs/trading/setups"
    data_cache_dir: str = "data/cache/ohlcv"
    obsidian: JournalObsidianConfig = JournalObsidianConfig()


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


class DayTraderConfig(BaseModel):
    database: DatabaseConfig = DatabaseConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    obsidian: ObsidianConfig = ObsidianConfig()
    premarket: PremarketConfig = PremarketConfig()
    backtest: BacktestConfig = BacktestConfig()
    journal: JournalConfig = JournalConfig()
    reports: ReportsConfig = ReportsConfig()


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
