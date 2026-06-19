
import json
import threading
from pathlib import Path

_PATH = Path.home() / ".jarvis" / "api_requests.json"
_lock = threading.Lock()


async def send_request(method: str, url: str, headers=None, params=None,
                       body=None, timeout: float = 30.0) -> dict:
    import httpx
    method = (method or "GET").upper()
    if isinstance(body, str) and body.strip().startswith(("{", "[")):
        try:
            body = json.loads(body)
        except Exception:
            pass
    kwargs = {"headers": headers or None, "params": params or None}
    if body not in (None, "") and method in ("POST", "PUT", "PATCH", "DELETE"):
        if isinstance(body, (dict, list)):
            kwargs["json"] = body
        else:
            kwargs["content"] = str(body)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.request(method, url, **kwargs)
        ct = resp.headers.get("content-type", "")
        out_body = resp.text
        if "application/json" in ct:
            try:
                out_body = json.dumps(resp.json(), indent=2)
            except Exception:
                pass
        return {
            "ok": True,
            "status": resp.status_code,
            "reason": resp.reason_phrase,
            "headers": dict(resp.headers),
            "body": out_body,
            "elapsed_ms": int(resp.elapsed.total_seconds() * 1000),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


class RequestStore:
    """Persists named API requests (a lightweight Postman-style collection)."""

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

    def save(self, name: str, spec: dict) -> None:
        with _lock:
            self._data[name] = spec
            self._save()

    def get(self, name: str) -> dict | None:
        with _lock:
            return self._data.get(name)

    def list_all(self) -> dict:
        with _lock:
            return dict(self._data)

    def delete(self, name: str) -> bool:
        with _lock:
            if name in self._data:
                del self._data[name]
                self._save()
                return True
            return False


_instance: "RequestStore | None" = None
_inst_lock = threading.Lock()


def get_request_store() -> "RequestStore":
    global _instance
    if _instance is None:
        with _inst_lock:
            if _instance is None:
                _instance = RequestStore()
    return _instance
