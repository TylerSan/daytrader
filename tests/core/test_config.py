from pathlib import Path
import yaml

from daytrader.core.config import load_config, DayTraderConfig


def test_load_default_config(default_config: Path):
    cfg = load_config(default_config=default_config)
    assert cfg.database.path == "data/db/daytrader.db"
    assert cfg.notifications.enabled is False


def test_user_config_overrides_default(tmp_dir: Path, default_config: Path):
    user_cfg = {"notifications": {"enabled": True}}
    user_path = tmp_dir / "user.yaml"
    user_path.write_text(yaml.dump(user_cfg))

    cfg = load_config(default_config=default_config, user_config=user_path)
    assert cfg.notifications.enabled is True
    # default values preserved
    assert cfg.database.path == "data/db/daytrader.db"


def test_missing_user_config_uses_defaults(default_config: Path):
    cfg = load_config(
        default_config=default_config,
        user_config=Path("/nonexistent/user.yaml"),
    )
    assert cfg.database.path == "data/db/daytrader.db"
