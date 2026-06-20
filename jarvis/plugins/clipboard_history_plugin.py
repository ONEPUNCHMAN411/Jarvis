import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class ClipboardHistoryPlugin(Plugin):
    """Exposes the existing clipboard history tracker to JARVIS — search past
    clipboard entries by keyword or meaning, pin favourites, and paste by index."""

    def __init__(self):
        super().__init__("clipboard_history")

    async def initialize(self):
        from jarvis.control.clipboard_history import get_history
        get_history().start()
        logger.info("ClipboardHistoryPlugin ready")

    async def shutdown(self):
        from jarvis.control.clipboard_history import get_history
        get_history().stop()

    def get_tools(self):
        return [
            (ToolDefinition(
                name="clipboard_list",
                description=(
                    "Show the most recent clipboard entries. "
                    "Use when user asks 'what's in my clipboard history?', "
                    "'show my recent copies', 'what did I copy earlier?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 20}},
                },
            ), self.list_entries),
            (ToolDefinition(
                name="clipboard_search",
                description=(
                    "Search clipboard history by keyword or meaning. "
                    "Use when user asks 'find that URL I copied about Python', "
                    "'search clipboard for the API key I had', "
                    "'find my recent copies about machine learning'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search term"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            ), self.search_entries),
            (ToolDefinition(
                name="clipboard_paste",
                description=(
                    "Paste a clipboard entry by its index number (from clipboard_list). "
                    "Puts it on the clipboard and types it into the focused field. "
                    "Use when user says 'paste clipboard item 3', 'send that to the cursor'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"index": {"type": "integer", "description": "Entry index from clipboard_list"}},
                    "required": ["index"],
                },
            ), self.paste_entry),
            (ToolDefinition(
                name="clipboard_pin",
                description=(
                    "Pin a clipboard entry so it's never pushed out by new copies. "
                    "Use when user says 'pin clipboard item 2', 'save that clipboard entry', "
                    "'keep that snippet'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "label": {"type": "string", "default": "", "description": "Optional label for the pin"},
                    },
                    "required": ["index"],
                },
            ), self.pin_entry),
            (ToolDefinition(
                name="clipboard_pinned",
                description="Show all pinned clipboard entries.",
                parameters={"type": "object", "properties": {}},
            ), self.list_pinned),
        ]


    async def list_entries(self, limit: int = 20, **_) -> str:
        from jarvis.control.clipboard_history import get_history
        h = get_history()
        entries = await self._run(h.all)
        if not entries:
            return "Clipboard history is empty."
        lines = [f"Clipboard history ({len(entries)} entries, showing newest first):"]
        for i, e in enumerate(reversed(entries[-limit:])):
            pin = " [PINNED]" if e.pinned else ""
            lines.append(f"  {i}  {e.preview(80)}{pin}")
        return "\n".join(lines)

    async def search_entries(self, query: str, limit: int = 10) -> str:
        from jarvis.control.clipboard_history import get_history
        results = await self._run(get_history().search, query, limit)
        if not results:
            return f"No clipboard entries matching '{query}'."
        lines = [f"Clipboard matches for '{query}':"]
        for i, e in enumerate(results):
            lines.append(f"  {i}  {e.preview(100)}")
        return "\n".join(lines)

    async def paste_entry(self, index: int) -> str:
        from jarvis.control.clipboard_history import get_history
        ok = await self._run(get_history().paste, index)
        return f"Pasted clipboard entry {index}." if ok else f"No clipboard entry at index {index}."

    async def pin_entry(self, index: int, label: str = "") -> str:
        from jarvis.control.clipboard_history import get_history
        ok = await self._run(get_history().pin, index, label)
        return f"Pinned clipboard entry {index}." if ok else f"No entry at index {index}."

    async def list_pinned(self, **_) -> str:
        from jarvis.control.clipboard_history import get_history
        pins = await self._run(get_history().pinned)
        if not pins:
            return "No pinned clipboard entries."
        lines = ["Pinned clipboard entries:"]
        for i, e in enumerate(pins):
            lbl = f" [{e.label}]" if getattr(e, "label", "") else ""
            lines.append(f"  {i}  {e.preview(100)}{lbl}")
        return "\n".join(lines)
