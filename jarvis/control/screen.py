import asyncio
import sys
import time
from pathlib import Path
from loguru import logger
import mss
from PIL import Image

def _resize_for_max_width(img: Image.Image, max_width: int | None) -> Image.Image:
    if not max_width:
        return img
    orig_w, orig_h = img.size
    if orig_w <= max_width:
        return img
    ratio = max_width / orig_w
    new_h = int(orig_h * ratio)
    return img.resize((max_width, new_h), Image.LANCZOS)

def _windows_system_dpi_percent() -> int | None:
    """Approximate UI scale % (100 = 96 DPI). Fits screenshot ↔ pyautogui alignment hints."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        dpi = ctypes.windll.user32.GetDpiForSystem()
        return int(round(dpi / 96.0 * 100))
    except Exception:
        return None

class Screen:
    def __init__(self, screenshot_dir: str = "data/screenshots"):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        # NOTE: Do NOT create a shared mss instance here.
        # mss uses Windows GDI/COM internally and is NOT thread-safe.
        # Creating it once and calling it from a thread pool thread causes
        # unpredictable segfaults.  Create a fresh instance per call instead.
        self._automation_hint_cache: str | None = None

    async def take_screenshot(self, monitor: int = 1, max_width: int | None = None) -> str:
        logger.debug(f"Taking screenshot of monitor {monitor}")

        try:
            def capture():
                # Fresh mss instance per thread-pool call — fully thread-safe.
                with mss.mss() as sct:
                    mon_index = min(monitor, len(sct.monitors) - 1)
                    screenshot = sct.grab(sct.monitors[mon_index])
                    img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                return _resize_for_max_width(img, max_width)

            img = await asyncio.to_thread(capture)

            filename = self.screenshot_dir / f"screenshot_{int(time.time() * 1000)}.png"
            await asyncio.to_thread(img.save, str(filename), optimize=True)

            logger.info(f"Screenshot saved: {filename} ({img.size[0]}x{img.size[1]})")
            return str(filename)

        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            raise

    def get_automation_display_hint(self) -> str:
        """
        Single cached line for the system prompt: ties MSS captures (monitor 1) to pyautogui pixels.
        Keeps model usage low versus repeating instructions every screenshot turn.
        """
        if self._automation_hint_cache is not None:
            return self._automation_hint_cache
        try:
            # Use a short-lived mss instance — thread-safe, no shared state.
            with mss.mss() as sct:
                mon = sct.monitors[1]
                w, h = mon["width"], mon["height"]
                left, top = mon["left"], mon["top"]
        except Exception:
            self._automation_hint_cache = ""
            return ""

        dpi = _windows_system_dpi_percent()
        dpi_note = f" Win UI scale ~{dpi}%." if dpi else ""

        self._automation_hint_cache = (
            f"PRIMARY monitor bitmap {w}x{h}px at virtual origin ({left},{top}); "
            f"mouse clicks use the same pixel grid as PNGs from take_screenshot (monitor 1).{dpi_note} "
            f"Grab one screenshot before the first click batch; repeat only after the UI changes or a miss."
        )
        return self._automation_hint_cache

    async def get_monitor_info(self) -> list[dict]:
        def _query():
            with mss.mss() as sct:
                return [
                    {
                        "index": i,
                        "left": monitor["left"],
                        "top": monitor["top"],
                        "width": monitor["width"],
                        "height": monitor["height"],
                    }
                    for i, monitor in enumerate(sct.monitors)
                ]
        return await asyncio.to_thread(_query)
