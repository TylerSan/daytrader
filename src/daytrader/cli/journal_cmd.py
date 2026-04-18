"""Journal CLI commands — pre-trade, post-trade, circuit."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import click

from daytrader.core.config import load_config
from daytrader.journal.checklist import ChecklistInput, ChecklistService
from daytrader.journal.circuit import CircuitService
from daytrader.journal.contract import parse_contract_md
from daytrader.journal.models import TradeMode, TradeSide
from daytrader.journal.repository import JournalRepository
from daytrader.journal.trades import PostTradeInput, PostTradeService


def _load_cfg_and_repo():
    """Load config + initialize repository.

    Also sync active contract from Contract.md if on-disk contract is newer
    than the DB active contract.  The contract_path guard (`if exists`) means
    tests that run without a real Contract.md on disk won't break.
    """
    project_root = Path(__file__).resolve().parents[3]
    cfg = load_config(
        default_config=project_root / "config" / "default.yaml",
        user_config=project_root / "config" / "user.yaml",
    )
    db_path = project_root / cfg.journal.db_path
    repo = JournalRepository(str(db_path))
    repo.initialize()

    contract_path = project_root / cfg.journal.contract_path
    if contract_path.exists():
        try:
            parsed = parse_contract_md(contract_path)
            if parsed.active:
                active = repo.get_active_contract()
                if active is None or active.version != parsed.version:
                    repo.save_contract(parsed)
        except Exception as e:
            click.echo(f"contract parse warning: {e}", err=True)

    return cfg, repo


@click.command("pre-trade")
@click.option("--symbol", required=True, type=click.Choice(["MES", "MNQ", "MGC"]))
@click.option("--direction", required=True, type=click.Choice(["long", "short"]))
@click.option("--setup", "setup_type", required=True,
              help="Setup name (must match contract lock-in)")
@click.option("--entry", "entry_price", required=True, type=str)
@click.option("--stop", "stop_price", required=True, type=str)
@click.option("--target", "target_price", required=True, type=str)
@click.option("--size", required=True, type=int)
@click.option("--stop-at-broker/--no-stop-at-broker", default=False,
              help="Confirm stop is already placed at broker (OCO/bracket)")
@click.option("--dry-run", is_flag=True,
              help="Record as dry-run instead of real trade")
def pre_trade(symbol, direction, setup_type, entry_price, stop_price,
              target_price, size, stop_at_broker, dry_run):
    """Run pre-trade checklist. Creates trade record only if all items pass."""
    _cfg, repo = _load_cfg_and_repo()
    circuit = CircuitService(repo)
    svc = ChecklistService(repo, circuit)

    inp = ChecklistInput(
        mode=TradeMode.DRY_RUN if dry_run else TradeMode.REAL,
        symbol=symbol,
        direction=TradeSide(direction),
        setup_type=setup_type,
        entry_price=Decimal(entry_price),
        stop_price=Decimal(stop_price),
        target_price=Decimal(target_price),
        size=size,
        stop_at_broker=stop_at_broker,
    )
    result = svc.run(inp, now=datetime.now(timezone.utc))

    if result.passed:
        click.echo(f"PASSED  checklist_id={result.checklist_id}")
        if result.trade_id:
            click.echo(f"  trade_id={result.trade_id}")
            click.echo(
                "  Now place the order at your broker with the exact stop. "
                "Call `daytrader journal post-trade` after exit."
            )
    else:
        click.echo(f"BLOCKED  reason={result.failure_reason}")
        if result.failed_items:
            click.echo(f"  failed_items: {', '.join(result.failed_items)}")
        raise click.exceptions.Exit(1)


@click.command("post-trade")
@click.argument("trade_id")
@click.option("--exit-price", required=True, type=str)
@click.option("--was-stop", is_flag=True, help="Exit was at stop (loss)")
@click.option("--notes", default="",
              help="One-sentence reflection (required, written immediately after exit)")
def post_trade(trade_id, exit_price, was_stop, notes):
    """Close a trade. Updates circuit state with outcome."""
    if not notes.strip():
        raise click.UsageError(
            "--notes is required (one sentence, written immediately after exit)"
        )

    _cfg, repo = _load_cfg_and_repo()
    svc = PostTradeService(repo, CircuitService(repo))
    try:
        svc.close(PostTradeInput(
            trade_id=trade_id,
            exit_time=datetime.now(timezone.utc),
            exit_price=Decimal(exit_price),
            was_stop=was_stop,
            notes=notes,
        ))
    except ValueError as e:
        raise click.UsageError(str(e))

    trade = repo.get_trade(trade_id)
    click.echo(f"closed  pnl_usd={trade.pnl_usd}  r={trade.r_multiple()}")
    state = repo.get_circuit_state(trade.date)
    if state.no_trade_flag:
        click.echo(f"Circuit LOCKED for {state.date}: {state.lock_reason}")


@click.group("circuit")
def circuit_group():
    """Daily loss circuit queries."""


@circuit_group.command("status")
def circuit_status():
    """Print today's circuit state."""
    _cfg, repo = _load_cfg_and_repo()
    today = datetime.now(timezone.utc).date()
    state = repo.get_circuit_state(today)
    click.echo(f"Date: {state.date}")
    click.echo(f"Realized R: {state.realized_r}")
    click.echo(f"Realized USD: {state.realized_usd}")
    click.echo(f"Trade count: {state.trade_count}")
    click.echo(f"No-trade flag: {state.no_trade_flag}")
    if state.no_trade_flag:
        click.echo(f"Lock reason: {state.lock_reason}")
    if state.last_stop_time:
        click.echo(f"Last stop: {state.last_stop_time}")


@click.group("sanity")
def sanity_group():
    """Sanity-floor backtest commands."""


@sanity_group.command("run")
@click.argument("setup_file", type=click.Path(exists=True, path_type=Path))
@click.option("--symbol", multiple=True, default=None,
              help="Override symbols (otherwise use setup's list)")
@click.option("--window-days", default=90, type=int)
def sanity_run(setup_file: Path, symbol: tuple[str, ...], window_days: int):
    """Run sanity-floor backtest on a setup YAML."""
    from datetime import date as _d
    from daytrader.journal.sanity_floor.data_loader import HistoricalDataLoader
    from daytrader.journal.sanity_floor.runner import (
        RunnerConfig, run_setup_for_symbol,
    )
    from daytrader.journal.sanity_floor.setup_yaml import load_setup_yaml

    cfg, repo = _load_cfg_and_repo()
    setup = load_setup_yaml(setup_file)
    loader = HistoricalDataLoader(cache_dir=cfg.journal.data_cache_dir)
    run_date = _d.today()
    symbols = list(symbol) if symbol else setup.symbols
    rconf = RunnerConfig(data_window_days=window_days)
    click.echo(
        "WARNING: Sanity-Floor Backtest -- this is NOT a 'good' backtest.\n"
        "         It only rejects obviously broken setups.\n"
        "         Passing does NOT mean the setup has edge.\n"
    )
    for sym in symbols:
        try:
            v = run_setup_for_symbol(
                setup=setup, symbol=sym, loader=loader,
                repo=repo, run_date=run_date, config=rconf,
            )
            status = "PASSED" if v.passed else "FAILED"
            click.echo(
                f"[{status}] {setup.name}/{sym}: "
                f"n={v.n_samples} win_rate={v.win_rate:.2%} "
                f"avg_r={v.avg_r:.3f}"
            )
        except Exception as e:
            click.echo(f"[ERROR] {setup.name}/{sym}: {e}", err=True)
