"""Setup YAML schema + strict parser.

Philosophy: every rule must be mechanically executable. Reject vague words
and unknown rule names up front to prevent 'judgment calls' leaking into
the backtester.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ALLOWED_SYMBOLS = {"MES", "MNQ", "MGC"}

ALLOWED_TRIGGERS = {
    "price_closes_beyond_or_by_ticks",
    "price_wicks_beyond_or_by_ticks",
    "bar_close_above_prior_high",
    "bar_close_below_prior_low",
}

ALLOWED_STOP_RULES = {
    "opposite_side_of_or",
    "fixed_ticks",
    "atr_multiple",
}

ALLOWED_TARGET_RULES = {
    "multiple_of_or_range",
    "fixed_ticks",
    "atr_multiple",
    "prior_session_extreme",
}

ALLOWED_ENTRY_DIRECTIONS = {
    "long_if_above_or_short_if_below",
    "long_only",
    "short_only",
}

REQUIRED_TOP_KEYS = {
    "name", "version", "symbols",
    "session_window", "entry", "stop", "target",
}


class SetupYamlError(ValueError):
    pass


@dataclass
class SetupDefinition:
    name: str
    version: str
    symbols: list[str]
    session_window: dict[str, Any]
    opening_range: dict[str, Any] | None
    entry: dict[str, Any]
    stop: dict[str, Any]
    target: dict[str, Any]
    filters: list[dict[str, Any]]
    raw: dict[str, Any]


def _req(d: dict, key: str, context: str) -> Any:
    if key not in d:
        raise SetupYamlError(f"{context} missing required key: {key}")
    return d[key]


def load_setup_yaml(path: Path) -> SetupDefinition:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise SetupYamlError(f"{path}: top-level must be a mapping")

    missing = REQUIRED_TOP_KEYS - set(data.keys())
    if missing:
        raise SetupYamlError(f"{path}: missing keys: {sorted(missing)}")

    symbols = data["symbols"]
    if not isinstance(symbols, list) or not symbols:
        raise SetupYamlError(f"{path}: symbols must be non-empty list")
    for s in symbols:
        if s not in ALLOWED_SYMBOLS:
            raise SetupYamlError(
                f"{path}: unknown symbol {s!r} (allowed: {sorted(ALLOWED_SYMBOLS)})"
            )

    session = data["session_window"]
    _req(session, "start", "session_window")
    _req(session, "end", "session_window")

    entry = data["entry"]
    direction = _req(entry, "direction", "entry")
    if direction not in ALLOWED_ENTRY_DIRECTIONS:
        raise SetupYamlError(
            f"entry.direction {direction!r} not in {sorted(ALLOWED_ENTRY_DIRECTIONS)}"
        )
    trigger = _req(entry, "trigger", "entry")
    if trigger not in ALLOWED_TRIGGERS:
        raise SetupYamlError(
            f"entry.trigger {trigger!r} not in {sorted(ALLOWED_TRIGGERS)}"
        )
    ticks = entry.get("ticks", 0)
    if not isinstance(ticks, int):
        raise SetupYamlError(f"entry.ticks must be integer, got {type(ticks).__name__}")

    stop = data["stop"]
    stop_rule = _req(stop, "rule", "stop")
    if stop_rule not in ALLOWED_STOP_RULES:
        raise SetupYamlError(
            f"stop.rule {stop_rule!r} not in {sorted(ALLOWED_STOP_RULES)}"
        )

    target = data["target"]
    target_rule = _req(target, "rule", "target")
    if target_rule not in ALLOWED_TARGET_RULES:
        raise SetupYamlError(
            f"target.rule {target_rule!r} not in {sorted(ALLOWED_TARGET_RULES)}"
        )

    filters = data.get("filters", [])
    if not isinstance(filters, list):
        raise SetupYamlError(f"filters must be a list")

    opening_range = data.get("opening_range")

    return SetupDefinition(
        name=str(data["name"]),
        version=str(data["version"]),
        symbols=list(symbols),
        session_window=dict(session),
        opening_range=dict(opening_range) if opening_range else None,
        entry=dict(entry),
        stop=dict(stop),
        target=dict(target),
        filters=list(filters),
        raw=dict(data),
    )
