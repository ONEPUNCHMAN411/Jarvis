
import json
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from loguru import logger

_TODO_FILE = Path.home() / ".jarvis" / "todos.json"

_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


@dataclass
class Todo:
    id: str
    text: str
    priority: str = "normal"   # "low" | "normal" | "high"
    due: str = ""               # ISO date string
    tags: list[str] = field(default_factory=list)
    done: bool = False
    created: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Todo":
        return cls(
            id=d["id"],
            text=d["text"],
            priority=d.get("priority", "normal"),
            due=d.get("due", ""),
            tags=d.get("tags", []),
            done=d.get("done", False),
            created=d.get("created", ""),
        )


class TodoStore:
    """JSON-backed todo list persisted at ~/.jarvis/todos.json."""

    def __init__(self):
        self._todos: dict[str, Todo] = {}
        self._lock = threading.Lock()
        self._load()

    # Persistence

    def _load(self) -> None:
        if not _TODO_FILE.exists():
            return
        try:
            data = json.loads(_TODO_FILE.read_text(encoding="utf-8"))
            for d in data:
                t = Todo.from_dict(d)
                self._todos[t.id] = t
            logger.debug(f"TodoStore: loaded {len(self._todos)} todos")
        except Exception as e:
            logger.warning(f"TodoStore: failed to load: {e}")

    def _save(self) -> None:
        try:
            _TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = [t.to_dict() for t in self._todos.values()]
            _TODO_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"TodoStore: failed to save: {e}")

    # CRUD

    def add(
        self,
        text: str,
        priority: str = "normal",
        due: str = "",
        tags: list[str] | None = None,
    ) -> Todo:
        with self._lock:
            todo = Todo(
                id=uuid.uuid4().hex[:8],
                text=text,
                priority=priority if priority in _PRIORITY_ORDER else "normal",
                due=due,
                tags=tags or [],
            )
            self._todos[todo.id] = todo
            self._save()
            return todo

    def get(self, todo_id: str) -> Todo | None:
        with self._lock:
            return self._todos.get(todo_id)

    def complete(self, todo_id: str) -> bool:
        with self._lock:
            todo = self._todos.get(todo_id)
            if todo:
                todo.done = True
                self._save()
                return True
        return False

    def remove(self, todo_id: str) -> bool:
        with self._lock:
            if todo_id in self._todos:
                del self._todos[todo_id]
                self._save()
                return True
        return False

    def list_todos(
        self,
        show_done: bool = False,
        priority: str | None = None,
    ) -> list[Todo]:
        with self._lock:
            items = list(self._todos.values())

        if not show_done:
            items = [t for t in items if not t.done]
        if priority:
            items = [t for t in items if t.priority == priority]

        items.sort(key=lambda t: _PRIORITY_ORDER.get(t.priority, 1))
        return items

    def search(self, query: str) -> list[Todo]:
        q = query.lower()
        with self._lock:
            return [
                t for t in self._todos.values()
                if q in t.text.lower() or any(q in tag.lower() for tag in t.tags)
            ]


# Singleton

_inst: TodoStore | None = None
_lock = threading.Lock()


def get_todo_store() -> TodoStore:
    global _inst
    if _inst is None:
        with _lock:
            if _inst is None:
                _inst = TodoStore()
    return _inst
