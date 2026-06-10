
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class CameraPlugin(Plugin):
    """Webcam or ESP32 camera feed with frame description."""

    def __init__(self):
        super().__init__("camera")
        self._cam = None
        self._monitoring = False

    def _get_cam(self):
        if self._cam is None:
            from jarvis.brain.camera_vision import get_camera_vision
            self._cam = get_camera_vision()
        return self._cam

    async def initialize(self) -> None:
        try:
            from jarvis.brain.camera_vision import _CV2_AVAILABLE
            if not _CV2_AVAILABLE:
                raise ImportError("opencv-python not installed")
            logger.info("CameraPlugin ready")
        except ImportError as e:
            self.enabled = False
            logger.warning(f"CameraPlugin disabled: {e}")

    async def shutdown(self) -> None:
        if self._cam and self._cam.is_running:
            self._cam.stop()

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="start_camera",
                    description=(
                        "Start a camera feed. Use source='0' for webcam, or an ESP32 "
                        "stream URL like 'http://192.168.1.x/stream' for an IP camera."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "'0' for webcam or ESP32 stream URL",
                            },
                        },
                    },
                ),
                self.start_camera,
            ),
            (
                ToolDefinition(
                    name="stop_camera",
                    description="Stop the active camera feed.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.stop_camera,
            ),
            (
                ToolDefinition(
                    name="describe_what_i_see",
                    description=(
                        "Capture a frame from the camera and describe what's in it. "
                        "Useful for recognizing objects, reading labels, or identifying items."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "What to look for or ask about",
                            },
                        },
                    },
                ),
                self.describe_what_i_see,
            ),
            (
                ToolDefinition(
                    name="take_photo",
                    description="Capture and save a photo from the camera to a file.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "save_path": {
                                "type": "string",
                                "description": "Full file path to save the photo",
                            },
                        },
                        "required": ["save_path"],
                    },
                ),
                self.take_photo,
            ),
            (
                ToolDefinition(
                    name="start_camera_monitoring",
                    description="Start continuous camera monitoring — JARVIS describes what it sees every N seconds.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "interval_seconds": {
                                "type": "number",
                                "description": "Seconds between captures (default: 10)",
                            },
                        },
                    },
                ),
                self.start_monitoring,
            ),
            (
                ToolDefinition(
                    name="stop_camera_monitoring",
                    description="Stop continuous camera monitoring.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.stop_monitoring,
            ),
        ]

    async def start_camera(self, source: str = "0") -> str:
        cam = self._get_cam()
        if cam.is_running:
            return f"Camera already running on source {cam.source}."
        src: int | str = int(source) if source.isdigit() else source
        ok = cam.start(src)
        return f"Camera started on source: {source}" if ok else f"Failed to open: {source}"

    async def stop_camera(self) -> str:
        cam = self._get_cam()
        if not cam.is_running:
            return "Camera is not running."
        cam.stop()
        return "Camera stopped."

    async def describe_what_i_see(self, prompt: str = "What objects do you see?") -> str:
        cam = self._get_cam()
        if not cam.is_running:
            return "Camera is not running. Use start_camera first."
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: cam.describe_frame(prompt))
        return f"Camera sees: {result}" if result else "Could not get description — check camera and vision model."

    async def take_photo(self, save_path: str) -> str:
        cam = self._get_cam()
        if not cam.is_running:
            return "Camera is not running. Use start_camera first."
        loop = asyncio.get_running_loop()
        path = await loop.run_in_executor(None, lambda: cam.capture_to_file(save_path))
        return f"Photo saved to {path}" if path else "Failed to capture photo."

    async def start_monitoring(self, interval_seconds: float = 10.0) -> str:
        cam = self._get_cam()
        if not cam.is_running:
            return "Camera is not running. Use start_camera first."
        if self._monitoring:
            return "Monitoring is already active."
        cam.start_monitoring(lambda d: logger.info(f"[Camera] {d}"), interval=interval_seconds)
        self._monitoring = True
        return f"Camera monitoring started — describing every {interval_seconds}s."

    async def stop_monitoring(self) -> str:
        self._get_cam().stop_monitoring()
        self._monitoring = False
        return "Camera monitoring stopped."
