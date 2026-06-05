import json
import subprocess
import time as _t
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

_PATH = Path.home() / ".jarvis" / "launch_sequences.json"


@dataclass
class LaunchApp:
    path: str
    args: list = field(default_factory=list)
    delay_ms: int = 800


@dataclass
class LaunchSequence:
    id: str
    name: str
    description: str
    apps: list
    workspace: str | None
    created_at: str

    def __post_init__(self):
        self.apps = [LaunchApp(**a) if isinstance(a, dict) else a for a in self.apps]


class AppLaunchStore:
    def __init__(self):
        self._seqs: list[LaunchSequence] = []
        self._load()

    def _load(self):
        if _PATH.exists():
            try:
                self._seqs = [LaunchSequence(**s) for s in json.loads(_PATH.read_text("utf-8"))]
            except Exception:
                self._seqs = []

    def _save(self):
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps([asdict(s) for s in self._seqs], indent=2), "utf-8")

    def add(self, name: str, description: str, apps: list, workspace: str | None = None) -> LaunchSequence:
        seq = LaunchSequence(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            apps=[LaunchApp(**a) if isinstance(a, dict) else a for a in apps],
            workspace=workspace,
            created_at=datetime.now().isoformat(),
        )
        self._seqs.append(seq)
        self._save()
        return seq

    def get(self, key: str) -> LaunchSequence | None:
        for s in self._seqs:
            if s.id == key or s.name.lower() == key.lower():
                return s
        return None

    def list_all(self) -> list[LaunchSequence]:
        return list(self._seqs)

    def delete(self, key: str) -> bool:
        for i, s in enumerate(self._seqs):
            if s.id == key or s.name.lower() == key.lower():
                self._seqs.pop(i)
                self._save()
                return True
        return False

    def run(self, key: str) -> dict:
        seq = self.get(key)
        if not seq:
            return {"ok": False, "error": f"No sequence named '{key}'"}
        launched, errors = [], []
        for app in seq.apps:
            if app.delay_ms > 0:
                _t.sleep(app.delay_ms / 1000)
            try:
                if app.path.lower().startswith("start "):
                    subprocess.Popen(["cmd", "/c", app.path])
                else:
                    subprocess.Popen([app.path] + list(app.args or []))
                launched.append(app.path)
            except Exception as e:
                errors.append(f"{app.path}: {e}")
        return {"ok": True, "launched": launched, "errors": errors, "workspace": seq.workspace}


_store: AppLaunchStore | None = None


def get_app_launch_store() -> AppLaunchStore:
    global _store
    if _store is None:
        _store = AppLaunchStore()
    return _store
