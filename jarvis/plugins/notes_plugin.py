"""JSON-backed note store — CRUD, tags, full-text search, markdown export."""


import json
import uuid
from datetime import datetime
from pathlib import Path

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

_STORE = Path.home() / ".jarvis" / "notes.json"


def _load() -> list[dict]:
    if not _STORE.exists():
        return []
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(notes: list[dict]) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _format_note(note: dict) -> str:
    tags = ", ".join(note.get("tags", [])) or "none"
    return f"[{note['id']}] **{note['title']}** (tags: {tags}, updated: {note['updated']})\n{note['body']}"


class NotesPlugin(Plugin):
    """Persistent note-taking with tags, search, and markdown export."""

    def __init__(self):
        super().__init__("notes")

    async def initialize(self) -> None:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Notes plugin ready — store: {_STORE}")

    async def shutdown(self) -> None:
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="add_note",
                    description="Create a new note with a title, body text, and optional tags.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Note title"},
                            "body":  {"type": "string", "description": "Note content"},
                            "tags":  {"type": "array", "items": {"type": "string"},
                                      "description": "Optional list of tag strings"},
                        },
                        "required": ["title", "body"],
                    },
                ),
                self.add_note,
            ),
            (
                ToolDefinition(
                    name="search_notes",
                    description="Full-text search across all notes. Returns ranked results.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "limit": {"type": "integer", "description": "Max results (default 5)"},
                        },
                        "required": ["query"],
                    },
                ),
                self.search_notes,
            ),
            (
                ToolDefinition(
                    name="list_notes",
                    description="List recent notes, optionally filtered by tag.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tag":   {"type": "string", "description": "Filter by tag (optional)"},
                            "limit": {"type": "integer", "description": "Max results (default 10)"},
                        },
                    },
                ),
                self.list_notes,
            ),
            (
                ToolDefinition(
                    name="update_note",
                    description="Update the title, body, or tags of an existing note by its ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "note_id": {"type": "string", "description": "Note ID prefix"},
                            "title":   {"type": "string"},
                            "body":    {"type": "string"},
                            "tags":    {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["note_id"],
                    },
                ),
                self.update_note,
            ),
            (
                ToolDefinition(
                    name="delete_note",
                    description="Permanently delete a note by its ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "note_id": {"type": "string", "description": "Note ID prefix"},
                        },
                        "required": ["note_id"],
                    },
                ),
                self.delete_note,
            ),
            (
                ToolDefinition(
                    name="export_notes_markdown",
                    description="Export all notes to a Markdown file and return the saved path.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "output_path": {"type": "string",
                                            "description": "Optional file path (defaults to ~/jarvis_notes.md)"},
                        },
                    },
                ),
                self.export_markdown,
            ),
        ]

    async def add_note(self, title: str, body: str, tags: list[str] | None = None) -> str:
        notes = _load()
        note = {
            "id": str(uuid.uuid4())[:8],
            "title": title.strip(),
            "body": body.strip(),
            "tags": [t.lower().strip() for t in (tags or [])],
            "created": _now(),
            "updated": _now(),
        }
        notes.append(note)
        _save(notes)
        logger.info(f"Note created: {note['id']} — {note['title']}")
        return f"Note saved (id: {note['id']})."

    async def search_notes(self, query: str, limit: int = 5) -> str:
        q = query.lower()
        scored: list[tuple[int, dict]] = []
        for n in _load():
            haystack = f"{n['title']} {n['body']} {' '.join(n.get('tags', []))}".lower()
            if q in haystack:
                scored.append((haystack.count(q), n))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [n for _, n in scored[:limit]]
        if not results:
            return f"No notes found for '{query}'."
        return "\n\n".join(_format_note(n) for n in results)

    async def list_notes(self, tag: str | None = None, limit: int = 10) -> str:
        notes = _load()
        if tag:
            notes = [n for n in notes if tag.lower() in n.get("tags", [])]
        notes.sort(key=lambda n: n["updated"], reverse=True)
        notes = notes[:limit]
        if not notes:
            return "No notes found."
        return "\n\n".join(_format_note(n) for n in notes)

    async def update_note(self, note_id: str, title: str | None = None,
                          body: str | None = None, tags: list[str] | None = None) -> str:
        notes = _load()
        for n in notes:
            if n["id"].startswith(note_id):
                if title is not None:
                    n["title"] = title.strip()
                if body is not None:
                    n["body"] = body.strip()
                if tags is not None:
                    n["tags"] = [t.lower().strip() for t in tags]
                n["updated"] = _now()
                _save(notes)
                return f"Note {n['id']} updated."
        return f"Note '{note_id}' not found."

    async def delete_note(self, note_id: str) -> str:
        notes = _load()
        before = len(notes)
        notes = [n for n in notes if not n["id"].startswith(note_id)]
        if len(notes) < before:
            _save(notes)
            return f"Note '{note_id}' deleted."
        return f"Note '{note_id}' not found."

    async def export_markdown(self, output_path: str | None = None) -> str:
        notes = _load()
        lines = ["# JARVIS Notes\n"]
        for n in sorted(notes, key=lambda x: x["updated"], reverse=True):
            tags_str = ", ".join(n.get("tags", [])) or "none"
            lines += [
                f"## {n['title']}",
                f"*{n['updated']}* | tags: {tags_str}\n",
                n["body"],
                "\n---\n",
            ]
        path = output_path or str(Path.home() / "jarvis_notes.md")
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        return f"Notes exported to {path}"
