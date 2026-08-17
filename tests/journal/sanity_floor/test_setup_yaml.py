"""Tests for setup YAML parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.journal.sanity_floor.setup_yaml import (
    SetupDefinition, SetupYamlError, load_setup_yaml,
)

_VALID = """
name: orb
version: v1
symbols: [MES, MNQ]
session_window:
  start: "09:30 America/New_York"
  end: "11:30 America/New_York"
opening_range:
  duration_minutes: 15
entry:
  direction: long_if_above_or_short_if_below
  trigger: price_closes_beyond_or_by_ticks
  ticks: 2
stop:
  rule: opposite_side_of_or
  offset_ticks: 2
target:
  rule: multiple_of_or_range
  multiple: 2.0
filters: []
"""


def test_load_valid(tmp_path: Path):
    p = tmp_path / "orb.yaml"
    p.write_text(_VALID)
    s = load_setup_yaml(p)
    assert s.name == "orb"
    assert "MES" in s.symbols
    assert s.opening_range["duration_minutes"] == 15
    assert s.entry["ticks"] == 2


def test_reject_missing_required_field(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("name: orb\nversion: v1\n")
    with pytest.raises(SetupYamlError):
        load_setup_yaml(p)


def test_reject_unknown_symbol(tmp_path: Path):
    content = _VALID.replace("[MES, MNQ]", "[AAPL]")
    p = tmp_path / "bad.yaml"
    p.write_text(content)
    with pytest.raises(SetupYamlError, match="symbol"):
        load_setup_yaml(p)


def test_reject_vague_rule(tmp_path: Path):
    content = _VALID.replace(
        "trigger: price_closes_beyond_or_by_ticks",
        "trigger: strong_breakout_with_confirmation",
    )
    p = tmp_path / "bad.yaml"
    p.write_text(content)
    with pytest.raises(SetupYamlError, match="trigger"):
        load_setup_yaml(p)


def test_reject_non_integer_ticks(tmp_path: Path):
    content = _VALID.replace("ticks: 2", "ticks: 2.5")
    p = tmp_path / "bad.yaml"
    p.write_text(content)
    with pytest.raises(SetupYamlError):
        load_setup_yaml(p)
