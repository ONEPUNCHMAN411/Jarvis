import asyncio
from pathlib import Path
import numpy as np
from loguru import logger

try:
    import openwakeword
    from openwakeword.model import Model
    from openwakeword.utils import download_models
    HAS_OPENWAKEWORD = True
except ImportError:
    HAS_OPENWAKEWORD = False

def _normalize_wakeword_model_name(wake_word: str) -> str:
    normalized = "_".join(wake_word.strip().lower().split())
    if not normalized.startswith("hey_"):
        normalized = f"hey_{normalized}"
    return normalized

def _resolve_asset_paths(model_name: str) -> tuple[str, str, str]:
    target_dir = Path.home() / ".jarvis" / "wakeword_models"
    target_dir.mkdir(parents=True, exist_ok=True)
    download_models([model_name], target_directory=str(target_dir))

    model_file = Path(openwakeword.MODELS[model_name]["download_url"]).name.replace(".tflite", ".onnx")
    melspec_file = Path(openwakeword.FEATURE_MODELS["melspectrogram"]["download_url"]).name.replace(".tflite", ".onnx")
    embedding_file = Path(openwakeword.FEATURE_MODELS["embedding"]["download_url"]).name.replace(".tflite", ".onnx")
    return (
        str(target_dir / model_file),
        str(target_dir / melspec_file),
        str(target_dir / embedding_file),
    )

class WakeWordDetector:
    def __init__(self, wake_word: str = "hey jarvis", sensitivity: float = 0.5):
        self.wake_word = wake_word
        self.sensitivity = sensitivity
        self.model = None
        self.has_model = False
        self.model_key = _normalize_wakeword_model_name(wake_word)

    async def initialize(self) -> None:
        logger.info(f"Loading wake word model for: {self.wake_word}")

        if not HAS_OPENWAKEWORD:
            logger.warning(
                "Wake word detection is unavailable on this system "
                "(openwakeword/tflite-runtime not installed). "
                "Use the mic button or press Ctrl+Shift+J to talk to JARVIS."
            )
            self.has_model = False
            self._emit_fallback_notification()
            return

        try:
            model_name = _normalize_wakeword_model_name(self.wake_word)
            self.model_key = model_name
            model_path, melspec_path, embedding_path = _resolve_asset_paths(model_name)

            def load_model():
                return Model(
                    wakeword_models=[model_path],
                    inference_framework="onnx",
                    melspec_model_path=melspec_path,
                    embedding_model_path=embedding_path,
                )

            self.model = await asyncio.to_thread(load_model)
            self.has_model = True
            logger.info(f"Wake word model loaded: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load wake word model: {e}")
            logger.warning(
                "Wake word detection disabled — use the mic button or Ctrl+Shift+J instead."
            )
            self.has_model = False
            self._emit_fallback_notification()

    async def detect(self, audio_chunk: np.ndarray) -> float:
        if not self.has_model:
            return 0.0

        try:
            audio_float = audio_chunk.astype(np.float32) / 32768.0
            if audio_float.ndim > 1:
                audio_float = audio_float.squeeze()

            def predict():
                return self.model.predict(audio_float, threshold=self.sensitivity)

            prediction = await asyncio.to_thread(predict)

            confidence = prediction.get(self.model_key, 0.0)
            logger.debug(f"Wake word confidence: {confidence:.3f}")

            return confidence

        except Exception as e:
            logger.error(f"Wake word detection error: {e}")
            return 0.0

    async def is_wake_word_detected(self, audio_chunk: np.ndarray) -> bool:
        confidence = await self.detect(audio_chunk)
        detected = confidence >= self.sensitivity
        if detected:
            logger.info(f"Wake word detected! (confidence: {confidence:.3f})")
        return detected

    def _emit_fallback_notification(self) -> None:
        """Write a startup warning to the log so the UI can surface it as a toast."""
        try:
            # The voice_manager reads this flag and emits a RuntimeLogEvent on startup.
            self._fallback_notified = True
        except Exception:
            pass

    @property
    def fallback_mode(self) -> bool:
        return not self.has_model

    async def shutdown(self) -> None:
        self.model = None
        logger.info("Wake word detector shutdown")
