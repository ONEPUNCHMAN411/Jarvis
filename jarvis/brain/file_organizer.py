import shutil
from pathlib import Path


class FileOrganizer:
    def scan(self, folder: str, extensions: list | None = None) -> list[dict]:
        root = Path(folder).expanduser()
        if not root.is_dir():
            return []
        results = []
        for p in root.iterdir():
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if extensions and ext not in extensions:
                continue
            stat = p.stat()
            results.append({
                "name": p.name,
                "path": str(p),
                "ext": ext or "(none)",
                "size_kb": round(stat.st_size / 1024, 1),
                "modified_ts": stat.st_mtime,
            })
        return sorted(results, key=lambda x: x["modified_ts"], reverse=True)

    def apply_plan(self, proposals: list[dict]) -> dict:
        moved, skipped, errors = [], [], []
        for p in proposals:
            src = Path(p["src"])
            dst = Path(p["dst"])
            if not src.exists():
                skipped.append(str(src.name))
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved.append(f"{src.name} → {dst}")
            except Exception as e:
                errors.append(f"{src.name}: {e}")
        return {"moved": moved, "skipped": skipped, "errors": errors}


_organizer: FileOrganizer | None = None


def get_file_organizer() -> FileOrganizer:
    global _organizer
    if _organizer is None:
        _organizer = FileOrganizer()
    return _organizer
