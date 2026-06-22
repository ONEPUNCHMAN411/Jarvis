
import json
import threading
from pathlib import Path

_PATH = Path.home() / ".jarvis" / "contacts.json"
_lock = threading.Lock()
_FIELDS = ("email", "phone", "slack", "discord", "company", "notes")


class ContactStore:
    """Stores people so 'email John' / 'Slack Sarah' can resolve to real details."""

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if _PATH.exists():
            try:
                return json.loads(_PATH.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def add(self, name: str, **fields) -> dict:
        key = name.strip().lower()
        with _lock:
            entry = self._data.get(key, {"name": name.strip()})
            for k, v in fields.items():
                if k in _FIELDS and v:
                    entry[k] = v
            entry["name"] = name.strip()
            self._data[key] = entry
            self._save()
            return entry

    def get(self, name: str) -> dict | None:
        q = name.strip().lower()
        with _lock:
            if q in self._data:
                return self._data[q]
            for key, entry in self._data.items():
                if q in key:
                    return entry
            return None

    def update(self, name: str, field: str, value: str) -> bool:
        if field not in _FIELDS:
            return False
        with _lock:
            entry = None
            q = name.strip().lower()
            if q in self._data:
                entry = self._data[q]
            else:
                for key, e in self._data.items():
                    if q in key:
                        entry = e
                        break
            if entry is None:
                return False
            entry[field] = value
            self._save()
            return True

    def delete(self, name: str) -> bool:
        q = name.strip().lower()
        with _lock:
            if q in self._data:
                del self._data[q]
                self._save()
                return True
            for key in list(self._data):
                if q in key:
                    del self._data[key]
                    self._save()
                    return True
            return False

    def list_all(self) -> list[dict]:
        with _lock:
            return list(self._data.values())


_instance: "ContactStore | None" = None


def get_contact_store() -> "ContactStore":
    global _instance
    if _instance is None:
        _instance = ContactStore()
    return _instance
