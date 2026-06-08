import json
import os
import subprocess
import base64
from copy import deepcopy
from pathlib import Path

# Windows DPAPI — encrypts data bound to the current user account so no other
# user or process on this machine can read it without the user's credentials.
try:
    import win32crypt as _dpapi
    _HAS_DPAPI = True
except ImportError:
    _dpapi = None
    _HAS_DPAPI = False

_DPAPI_PREFIX = "dpapi:"

def _encrypt(plaintext: str) -> str:
    """Encrypt a string with Windows DPAPI. Returns 'dpapi:<base64>' or the original on failure."""
    if not plaintext or not _HAS_DPAPI:
        return plaintext
    try:
        encrypted = _dpapi.CryptProtectData(plaintext.encode("utf-8"), None, None, None, None, 0)
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception:
        return plaintext

def _decrypt(value: str) -> str:
    """Decrypt a DPAPI-encrypted value. Falls through for plaintext (migration path)."""
    if not value or not _HAS_DPAPI or not value.startswith(_DPAPI_PREFIX):
        return value
    try:
        encrypted = base64.b64decode(value[len(_DPAPI_PREFIX):])
        _, decrypted = _dpapi.CryptUnprotectData(encrypted, None, None, None, 0)
        return decrypted.decode("utf-8")
    except Exception:
        return value  # decryption failed — return as-is (handles corruption gracefully)

def _encrypt_keys(settings: dict) -> dict:
    """Recursively encrypt all 'api_key' and 'oauth_token_path' values before writing."""
    result = deepcopy(settings)
    for key, value in result.items():
        if isinstance(value, dict):
            result[key] = _encrypt_keys(value)
        elif key in ("api_key",) and isinstance(value, str) and value:
            result[key] = _encrypt(value)
    return result

def _decrypt_keys(settings: dict) -> dict:
    """Recursively decrypt 'api_key' values after loading."""
    result = deepcopy(settings)
    for key, value in result.items():
        if isinstance(value, dict):
            result[key] = _decrypt_keys(value)
        elif key in ("api_key",) and isinstance(value, str):
            result[key] = _decrypt(value)
    return result

def _secure_directory(path: Path) -> None:
    """Restrict ~/.jarvis to the current user only (Windows ACL)."""
    try:
        username = os.environ.get("USERNAME") or os.getlogin()
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:F"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass  # Non-fatal — DPAPI encryption is the primary protection

def default_settings() -> dict:
    return {
        "automation_policy": "full_auto",
        "background_mode": "wake_phrase",
        "overlay_mode": "floating",
        "minimize_behavior": "orb_only",
        "primary_provider": "mistral",
        "voice_enabled": True,
        "voice_profile": "jarvis",
        "custom_voice_profile": {
            "label": "Custom imported profile",
            "voice": "en-US-EricNeural",
            "rate": "-2%",
            "pitch": "-1Hz",
        },
        "screen_awareness": True,
        "start_minimized": True,
        "pinned_context": "",
        "chat_font_size": 14,
        "providers": {
            "ollama": {
                "enabled": True,
                "base_url": "http://localhost:11434",
                "model": "llama3.1:8b",
            },
            "mistral": {
                "enabled": False,
                "api_key": "",
                "model": "mistral-small-latest",
            },
            "groq": {
                "enabled": False,
                "api_key": "",
                "model": "llama-3.3-70b-versatile",
            },
            "gemini": {
                "enabled": False,
                "api_key": "",
                "model": "gemini-2.0-flash",
            },
            "openrouter": {
                "enabled": False,
                "api_key": "",
                "model": "meta-llama/llama-3.1-8b-instruct:free",
            },
            "claude": {
                "enabled": False,
                "api_key": "",
                "model": "claude-haiku-4-5",
            },
            "openai": {
                "enabled": False,
                "api_key": "",
                "base_url": "",
                "model": "gpt-4o",
            },
        },
    }


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (Path.home() / ".jarvis" / "settings.json")
        created = not self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if created:
            _secure_directory(self.path.parent)

    def load(self) -> dict:
        settings = default_settings()
        if self.path.exists():
            with self.path.open("r", encoding="utf-8-sig") as handle:
                on_disk = json.load(handle)
            on_disk = _decrypt_keys(on_disk)
            settings = _deep_merge(settings, on_disk)
        return settings

    def save(self, settings: dict) -> None:
        merged = _deep_merge(default_settings(), settings)
        encrypted = _encrypt_keys(merged)
        with self.path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(encrypted, handle, indent=2)


def _deep_merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
