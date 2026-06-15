
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class OCRPlugin(Plugin):
    """Extract text from images and screenshots using OCR."""

    def __init__(self):
        super().__init__("ocr")
        self._ocr = None

    def _get(self):
        if self._ocr is None:
            from jarvis.brain.ocr_engine import get_ocr_engine
            self._ocr = get_ocr_engine()
        return self._ocr

    async def initialize(self) -> None:
        try:
            from jarvis.brain.ocr_engine import _AVAILABLE
            if not _AVAILABLE:
                raise ImportError("no OCR engine found")
            logger.info("OCRPlugin ready")
        except ImportError as e:
            self.enabled = False
            logger.warning(f"OCRPlugin disabled: {e}")

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="read_image_text",
                    description=(
                        "Extract all text from an image file using OCR. "
                        "Supports PNG, JPG, TIFF, BMP and most standard image formats."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Full path to the image file",
                            },
                        },
                        "required": ["path"],
                    },
                ),
                self.read_image_text,
            ),
            (
                ToolDefinition(
                    name="read_screen_text",
                    description=(
                        "Capture the current screen and extract all visible text from it. "
                        "Useful for reading content from apps that don't expose text directly."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.read_screen_text,
            ),
        ]

    async def read_image_text(self, path: str) -> str:
        ocr = self._get()
        loop = asyncio.get_running_loop()
        try:
            text = await loop.run_in_executor(None, lambda: ocr.read_image(path))
            return f"Extracted text:\n{text}" if text else "No text found in image."
        except FileNotFoundError:
            return f"File not found: {path}"
        except Exception as e:
            return f"OCR failed: {e}"

    async def read_screen_text(self) -> str:
        ocr = self._get()
        loop = asyncio.get_running_loop()
        try:
            text = await loop.run_in_executor(None, ocr.read_screenshot)
            return f"Screen text:\n{text}" if text else "No text found on screen."
        except Exception as e:
            return f"Screen OCR failed: {e}"
