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


def test_write_intraday_4h_1_to_vault(tmp_path):
    """4h-1 writes <date>-0700PT-4H1.md."""
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    daily = vault / "Daily"
    daily.mkdir(parents=True)

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_intraday_4h(
        date_iso="2026-05-05",
        time_label="0700PT-4H1",
        content="# Intraday 4H Report\nbody\n",
    )
    assert result.path.name == "2026-05-05-0700PT-4H1.md"
    assert result.path.parent == daily
    assert result.path.read_text().startswith("# Intraday 4H Report")


def test_write_intraday_4h_2_to_vault(tmp_path):
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    daily = vault / "Daily"
    daily.mkdir(parents=True)

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_intraday_4h(
        date_iso="2026-05-05",
        time_label="1100PT-4H2",
        content="# Intraday 4H Report (#2)\n",
    )
    assert result.path.name == "2026-05-05-1100PT-4H2.md"


def test_write_intraday_4h_falls_back_when_vault_missing(tmp_path):
    """When vault path doesn't exist, fall back to fallback_dir."""
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "missing-vault"
    fallback = tmp_path / "fallback"
    fallback.mkdir()

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_intraday_4h(
        date_iso="2026-05-05", time_label="0700PT-4H1",
        content="# fallback test\n",
    )
    assert result.path.parent == fallback
    assert result.path.read_text() == "# fallback test\n"


def test_write_night_to_vault(tmp_path):
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    daily = vault / "Daily"
    daily.mkdir(parents=True)

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_night_asia(
        date_iso="2026-05-05",
        cadence="night",
        content="# Night D-Archive\n",
    )
    assert result.path.name == "2026-05-05-1900PT-night.md"


def test_write_asia_to_vault(tmp_path):
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    daily = vault / "Daily"
    daily.mkdir(parents=True)

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_night_asia(
        date_iso="2026-05-05",
        cadence="asia",
        content="# Asia D-Archive\n",
    )
    assert result.path.name == "2026-05-05-2300PT-asia.md"


def test_write_night_asia_invalid_cadence_raises():
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    from pathlib import Path
    writer = ObsidianWriter(vault_root=Path("/tmp"),
                            fallback_dir=Path("/tmp"),
                            daily_folder="Daily")
    with pytest.raises(ValueError, match="cadence"):
        writer.write_night_asia(
            date_iso="2026-05-05", cadence="invalid",
            content="x",
        )
