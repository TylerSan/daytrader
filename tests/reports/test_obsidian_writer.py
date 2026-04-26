"""Tests for ObsidianWriter."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.delivery.obsidian_writer import ObsidianWriter, WriteResult


def test_writer_writes_to_vault(tmp_path):
    """Successful write creates parent directories and the file."""
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    writer = ObsidianWriter(
        vault_root=vault,
        fallback_dir=fallback,
        daily_folder="Daily",
    )

    result = writer.write_premarket(
        date_iso="2026-04-25",
        content="# Premarket Report\n\nbody",
    )
    assert isinstance(result, WriteResult)
    assert result.success is True
    assert result.path.exists()
    assert "2026-04-25-premarket" in result.path.name
    assert result.fallback_used is False


def test_writer_falls_back_when_vault_unwritable(tmp_path, monkeypatch):
    """When vault write fails, writer falls back to fallback_dir."""
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"

    # Force vault writes to fail
    real_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if str(self).startswith(str(vault)):
            raise PermissionError("simulated")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    writer = ObsidianWriter(
        vault_root=vault,
        fallback_dir=fallback,
        daily_folder="Daily",
    )

    result = writer.write_premarket(
        date_iso="2026-04-25",
        content="# Premarket\n",
    )
    assert result.success is True
    assert result.fallback_used is True
    assert str(fallback) in str(result.path)
