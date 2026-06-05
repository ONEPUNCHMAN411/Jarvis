
import json
import threading
from pathlib import Path

_PATH = Path.home() / ".jarvis" / "profile.json"
_lock = threading.Lock()

# Map many field aliases to a small set of canonical keys used for autofill.
_ALIASES = {
    "name": "full_name", "fullname": "full_name", "full_name": "full_name",
    "first": "first_name", "firstname": "first_name", "first_name": "first_name", "fname": "first_name",
    "last": "last_name", "lastname": "last_name", "last_name": "last_name", "lname": "last_name", "surname": "last_name",
    "email": "email", "mail": "email", "e_mail": "email",
    "phone": "phone", "tel": "phone", "mobile": "phone", "cell": "phone", "telephone": "phone",
    "address": "address", "street": "address", "address1": "address", "addressline1": "address",
    "address2": "address2", "apt": "address2", "apartment": "address2", "suite": "address2", "unit": "address2",
    "city": "city", "town": "city",
    "state": "state", "province": "state", "region": "state",
    "zip": "zip", "zipcode": "zip", "postal": "zip", "postcode": "zip", "postalcode": "zip",
    "country": "country",
    "company": "company", "organization": "company", "organisation": "company", "employer": "company",
    "job": "job_title", "jobtitle": "job_title", "title": "job_title", "position": "job_title", "occupation": "job_title",
    "url": "url", "website": "url", "homepage": "url",
    "username": "username", "user": "username", "login": "username", "userid": "username",
}


def canonical_key(key: str) -> str:
    k = key.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    return _ALIASES.get(k, key.strip().lower().replace(" ", "_"))


class ProfileStore:
    """Stores the user's autofill profile (name, email, address, etc.)."""

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

    def set_field(self, key: str, value: str) -> str:
        ck = canonical_key(key)
        with _lock:
            self._data[ck] = value
            self._save()
        return ck

    def get_field(self, key: str) -> str | None:
        return self._data.get(canonical_key(key))

    def clear_field(self, key: str) -> bool:
        ck = canonical_key(key)
        with _lock:
            if ck in self._data:
                del self._data[ck]
                self._save()
                return True
        return False

    def get_all(self) -> dict:
        with _lock:
            return dict(self._data)


_instance: "ProfileStore | None" = None


def get_profile_store() -> "ProfileStore":
    global _instance
    if _instance is None:
        _instance = ProfileStore()
    return _instance
