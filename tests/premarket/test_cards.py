from datetime import date, datetime, timezone

import pytest

from daytrader.premarket.collectors.base import CollectorResult
from daytrader.premarket.renderers.cards import CardGenerator


@pytest.fixture
def sample_results() -> dict[str, CollectorResult]:
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "ES=F": {
                    "price": 5425.50,
                    "change_pct": 0.35,
                    "prev_close": 5400.0,
                    "day_high": 5440.0,
                    "day_low": 5390.0,
                    "overnight_high": 5435.0,
                    "overnight_low": 5395.0,
                    "overnight_range": 40.0,
                    "asia_high": 5420.0,
                    "asia_low": 5400.0,
                    "europe_high": 5435.0,
                    "europe_low": 5395.0,
                },
                "NQ=F": {
                    "price": 19250.0,
                    "change_pct": 0.45,
                    "prev_close": 19150.0,
                    "day_high": 19300.0,
                    "day_low": 19100.0,
                },
                "^VIX": {"price": 18.5, "change_pct": -2.1, "prev_close": 18.9},
            },
            success=True,
        ),
        "sectors": CollectorResult(
            collector_name="sectors",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "XLK": {"name": "Technology", "change_pct": 1.2},
                "XLF": {"name": "Financials", "change_pct": -0.3},
            },
            success=True,
        ),
        "movers": CollectorResult(
            collector_name="movers",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "movers": [
                    {"symbol": "PLTR", "name": "Palantir", "price": 129.55, "gap_pct": -7.96, "vol_ratio": 2.14},
                    {"symbol": "AMZN", "name": "Amazon", "price": 233.09, "gap_pct": 5.35, "vol_ratio": 1.23},
                ]
            },
            success=True,
        ),
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "prior_day_high": 681.15,
                    "prior_day_low": 673.77,
                    "prior_day_close": 676.01,
                    "approx_vwap_5d": 666.54,
                    "weekly_high": 681.15,
                    "weekly_low": 645.11,
                },
            },
            success=True,
        ),
    }


# --- Data extraction tests ---

def test_extract_overview_data(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    data = gen._extract_overview_data(sample_results, date(2026, 4, 9))
    assert data is not None
    assert "instruments" in data
    symbols = [i["symbol"] for i in data["instruments"]]
    assert "ES=F" in symbols
    # Check ES=F values
    es = next(i for i in data["instruments"] if i["symbol"] == "ES=F")
    assert es["price"] == 5425.50
    # VIX is present
    assert any("VIX" in i["symbol"] for i in data["instruments"])
    vix = next(i for i in data["instruments"] if "VIX" in i["symbol"])
    assert vix["price"] == 18.5


def test_extract_sectors_data(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    data = gen._extract_sectors_data(sample_results)
    assert data is not None
    assert isinstance(data, list)
    # Should be sorted descending by pct: XLK(1.2) before XLF(-0.3)
    syms = [t[0] for t in data]
    assert syms.index("XLK") < syms.index("XLF")
    # Check names are present
    names = [t[1] for t in data]
    assert "Technology" in names
    # Check pct values
    pcts = {t[0]: t[2] for t in data}
    assert pcts["XLK"] == 1.2


def test_extract_movers_data(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    data = gen._extract_movers_data(sample_results)
    assert data is not None
    assert isinstance(data, list)
    syms = [m["symbol"] for m in data]
    assert "PLTR" in syms
    pltr = next(m for m in data if m["symbol"] == "PLTR")
    assert pltr["gap_pct"] == -7.96
    assert "AMZN" in syms


def test_extract_levels_data(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    data = gen._extract_levels_data(sample_results)
    assert data is not None
    assert isinstance(data, dict)
    assert "SPY" in data
    spy = data["SPY"]
    assert spy["prior_day_high"] == 681.15
    assert "approx_vwap_5d" in spy


def test_extract_returns_none_on_missing_data():
    gen = CardGenerator(output_dir="/tmp/test-cards")
    empty: dict = {}
    assert gen._extract_overview_data(empty, date(2026, 4, 9)) is None
    assert gen._extract_sectors_data(empty) is None
    assert gen._extract_movers_data(empty) is None
    assert gen._extract_levels_data(empty) is None


# --- Integration tests (real matplotlib rendering) ---

def test_generate_premarket_cards_creates_files(sample_results, tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    paths = gen.generate_premarket_cards(sample_results, date(2026, 4, 9))
    assert len(paths) == 4  # overview, sectors, movers, levels
    for p in paths:
        assert p.exists(), f"{p} does not exist"
        assert p.stat().st_size > 1000, f"{p} is suspiciously small"


def test_generate_premarket_cards_skips_missing(tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    paths = gen.generate_premarket_cards({}, date(2026, 4, 9))
    assert paths == []


def test_generate_weekly_cards_creates_files(sample_results, tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    paths = gen.generate_weekly_cards(sample_results, date(2026, 4, 9))
    assert len(paths) >= 2  # overview, levels, sectors
    for p in paths:
        assert p.exists(), f"{p} does not exist"
        assert p.stat().st_size > 1000, f"{p} is suspiciously small"
