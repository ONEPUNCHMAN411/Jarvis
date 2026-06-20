import json
import os
import sqlite3
import shutil
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Bookmark:
    name: str
    url: str
    folder: str = ""


def _chrome_path() -> Path | None:
    local = os.environ.get("LOCALAPPDATA", "")
    p = Path(local) / "Google" / "Chrome" / "User Data" / "Default" / "Bookmarks"
    return p if p.exists() else None


def _edge_path() -> Path | None:
    local = os.environ.get("LOCALAPPDATA", "")
    p = Path(local) / "Microsoft" / "Edge" / "User Data" / "Default" / "Bookmarks"
    return p if p.exists() else None


def _firefox_places_path() -> Path | None:
    roaming = os.environ.get("APPDATA", "")
    profiles_root = Path(roaming) / "Mozilla" / "Firefox" / "Profiles"
    if not profiles_root.is_dir():
        return None
    for profile_dir in profiles_root.iterdir():
        db = profile_dir / "places.sqlite"
        if db.exists():
            return db
    return None


def _parse_chromium_json(path: Path) -> list[Bookmark]:
    data = json.loads(path.read_text("utf-8"))
    bookmarks = []

    def walk(node, folder=""):
        if node.get("type") == "url":
            bookmarks.append(Bookmark(
                name=node.get("name", ""),
                url=node.get("url", ""),
                folder=folder,
            ))
        for child in node.get("children", []):
            walk(child, node.get("name", folder))

    roots = data.get("roots", {})
    for root_key in ("bookmark_bar", "other", "synced"):
        if root_key in roots:
            walk(roots[root_key])
    return bookmarks


def _parse_firefox_sqlite(path: Path) -> list[Bookmark]:
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copy2(str(path), str(tmp_path))
        conn = sqlite3.connect(str(tmp_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT b.title, p.url FROM moz_bookmarks b "
            "JOIN moz_places p ON b.fk = p.id "
            "WHERE b.type=1 AND p.url NOT LIKE 'place:%'"
        )
        rows = cur.fetchall()
        conn.close()
        return [Bookmark(name=r[0] or r[1], url=r[1]) for r in rows]
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


class BrowserBookmarkStore:
    def __init__(self):
        self._bookmarks: list[Bookmark] = []
        self._source = ""

    def import_auto(self) -> dict:
        candidates = [
            ("Chrome", _chrome_path, _parse_chromium_json),
            ("Edge", _edge_path, _parse_chromium_json),
        ]
        for label, path_fn, parser in candidates:
            p = path_fn()
            if p:
                try:
                    items = parser(p)
                    if items:
                        self._bookmarks = items
                        self._source = label
                        return {"ok": True, "browser": label, "count": len(items)}
                except Exception:
                    continue
        ff = _firefox_places_path()
        if ff:
            try:
                items = _parse_firefox_sqlite(ff)
                if items:
                    self._bookmarks = items
                    self._source = "Firefox"
                    return {"ok": True, "browser": "Firefox", "count": len(items)}
            except Exception:
                pass
        return {"ok": False, "error": "No Chrome, Edge, or Firefox bookmarks found."}

    def import_file(self, path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"File not found: {path}"}
        try:
            items = _parse_chromium_json(p)
            if items:
                self._bookmarks = items
                self._source = p.name
                return {"ok": True, "browser": p.name, "count": len(items)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Could not parse bookmarks file."}

    def search(self, query: str, limit: int = 20) -> list[Bookmark]:
        q = query.lower()
        return [
            b for b in self._bookmarks
            if q in b.name.lower() or q in b.url.lower() or q in b.folder.lower()
        ][:limit]

    def open(self, url: str) -> bool:
        try:
            webbrowser.open(url)
            return True
        except Exception:
            return False

    @property
    def count(self) -> int:
        return len(self._bookmarks)

    @property
    def source(self) -> str:
        return self._source


_store: BrowserBookmarkStore | None = None


def get_bookmark_store() -> BrowserBookmarkStore:
    global _store
    if _store is None:
        _store = BrowserBookmarkStore()
    return _store
