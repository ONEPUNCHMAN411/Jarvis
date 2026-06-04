
import json
import threading
from pathlib import Path

from loguru import logger

try:
    import pygetwindow as gw
    _HAS_GW = True
except ImportError:
    _HAS_GW = False


class WorkspaceManager:
    """Save and restore named window layouts (positions + sizes)."""

    def __init__(self, path: str = "~/.jarvis/workspaces.json"):
        self._path = Path(path).expanduser()
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def save_layout(self, name: str) -> dict:
        if not _HAS_GW:
            return {"ok": False, "error": "pygetwindow not available"}
        wins = []
        seen = set()
        for w in gw.getAllWindows():
            title = (w.title or "").strip()
            if not title or not w.visible or w.width <= 0 or w.height <= 0:
                continue
            if title in seen:
                continue
            seen.add(title)
            wins.append({"title": title, "x": w.left, "y": w.top,
                         "w": w.width, "h": w.height})
        if not wins:
            return {"ok": False, "error": "No visible windows to save."}
        self._data[name] = wins
        self._save()
        return {"ok": True, "count": len(wins)}

    def restore_layout(self, name: str) -> dict:
        if not _HAS_GW:
            return {"ok": False, "error": "pygetwindow not available"}
        layout = self._data.get(name)
        if not layout:
            return {"ok": False, "error": f"No saved workspace named '{name}'."}
        restored = 0
        for entry in layout:
            try:
                matches = gw.getWindowsWithTitle(entry["title"])
                if not matches:
                    continue
                win = matches[0]
                if getattr(win, "isMinimized", False):
                    win.restore()
                win.moveTo(int(entry["x"]), int(entry["y"]))
                win.resizeTo(int(entry["w"]), int(entry["h"]))
                restored += 1
            except Exception as e:
                logger.debug(f"Workspace restore skipped '{entry.get('title')}': {e}")
        return {"ok": True, "restored": restored, "total": len(layout)}

    def list_layouts(self) -> dict:
        return {name: len(wins) for name, wins in self._data.items()}

    def delete_layout(self, name: str) -> bool:
        if name in self._data:
            del self._data[name]
            self._save()
            return True
        return False


_instance: "WorkspaceManager | None" = None
_lock = threading.Lock()


def get_workspace_manager() -> "WorkspaceManager":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = WorkspaceManager()
    return _instance
