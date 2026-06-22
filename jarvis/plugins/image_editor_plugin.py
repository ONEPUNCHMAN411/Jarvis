
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class ImageEditorPlugin(Plugin):
    """Remove image backgrounds (rembg) and add watermarks. Basic resize/convert
    already live in the file-converter plugin."""

    def __init__(self):
        super().__init__("image_editor")

    async def initialize(self) -> None:
        logger.info("ImageEditorPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="remove_background",
                    description=(
                        "Remove the background from an image, saving a transparent "
                        "PNG. Use when the user says 'remove the background', 'cut out "
                        "the subject', 'make this transparent'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Image file path"},
                            "output": {"type": "string", "description": "Optional output PNG path"},
                        },
                        "required": ["path"],
                    },
                ),
                self.remove_background,
            ),
            (
                ToolDefinition(
                    name="batch_remove_background",
                    description="Remove backgrounds from every image in a folder.",
                    parameters={
                        "type": "object",
                        "properties": {"folder": {"type": "string"}},
                        "required": ["folder"],
                    },
                ),
                self.batch_remove_background,
            ),
            (
                ToolDefinition(
                    name="add_watermark",
                    description=(
                        "Overlay a text watermark on an image. position can be "
                        "bottom-right, bottom-left, top-right, top-left, or center."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "text": {"type": "string"},
                            "position": {"type": "string", "description": "Default bottom-right"},
                            "opacity": {"type": "integer", "description": "0-255 (default 140)"},
                            "output": {"type": "string"},
                        },
                        "required": ["path", "text"],
                    },
                ),
                self.add_watermark,
            ),
        ]

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    async def remove_background(self, path: str, output: str = "") -> str:
        from jarvis.brain.image_editor import remove_background as _rb
        res = await self._run(_rb, path, output or None)
        if not res.get("ok"):
            return res.get("error", "Background removal failed.")
        return f"Background removed → {res['out']}"

    async def batch_remove_background(self, folder: str) -> str:
        from jarvis.brain.image_editor import batch_remove_background as _brb
        res = await self._run(_brb, folder)
        if not res.get("ok"):
            return res.get("error", "Batch failed.")
        return f"Removed backgrounds on {res['done']}/{res['total']} image(s) ({res['failed']} failed)."

    async def add_watermark(self, path: str, text: str, position: str = "bottom-right",
                            opacity: int = 140, output: str = "") -> str:
        from jarvis.brain.image_editor import add_watermark as _wm
        res = await self._run(_wm, path, text, output or None, int(opacity), position)
        if not res.get("ok"):
            return res.get("error", "Watermark failed.")
        return f"Watermarked → {res['out']}"
