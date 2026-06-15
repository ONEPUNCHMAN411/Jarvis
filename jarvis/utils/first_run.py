"""First-run detection and user config directory management."""
import os
from pathlib import Path

def _appdata_jarvis_dir() -> Path:
    base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    return Path(base) / "JARVIS"

def get_user_config_path() -> Path:
    return _appdata_jarvis_dir() / "config.yaml"

def is_first_run() -> bool:
    return not get_user_config_path().exists()

def mark_setup_complete() -> None:
    _appdata_jarvis_dir().mkdir(parents=True, exist_ok=True)
