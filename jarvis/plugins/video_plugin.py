
import asyncio
from pathlib import Path

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class VideoPlugin(Plugin):
    """Video transcription and summarization (local Whisper)."""

    def __init__(self):
        super().__init__("video")

    def _transcriber(self, model_size: str = "base"):
        from jarvis.brain.video_transcriber import get_transcriber
        return get_transcriber(model_size=model_size)

    async def initialize(self) -> None:
        try:
            from jarvis.brain.video_transcriber import _FW_AVAILABLE
            if not _FW_AVAILABLE:
                raise ImportError("faster-whisper not installed")
            logger.info("VideoPlugin ready (faster-whisper)")
        except ImportError as e:
            self.enabled = False
            logger.warning(f"VideoPlugin disabled: {e}")

    async def shutdown(self) -> None:
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="transcribe_video",
                    description=(
                        "Transcribe a video file (MP4, MKV, AVI, MOV, etc.) up to ~1 hour. "
                        "Returns the full transcript."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "video_path": {
                                "type": "string",
                                "description": "Absolute path to the video file",
                            },
                            "model_size": {
                                "type": "string",
                                "description": "Whisper model: tiny, base, small, medium, large-v3 (default: base)",
                                "enum": ["tiny", "base", "small", "medium", "large-v3"],
                            },
                            "language": {
                                "type": "string",
                                "description": "Force language code e.g. 'en', 'es' (auto-detected if omitted)",
                            },
                            "timestamps": {
                                "type": "boolean",
                                "description": "Include timestamps in output (default false)",
                            },
                        },
                        "required": ["video_path"],
                    },
                ),
                self.transcribe_video,
            ),
            (
                ToolDefinition(
                    name="summarize_video",
                    description=(
                        "Transcribe a video and return a summary of its content."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "video_path": {
                                "type": "string",
                                "description": "Absolute path to the video file",
                            },
                            "model_size": {
                                "type": "string",
                                "description": "Whisper model size (default: base)",
                                "enum": ["tiny", "base", "small", "medium", "large-v3"],
                            },
                            "language": {
                                "type": "string",
                                "description": "Force language code e.g. 'en' (auto-detected if omitted)",
                            },
                        },
                        "required": ["video_path"],
                    },
                ),
                self.summarize_video,
            ),
            (
                ToolDefinition(
                    name="export_transcript",
                    description="Transcribe a video and save the transcript as a .txt or .srt subtitle file.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "video_path": {
                                "type": "string",
                                "description": "Absolute path to the video file",
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Where to save the transcript (.txt or .srt)",
                            },
                            "format": {
                                "type": "string",
                                "description": "Output format: txt or srt (default: txt)",
                                "enum": ["txt", "srt"],
                            },
                            "model_size": {
                                "type": "string",
                                "description": "Whisper model size (default: base)",
                                "enum": ["tiny", "base", "small", "medium", "large-v3"],
                            },
                        },
                        "required": ["video_path", "output_path"],
                    },
                ),
                self.export_transcript,
            ),
        ]

    async def transcribe_video(
        self,
        video_path: str,
        model_size: str = "base",
        language: str | None = None,
        timestamps: bool = False,
    ) -> str:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._transcriber(model_size).transcribe(
                    video_path, model_size=model_size, language=language
                ),
            )
        except FileNotFoundError as e:
            return f"Error: {e}"
        except RuntimeError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.exception("transcribe_video failed")
            return f"Transcription failed: {e}"
        text = result.with_timestamps() if timestamps else result.text
        header = (
            f"[Transcription — {Path(video_path).name}]\n"
            f"Language: {result.language} | Duration: {result.duration:.1f}s | Model: {result.model}\n\n"
        )
        return header + text

    async def summarize_video(
        self,
        video_path: str,
        model_size: str = "base",
        language: str | None = None,
    ) -> str:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._transcriber(model_size).transcribe(
                    video_path, model_size=model_size, language=language
                ),
            )
        except Exception as e:
            logger.exception("summarize_video failed")
            return f"Transcription failed: {e}"
        name = Path(video_path).name
        duration_min = result.duration / 60
        return (
            f"[Video: {name} | {duration_min:.1f} min | lang: {result.language}]\n\n"
            f"TRANSCRIPT:\n{result.text[:12000]}"
        )

    async def export_transcript(
        self,
        video_path: str,
        output_path: str,
        format: str = "txt",
        model_size: str = "base",
    ) -> str:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._transcriber(model_size).transcribe(
                    video_path, model_size=model_size
                ),
            )
        except Exception as e:
            return f"Transcription failed: {e}"
        out = Path(output_path).expanduser()
        if format == "srt":
            out.write_text(result.as_srt(), encoding="utf-8")
        else:
            out.write_text(result.text, encoding="utf-8")
        return f"Transcript saved to {out} ({format.upper()}, {len(result.segments)} segments)"
