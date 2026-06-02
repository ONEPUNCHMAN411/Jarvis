"""
Live desktop audio transcription service.

Captures speaker output in 4-second chunks, transcribes each with Whisper,
publishes TranscriptionChunkEvent for the subtitle overlay, and writes a
timestamped session file for later recall.

Usage (via tool calls):
    start_live_transcription()
    stop_live_transcription()
    get_recent_transcript(seconds=120)
    recall_transcription(session_id="2026-06-02_22-30")
"""

import asyncio
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from loguru import logger


_CHUNK_SECONDS = 4.0        # audio chunk length per transcription cycle
_MAX_BUFFER = 200           # max chunks kept in memory for Q&A recall
_TRANSCRIPTION_DIR = Path.home() / ".jarvis" / "transcriptions"


class LiveTranscriptionService:
    def __init__(self, event_bus):
        self._bus = event_bus
        self._running = False
        self._task: asyncio.Task | None = None
        self._session_id: str = ""
        self._session_file: Path | None = None
        self._buffer: deque[dict] = deque(maxlen=_MAX_BUFFER)
        self._stt = None

    async def start(self) -> str:
        if self._running:
            return f"Live transcription already running (session {self._session_id})"

        self._session_id = datetime.now().strftime("%Y-%m-%d_%H-%M")
        _TRANSCRIPTION_DIR.mkdir(parents=True, exist_ok=True)
        self._session_file = _TRANSCRIPTION_DIR / f"{self._session_id}.txt"
        self._session_file.write_text(
            f"# JARVIS Live Transcription — {self._session_id}\n\n",
            encoding="utf-8",
        )
        self._buffer.clear()
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Live transcription started — session {self._session_id}")
        return f"Live transcription started. Session saved to: {self._session_file}"

    async def stop(self) -> str:
        if not self._running:
            return "Live transcription is not running."
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        path = str(self._session_file) if self._session_file else "unknown"
        logger.info(f"Live transcription stopped — session {self._session_id}")
        return f"Live transcription stopped. Transcript saved to: {path}"

    def get_recent_transcript(self, seconds: float = 120.0) -> str:
        if not self._buffer:
            return "No live transcription is running or no audio has been captured yet."
        cutoff = time.monotonic() - seconds
        chunks = [c["text"] for c in self._buffer if c["ts"] >= cutoff]
        if not chunks:
            return f"No speech detected in the last {seconds:.0f} seconds."
        return " ".join(chunks)

    def is_running(self) -> bool:
        return self._running

    @property
    def session_id(self) -> str:
        return self._session_id

    async def _loop(self) -> None:
        from jarvis.voice.desktop_audio import _capture_loopback_sync, _SAMPLE_RATE
        stt = await self._get_stt()

        while self._running:
            try:
                audio = await asyncio.to_thread(_capture_loopback_sync, _CHUNK_SECONDS)
                if audio is None:
                    await asyncio.sleep(1.0)
                    continue

                rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
                if rms < 8.0:
                    continue  # silence — skip transcription

                text = await stt.transcribe(audio, sample_rate=_SAMPLE_RATE)
                if not text or not text.strip():
                    continue

                text = text.strip()
                ts = time.monotonic()
                self._buffer.append({"text": text, "ts": ts})
                self._write_to_file(text)

                from jarvis.models import TranscriptionChunkEvent
                await self._bus.publish(
                    TranscriptionChunkEvent(
                        text=text,
                        timestamp=ts,
                        session_id=self._session_id,
                    )
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Live transcription chunk error: {e}")
                await asyncio.sleep(1.0)

    async def _get_stt(self):
        if self._stt is None:
            from jarvis.voice.stt import STT
            logger.info("Loading Whisper base.en for live transcription…")
            self._stt = STT(model_name="base.en", device="auto", compute_type="auto", language="en")
            await self._stt.initialize()
            logger.info("Live transcription STT ready.")
        return self._stt

    def _write_to_file(self, text: str) -> None:
        if not self._session_file:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            with open(self._session_file, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {text}\n")
        except Exception as e:
            logger.warning(f"Failed to write transcription: {e}")


def list_transcription_sessions() -> list[str]:
    """Return sorted list of saved session IDs."""
    if not _TRANSCRIPTION_DIR.exists():
        return []
    return sorted(
        p.stem for p in _TRANSCRIPTION_DIR.glob("*.txt")
        if not p.stem.startswith(".")
    )


def read_transcription_session(session_id: str) -> str:
    """Read a saved transcription file by session ID."""
    path = _TRANSCRIPTION_DIR / f"{session_id}.txt"
    if not path.exists():
        sessions = list_transcription_sessions()
        if not sessions:
            return "No saved transcriptions found."
        return f"Session '{session_id}' not found. Available: {', '.join(sessions[-10:])}"
    text = path.read_text(encoding="utf-8")
    return text[:8000] + ("\n… [truncated]" if len(text) > 8000 else "")
