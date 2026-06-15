
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class TranslatorPlugin(Plugin):
    """Translate text between 100+ languages using Google Translate."""

    def __init__(self):
        super().__init__("translator")
        self._translator = None

    def _get(self):
        if self._translator is None:
            from jarvis.brain.translator import get_translator
            self._translator = get_translator()
        return self._translator

    async def initialize(self) -> None:
        try:
            from jarvis.brain.translator import _AVAILABLE
            if not _AVAILABLE:
                raise ImportError("deep-translator not installed")
            logger.info("TranslatorPlugin ready")
        except ImportError as e:
            self.enabled = False
            logger.warning(f"TranslatorPlugin disabled: {e}")

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="translate_text",
                    description=(
                        "Translate text from one language to another. Supports 100+ "
                        "languages. Use codes like 'es' for Spanish, 'fr' for French, "
                        "'de' for German, 'ja' for Japanese, 'zh-cn' for Chinese. "
                        "Leave source as 'auto' to detect the input language automatically."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Text to translate",
                            },
                            "target": {
                                "type": "string",
                                "description": "Target language code, e.g. 'es', 'fr', 'de'. Default: 'en'",
                            },
                            "source": {
                                "type": "string",
                                "description": "Source language code or 'auto' to detect. Default: 'auto'",
                            },
                        },
                        "required": ["text"],
                    },
                ),
                self.translate_text,
            ),
            (
                ToolDefinition(
                    name="detect_language",
                    description="Detect the language of a piece of text.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Text whose language to identify",
                            },
                        },
                        "required": ["text"],
                    },
                ),
                self.detect_language,
            ),
            (
                ToolDefinition(
                    name="list_languages",
                    description="List all supported translation languages and their codes.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_languages,
            ),
        ]

    async def translate_text(
        self,
        text: str,
        target: str = "en",
        source: str = "auto",
    ) -> str:
        try:
            result = self._get().translate(text, target=target, source=source)
            return f"Translation ({source} -> {target}):\n{result}"
        except Exception as e:
            return f"Translation failed: {e}"

    async def detect_language(self, text: str) -> str:
        try:
            lang = self._get().detect_language(text)
            return f"Detected language: {lang}"
        except Exception as e:
            return f"Detection failed: {e}"

    async def list_languages(self) -> str:
        langs = self._get().list_languages()
        lines = [f"  {code}: {name}" for code, name in sorted(langs.items())]
        return "Supported languages:\n" + "\n".join(lines)
