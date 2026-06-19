import difflib
import os
from pathlib import Path


class DiffViewer:
    def diff_files(self, path_a: str, path_b: str, context: int = 3) -> dict:
        try:
            text_a = Path(path_a).read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
            text_b = Path(path_b).read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        diff = list(difflib.unified_diff(
            text_a, text_b,
            fromfile=os.path.basename(path_a),
            tofile=os.path.basename(path_b),
            n=context,
        ))
        return {"ok": True, "diff": "".join(diff), "changed_lines": sum(1 for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))}

    def diff_strings(self, before: str, after: str, label_a: str = "before", label_b: str = "after", context: int = 3) -> dict:
        lines_a = before.splitlines(keepends=True)
        lines_b = after.splitlines(keepends=True)
        diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, n=context))
        return {"ok": True, "diff": "".join(diff), "changed_lines": sum(1 for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))}

    def preview_edit(self, file_path: str, old_text: str, new_text: str) -> dict:
        p = Path(file_path)
        if not p.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}
        content = p.read_text(encoding="utf-8", errors="ignore")
        if old_text not in content:
            return {"ok": False, "error": "old_text not found in file — nothing to change."}
        updated = content.replace(old_text, new_text, 1)
        return self.diff_strings(content, updated, label_a=file_path + " (before)", label_b=file_path + " (after)")

    def apply_edit(self, file_path: str, old_text: str, new_text: str) -> dict:
        p = Path(file_path)
        if not p.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}
        content = p.read_text(encoding="utf-8", errors="ignore")
        if old_text not in content:
            return {"ok": False, "error": "old_text not found in file."}
        updated = content.replace(old_text, new_text, 1)
        p.write_text(updated, encoding="utf-8")
        lines_changed = abs(old_text.count("\n") - new_text.count("\n")) + 1
        return {"ok": True, "message": f"Applied edit to {p.name} ({lines_changed} lines affected)."}

    def apply_file_replace(self, src_path: str, dst_path: str) -> dict:
        try:
            import shutil
            shutil.copy2(src_path, dst_path)
            return {"ok": True, "message": f"Replaced {dst_path} with {src_path}."}
        except Exception as e:
            return {"ok": False, "error": str(e)}


_viewer: DiffViewer | None = None


def get_diff_viewer() -> DiffViewer:
    global _viewer
    if _viewer is None:
        _viewer = DiffViewer()
    return _viewer
