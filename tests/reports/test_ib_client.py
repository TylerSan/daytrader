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
