
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class DictationPlugin(Plugin):
    """Global voice dictation. Press Ctrl+Shift+D in any app, speak, and the
    text is typed where your cursor is. Also exposes a 'dictate' tool."""

    def __init__(self):
        super().__init__("dictation")
        self._hotkey = None

    async def initialize(self) -> None:
        try:
            from jarvis.utils.hotkey import GlobalHotkey
            from jarvis.app import get_runtime
            from jarvis.brain.dictation import get_dictation_manager

            def _fire():
                rt = get_runtime()
                if rt is not None:
                    rt.async_runtime.submit(get_dictation_manager().dictate_once())

            self._hotkey = GlobalHotkey("<ctrl>+<shift>+d", callback=_fire)
            if self._hotkey.start():
                logger.info("DictationPlugin ready — Ctrl+Shift+D to dictate")
            else:
                logger.warning("DictationPlugin: global hotkey unavailable")
        except Exception as e:
            logger.warning(f"DictationPlugin init failed: {e}")

    async def shutdown(self) -> None:
        if self._hotkey is not None:
            try:
                self._hotkey.stop()
            except Exception:
                pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="dictate",
                    description=(
                        "Capture one spoken phrase and type it into the currently "
                        "focused window. Best triggered by the global hotkey "
                        "Ctrl+Shift+D while another app is focused. Use when the user "
                        "says 'take dictation', 'let me dictate', 'type what I say'."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.dictate,
            ),
        ]

    async def dictate(self, **_) -> str:
        from jarvis.brain.dictation import get_dictation_manager
        return await get_dictation_manager().dictate_once()
