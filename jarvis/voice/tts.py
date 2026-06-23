import asyncio
import io
import os
import tempfile
from loguru import logger
import edge_tts

try:
    import pyttsx3
    _PYTTSX3_AVAILABLE = True
except ImportError:
    _PYTTSX3_AVAILABLE = False

class TTS:
    def __init__(self, voice: str = "en-GB-RyanNeural", rate: str = "+5%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    def set_voice(self, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> None:
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    async def synthesize_stream(self, text: str):
        """Yields audio chunks for streaming playback, with offline fallback."""
        logger.debug(f"Synthesizing stream: {text[:50]}...")
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch,
            )
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as e:
            logger.warning(f"edge-tts failed ({e}), trying local TTS fallback")
            data = await self._synthesize_local(text)
            if data:
                yield data
            else:
                raise

    async def synthesize(self, text: str) -> bytes:
        """Collects all chunks into bytes, with offline fallback."""
        audio_buffer = io.BytesIO()
        async for chunk in self.synthesize_stream(text):
            audio_buffer.write(chunk)
        return audio_buffer.getvalue()

    async def _synthesize_local(self, text: str) -> bytes | None:
        """Offline fallback using pyttsx3 — saves to a temp WAV and returns bytes."""
        if not _PYTTSX3_AVAILABLE:
            logger.warning("pyttsx3 not installed — offline TTS unavailable")
            return None
        try:
            def _run() -> bytes:
                engine = pyttsx3.init()
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.close()
                try:
                    engine.save_to_file(text, tmp.name)
                    engine.runAndWait()
                    engine.stop()
                    with open(tmp.name, "rb") as f:
                        return f.read()
                finally:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass

            data = await asyncio.to_thread(_run)
            logger.info("Local TTS fallback succeeded")
            return data
        except Exception as exc:
            logger.error(f"Local TTS fallback failed: {exc}")
            return None

    async def get_available_voices(self) -> list[str]:
        voices = await edge_tts.list_voices()
        return [v["Name"] for v in voices]
