"""
Desktop audio loopback capture and transcription.

Captures whatever is playing through the speakers (WASAPI loopback on Windows)
and transcribes it with faster-whisper — no file or URL required.

Priority order:
  1. pyaudiowpatch  — best Windows loopback support (install: pip install pyaudiowpatch)
  2. sounddevice    — works if Windows "Stereo Mix" is enabled in Sound settings
"""

import asyncio
import numpy as np
from loguru import logger

_MAX_DURATION_S = 300   # 5 minutes cap per call
_SAMPLE_RATE = 16000    # Whisper expects 16 kHz
_CHUNK_FRAMES = 1024

# Module-level STT cache so we don't reload Whisper on every call
_desktop_stt = None
_desktop_stt_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _desktop_stt_lock
    if _desktop_stt_lock is None:
        _desktop_stt_lock = asyncio.Lock()
    return _desktop_stt_lock


async def _get_stt():
    """Lazy-load a base.en Whisper model for desktop transcription."""
    global _desktop_stt
    async with _get_lock():
        if _desktop_stt is None:
            from jarvis.voice.stt import STT
            logger.info("Loading Whisper base.en for desktop transcription (first use only)…")
            _desktop_stt = STT(
                model_name="base.en",
                device="auto",
                compute_type="auto",
                language="en",
            )
            await _desktop_stt.initialize()
            logger.info("Desktop transcription model ready.")
    return _desktop_stt


async def transcribe_desktop_audio(duration_s: float = 30.0) -> str:
    """
    Capture WASAPI loopback for duration_s seconds, then transcribe with Whisper.
    Returns the transcribed text, or an error message if capture failed.
    """
    duration_s = max(3.0, min(float(duration_s), _MAX_DURATION_S))
    logger.info(f"Desktop audio capture: {duration_s:.0f}s")

    audio = await asyncio.to_thread(_capture_loopback_sync, duration_s)

    if audio is None or len(audio) < _SAMPLE_RATE * 0.5:
        return (
            "Couldn't capture desktop audio. Make sure something is playing. "
            "If this keeps failing, install pyaudiowpatch: "
            "pip install pyaudiowpatch"
        )

    rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
    if rms < 8.0:
        return "Desktop audio was captured but the output was silent or too quiet to transcribe."

    stt = await _get_stt()
    text = await stt.transcribe(audio, sample_rate=_SAMPLE_RATE)
    if not text or not text.strip():
        return "Audio captured but no speech detected in the recording."

    return text.strip()


def _capture_loopback_sync(duration_s: float) -> np.ndarray | None:
    """Try pyaudiowpatch first, fall back to sounddevice loopback."""
    try:
        return _capture_pyaudiowpatch(duration_s)
    except ImportError:
        logger.debug("pyaudiowpatch not installed — falling back to sounddevice loopback")
    except Exception as e:
        logger.warning(f"pyaudiowpatch capture failed ({e}), falling back to sounddevice")

    try:
        return _capture_sounddevice(duration_s)
    except Exception as e:
        logger.error(f"Desktop audio capture failed: {e}")
        return None


def _capture_pyaudiowpatch(duration_s: float) -> np.ndarray:
    """WASAPI loopback via pyaudiowpatch — works on all Windows 10/11 systems."""
    import pyaudiowpatch as pyaudio

    p = pyaudio.PyAudio()
    try:
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])

        loopback = None
        for dev in p.get_loopback_device_info_generator():
            if default_out["name"] in dev["name"]:
                loopback = dev
                break

        if loopback is None:
            raise RuntimeError("No WASAPI loopback device found for default speakers")

        rate = int(loopback["defaultSampleRate"])
        channels = min(int(loopback["maxInputChannels"]), 2)
        total_samples = int(rate * duration_s)
        frames = []
        collected = 0

        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=int(loopback["index"]),
            frames_per_buffer=_CHUNK_FRAMES,
        )
        try:
            while collected < total_samples:
                data = stream.read(_CHUNK_FRAMES, exception_on_overflow=False)
                frames.append(data)
                collected += _CHUNK_FRAMES
        finally:
            stream.stop_stream()
            stream.close()

        audio = np.frombuffer(b"".join(frames), dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
        if rate != _SAMPLE_RATE:
            audio = _resample(audio, rate, _SAMPLE_RATE)
        return audio
    finally:
        p.terminate()


def _capture_sounddevice(duration_s: float) -> np.ndarray:
    """Fallback: sounddevice loopback (requires Stereo Mix enabled in Windows Sound settings)."""
    import sounddevice as sd

    loopback_idx = None
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and "loopback" in dev["name"].lower():
            loopback_idx = i
            break

    if loopback_idx is None:
        raise RuntimeError(
            "No loopback input device found. "
            "Either install pyaudiowpatch (pip install pyaudiowpatch) "
            "or enable 'Stereo Mix' in Windows Sound > Recording devices."
        )

    info = sd.query_devices(loopback_idx)
    rate = int(info["default_samplerate"])
    channels = min(int(info["max_input_channels"]), 2)

    recording = sd.rec(
        int(rate * duration_s),
        samplerate=rate,
        channels=channels,
        dtype=np.int16,
        device=loopback_idx,
    )
    sd.wait()

    audio = recording.mean(axis=1).astype(np.int16) if channels > 1 else recording.flatten()
    if rate != _SAMPLE_RATE:
        audio = _resample(audio, rate, _SAMPLE_RATE)
    return audio


def _resample(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return audio
    new_len = int(len(audio) * to_rate / from_rate)
    indices = np.linspace(0, len(audio) - 1, new_len)
    return np.interp(indices, np.arange(len(audio)), audio.astype(np.float64)).astype(np.int16)
