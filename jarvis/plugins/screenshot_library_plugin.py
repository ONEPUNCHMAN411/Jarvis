import asyncio
import os
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class ScreenshotLibraryPlugin(Plugin):
    def __init__(self):
        super().__init__("screenshot_library")

    async def initialize(self):
        logger.info("ScreenshotLibraryPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="capture_and_index_screenshot",
                description=(
                    "Take a screenshot right now and save it to the searchable library with an "
                    "AI-written description. You write the description based on what you know "
                    "the user is doing, or ask them what to tag it as. "
                    "Use when user says 'save this to my screenshot library', "
                    "'index my screen', 'screenshot and remember this'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Concise description of what the screenshot shows",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tags e.g. [\"work\", \"bug\", \"design\"]",
                        },
                        "monitor": {"type": "integer", "default": 1},
                    },
                    "required": ["description"],
                },
            ), self.capture_and_index),
            (ToolDefinition(
                name="index_existing_screenshot",
                description=(
                    "Add an existing screenshot file to the library with a description. "
                    "Use when user says 'add this screenshot to the library', "
                    "'index that screen capture', 'remember this file'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Full path to the screenshot file"},
                        "description": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["path", "description"],
                },
            ), self.index_existing),
            (ToolDefinition(
                name="search_screenshot_library",
                description=(
                    "Search saved screenshots by description or topic using keyword matching. "
                    "Use when user asks 'find my screenshot of the error', "
                    "'search screenshots for the dashboard design', "
                    "'what screenshots do I have about Python?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 8},
                    },
                    "required": ["query"],
                },
            ), self.search),
            (ToolDefinition(
                name="list_recent_screenshots",
                description=(
                    "List the most recently indexed screenshots. "
                    "Use when user asks 'show my recent screenshots', "
                    "'what screenshots have I saved?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}},
                },
            ), self.recent),
            (ToolDefinition(
                name="open_screenshot",
                description="Open a screenshot file in the default image viewer.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ), self.open_ss),
        ]


    async def capture_and_index(self, description: str, tags: list = None, monitor: int = 1, **_) -> str:
        from jarvis.control.screen import take_screenshot
        from jarvis.brain.screenshot_library import get_screenshot_library
        path = await self._run(take_screenshot, monitor)
        if not path:
            return "Screenshot capture failed."
        entry = await self._run(get_screenshot_library().add, path, description, tags or [])
        tag_str = f"  tags: {', '.join(entry.tags)}" if entry.tags else ""
        return f"Screenshot captured and indexed.\nPath: {entry.path}\nDescription: {entry.description}{tag_str}"

    async def index_existing(self, path: str, description: str, tags: list = None, **_) -> str:
        from jarvis.brain.screenshot_library import get_screenshot_library
        if not os.path.exists(path):
            return f"File not found: {path}"
        entry = await self._run(get_screenshot_library().add, path, description, tags or [])
        return f"Indexed: {entry.path}\nDescription: {entry.description}"

    async def search(self, query: str, limit: int = 8, **_) -> str:
        from jarvis.brain.screenshot_library import get_screenshot_library
        lib = get_screenshot_library()
        if lib.count == 0:
            return "Screenshot library is empty. Use capture_and_index_screenshot to start building it."
        results = await self._run(lib.search, query, limit)
        if not results:
            return f"No screenshots matching '{query}'."
        lines = [f"Found {len(results)} screenshot(s) matching '{query}':"]
        for e in results:
            lines.append(f"  [{e.timestamp[:16]}]  {e.path}")
            lines.append(f"    {e.description[:100]}")
            if e.tags:
                lines.append(f"    tags: {', '.join(e.tags)}")
        return "\n".join(lines)

    async def recent(self, limit: int = 10, **_) -> str:
        from jarvis.brain.screenshot_library import get_screenshot_library
        lib = get_screenshot_library()
        entries = await self._run(lib.recent, limit)
        if not entries:
            return "No screenshots indexed yet."
        lines = [f"Recent screenshots ({lib.count} total in library):"]
        for e in entries:
            lines.append(f"  [{e.timestamp[:16]}]  {e.path}")
            lines.append(f"    {e.description[:80]}")
        return "\n".join(lines)

    async def open_ss(self, path: str, **_) -> str:
        if not os.path.exists(path):
            return f"File not found: {path}"
        try:
            os.startfile(path)
            return f"Opened {path}"
        except Exception as e:
            return f"Could not open: {e}"
