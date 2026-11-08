"""Unit tests for BaseCadenceGenerator template-method pattern."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.types.base import BaseCadenceGenerator, CadenceOutcome


def _ctx() -> ReportContext:
    return ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n" + "## Detail\n" * 30,
        lock_in_trades_done=0, lock_in_target=30,
        cumulative_r=None, last_trade_date=None, last_trade_r=None, streak=None,
    )


def _ohlcv(c: float = 5240.0):
    from datetime import datetime, timezone
    return OHLCV(
        timestamp=datetime(2026, 5, 5, 7, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def _ai_result_text():
    """Mock AI result; subclass tests assert validator-pass text."""
    result = MagicMock()
    result.text = "## Required\nstub\n"
    result.input_tokens = 100
    result.output_tokens = 200
    result.cache_creation_tokens = 0
    result.cache_read_tokens = 0
    result.model = "claude-opus-4-7"
    result.stop_reason = "end_turn"
    return result


class _DummyCadence(BaseCadenceGenerator):
    """Minimal concrete subclass for testing the abstract base."""

    @property
    def report_type(self) -> str:
        return "test-cadence"

    @property
    def tfs(self) -> tuple[str, ...]:
        return ("1D", "4H")

    @property
    def bars_per_tf(self) -> dict[str, int]:
        return {"1D": 5, "4H": 6}

    def _build_prompt(self, **kwargs):
        return [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "test"},
        ]


def _make_dummy(**overrides):
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()
    fake_validator = MagicMock()
    fake_validator.validate.return_value = MagicMock(ok=True, missing=[])

    return _DummyCadence(
        ib_client=overrides.get("ib", fake_ib),
        ai_analyst=overrides.get("ai", fake_ai),
        symbols=overrides.get("symbols", ["MES", "MNQ", "MGC"]),
        tradable_symbols=overrides.get("tradable", ["MES", "MGC"]),
        validator=overrides.get("validator", fake_validator),
    )


def test_base_default_sentiment_returns_empty():
    gen = _make_dummy()
    assert gen._maybe_fetch_sentiment() == ""


def test_base_default_read_plan_returns_empty_dict():
    gen = _make_dummy()
    assert gen._maybe_read_plan("2026-05-05") == {}


def test_base_default_fetch_trades_returns_empty_list():
    gen = _make_dummy()
    assert gen._maybe_fetch_trades("2026-05-05") == []


def test_base_default_compose_retrospective_returns_empty():
    gen = _make_dummy()
    assert gen._maybe_compose_retrospective({}, [], "2026-05-05") == ""


def test_base_default_compose_tomorrow_returns_empty():
    gen = _make_dummy()
    assert gen._maybe_compose_tomorrow() == ""


def test_base_validates_symbols_non_empty():
    fake_ib = MagicMock()
    fake_ai = MagicMock()
    with pytest.raises(ValueError, match="symbols must be non-empty"):
        _DummyCadence(
            ib_client=fake_ib, ai_analyst=fake_ai,
            symbols=[], tradable_symbols=[],
        )


def test_base_validates_tradable_subset_of_symbols():
    fake_ib = MagicMock()
    fake_ai = MagicMock()
    with pytest.raises(ValueError, match="not in symbols"):
        _DummyCadence(
            ib_client=fake_ib, ai_analyst=fake_ai,
            symbols=["MES"], tradable_symbols=["MGC"],
        )


def test_base_generate_returns_cadence_outcome():
    gen = _make_dummy()
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="07:00 PT", run_timestamp_et="10:00 ET",
        news_items=[], sentiment_md="",
    )
    assert isinstance(outcome, CadenceOutcome)
    assert outcome.report_text == "## Required\nstub\n"
    assert outcome.warnings == ()


def test_base_generate_fetches_all_tfs_per_symbol():
    """3 symbols × 2 TFs = 6 get_bars calls (no F-section get_bars to count separately)."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()
    fake_validator = MagicMock()
    fake_validator.validate.return_value = MagicMock(ok=True, missing=[])

    gen = _DummyCadence(
        ib_client=fake_ib, ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES"],
        validator=fake_validator,
    )
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="07:00 PT", run_timestamp_et="10:00 ET",
    )
    # Multi-TF: 3 symbols × 2 TFs = 6 bar fetches + 1 VP fetch per symbol = 9
    assert fake_ib.get_bars.call_count >= 6


def test_base_generate_warnings_accumulate():
    """When _fetch_news raises, warning entry is added but pipeline continues."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()
    fake_validator = MagicMock()
    fake_validator.validate.return_value = MagicMock(ok=True, missing=[])

    fake_news_collector = MagicMock(side_effect=RuntimeError("network blew up"))

    gen = _DummyCadence(
        ib_client=fake_ib, ai_analyst=fake_ai,
        symbols=["MES"], tradable_symbols=["MES"],
        validator=fake_validator,
        news_collector=fake_news_collector,
    )
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="07:00 PT", run_timestamp_et="10:00 ET",
    )
    assert any("news" in w for w in outcome.warnings), \
        f"news failure must be in warnings, got: {outcome.warnings}"


def test_cadence_outcome_is_frozen_dataclass():
    """CadenceOutcome should be frozen — no in-place mutation."""
    from daytrader.reports.types.base import CadenceOutcome
    fake_ai_result = MagicMock()
    fake_validation = MagicMock(ok=True, missing=[])
    outcome = CadenceOutcome(
        report_text="x", ai_result=fake_ai_result, validation=fake_validation,
        bars_by_symbol_and_tf={}, warnings=(),
    )
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        outcome.report_text = "different"


def test_cadence_outcome_warnings_default_empty_tuple():
    from daytrader.reports.types.base import CadenceOutcome
    outcome = CadenceOutcome(
        report_text="x",
        ai_result=MagicMock(),
        validation=MagicMock(ok=True, missing=[]),
    )
    assert outcome.warnings == ()
    assert outcome.bars_by_symbol_and_tf is None
