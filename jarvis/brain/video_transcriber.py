
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

try:
    from faster_whisper import WhisperModel
    _FW_AVAILABLE = True
except ImportError:
    _FW_AVAILABLE = False


@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    segments: list[TranscriptionSegment] = field(default_factory=list)
    language: str = ""
    duration: float = 0.0
    model: str = ""

    def as_srt(self) -> str:
        lines = []
        for i, seg in enumerate(self.segments, 1):
            lines += [str(i), f"{_ts(seg.start)} --> {_ts(seg.end)}", seg.text.strip(), ""]
        return "\n".join(lines)

    def with_timestamps(self) -> str:
        return "\n".join(f"[{_ts(s.start)}] {s.text.strip()}" for s in self.segments)


def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _extract_audio(video_path: Path, out_wav: Path) -> bool:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(out_wav),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=3600)
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg audio extraction timed out (>3600s)")
        return False
    if result.returncode != 0:
        logger.error(f"ffmpeg failed: {result.stderr.decode(errors='replace')[:500]}")
        return False
    return True


class VideoTranscriber:
    """Local video transcription via faster-whisper."""

    _models: dict[str, "WhisperModel"] = {}

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        if not _FW_AVAILABLE:
            raise ImportError("faster-whisper is required. Run: pip install faster-whisper")
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type

    def _get_model(self, size: str) -> "WhisperModel":
        if size not in VideoTranscriber._models:
            logger.info(f"Loading Whisper '{size}' (first run downloads weights)...")
            VideoTranscriber._models[size] = WhisperModel(
                size, device=self._device, compute_type=self._compute_type
            )
        return VideoTranscriber._models[size]

    def transcribe(
        self,
        video_path: str | Path,
        model_size: str | None = None,
        language: str | None = None,
    ) -> TranscriptionResult:
        path = Path(video_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Video not found: {path}")
        size = model_size or self._model_size
        model = self._get_model(size)
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.wav"
            logger.info(f"Extracting audio from {path.name}...")
            if not _extract_audio(path, audio):
                raise RuntimeError("ffmpeg audio extraction failed — is ffmpeg installed?")
            logger.info(f"Transcribing with Whisper '{size}'...")
            segments_iter, info = model.transcribe(
                str(audio),
                language=language,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            segments: list[TranscriptionSegment] = []
            for seg in segments_iter:
                segments.append(TranscriptionSegment(start=seg.start, end=seg.end, text=seg.text))
        full_text = " ".join(s.text.strip() for s in segments)
        result = TranscriptionResult(
            text=full_text,
            segments=segments,
            language=info.language,
            duration=info.duration,
            model=size,
        )
        logger.info(
            f"Transcription done: {len(segments)} segments, "
            f"{info.duration:.1f}s, lang={info.language}"
        )
        return result


_transcriber: VideoTranscriber | None = None
_transcriber_lock = threading.Lock()


def get_transcriber(model_size: str = "base") -> VideoTranscriber:
    global _transcriber
    if _transcriber is None:
        with _transcriber_lock:
            if _transcriber is None:
                _transcriber = VideoTranscriber(model_size=model_size)
    return _transcriber
