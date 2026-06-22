
import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class Bookmark:
    id: str
    text: str
    preview: str
    created: str
    session_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Bookmark":
        return cls(
            **{k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        )


class BookmarkStore:
    _PATH = Path.home() / ".jarvis" / "bookmarks.json"
    _lock = threading.Lock()

    def __init__(self):
        self._bookmarks: list[Bookmark] = []
        self._load()

    def _load(self) -> None:
        try:
            if self._PATH.exists():
                data = json.loads(self._PATH.read_text(encoding="utf-8"))
                self._bookmarks = [Bookmark.from_dict(d) for d in data]
        except Exception:
            self._bookmarks = []

    def _save(self) -> None:
        self._PATH.parent.mkdir(parents=True, exist_ok=True)
        self._PATH.write_text(
            json.dumps(
                [b.to_dict() for b in self._bookmarks],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def add(self, text: str, session_id: str = "") -> Bookmark:
        with self._lock:
            preview = (
                text[:100].replace("\n", " ")
                + ("…" if len(text) > 100 else "")
            )
            b = Bookmark(
                id=uuid.uuid4().hex[:8],
                text=text,
                preview=preview,
                created=datetime.now().isoformat(timespec="seconds"),
                session_id=session_id,
            )
            self._bookmarks.append(b)
            self._save()
            return b

    def remove(self, bookmark_id: str) -> bool:
        with self._lock:
            before = len(self._bookmarks)
            self._bookmarks = [
                b for b in self._bookmarks if b.id != bookmark_id
            ]
            if len(self._bookmarks) < before:
                self._save()
                return True
            return False

    def list_all(self) -> list[Bookmark]:
        return list(reversed(self._bookmarks))

    def get(self, bookmark_id: str) -> Bookmark | None:
        for b in self._bookmarks:
            if b.id == bookmark_id:
                return b
        return None


_store: BookmarkStore | None = None


def get_bookmark_store() -> BookmarkStore:
    global _store
    if _store is None:
        _store = BookmarkStore()
    return _store
