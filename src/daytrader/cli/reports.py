"""CLI command group `daytrader reports`.

Phase 1 provided dry-run; Phase 2 added run --type premarket which
invokes the full pipeline (IB → claude -p → Obsidian).
Phase 5+ will add other report types via the same dispatch table.
"""

from __future__ import annotations

import click


VALID_TYPES = (
    "premarket",
    "intraday-4h-1",
    "intraday-4h-2",
    "eod",
    "night",
    "asia",
    "weekly",
)


@click.group()
def reports() -> None:
    """Multi-cadence trading reports system."""


@reports.command("dry-run")
@click.option(
    "--type",
    "report_type",
    required=True,
    type=click.Choice(VALID_TYPES, case_sensitive=False),
    help="Report type to dry-run.",
)
def dry_run(report_type: str) -> None:
    """Dry-run a report-type pipeline (no network / file side effects).

    Phase 1 scope: prints the report type and exits successfully.
    Later phases plug in real fetch/AI/delivery steps with --no-side-effects flag.
    """
    click.echo(f"[dry-run] report_type={report_type}")
    click.echo("[dry-run] config load: OK (Phase 1 stub)")
    click.echo("[dry-run] state DB init: OK (Phase 1 stub)")
    click.echo("[dry-run] IB connection: skipped (Phase 1 stub)")
    click.echo("[dry-run] AI generation: skipped (Phase 1 stub)")
    click.echo("[dry-run] delivery: skipped (Phase 1 stub)")
    click.echo("[dry-run] dry-run complete")


@reports.command("run")
@click.option(
    "--type",
    "report_type",
    required=True,
    type=click.Choice(VALID_TYPES, case_sensitive=False),
    help="Report type to generate (Phase 2: only 'premarket' is implemented).",
)
@click.option(
    "--no-telegram",
    is_flag=True,
    default=False,
    help="Skip Telegram push (still writes Obsidian + PDF + charts).",
)
@click.option(
    "--no-pdf",
    is_flag=True,
    default=False,
    help="Skip PDF rendering (faster runs for testing).",
)
@click.pass_context
def run_cmd(ctx: click.Context, report_type: str, no_telegram: bool, no_pdf: bool) -> None:
    """Run a real report end-to-end (touches IB Gateway and Anthropic API).

    Phase 2 implements `--type premarket` only. Other types raise NotImplementedError.
    """
    import shutil
    from datetime import datetime, timezone
    from pathlib import Path

    from daytrader.core.config import load_config
    from daytrader.core.ib_client import IBClient
    from daytrader.core.state import StateDB
    from daytrader.reports.core.ai_analyst import AIAnalyst
    from daytrader.reports.core.orchestrator import Orchestrator

    if report_type != "premarket":
        click.echo(
            f"Phase 2 implements premarket only. {report_type!r} is in a later phase.",
            err=True,
        )
        ctx.exit(2)

    if shutil.which("claude") is None:
        click.echo(
            "claude CLI not found on PATH. Phase 2 uses `claude -p` "
            "(Pro Max subscription) — install Claude Code first.",
            err=True,
        )
        ctx.exit(3)

    project_root = Path(ctx.obj["project_root"]) if ctx.obj else Path.cwd()
    cfg = load_config(
        default_config=project_root / "config" / "default.yaml",
        user_config=project_root / "config" / "user.yaml",
    )

    state = StateDB(str(project_root / cfg.reports.state_db_path))
    state.initialize()

    ib = IBClient(
        host=cfg.reports.ib.host,
        port=cfg.reports.ib.port,
        client_id=cfg.reports.ib.client_id,
    )
    ib.connect()
    try:
        ai = AIAnalyst()  # claude -p backend; no API key needed

        vault_root = Path(cfg.obsidian.vault_path).expanduser()
        fallback_dir = project_root / "data" / "exports"

        from daytrader.reports.instruments.definitions import (
            load_instruments,
            tradable_symbols as get_tradable,
        )

        instruments = load_instruments(
            str(project_root / cfg.reports.instruments_yaml)
        )
        all_symbols = sorted(instruments.keys())
        tradable = get_tradable(instruments)

        from daytrader.reports.delivery.chart_renderer import ChartRenderer
        from daytrader.reports.delivery.pdf_renderer import PDFRenderer
        from daytrader.reports.delivery.telegram_pusher import TelegramPusher
        from daytrader.reports.core.secrets import load_secrets, SecretsError

        chart_renderer = ChartRenderer(
            output_dir=project_root / "data" / "exports" / "charts",
        )

        pdf_renderer = None
        if not no_pdf:
            try:
                pdf_renderer = PDFRenderer(
                    output_dir=project_root / "data" / "exports" / "pdfs",
                )
            except Exception as e:
                click.echo(f"PDF renderer unavailable: {e}", err=True)

        telegram_pusher = None
        if not no_telegram:
            try:
                secrets = load_secrets(str(project_root / "config" / "secrets.yaml"))
                from telegram import Bot
                bot = Bot(token=secrets.telegram_bot_token)
                telegram_pusher = TelegramPusher(
                    bot=bot,
                    chat_id=secrets.telegram_chat_id,
                )
            except SecretsError as e:
                click.echo(f"Telegram disabled: {e}", err=True)
            except Exception as e:
                click.echo(f"Telegram setup failed: {e}", err=True)

        orchestrator = Orchestrator(
            state_db=state,
            ib_client=ib,
            ai_analyst=ai,
            contract_path=project_root / cfg.journal.contract_path,
            journal_db_path=project_root / cfg.journal.db_path,
            vault_root=vault_root,
            fallback_dir=fallback_dir,
            daily_folder=cfg.obsidian.daily_folder,
            symbols=all_symbols,
            tradable_symbols=tradable,
            chart_renderer=chart_renderer,
            pdf_renderer=pdf_renderer,
            telegram_pusher=telegram_pusher,
        )
        result = orchestrator.run_premarket(run_at=datetime.now(timezone.utc))

        if result.skipped_idempotent:
            click.echo("Report already generated today (skipped).")
            return
        if result.success:
            click.echo(f"Report generated: {result.report_path}")
        else:
            click.echo(f"Report FAILED: {result.failure_reason}", err=True)
            ctx.exit(1)
    finally:
        ib.disconnect()


@reports.command("pine")
@click.option(
    "--symbol",
    "symbols",
    multiple=True,
    default=None,
    help="One or more symbols to render (repeat the flag). Defaults to "
         "all symbols in instruments.yaml.",
)
@click.pass_context
def pine_cmd(ctx: click.Context, symbols: tuple[str, ...]) -> None:
    """Generate Pine Script files of key levels for TradingView paste-in.

    Output: data/exports/pine/levels-{SYMBOL}-{YYYY-MM-DD}.pine
    Per the user contract, all instruments in instruments.yaml are rendered
    (MES + MGC tradable, MNQ context-only — TradingView gets levels for all).

    Workflow:
      1. Run this command (5-10 sec for 3 symbols)
      2. Open TradingView, switch to MES (or ES) chart
      3. Open Pine Editor → paste contents of levels-MES-DATE.pine
      4. "Add to chart" → hlines appear
      5. Repeat for MGC + MNQ
    """
    from datetime import date as date_cls
    from pathlib import Path

    from daytrader.core.config import load_config
    from daytrader.core.ib_client import IBClient
    from daytrader.reports.delivery.pine_renderer import (
        LevelExtractor,
        PineScriptRenderer,
    )
    from daytrader.reports.instruments.definitions import load_instruments

    project_root = Path(ctx.obj["project_root"]) if ctx.obj else Path.cwd()
    cfg = load_config(
        default_config=project_root / "config" / "default.yaml",
        user_config=project_root / "config" / "user.yaml",
    )

    if symbols:
        target_symbols = list(symbols)
    else:
        instruments = load_instruments(
            str(project_root / cfg.reports.instruments_yaml)
        )
        target_symbols = sorted(instruments.keys())

    output_dir = project_root / "data" / "exports" / "pine"
    today = date_cls.today()

    ib = IBClient(
        host=cfg.reports.ib.host,
        port=cfg.reports.ib.port,
        client_id=cfg.reports.ib.client_id + 100,  # avoid conflict with `run`
    )
    ib.connect()
    try:
        extractor = LevelExtractor(ib_client=ib)
        renderer = PineScriptRenderer(output_dir=output_dir)

        click.echo(f"Generating Pine for {len(target_symbols)} symbols → {output_dir}/")
        for symbol in target_symbols:
            try:
                levels = extractor.extract(symbol=symbol)
                path = renderer.render_and_save(
                    levels=levels, symbol=symbol, today=today
                )
                non_null = sum(
                    1 for v in (
                        levels.prior_day_high, levels.prior_day_low,
                        levels.prior_day_close, levels.weekly_high,
                        levels.weekly_low,
                    ) if v is not None
                )
                click.echo(f"  ✓ {symbol}: {non_null}/5 levels → {path.name}")
            except Exception as e:
                click.echo(f"  ✗ {symbol}: {type(e).__name__}: {e}", err=True)
    finally:
        ib.disconnect()

    click.echo(f"\nDone. Paste each .pine file into TradingView Pine Editor.")
