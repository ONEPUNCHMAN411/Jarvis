
import os
import tempfile
import threading
from pathlib import Path

from loguru import logger

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


class CameraVision:
    """Camera capture with frame description via local vision models."""

    def __init__(self):
        if not _CV2_AVAILABLE:
            raise ImportError("opencv-python is required. Run: pip install opencv-python")
        self._cap = None
        self._cap_lock = threading.Lock()
        self._source = None
        self._monitor_thread: threading.Thread | None = None
        self._monitor_stop = threading.Event()
        self._running = False

    def start(self, source: int | str = 0) -> bool:
        self._source = source
        # Try DirectShow first (avoids MSMF driver issues on Windows),
        # fall back to default backend for non-integer sources (IP streams).
        if isinstance(source, int):
            self._cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            if not self._cap.isOpened():
                self._cap = cv2.VideoCapture(source)
        else:
            self._cap = cv2.VideoCapture(source)
        if not self._cap.isOpened():
            logger.error(f"CameraVision: failed to open source {source}")
            return False
        self._running = True
        logger.info(f"CameraVision started: {source}")
        return True

    def stop(self) -> None:
        self._monitor_stop.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=3.0)
        with self._cap_lock:
            if self._cap:
                self._cap.release()
                self._cap = None
        self._running = False
        logger.info("CameraVision stopped")

    def capture_frame(self):
        with self._cap_lock:
            if not self._cap or not self._running:
                return None
            ret, frame = self._cap.read()
            if not ret:
                logger.warning("CameraVision: frame capture failed")
                return None
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if _PIL_AVAILABLE:
            return Image.fromarray(frame_rgb)
        return None

    def capture_to_file(self, path: str | None = None) -> str | None:
        img = self.capture_frame()
        if img is None:
            return None
        if path:
            out = path
        else:
            fd, out = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
        try:
            img.save(out, quality=90)
        except Exception as e:
            logger.error(f"capture_to_file save failed: {e}")
            if not path:
                Path(out).unlink(missing_ok=True)
            return None
        return out

    def describe_frame(self, prompt: str = "What do you see in this image?") -> str | None:
        img_path = self.capture_to_file()
        if not img_path:
            return None
        try:
            from jarvis.brain.local_vision import get_local_vision
            lv = get_local_vision()
            if lv.ready:
                return lv.describe(img_path, prompt)
            from jarvis.brain.vision_bridge import VisionBridge
            return VisionBridge([]).describe(img_path, prompt)
        except Exception as e:
            logger.error(f"CameraVision.describe_frame failed: {e}")
            return None
        finally:
            Path(img_path).unlink(missing_ok=True)

    def start_monitoring(self, callback, interval: float = 5.0) -> None:
        self._monitor_stop.clear()

        def _loop():
            while not self._monitor_stop.is_set():
                desc = self.describe_frame()
                if desc:
                    callback(desc)
                self._monitor_stop.wait(interval)

        self._monitor_thread = threading.Thread(target=_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"CameraVision monitoring every {interval}s")

    def stop_monitoring(self) -> None:
        self._monitor_stop.set()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def source(self):
        return self._source


_instance: CameraVision | None = None
_instance_lock = threading.Lock()


def get_camera_vision() -> CameraVision:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CameraVision()
    return _instance
