
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class QrPlugin(Plugin):
    """Generate QR codes (to PNG) and read QR codes from an image or the screen."""

    def __init__(self):
        super().__init__("qr")

    async def initialize(self) -> None:
        logger.info("QrPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="generate_qr",
                    description=(
                        "Create a QR code PNG for any text, URL, or Wi-Fi string and "
                        "return the file path. Use when the user says 'make a QR code "
                        "for ...', 'generate a QR for this link', 'qr code for the "
                        "phone remote URL'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "data": {"type": "string", "description": "Text/URL to encode"},
                            "output": {"type": "string", "description": "Optional output PNG path"},
                        },
                        "required": ["data"],
                    },
                ),
                self.generate_qr,
            ),
            (
                ToolDefinition(
                    name="read_qr_image",
                    description="Read/decode any QR codes in an image file.",
                    parameters={
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "Image file path"}},
                        "required": ["path"],
                    },
                ),
                self.read_qr_image,
            ),
            (
                ToolDefinition(
                    name="read_qr_screen",
                    description=(
                        "Scan the screen (or a region) for QR codes and decode them. "
                        "Omit coordinates to scan the whole primary screen."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"}, "y": {"type": "integer"},
                            "width": {"type": "integer"}, "height": {"type": "integer"},
                        },
                    },
                ),
                self.read_qr_screen,
            ),
        ]

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    async def generate_qr(self, data: str, output: str = "") -> str:
        from jarvis.brain.qr_tool import generate_qr as _gen
        res = await self._run(_gen, data, output or None)
        if not res.get("ok"):
            return res.get("error", "QR generation failed.")
        return f"QR code saved: {res['out']}"

    async def read_qr_image(self, path: str) -> str:
        from jarvis.brain.qr_tool import read_qr_image as _read
        res = await self._run(_read, path)
        if not res.get("ok"):
            return res.get("error", "QR read failed.")
        found = res.get("found", [])
        if not found:
            return "No QR codes found in that image."
        return "Decoded QR:\n" + "\n".join(f"  • {v}" for v in found)

    async def read_qr_screen(self, x=None, y=None, width=None, height=None) -> str:
        from jarvis.brain.qr_tool import read_qr_screen as _read
        res = await self._run(_read, x, y, width, height)
        if not res.get("ok"):
            return res.get("error", "QR screen scan failed.")
        found = res.get("found", [])
        if not found:
            return "No QR codes detected on screen."
        return "Decoded QR:\n" + "\n".join(f"  • {v}" for v in found)
