import yaml
from pathlib import Path
from loguru import logger
from jarvis.models import JarvisConfig

def load_config(config_dir: Path = None) -> JarvisConfig:
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / "config"

    default_yaml = config_dir / "default.yaml"
    user_yaml = config_dir / "user.yaml"

    if not default_yaml.exists():
        logger.warning(f"Default config not found at {default_yaml}")
        return JarvisConfig()

    with open(default_yaml, "r") as f:
        default_config = yaml.safe_load(f) or {}

    user_config = {}
    if user_yaml.exists():
        with open(user_yaml, "r") as f:
            user_config = yaml.safe_load(f) or {}

    merged = _deep_merge(default_config, user_config)

    try:
        config = JarvisConfig(**merged)
        logger.info(f"Loaded config from {config_dir}")
        return config
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        logger.info("Using default config")
        return JarvisConfig()

def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def save_user_config(config: JarvisConfig, config_dir: Path = None) -> None:
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / "config"

    config_dir.mkdir(parents=True, exist_ok=True)
    user_yaml = config_dir / "user.yaml"

    user_data = config.model_dump(mode="json")
    with open(user_yaml, "w") as f:
        yaml.dump(user_data, f, default_flow_style=False)

    logger.info(f"Saved user config to {user_yaml}")
