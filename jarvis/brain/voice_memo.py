
import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from loguru import logger

_MEMO_DIR = Path.home() / ".jarvis" / "memos"
_INDEX_FILE = _MEMO_DIR / "index.json"
_SAMPLE_RATE = 16000


@dataclass
class Memo:
    id: str
    title: str
    transcript: str
    audio_file: str
    created: str
    duration_s: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Memo":
        return cls(**d)


class VoiceMemoRecorder:
    """Record short voice memos via sounddevice and transcribe with Whisper."""

    def __init__(self):
        self._lock = threading.Lock()
        self._memos: list[Memo] = []
        self._model = None
        self._load_index()

    def _load_index(self) -> None:
        if not _INDEX_FILE.exists():
            return
        try:
            data = json.loads(_INDEX_FILE.read_text(encoding="utf-8"))
            self._memos = [Memo.from_dict(d) for d in data]
            logger.debug(f"VoiceMemo: loaded {len(self._memos)} memos")
        except Exception as e:
            logger.warning(f"VoiceMemo index load error: {e}")

    def _save_index(self) -> None:
        try:
            _MEMO_DIR.mkdir(parents=True, exist_ok=True)
            _INDEX_FILE.write_text(
                json.dumps([m.to_dict() for m in self._memos], indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"VoiceMemo index save error: {e}")

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                "base", device="cpu", compute_type="int8"
            )
            logger.info("VoiceMemo: Whisper model loaded")
        return self._model

    def record(self, duration: int = 30, title: str = "") -> Memo:
        import sounddevice as sd
        import soundfile as sf

        logger.info(f"VoiceMemo: recording {duration}s...")
        audio = sd.rec(
            int(duration * _SAMPLE_RATE),
            samplerate=_SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        logger.info("VoiceMemo: recording done, transcribing...")

        _MEMO_DIR.mkdir(parents=True, exist_ok=True)
        memo_id = uuid.uuid4().hex[:8]
        audio_path = _MEMO_DIR / f"{memo_id}.wav"
        sf.write(str(audio_path), audio, _SAMPLE_RATE)

        transcript = self._transcribe(audio_path)

        if title:
            auto_title = title
        elif transcript:
            auto_title = (
                transcript[:50].strip() + "..."
                if len(transcript) > 50
                else transcript
            )
        else:
            auto_title = f"Voice memo {datetime.now().strftime('%b %d %H:%M')}"

        memo = Memo(
            id=memo_id,
            title=auto_title,
            transcript=transcript,
            audio_file=str(audio_path),
            created=datetime.now().isoformat(timespec="seconds"),
            duration_s=float(duration),
        )
        with self._lock:
            self._memos.insert(0, memo)
            self._save_index()
        return memo

    def _transcribe(self, audio_path: Path) -> str:
        try:
            model = self._get_model()
            segments, _ = model.transcribe(str(audio_path), language="en")
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:
            logger.warning(f"VoiceMemo transcription error: {e}")
            return "[Transcription failed]"

    def list_memos(self) -> list[Memo]:
        with self._lock:
            return list(self._memos)

    def get_memo(self, memo_id: str) -> Memo | None:
        with self._lock:
            return next(
                (m for m in self._memos if m.id == memo_id), None
            )

    def delete_memo(self, memo_id: str) -> bool:
        with self._lock:
            memo = next(
                (m for m in self._memos if m.id == memo_id), None
            )
            if not memo:
                return False
            self._memos = [m for m in self._memos if m.id != memo_id]
            try:
                Path(memo.audio_file).unlink(missing_ok=True)
            except Exception:
                pass
            self._save_index()
            return True


_inst: VoiceMemoRecorder | None = None
_lock = threading.Lock()


def get_voice_memo() -> VoiceMemoRecorder:
    global _inst
    if _inst is None:
        with _lock:
            if _inst is None:
                _inst = VoiceMemoRecorder()
    return _inst
