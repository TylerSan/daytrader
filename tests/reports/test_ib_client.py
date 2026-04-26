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
