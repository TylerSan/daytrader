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
