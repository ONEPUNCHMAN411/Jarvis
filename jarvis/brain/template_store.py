
import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class PromptTemplate:
    id: str
    name: str
    text: str
    category: str = "general"
    created: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PromptTemplate":
        return cls(
            **{k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        )


class TemplateStore:
    _PATH = Path.home() / ".jarvis" / "templates.json"
    _lock = threading.Lock()

    def __init__(self):
        self._templates: list[PromptTemplate] = []
        self._load()

    def _load(self) -> None:
        try:
            if self._PATH.exists():
                data = json.loads(self._PATH.read_text(encoding="utf-8"))
                self._templates = [PromptTemplate.from_dict(d) for d in data]
        except Exception:
            self._templates = []

    def _save(self) -> None:
        self._PATH.parent.mkdir(parents=True, exist_ok=True)
        self._PATH.write_text(
            json.dumps(
                [t.to_dict() for t in self._templates],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def add(
        self,
        name: str,
        text: str,
        category: str = "general",
    ) -> PromptTemplate:
        with self._lock:
            t = PromptTemplate(
                id=uuid.uuid4().hex[:8],
                name=name,
                text=text,
                category=category,
                created=datetime.now().isoformat(timespec="seconds"),
            )
            self._templates.append(t)
            self._save()
            return t

    def remove(self, template_id: str) -> bool:
        with self._lock:
            before = len(self._templates)
            self._templates = [
                t for t in self._templates if t.id != template_id
            ]
            if len(self._templates) < before:
                self._save()
                return True
            return False

    def list_all(self) -> list[PromptTemplate]:
        return list(self._templates)

    def get(self, template_id: str) -> PromptTemplate | None:
        for t in self._templates:
            if t.id == template_id:
                return t
        return None


_store: TemplateStore | None = None


def get_template_store() -> TemplateStore:
    global _store
    if _store is None:
        _store = TemplateStore()
    return _store
