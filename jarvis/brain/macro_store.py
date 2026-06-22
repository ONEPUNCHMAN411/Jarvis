import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

_PATH = Path.home() / ".jarvis" / "macros.json"


@dataclass
class MacroStep:
    action: str
    params: dict = field(default_factory=dict)


@dataclass
class Macro:
    id: str
    name: str
    description: str
    steps: list
    created_at: str
    last_run: str | None = None
    run_count: int = 0

    def __post_init__(self):
        self.steps = [MacroStep(**s) if isinstance(s, dict) else s for s in self.steps]


class MacroStore:
    def __init__(self):
        self._macros: list[Macro] = []
        self._load()

    def _load(self):
        if _PATH.exists():
            try:
                raw = json.loads(_PATH.read_text(encoding="utf-8"))
                self._macros = [Macro(**m) for m in raw]
            except Exception:
                self._macros = []

    def _save(self):
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(m) for m in self._macros]
        _PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, name: str, description: str, steps: list[MacroStep]) -> "Macro":
        m = Macro(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            steps=steps,
            created_at=datetime.now().isoformat(),
        )
        self._macros.append(m)
        self._save()
        return m

    def get(self, macro_id: str) -> "Macro" | None:
        for m in self._macros:
            if m.id == macro_id or m.name.lower() == macro_id.lower():
                return m
        return None

    def list_all(self) -> list["Macro"]:
        return list(self._macros)

    def delete(self, macro_id: str) -> bool:
        for i, m in enumerate(self._macros):
            if m.id == macro_id or m.name.lower() == macro_id.lower():
                self._macros.pop(i)
                self._save()
                return True
        return False

    def record_run(self, macro_id: str):
        m = self.get(macro_id)
        if m:
            m.last_run = datetime.now().isoformat()
            m.run_count += 1
            self._save()


_store: MacroStore | None = None


def get_macro_store() -> MacroStore:
    global _store
    if _store is None:
        _store = MacroStore()
    return _store
