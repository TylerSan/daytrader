"""Market-data source selection for `daytrader reports run`.

IB (TWS / IB Gateway) is the primary source. When it is unreachable, the
reports pipeline degrades to a yfinance-backed client (delayed ~15 min, no
open interest / contract chain) instead of losing the whole report.

This module is deliberately dependency-free (stdlib only) so it can be
imported from the prompt builder and the CLI without pulling in ib_insync
or yfinance.
"""

from __future__ import annotations

import socket
import sys
from typing import Any, Callable

DATA_SOURCE_NOTE_YF = "数据源：yfinance（延迟约 15 分钟；OI 与合约链不可用）"

VALID_SOURCES = ("ib", "yfinance", "auto")


def tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True iff a plain TCP connect to ``host:port`` succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _default_log(msg: str) -> None:
    print(msg, file=sys.stderr)


def select_data_client(
    source: str,
    *,
    ib_factory: Callable[[], Any],
    yf_factory: Callable[[], Any],
    probe: Callable[[], bool],
    log: Callable[[str], None] | None = None,
) -> tuple[Any, str]:
    """Pick and connect the market-data client.

    Returns ``(client, source_name)`` where ``source_name`` is ``"ib"`` or
    ``"yfinance"``.

    - ``"ib"``: build + connect IB; connection errors propagate (legacy
      behavior).
    - ``"yfinance"``: build the yfinance client unconditionally.
    - ``"auto"``: TCP-probe TWS first; if the port is closed or
      ``connect()`` raises, fall back to yfinance.
    """
    emit = log if log is not None else _default_log

    if source == "ib":
        ib = ib_factory()
        ib.connect()
        emit("[reports] data source: ib")
        return ib, "ib"

    if source == "yfinance":
        yf = yf_factory()
        emit("[reports] data source: yfinance (--source yfinance)")
        return yf, "yfinance"

    if source == "auto":
        if probe():
            ib = None
            try:
                ib = ib_factory()
                ib.connect()
            except Exception as exc:  # noqa: BLE001 — any IB failure → fallback
                emit(f"[reports] IB connect failed: {type(exc).__name__}: {exc}")
                if ib is not None:
                    try:
                        ib.disconnect()
                    except Exception:  # noqa: BLE001 — best-effort cleanup
                        pass
            else:
                emit("[reports] data source: ib")
                return ib, "ib"
        yf = yf_factory()
        emit("[reports] data source: yfinance (IB unreachable)")
        return yf, "yfinance"

    raise ValueError(
        f"unknown data source {source!r}; expected one of {VALID_SOURCES}"
    )
