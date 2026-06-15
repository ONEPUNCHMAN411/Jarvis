
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition
from jarvis.ui.settings_store import SettingsStore


class ContextPinPlugin(Plugin):
    """Pin text that is injected into every JARVIS prompt until cleared."""

    def __init__(self):
        super().__init__("context_pin")
        self._store = SettingsStore()

    async def initialize(self) -> None:
        logger.info("ContextPinPlugin ready")

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="pin_context",
                    description=(
                        "Save a piece of text as pinned context. It is automatically "
                        "injected at the top of every future prompt so JARVIS always "
                        "has it in view. Perfect for ongoing goals, project context, "
                        "personal preferences, or standing instructions."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Text to pin into every prompt",
                            },
                        },
                        "required": ["text"],
                    },
                ),
                self.pin_context,
            ),
            (
                ToolDefinition(
                    name="clear_pinned_context",
                    description=(
                        "Remove the currently pinned context so nothing extra "
                        "is injected into prompts."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.clear_pinned_context,
            ),
            (
                ToolDefinition(
                    name="show_pinned_context",
                    description="Display what text is currently pinned into every prompt.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.show_pinned_context,
            ),
        ]

    def _load(self) -> dict:
        return self._store.load()

    async def pin_context(self, text: str) -> str:
        s = self._load()
        s["pinned_context"] = text.strip()
        self._store.save(s)
        preview = text[:120] + ("..." if len(text) > 120 else "")
        return f"Pinned. Will appear in every prompt:\n{preview}"

    async def clear_pinned_context(self) -> str:
        s = self._load()
        if not s.get("pinned_context", "").strip():
            return "Nothing was pinned."
        s["pinned_context"] = ""
        self._store.save(s)
        return "Pinned context cleared."

    async def show_pinned_context(self) -> str:
        s = self._load()
        pinned = s.get("pinned_context", "").strip()
        if not pinned:
            return "Nothing is currently pinned."
        return f"Currently pinned:\n{pinned}"
