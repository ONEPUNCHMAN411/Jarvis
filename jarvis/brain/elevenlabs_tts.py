
import os
import tempfile
import threading
from pathlib import Path

from loguru import logger

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import play, stream
    from elevenlabs.types import VoiceSettings
    _EL_AVAILABLE = True
except ImportError:
    _EL_AVAILABLE = False

try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False

_DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"
_DEFAULT_MODEL = "eleven_turbo_v2_5"


class ElevenLabsTTS:
    """ElevenLabs TTS with streaming playback."""

    def __init__(self, api_key: str | None = None):
        if not _EL_AVAILABLE:
            raise ImportError("elevenlabs package not installed. Run: pip install elevenlabs")
        key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
        if not key:
            raise ValueError("ELEVENLABS_API_KEY not set")
        self._api_key = key
        self._client = ElevenLabs(api_key=key)
        self._voice_id = _DEFAULT_VOICE
        self._model = _DEFAULT_MODEL
        if _PYGAME_AVAILABLE:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            except Exception as e:
                logger.warning(f"pygame mixer init failed: {e}")
        logger.info("ElevenLabsTTS initialized")

    def list_voices(self) -> list[dict]:
        resp = self._client.voices.get_all()
        return [
            {
                "id": v.voice_id,
                "name": v.name,
                "category": getattr(v, "category", ""),
                "description": getattr(v, "description", ""),
            }
            for v in resp.voices
        ]

    def set_voice(self, voice_id: str) -> None:
        self._voice_id = voice_id
        logger.info(f"Voice set to {voice_id}")

    def set_model(self, model: str) -> None:
        self._model = model
        logger.info(f"TTS model set to {model}")

    def speak(self, text: str, stream_audio: bool = True) -> bool:
        try:
            settings = VoiceSettings(stability=0.5, similarity_boost=0.75, style=0.0)
            if stream_audio:
                audio_iter = self._client.text_to_speech.stream(  # stream() not convert_as_stream()
                    voice_id=self._voice_id,
                    text=text,
                    model_id=self._model,
                    voice_settings=settings,
                )
                stream(audio_iter)
            else:
                chunks = self._client.text_to_speech.convert(
                    voice_id=self._voice_id,
                    text=text,
                    model_id=self._model,
                    voice_settings=settings,
                )
                self._play_bytes(b"".join(chunks))
            return True
        except Exception as e:
            logger.error(f"ElevenLabsTTS.speak failed: {e}")
            return False

    def speak_to_file(self, text: str, output_path: str) -> bool:
        try:
            settings = VoiceSettings(stability=0.5, similarity_boost=0.75, style=0.0)
            chunks = self._client.text_to_speech.convert(
                voice_id=self._voice_id,
                text=text,
                model_id=self._model,
                voice_settings=settings,
            )
            Path(output_path).write_bytes(b"".join(chunks))
            return True
        except Exception as e:
            logger.error(f"ElevenLabsTTS.speak_to_file failed: {e}")
            return False

    def _play_bytes(self, audio_bytes: bytes) -> None:
        if _PYGAME_AVAILABLE and pygame.mixer.get_init():
            import io
            pygame.mixer.music.load(io.BytesIO(audio_bytes))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(50)
        else:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_bytes)
                tmp = f.name
            try:
                play(Path(tmp).read_bytes())
            finally:
                Path(tmp).unlink(missing_ok=True)


_instance: ElevenLabsTTS | None = None
_instance_lock = threading.Lock()


def get_tts(api_key: str | None = None) -> ElevenLabsTTS:
    global _instance
    # Rebuild if a new key is explicitly provided and differs from the current one
    if _instance is None or (api_key and api_key != getattr(_instance, "_api_key", None)):
        with _instance_lock:
            if _instance is None or (api_key and api_key != getattr(_instance, "_api_key", None)):
                _instance = ElevenLabsTTS(api_key=api_key)
    return _instance
