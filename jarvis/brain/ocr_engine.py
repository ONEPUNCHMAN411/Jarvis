
import os
import tempfile
import threading
from pathlib import Path

from loguru import logger

_EASY_AVAILABLE = False
_TESS_AVAILABLE = False

try:
    import easyocr
    _EASY_AVAILABLE = True
except ImportError:
    pass

try:
    import pytesseract
    from PIL import Image as _PILImage
    _TESS_AVAILABLE = True
except ImportError:
    pass

_AVAILABLE = _EASY_AVAILABLE or _TESS_AVAILABLE


class OCREngine:
    """Extract text from image files using EasyOCR or Tesseract."""

    def __init__(self, languages: Optional[list[str]] = None):
        self._languages = languages or ["en"]
        self._reader = None
        self._reader_lock = threading.Lock()

    def _get_easy_reader(self):
        with self._reader_lock:
            if self._reader is None:
                logger.info("Loading EasyOCR model -- first run may take a moment...")
                self._reader = easyocr.Reader(self._languages, gpu=False)
        return self._reader

    def read_image(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        if _EASY_AVAILABLE:
            return self._read_easyocr(str(p))
        if _TESS_AVAILABLE:
            return self._read_tesseract(str(p))
        raise RuntimeError(
            "No OCR engine available.\n"
            "Install one: pip install easyocr\n"
            "or: pip install pytesseract pillow (plus Tesseract binary)"
        )

    def _read_easyocr(self, path: str) -> str:
        reader = self._get_easy_reader()
        results = reader.readtext(path, detail=0, paragraph=True)
        return "\n".join(results).strip()

    def _read_tesseract(self, path: str) -> str:
        img = _PILImage.open(path)
        return pytesseract.image_to_string(img).strip()

    def read_screenshot(self) -> str:
        """Capture the current screen and extract all visible text from it."""
        try:
            import pyautogui
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            try:
                pyautogui.screenshot(tmp)
                return self.read_image(tmp)
            finally:
                Path(tmp).unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Screenshot OCR failed: {e}")
            raise


_instance: OCREngine | None = None
_lock = threading.Lock()


def get_ocr_engine(languages: Optional[list[str]] = None) -> OCREngine:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = OCREngine(languages=languages)
    return _instance
