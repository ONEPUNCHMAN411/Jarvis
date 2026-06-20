"""Background clipboard monitor with history, pinning, and search."""


import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from loguru import logger


@dataclass
class ClipEntry:
    text: str
    timestamp: str
    pinned: bool = False
    label: str = ""

    def preview(self, chars: int = 80) -> str:
        t = self.text.replace("\n", " ").strip()
        return (t[:chars] + "…") if len(t) > chars else t


class ClipboardHistory:
    """
    Polls the system clipboard and maintains a deduplicated, eviction-managed history.
    Pinned entries are never evicted.
    """

    def __init__(
        self,
        max_entries: int = 200,
        poll_interval: float = 0.8,
        on_change: Callable[[ClipEntry], None] | None = None,
    ):
        self._max = max_entries
        self._interval = poll_interval
        self._on_change = on_change
        self._entries: list[ClipEntry] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last = ""

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()
        logger.debug("ClipboardHistory monitor started.")

    def stop(self):
        self._stop.set()
        logger.debug("ClipboardHistory monitor stopped.")

    def _poll(self):
        while not self._stop.wait(self._interval):
            try:
                import pyperclip
                text = pyperclip.paste()
            except Exception:
                continue
            if not text or text == self._last:
                continue
            self._last = text
            entry = self._push(text)
            if self._on_change:
                try:
                    self._on_change(entry)
                except Exception:
                    pass

    def _push(self, text: str) -> ClipEntry:
        with self._lock:
            # Remove any older identical entry to deduplicate
            self._entries = [e for e in self._entries if e.text != text]
            entry = ClipEntry(
                text=text,
                timestamp=datetime.now().isoformat(timespec="seconds"),
            )
            self._entries.insert(0, entry)
            # Evict oldest unpinned entries when over limit
            unpinned = [e for e in self._entries if not e.pinned]
            while len(self._entries) > self._max and unpinned:
                self._entries.remove(unpinned.pop())
            return entry

    def all(self) -> list[ClipEntry]:
        with self._lock:
            return list(self._entries)

    def pinned(self) -> list[ClipEntry]:
        with self._lock:
            return [e for e in self._entries if e.pinned]

    def search(self, query: str, limit: int = 10) -> list[ClipEntry]:
        q = query.lower()
        with self._lock:
            return [e for e in self._entries if q in e.text.lower()][:limit]

    def get(self, index: int) -> ClipEntry | None:
        with self._lock:
            return self._entries[index] if 0 <= index < len(self._entries) else None

    def pin(self, index: int, label: str = "") -> bool:
        with self._lock:
            if 0 <= index < len(self._entries):
                self._entries[index].pinned = True
                if label:
                    self._entries[index].label = label
                return True
        return False

    def unpin(self, index: int) -> bool:
        with self._lock:
            if 0 <= index < len(self._entries):
                self._entries[index].pinned = False
                return True
        return False

    def delete(self, index: int) -> bool:
        with self._lock:
            if 0 <= index < len(self._entries):
                del self._entries[index]
                return True
        return False

    def clear_unpinned(self):
        with self._lock:
            self._entries = [e for e in self._entries if e.pinned]

    def paste(self, index: int) -> bool:
        """Copy entry back to the system clipboard."""
        entry = self.get(index)
        if not entry:
            return False
        try:
            import pyperclip
            pyperclip.copy(entry.text)
            self._last = entry.text
            return True
        except Exception:
            return False

    def format_list(self, limit: int = 20) -> str:
        entries = self.all()[:limit]
        if not entries:
            return "Clipboard history is empty."
        lines = []
        for i, e in enumerate(entries):
            pin = "📌 " if e.pinned else "   "
            label = f" [{e.label}]" if e.label else ""
            lines.append(f"{i:3d}  {pin}{e.timestamp}  {e.preview(60)}{label}")
        return "\n".join(lines)


# Module-level singleton — started on first access
_history: ClipboardHistory | None = None


def get_history() -> ClipboardHistory:
    """Return the module-level singleton, starting background polling if needed."""
    global _history
    if _history is None:
        _history = ClipboardHistory()
        _history.start()
    return _history
