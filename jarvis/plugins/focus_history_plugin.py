import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class FocusHistoryPlugin(Plugin):
    """Tracks the last 30 foreground windows with timestamps. Answer
    'what was I working on at 2pm?' and switch back to any past window."""

    def __init__(self):
        super().__init__("focus_history")

    async def initialize(self):
        from jarvis.control.focus_history import get_focus_tracker
        get_focus_tracker().start()
        logger.info("FocusHistoryPlugin ready")

    async def shutdown(self):
        from jarvis.control.focus_history import get_focus_tracker
        get_focus_tracker().stop()

    def get_tools(self):
        return [
            (ToolDefinition(
                name="get_focus_history",
                description=(
                    "List recently focused windows with timestamps (newest first). "
                    "Use when user asks 'what was I working on?', 'show my recent windows', "
                    "'what apps have I had open today?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 15}},
                },
            ), self.get_history),
            (ToolDefinition(
                name="focus_history_at_time",
                description=(
                    "Show what window was active around a specific time today. "
                    "Use when user asks 'what was I looking at at 2pm?', 'what had focus at 14:30?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "hour": {"type": "integer"},
                        "minute": {"type": "integer", "default": 0},
                    },
                    "required": ["hour"],
                },
            ), self.at_time),
            (ToolDefinition(
                name="refocus_window",
                description=(
                    "Bring a recently seen window back to the foreground. "
                    "Use when user says 'switch back to VSCode', 'bring Chrome back', "
                    "'go back to that terminal'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "App name or window title fragment"}},
                    "required": ["query"],
                },
            ), self.refocus),
        ]


    async def get_history(self, limit: int = 15, **_) -> str:
        from jarvis.control.focus_history import get_focus_tracker
        entries = await self._run(get_focus_tracker().get_history, limit)
        if not entries:
            return "No focus history yet — it builds as you switch windows."
        lines = ["Recent foreground windows (newest first):"]
        for e in entries:
            lines.append(f"  {e.timestamp[11:16]}  {e.app_name}  —  {e.window_title[:72]}")
        return "\n".join(lines)

    async def at_time(self, hour: int, minute: int = 0, **_) -> str:
        from jarvis.control.focus_history import get_focus_tracker
        entries = await self._run(get_focus_tracker().get_at_time, hour, minute)
        if not entries:
            return f"No focus history recorded around {hour:02d}:{minute:02d} today."
        lines = [f"Windows active around {hour:02d}:{minute:02d}:"]
        for e in entries:
            lines.append(f"  {e.timestamp[11:16]}  {e.app_name}  —  {e.window_title[:72]}")
        return "\n".join(lines)

    async def refocus(self, query: str) -> str:
        from jarvis.control.focus_history import get_focus_tracker
        ok = await self._run(get_focus_tracker().refocus, query)
        return f"Switched to '{query}'." if ok else f"No window matching '{query}' in focus history."
