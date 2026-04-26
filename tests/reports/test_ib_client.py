"""Unit tests for daytrader.core.ib_client.IBClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from daytrader.core.ib_client import IBClient


def test_ibclient_instantiates_with_defaults():
    """IBClient can be created with default host/port."""
    client = IBClient()
    assert client.host == "127.0.0.1"
    assert client.port == 4002  # IB Gateway live default
    assert client.client_id == 1
    assert client.is_healthy() is False  # not connected yet


def test_ibclient_custom_host_port():
    """IBClient accepts custom host/port/client_id."""
    client = IBClient(host="10.0.0.5", port=7497, client_id=42)
    assert client.host == "10.0.0.5"
    assert client.port == 7497
    assert client.client_id == 42


def test_ibclient_connect_calls_ib_insync(monkeypatch):
    """connect() invokes ib_insync.IB().connect with our params."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    fake_ib_class = MagicMock(return_value=fake_ib)
    monkeypatch.setattr("daytrader.core.ib_client.IB", fake_ib_class)

    client = IBClient(host="1.2.3.4", port=9999, client_id=7)
    client.connect()

    fake_ib_class.assert_called_once()
    fake_ib.connect.assert_called_once_with(
        host="1.2.3.4", port=9999, clientId=7, timeout=10
    )
    assert client.is_healthy() is True


def test_ibclient_disconnect_closes_connection(monkeypatch):
    """disconnect() calls ib_insync.IB.disconnect and resets state."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    client.disconnect()

    fake_ib.disconnect.assert_called_once()


from datetime import datetime, timezone


def test_ibclient_get_bars_returns_ohlcv(monkeypatch):
    """get_bars() returns list of OHLCV from ib_insync."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    fake_bar = MagicMock()
    fake_bar.date = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    fake_bar.open = 5240.00
    fake_bar.high = 5252.50
    fake_bar.low = 5238.25
    fake_bar.close = 5246.75
    fake_bar.volume = 142830

    fake_ib.reqHistoricalData.return_value = [fake_bar]

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    bars = client.get_bars(symbol="MES", timeframe="4H", bars=50)

    assert len(bars) == 1
    assert bars[0].open == 5240.00
    assert bars[0].close == 5246.75
    assert bars[0].volume == 142830

    # Verify the IB call
    fake_ib.reqHistoricalData.assert_called_once()
    call_kwargs = fake_ib.reqHistoricalData.call_args.kwargs
    assert call_kwargs["barSizeSetting"] == "4 hours"
    assert call_kwargs["durationStr"] == "8 D"  # 50 × 4H ≈ 8 days


def test_ibclient_get_bars_unsupported_timeframe_raises():
    """Unsupported timeframe raises ValueError."""
    client = IBClient()
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        client.get_bars(symbol="MES", timeframe="3H", bars=10)


def test_ibclient_get_snapshot_returns_current_quote(monkeypatch):
    """get_snapshot() returns current bid/ask/last."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    fake_ticker = MagicMock()
    fake_ticker.bid = 5246.50
    fake_ticker.ask = 5246.75
    fake_ticker.last = 5246.75
    fake_ticker.time = datetime(2026, 4, 25, 14, 30, tzinfo=timezone.utc)

    fake_ib.reqMktData.return_value = fake_ticker
    fake_ib.sleep = MagicMock()

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    snap = client.get_snapshot(symbol="MES")

    assert snap.bid == 5246.50
    assert snap.ask == 5246.75
    assert snap.last == 5246.75


def test_ibclient_connect_idempotent(monkeypatch):
    """Calling connect() twice does not call ib_insync.connect() twice."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    client.connect()  # second call must early-return

    # connect() called exactly once on the underlying IB
    fake_ib.connect.assert_called_once()


def test_ibclient_reconnect_disconnects_then_reconnects(monkeypatch):
    """reconnect() calls disconnect() then connect()."""
    fake_ib = MagicMock()
    # isConnected() call sequence during reconnect():
    #   call #1 (in disconnect()): True  → triggers ib.disconnect()
    #   call #2 (in connect()):    False → allows ib.connect() to proceed
    fake_ib.isConnected.side_effect = [True, False]

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    client.reconnect()

    # disconnect was called once, connect was called twice (initial + after reconnect)
    fake_ib.disconnect.assert_called_once()
    assert fake_ib.connect.call_count == 2


def test_ibclient_get_bars_raises_when_not_connected(monkeypatch):
    """get_bars raises RuntimeError when called after disconnect."""
    fake_ib = MagicMock()
    # Track connection state: True after connect, False after disconnect
    fake_ib.isConnected.return_value = True

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    fake_ib.isConnected.return_value = False  # simulate disconnect
    client.disconnect()

    with pytest.raises(RuntimeError, match="not connected"):
        client.get_bars(symbol="MES", timeframe="4H", bars=10)


def test_ibclient_get_snapshot_raises_when_not_connected(monkeypatch):
    """get_snapshot raises RuntimeError when called after disconnect."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    client = IBClient()
    client.connect()
    fake_ib.isConnected.return_value = False
    client.disconnect()

    with pytest.raises(RuntimeError, match="not connected"):
        client.get_snapshot(symbol="MES")


def test_ibclient_get_bars_routes_mgc_to_comex(monkeypatch):
    """MGC must use COMEX exchange, not CME."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    fake_bar = MagicMock()
    fake_bar.date = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    fake_bar.open = fake_bar.high = fake_bar.low = fake_bar.close = 2340.0
    fake_bar.volume = 50000
    fake_ib.reqHistoricalData.return_value = [fake_bar]

    monkeypatch.setattr(
        "daytrader.core.ib_client.IB", MagicMock(return_value=fake_ib)
    )

    # patch ContFuture so we can capture the exchange arg
    fake_cont_future_class = MagicMock()
    monkeypatch.setattr(
        "ib_insync.ContFuture",
        fake_cont_future_class,
    )

    client = IBClient()
    client.connect()
    client.get_bars(symbol="MGC", timeframe="1D", bars=5)

    # The ContFuture was called with ("MGC", "COMEX")
    fake_cont_future_class.assert_called_with("MGC", "COMEX")


def test_ibclient_unknown_symbol_raises():
    """Unknown symbol → ValueError from _exchange_for."""
    from daytrader.core.ib_client import _exchange_for

    with pytest.raises(ValueError, match="Unknown symbol"):
        _exchange_for("BOGUS")
