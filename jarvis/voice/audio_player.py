import asyncio
import io
import numpy as np
import sounddevice as sd
import soundfile as sf
from loguru import logger


def _decode_audio(audio_bytes: bytes) -> tuple[np.ndarray, int]:
    """Decode audio bytes (MP3/WAV/etc) to float32 PCM via PyAV with soundfile fallback."""
    try:
        import av
        container = av.open(io.BytesIO(audio_bytes))
        stream = container.streams.audio[0]
        frames = []
        for frame in container.decode(stream):
            arr = frame.to_ndarray()
            # fltp (float planar) is already normalized [-1, 1]; s16p is int16
            if arr.dtype == np.int16:
                frames.append(arr.astype(np.float32) / 32768.0)
            else:
                frames.append(arr.astype(np.float32))
        container.close()
        data = np.concatenate(frames, axis=1).T
        if data.ndim == 2 and data.shape[1] == 1:
            data = data[:, 0]
        return data, stream.sample_rate
    except Exception:
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        return data, sr


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

            data, samplerate = await asyncio.to_thread(_decode_audio, audio_bytes)

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
