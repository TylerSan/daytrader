import pytest
from pathlib import Path
import tempfile
import yaml


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
