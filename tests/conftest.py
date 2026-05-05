import pytest
from pathlib import Path
import tempfile
import yaml


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip tests marked `slow` unless the user explicitly selects them via -m slow."""
    if config.option.markexpr and "slow" in config.option.markexpr:
        return  # user opted in — run them
    skip_slow = pytest.mark.skip(reason="slow test — run with: uv run pytest -m slow")
    for item in items:
        if item.get_closest_marker("slow"):
            item.add_marker(skip_slow)


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def default_config(tmp_dir: Path) -> Path:
    cfg = {
        "database": {"path": "data/db/daytrader.db"},
        "notifications": {
            "enabled": False,
            "channels": {
                "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
                "discord": {"enabled": False, "webhook_url": ""},
                "imessage": {"enabled": False, "recipient": ""},
            },
        },
        "premarket": {"push_on_complete": False},
        "backtest": {"default_config": "stacked_imbalance.yaml"},
    }
    path = tmp_dir / "default.yaml"
    path.write_text(yaml.dump(cfg))
    return path
