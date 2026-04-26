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
