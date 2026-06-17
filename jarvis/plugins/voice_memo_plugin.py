
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class VoiceMemoPlugin(Plugin):
    """Voice memo recorder — speak a thought, JARVIS transcribes and saves it."""

    def __init__(self):
        super().__init__("voice_memo")
        self._recorder = None

    def _get(self):
        if self._recorder is None:
            from jarvis.brain.voice_memo import get_voice_memo
            self._recorder = get_voice_memo()
        return self._recorder

    async def initialize(self) -> None:
        logger.info("VoiceMemoPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="record_memo",
                    description=(
                        "Record a voice memo using the microphone and "
                        "auto-transcribe it using Whisper. "
                        "Use when user says 'take a voice memo', "
                        "'record a quick thought', 'let me dictate a note', "
                        "'voice memo', 'I want to record something'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "duration": {
                                "type": "integer",
                                "description": (
                                    "Recording duration in seconds "
                                    "(default 30, max 300)"
                                ),
                            },
                            "title": {
                                "type": "string",
                                "description": (
                                    "Optional title — auto-generated from "
                                    "transcript if not provided"
                                ),
                            },
                        },
                    },
                ),
                self.record_memo,
            ),
            (
                ToolDefinition(
                    name="list_memos",
                    description=(
                        "List all saved voice memos. Use when user says "
                        "'show my voice memos', 'what memos do I have?', "
                        "'list my recordings'."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_memos,
            ),
            (
                ToolDefinition(
                    name="read_memo",
                    description="Read the full transcript of a voice memo by ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "memo_id": {
                                "type": "string",
                                "description": "Memo ID from list_memos",
                            }
                        },
                        "required": ["memo_id"],
                    },
                ),
                self.read_memo,
            ),
            (
                ToolDefinition(
                    name="delete_memo",
                    description="Delete a voice memo and its audio file by ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "memo_id": {
                                "type": "string",
                                "description": "Memo ID to delete",
                            }
                        },
                        "required": ["memo_id"],
                    },
                ),
                self.delete_memo,
            ),
        ]

    async def record_memo(
        self, duration: int = 30, title: str = ""
    ) -> str:
        duration = max(5, min(duration, 300))
        loop = asyncio.get_running_loop()
        try:
            memo = await loop.run_in_executor(
                None,
                lambda: self._get().record(duration=duration, title=title),
            )
            return (
                f"Voice memo saved  [ID: {memo.id}]\n"
                f"Title: {memo.title}\n"
                f"Duration: {memo.duration_s:.0f}s\n"
                f"Transcript: {memo.transcript}"
            )
        except Exception as e:
            return f"Failed to record memo: {e}"

    async def list_memos(self) -> str:
        memos = self._get().list_memos()
        if not memos:
            return "No voice memos saved yet."
        lines = ["Voice memos:"]
        for m in memos:
            preview = (
                m.transcript[:60] + "..."
                if len(m.transcript) > 60
                else m.transcript
            )
            lines.append(
                f"  [{m.id}] {m.title}  ({m.created[:10]})  {preview}"
            )
        return "\n".join(lines)

    async def read_memo(self, memo_id: str) -> str:
        memo = self._get().get_memo(memo_id)
        if not memo:
            return f"No memo found with ID '{memo_id}'."
        return (
            f"Memo: {memo.title}\n"
            f"Recorded: {memo.created}  ({memo.duration_s:.0f}s)\n"
            f"\n{memo.transcript}"
        )

    async def delete_memo(self, memo_id: str) -> str:
        if self._get().delete_memo(memo_id):
            return f"Memo [{memo_id}] deleted."
        return f"No memo found with ID '{memo_id}'."
