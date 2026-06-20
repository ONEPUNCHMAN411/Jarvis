import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class BrowserBookmarksPlugin(Plugin):
    def __init__(self):
        super().__init__("browser_bookmarks")

    async def initialize(self):
        logger.info("BrowserBookmarksPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="import_browser_bookmarks",
                description=(
                    "Import bookmarks from Chrome, Edge, or Firefox automatically. "
                    "Optionally supply a path to a specific Bookmarks JSON file to import from. "
                    "Use when user says 'import my bookmarks', 'load my browser bookmarks', "
                    "'sync bookmarks', 'add my Chrome bookmarks to JARVIS'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Optional path to a Bookmarks JSON file. Omit to auto-detect browser.",
                        },
                    },
                },
            ), self.import_bookmarks),
            (ToolDefinition(
                name="search_bookmarks",
                description=(
                    "Search imported bookmarks by name, URL, or folder topic. "
                    "Use when user says 'find my bookmark about Python', "
                    "'search bookmarks for machine learning', 'open my YouTube bookmark'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 15},
                    },
                    "required": ["query"],
                },
            ), self.search),
            (ToolDefinition(
                name="open_bookmark",
                description=(
                    "Open a bookmark URL in the default browser. "
                    "Call after search_bookmarks when user wants to open a specific result."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to open"},
                    },
                    "required": ["url"],
                },
            ), self.open_bm),
        ]


    async def import_bookmarks(self, file_path: str = None, **_) -> str:
        from jarvis.brain.browser_bookmarks import get_bookmark_store
        store = get_bookmark_store()
        if file_path:
            res = await self._run(store.import_file, file_path)
        else:
            res = await self._run(store.import_auto)
        if res.get("ok"):
            return (
                f"Imported {res['count']} bookmarks from {res['browser']}. "
                "You can now search them by name or topic."
            )
        return f"Import failed: {res.get('error', 'unknown error')}"

    async def search(self, query: str, limit: int = 15, **_) -> str:
        from jarvis.brain.browser_bookmarks import get_bookmark_store
        store = get_bookmark_store()
        if store.count == 0:
            return "No bookmarks loaded yet. Call import_browser_bookmarks first."
        results = await self._run(store.search, query, limit)
        if not results:
            return f"No bookmarks matching '{query}'."
        lines = [f"Found {len(results)} bookmark(s) matching '{query}' (from {store.source}):"]
        for b in results:
            folder = f"  [{b.folder}]" if b.folder else ""
            lines.append(f"  {b.name}{folder}")
            lines.append(f"    {b.url}")
        return "\n".join(lines)

    async def open_bm(self, url: str) -> str:
        from jarvis.brain.browser_bookmarks import get_bookmark_store
        ok = await self._run(get_bookmark_store().open, url)
        return f"Opened {url}" if ok else f"Failed to open {url}"
