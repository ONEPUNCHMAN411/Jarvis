import json
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path


_PATH = Path.home() / ".jarvis" / "screenshot_library.json"
_MAX = 500


@dataclass
class ScreenshotEntry:
    path: str
    description: str
    tags: list = field(default_factory=list)
    timestamp: str = ""
    ts_epoch: float = 0.0


class ScreenshotLibrary:
    def __init__(self):
        self._entries: list[ScreenshotEntry] = []
        self._load()

    def _load(self):
        if _PATH.exists():
            try:
                raw = json.loads(_PATH.read_text("utf-8"))
                self._entries = [ScreenshotEntry(**e) for e in raw]
            except Exception:
                self._entries = []

    def _save(self):
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps([asdict(e) for e in self._entries], indent=2), "utf-8")

    def add(self, path: str, description: str, tags: list = None) -> ScreenshotEntry:
        entry = ScreenshotEntry(
            path=path,
            description=description,
            tags=tags or [],
            timestamp=datetime.now().isoformat(),
            ts_epoch=time.time(),
        )
        self._entries.append(entry)
        if len(self._entries) > _MAX:
            self._entries = self._entries[-_MAX:]
        self._save()
        return entry

    def search(self, query: str, limit: int = 10) -> list[ScreenshotEntry]:
        q = query.lower()
        scored = []
        for e in reversed(self._entries):
            score = 0
            if q in e.description.lower():
                score += 2
            if any(q in t.lower() for t in e.tags):
                score += 1
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def recent(self, limit: int = 10) -> list[ScreenshotEntry]:
        return list(reversed(self._entries[-limit:]))

    @property
    def count(self) -> int:
        return len(self._entries)


_lib: ScreenshotLibrary | None = None


def get_screenshot_library() -> ScreenshotLibrary:
    global _lib
    if _lib is None:
        _lib = ScreenshotLibrary()
    return _lib
