"""Tests for reports.core.data_source (IB → yfinance fallback selection)."""

from __future__ import annotations

import socket

import pytest

from daytrader.reports.core.data_source import (
    DATA_SOURCE_NOTE_YF,
    select_data_client,
    tcp_probe,
)


class FakeIB:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.connected = False
        self.disconnected = False

    def connect(self, timeout=10):
        if self.fail:
            raise ConnectionRefusedError("TWS down")
        self.connected = True

    def disconnect(self):
        self.disconnected = True


class FakeYF:
    source_name = "yfinance"


def _run(source, *, probe_ok=True, ib_fail=False):
    logs: list[str] = []
    made = {"ib": [], "yf": []}

    def ib_factory():
        ib = FakeIB(fail=ib_fail)
        made["ib"].append(ib)
        return ib

    def yf_factory():
        yf = FakeYF()
        made["yf"].append(yf)
        return yf

    client, name = select_data_client(
        source,
        ib_factory=ib_factory,
        yf_factory=yf_factory,
        probe=lambda: probe_ok,
        log=logs.append,
    )
    return client, name, logs, made


def test_note_text():
    assert DATA_SOURCE_NOTE_YF.startswith("数据源：yfinance")


def test_source_ib_connects_and_logs():
    client, name, logs, made = _run("ib")
    assert name == "ib" and isinstance(client, FakeIB) and client.connected
    assert logs == ["[reports] data source: ib"]
    assert made["yf"] == []


def test_source_ib_propagates_connect_error():
    with pytest.raises(ConnectionRefusedError):
        _run("ib", ib_fail=True)


def test_source_ib_does_not_probe():
    def boom():
        raise AssertionError("probe must not be called for --source ib")

    client, name = select_data_client(
        "ib", ib_factory=FakeIB, yf_factory=FakeYF, probe=boom, log=lambda m: None
    )
    assert name == "ib"


def test_source_yfinance_skips_ib():
    client, name, logs, made = _run("yfinance")
    assert name == "yfinance" and isinstance(client, FakeYF)
    assert made["ib"] == []
    assert logs == ["[reports] data source: yfinance (--source yfinance)"]


def test_auto_probe_down_falls_back_without_building_ib():
    client, name, logs, made = _run("auto", probe_ok=False)
    assert name == "yfinance" and isinstance(client, FakeYF)
    assert made["ib"] == []
    assert logs == ["[reports] data source: yfinance (IB unreachable)"]


def test_auto_connect_failure_falls_back_and_disconnects():
    client, name, logs, made = _run("auto", probe_ok=True, ib_fail=True)
    assert name == "yfinance" and isinstance(client, FakeYF)
    assert made["ib"][0].disconnected is True
    assert logs[-1] == "[reports] data source: yfinance (IB unreachable)"


def test_auto_ib_factory_failure_falls_back():
    def bad_factory():
        raise RuntimeError("cannot build")

    client, name = select_data_client(
        "auto", ib_factory=bad_factory, yf_factory=FakeYF,
        probe=lambda: True, log=lambda m: None,
    )
    assert name == "yfinance"


def test_auto_ib_up_uses_ib():
    client, name, logs, made = _run("auto", probe_ok=True)
    assert name == "ib" and client.connected
    assert made["yf"] == []
    assert logs == ["[reports] data source: ib"]


def test_unknown_source_raises():
    with pytest.raises(ValueError):
        _run("bloomberg")


def test_default_log_goes_to_stderr(capsys):
    select_data_client(
        "yfinance", ib_factory=FakeIB, yf_factory=FakeYF, probe=lambda: True
    )
    captured = capsys.readouterr()
    assert "[reports] data source: yfinance (--source yfinance)" in captured.err
    assert captured.out == ""


def test_tcp_probe_open_and_closed_port():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert tcp_probe("127.0.0.1", port, timeout=1.0) is True
    finally:
        srv.close()
    # Same port, now closed.
    assert tcp_probe("127.0.0.1", port, timeout=1.0) is False
