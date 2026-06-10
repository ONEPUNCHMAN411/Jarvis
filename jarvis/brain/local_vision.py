"""Lightweight local vision model for describing screenshots without any API calls."""


import threading

from loguru import logger

_MODEL_NAME = "moondream-2b-int8.mf"


class LocalVision:
    """Wraps a small local vision model loaded once in a background thread.

    Falls back gracefully if the model file is missing so the rest of
    JARVIS is completely unaffected.
    """

    def __init__(self):
        self._model = None
        self._ready = False
        self._loading = False
        self._lock = threading.Lock()

    def load_async(self):
        if self._ready or self._loading:
            return
        self._loading = True
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            import moondream as md
            logger.info("LocalVision: loading model...")
            with self._lock:
                self._model = md.vl(model=_MODEL_NAME)
                self._ready = True
            logger.info("LocalVision: model ready.")
        except Exception as e:
            logger.warning(f"LocalVision: model unavailable — {e}")
        finally:
            self._loading = False

    @property
    def ready(self) -> bool:
        return self._ready

    @staticmethod
    def _resize_for_model(img, max_side: int = 1024):
        """Downscale image so the longest side is at most max_side px."""
        from PIL import Image
        w, h = img.size
        if max(w, h) <= max_side:
            return img
        ratio = max_side / max(w, h)
        return img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    def describe(self, image_path: str, prompt: str | None = None) -> str | None:
        """Return a text description of an image file (blocking)."""
        if not self._ready:
            return None
        _prompt = prompt or (
            "Describe everything visible in this image in full detail. "
            "Include all text, UI elements, error messages, charts, and code."
        )
        try:
            from PIL import Image
            img = Image.open(image_path).convert("RGB")
            img = self._resize_for_model(img)
            with self._lock:
                result = self._model.query(img, _prompt)
            return (result.get("answer") or "").strip() or None
        except Exception as e:
            logger.warning(f"LocalVision.describe: {e}")
            return None

    def describe_screen(self, prompt: str | None = None) -> str | None:
        """Capture the monitor containing the active window and return a description."""
        if not self._ready:
            return None
        try:
            import mss
            from PIL import Image as PILImage
            monitor = self._get_active_monitor()
            with mss.mss() as sct:
                region = monitor or sct.monitors[1]
                shot = sct.grab(region)
                img = PILImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            img = self._resize_for_model(img)
            with self._lock:
                result = self._model.query(img, prompt or (
                    "Describe everything visible in this screenshot in full detail. "
                    "Include all text, UI elements, error messages, charts, and code."
                ))
            return (result.get("answer") or "").strip() or None
        except Exception as e:
            logger.warning(f"LocalVision.describe_screen: {e}")
            return None

    @staticmethod
    def _get_active_monitor() -> dict | None:
        """Return mss monitor dict for the monitor containing the foreground window."""
        try:
            import ctypes
            import mss
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return None
            from ctypes import wintypes
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            # Window center point
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            with mss.mss() as sct:
                for mon in sct.monitors[1:]:  # skip monitor[0] (virtual combined)
                    if (mon["left"] <= cx < mon["left"] + mon["width"] and
                            mon["top"] <= cy < mon["top"] + mon["height"]):
                        return mon
                return sct.monitors[1] if sct.monitors[1:] else None
        except Exception:
            return None


_instance: LocalVision | None = None


def get_local_vision() -> LocalVision:
    """Return the module-level singleton, starting async load if needed."""
    global _instance
    if _instance is None:
        _instance = LocalVision()
        _instance.load_async()
    return _instance
