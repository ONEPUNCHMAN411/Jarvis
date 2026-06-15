
import os
import threading
import urllib.request
from pathlib import Path

from loguru import logger

_AVAILABLE = False
try:
    import openai
    _AVAILABLE = True
except ImportError:
    pass


class ImageGenerator:
    """Generate images with DALL-E 3 and optionally save them locally."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not self._api_key:
            logger.warning("ImageGenerator: OPENAI_API_KEY not set")

    def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        save_path: str | None = None,
    ) -> dict:
        if not _AVAILABLE:
            return {
                "success": False,
                "error": "openai package not installed: pip install openai",
            }
        if not self._api_key:
            return {"success": False, "error": "OPENAI_API_KEY not set"}
        try:
            client = openai.OpenAI(api_key=self._api_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
            )
            url = response.data[0].url
            revised = getattr(response.data[0], "revised_prompt", prompt)
            out_path = None
            if save_path:
                out = Path(save_path)
                out.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(url, str(out))
                out_path = str(out)
                logger.info(f"Image saved to {out_path}")
            return {
                "success": True,
                "url": url,
                "revised_prompt": revised,
                "saved_to": out_path,
            }
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return {"success": False, "error": str(e)}


_instance: ImageGenerator | None = None
_lock = threading.Lock()


def get_image_generator(api_key: str | None = None) -> ImageGenerator:
    global _instance
    if _instance is None or (
        api_key and api_key != getattr(_instance, "_api_key", None)
    ):
        with _lock:
            if _instance is None or (
                api_key and api_key != getattr(_instance, "_api_key", None)
            ):
                _instance = ImageGenerator(api_key=api_key)
    return _instance
