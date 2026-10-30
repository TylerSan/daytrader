"""`daytrader reports run --source` wiring (IB / yfinance / auto)."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from daytrader.cli.main import cli


def test_run_help_lists_source_option():
    result = CliRunner().invoke(cli, ["reports", "run", "--help"])
    assert result.exit_code == 0
    assert "--source" in result.output
    assert "[ib|yfinance|auto]" in result.output
    assert "auto" in result.output and "yfinance" in result.output


def test_run_rejects_unknown_source():
    result = CliRunner().invoke(
        cli, ["reports", "run", "--type", "premarket", "--source", "bloomberg"]
    )
    assert result.exit_code != 0


class _FakeIB:
    instances: list["_FakeIB"] = []

    def __init__(self, host, port, client_id):
        self.host, self.port, self.client_id = host, port, client_id
        self.connected = False
        self.disconnected = False
        _FakeIB.instances.append(self)

    def connect(self, timeout=10):
        self.connected = True

    def disconnect(self):
        self.disconnected = True


class _FakeYF:
    instances: list["_FakeYF"] = []

    def __init__(self):
        self.disconnected = False
        _FakeYF.instances.append(self)

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Patch every heavy dependency of run_cmd; capture Orchestrator kwargs."""
    _FakeIB.instances.clear()
    _FakeYF.instances.clear()
    captured: dict = {}

    import daytrader.core.config as config_mod
    import daytrader.core.ib_client as ib_mod
    import daytrader.core.state as state_mod
    import daytrader.reports.core.ai_analyst as ai_mod
    import daytrader.reports.core.data_source as ds_mod
    import daytrader.reports.core.orchestrator as orch_mod
    import daytrader.reports.delivery.chart_renderer as chart_mod
    import daytrader.reports.instruments.definitions as inst_mod

    cfg = SimpleNamespace(
        reports=SimpleNamespace(
            state_db_path="data/state.db",
            instruments_yaml="config/instruments.yaml",
            ib=SimpleNamespace(host="127.0.0.1", port=7496, client_id=7),
        ),
        obsidian=SimpleNamespace(vault_path=str(tmp_path / "vault"), daily_folder="Daily"),
        journal=SimpleNamespace(contract_path="Contract.md", db_path="journal.db"),
    )
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(config_mod, "load_config", lambda **kw: cfg)
    monkeypatch.setattr(state_mod, "StateDB", MagicMock())
    monkeypatch.setattr(ib_mod, "IBClient", _FakeIB)
    monkeypatch.setattr(ai_mod, "AIAnalyst", MagicMock())
    monkeypatch.setattr(inst_mod, "load_instruments", lambda path: {"MES": {}, "MGC": {}})
    monkeypatch.setattr(inst_mod, "tradable_symbols", lambda inst: ["MES"])
    monkeypatch.setattr(chart_mod, "ChartRenderer", MagicMock())

    fake_yf_module = types.ModuleType("daytrader.reports.core.yf_client")
    fake_yf_module.YFClient = _FakeYF
    monkeypatch.setitem(sys.modules, "daytrader.reports.core.yf_client", fake_yf_module)

    def _orchestrator(**kwargs):
        captured.update(kwargs)
        orch = MagicMock()
        orch.run_premarket.return_value = SimpleNamespace(
            skipped_idempotent=False, success=True,
            report_path=tmp_path / "r.md", failure_reason=None,
        )
        return orch

    monkeypatch.setattr(orch_mod, "Orchestrator", _orchestrator)

    def set_probe(ok: bool):
        monkeypatch.setattr(ds_mod, "tcp_probe", lambda host, port, timeout=2.0: ok)

    return SimpleNamespace(captured=captured, set_probe=set_probe)


def _invoke(*extra):
    return CliRunner().invoke(
        cli,
        ["reports", "run", "--type", "premarket", "--no-telegram", "--no-pdf", *extra],
    )


def test_auto_falls_back_to_yfinance_when_tws_port_closed(wired):
    wired.set_probe(False)
    result = _invoke()
    assert result.exit_code == 0, result.output
    assert wired.captured["data_source"] == "yfinance"
    assert isinstance(wired.captured["ib_client"], _FakeYF)
    assert _FakeIB.instances == []
    assert _FakeYF.instances[0].disconnected is True  # finally: disconnect()


def test_auto_uses_ib_when_reachable(wired):
    wired.set_probe(True)
    result = _invoke("--source", "auto")
    assert result.exit_code == 0, result.output
    assert wired.captured["data_source"] == "ib"
    ib = _FakeIB.instances[0]
    assert wired.captured["ib_client"] is ib
    assert (ib.host, ib.port, ib.client_id) == ("127.0.0.1", 7496, 7)
    assert ib.connected and ib.disconnected


def test_source_yfinance_never_touches_ib(wired):
    wired.set_probe(True)
    result = _invoke("--source", "yfinance")
    assert result.exit_code == 0, result.output
    assert wired.captured["data_source"] == "yfinance"
    assert _FakeIB.instances == []


def test_source_ib_keeps_legacy_behavior(wired):
    wired.set_probe(False)  # probe ignored for --source ib
    result = _invoke("--source", "ib")
    assert result.exit_code == 0, result.output
    assert wired.captured["data_source"] == "ib"
    assert _FakeIB.instances[0].connected
