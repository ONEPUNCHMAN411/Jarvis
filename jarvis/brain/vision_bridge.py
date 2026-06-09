"""Vision bridge — converts screenshots to text for providers without vision support.

Resolution order:
  1. Local lightweight model (free, no API key, no network latency)
  2. First available vision-capable API provider (claude > gemini > openai > ...)
"""


import asyncio
import tempfile
from pathlib import Path

from loguru import logger

_VISION_PRIORITY = ["claude", "gemini", "openai", "mistral", "groq", "llamacpp", "ollama"]

_DEFAULT_PROMPT = (
    "Describe this image in full detail. Include all visible text, UI elements, "
    "charts, code, error messages, or any other relevant content."
)


class VisionBridge:
    """Routes image descriptions through local model first, then API providers."""

    def __init__(self, providers: dict):
        self._providers = providers

    def _pick_api_provider(self):
        for name in _VISION_PRIORITY:
            p = self._providers.get(name)
            if p and getattr(p, "supports_vision", True):
                return name, p
        return None, None

    async def describe(self, image_path: str, prompt: str | None = None) -> str | None:
        """Describe an image file — tries local model first, then API."""
        _prompt = prompt or _DEFAULT_PROMPT

        # 1. Local model — free, instant, no network
        try:
            from jarvis.brain.local_vision import get_local_vision
            lv = get_local_vision()
            if lv.ready:
                result = lv.describe(image_path, _prompt)
                if result:
                    logger.debug("VisionBridge: described via local model")
                    return result
        except Exception as e:
            logger.debug(f"VisionBridge: local model skipped — {e}")

        # 2. API provider fallback
        _, provider = self._pick_api_provider()
        if not provider:
            return None
        from jarvis.models import Message
        msg = Message(
            role="user",
            content=_prompt,
            image_paths=[image_path],
        )
        try:
            resp = await asyncio.wait_for(
                provider.chat([msg], system_prompt="You are a precise vision assistant."),
                timeout=45,
            )
            return (resp.text or "").strip() or None
        except Exception as e:
            logger.warning(f"VisionBridge: API provider failed — {e}")
            return None

    async def describe_screen(self, prompt: str | None = None) -> str | None:
        """Capture the primary monitor and return a text description."""
        # Try local model's built-in screen capture first
        try:
            from jarvis.brain.local_vision import get_local_vision
            lv = get_local_vision()
            if lv.ready:
                result = lv.describe_screen(prompt or _DEFAULT_PROMPT)
                if result:
                    return result
        except Exception:
            pass

        # Fall back to temp file + API provider (JPEG for speed, capped at 1280px)
        try:
            import mss
            from PIL import Image as PILImage
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                shot = sct.grab(monitor)
                img = PILImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            w, h = img.size
            if max(w, h) > 1280:
                ratio = 1280 / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                img.save(f, format="JPEG", quality=85)
                tmp = f.name
            result = await self.describe(tmp, prompt)
            Path(tmp).unlink(missing_ok=True)
            return result
        except Exception:
            return None

    async def bridge_messages(self, messages: list) -> list:
        """Replace image_paths with inline text descriptions for non-vision providers."""
        from jarvis.models import Message
        out: list = []
        for msg in messages:
            paths = getattr(msg, "image_paths", None)
            if not paths:
                out.append(msg)
                continue
            descs: list[str] = []
            for path in paths:
                desc = await self.describe(path)
                if desc:
                    descs.append(f"[Image: {desc}]")
            combined = "\n".join(descs)
            content = f"{combined}\n\n{msg.content}" if msg.content else combined
            out.append(Message(role=msg.role, content=content))
        return out
