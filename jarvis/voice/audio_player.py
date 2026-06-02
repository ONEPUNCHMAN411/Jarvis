import asyncio
import io
import sounddevice as sd
import soundfile as sf
from loguru import logger

class AudioPlayer:
    def __init__(self, sample_rate: int = 24000, device: int | None = None):
        self.sample_rate = sample_rate
        self.device = device
        self.is_playing = False
        self._current_stream = None

    async def play_audio(self, audio_bytes: bytes) -> None:
        try:
            logger.debug(f"Playing audio ({len(audio_bytes)} bytes)")
            self.is_playing = True

            audio_buffer = io.BytesIO(audio_bytes)
            data, samplerate = await asyncio.to_thread(
                sf.read, audio_buffer, dtype="float32"
            )

            await asyncio.to_thread(
                sd.play, data, samplerate=samplerate, device=self.device, blocking=True
            )

            self.is_playing = False
            logger.debug("Audio playback completed")

        except Exception as e:
            logger.error(f"Audio playback error: {e}")
            self.is_playing = False
            raise

    async def stop_playback(self) -> None:
        if self.is_playing:
            await asyncio.to_thread(sd.stop)
            self.is_playing = False
            logger.debug("Audio playback stopped")

    def stop(self) -> None:
        """Synchronous immediate stop — safe to call from any thread/context."""
        try:
            sd.stop()
            self.is_playing = False
        except Exception:
            pass
