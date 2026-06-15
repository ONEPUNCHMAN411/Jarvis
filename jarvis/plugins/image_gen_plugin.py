
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class ImageGenPlugin(Plugin):
    """Generate images from text prompts using OpenAI DALL-E 3."""

    def __init__(self):
        super().__init__("image_gen")
        self._gen = None

    def _get(self):
        if self._gen is None:
            from jarvis.brain.image_generator import get_image_generator
            self._gen = get_image_generator()
        return self._gen

    async def initialize(self) -> None:
        try:
            from jarvis.brain.image_generator import _AVAILABLE
            if not _AVAILABLE:
                raise ImportError("openai package not installed")
            logger.info("ImageGenPlugin ready (DALL-E 3)")
        except ImportError as e:
            self.enabled = False
            logger.warning(f"ImageGenPlugin disabled: {e}")

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="generate_image",
                    description=(
                        "Generate an image from a text description using DALL-E 3. "
                        "Optionally save it to a local file. Returns the image URL "
                        "and the revised prompt DALL-E actually used."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Description of the image to generate",
                            },
                            "size": {
                                "type": "string",
                                "description": (
                                    "Image dimensions: '1024x1024', '1792x1024' "
                                    "(landscape), or '1024x1792' (portrait). "
                                    "Default: '1024x1024'"
                                ),
                            },
                            "quality": {
                                "type": "string",
                                "description": (
                                    "'standard' or 'hd'. HD costs more tokens but has "
                                    "finer detail. Default: 'standard'"
                                ),
                            },
                            "save_path": {
                                "type": "string",
                                "description": (
                                    "Optional local file path to save the image, "
                                    "e.g. 'C:/Users/you/Pictures/output.png'"
                                ),
                            },
                        },
                        "required": ["prompt"],
                    },
                ),
                self.generate_image,
            ),
        ]

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        save_path: str = "",
    ) -> str:
        gen = self._get()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: gen.generate(
                prompt=prompt,
                size=size,
                quality=quality,
                save_path=save_path or None,
            ),
        )
        if not result["success"]:
            return f"Image generation failed: {result['error']}"
        lines = [
            "Image generated successfully!",
            f"URL: {result['url']}",
            f"Revised prompt: {result['revised_prompt']}",
        ]
        if result.get("saved_to"):
            lines.append(f"Saved to: {result['saved_to']}")
        return "\n".join(lines)
