"""Unit tests for PremarketPlanReader."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.eod.plan_reader import PremarketPlanReader


SAMPLE_PREMARKET_MD = """---
date: 2026-05-04
type: premarket
---

# Premarket Daily Report

## 📊 MES (Micro E-mini S&P 500)
[multi-TF data...]

## C. 计划复核 / Plan Formation

### C-MES

**Today's plan**:
- **Setup**: stacked_imbalance_reversal_at_level
- **Entry**: 仅在以下其一区域出现 3+ stacked imbalance 时触发
  - **Long bias 区**: 7199.25（D low）+ 7185–7195（W 低区）
  - **Short bias 区**: 7271–7279.5（4H R）
- **Stop**: 入场 ±1R = ± 8 pt
- **Target**: +2R

**Invalidation conditions**:
1. MES 跌破 7185 RTH close → 转空头观察

**Today's posture**: neutral / wait for setup

### C-MGC

**Today's plan**:
- **Setup**: stacked_imbalance_reversal_at_level
- **Entry**: 触发条件
  - **Long bias 区**: 4570（D low）
  - **Short bias 区**: 4673（D high）

## B. 市场叙事
"""


def test_reader_extracts_both_C_blocks(tmp_path):
    vault = tmp_path / "Vault"
    daily = vault / "Daily"
    daily.mkdir(parents=True)
    (daily / "2026-05-04-premarket.md").write_text(SAMPLE_PREMARKET_MD, encoding="utf-8")

    reader = PremarketPlanReader(vault_path=vault, daily_folder="Daily")
    blocks = reader.read_today_plan(date_et="2026-05-04")

    assert "MES" in blocks
    assert "MGC" in blocks
    assert "Long bias 区" in blocks["MES"]
    assert "7199.25" in blocks["MES"]
    assert "4570" in blocks["MGC"]


def test_reader_returns_empty_dict_when_file_missing(tmp_path):
    vault = tmp_path / "Vault"
    (vault / "Daily").mkdir(parents=True)
    reader = PremarketPlanReader(vault_path=vault, daily_folder="Daily")

    blocks = reader.read_today_plan(date_et="2026-05-04")
    assert blocks == {}


def test_reader_handles_only_one_C_block(tmp_path):
    """If only C-MES is present (no C-MGC), returns just MES."""
    md = """## C. 计划复核

### C-MES

**Today's plan**:
- Setup: ...
- Long bias 区: 7199

## B. 市场叙事
"""
    vault = tmp_path / "Vault"
    daily = vault / "Daily"
    daily.mkdir(parents=True)
    (daily / "2026-05-04-premarket.md").write_text(md, encoding="utf-8")

    reader = PremarketPlanReader(vault_path=vault, daily_folder="Daily")
    blocks = reader.read_today_plan(date_et="2026-05-04")
    assert "MES" in blocks
    assert "MGC" not in blocks


def test_reader_strips_block_at_next_h3_or_h2(tmp_path):
    """Block extraction should stop at next ### or ## header to avoid
    bleeding into B section."""
    vault = tmp_path / "Vault"
    daily = vault / "Daily"
    daily.mkdir(parents=True)
    (daily / "2026-05-04-premarket.md").write_text(SAMPLE_PREMARKET_MD, encoding="utf-8")

    reader = PremarketPlanReader(vault_path=vault, daily_folder="Daily")
    blocks = reader.read_today_plan(date_et="2026-05-04")

    # MES block should NOT contain anything from C-MGC or B section
    assert "C-MGC" not in blocks["MES"]
    assert "市场叙事" not in blocks["MES"]
    # MGC block should NOT contain B section
    assert "市场叙事" not in blocks["MGC"]
