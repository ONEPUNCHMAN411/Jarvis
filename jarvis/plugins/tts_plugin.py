
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class TTSPlugin(Plugin):
    """ElevenLabs text-to-speech tools."""

    def __init__(self):
        super().__init__("tts")
        self._tts = None

    def _get_tts(self):
        if self._tts is None:
            from jarvis.brain.elevenlabs_tts import get_tts
            self._tts = get_tts()
        return self._tts

    async def initialize(self) -> None:
        try:
            self._get_tts()
            logger.info("TTSPlugin (ElevenLabs) ready")
        except Exception as e:
            self.enabled = False
            logger.warning(f"TTSPlugin disabled: {e}")

    async def shutdown(self) -> None:
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="speak",
                    description="Speak text aloud using ElevenLabs voice synthesis.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Text to speak",
                            },
                            "stream": {
                                "type": "boolean",
                                "description": "Stream audio as it generates (default true)",
                            },
                        },
                        "required": ["text"],
                    },
                ),
                self.speak,
            ),
            (
                ToolDefinition(
                    name="list_voices",
                    description="List all available ElevenLabs voices with their IDs.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_voices,
            ),
            (
                ToolDefinition(
                    name="set_voice",
                    description="Switch the active ElevenLabs voice by its voice ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "voice_id": {
                                "type": "string",
                                "description": "ElevenLabs voice ID",
                            },
                        },
                        "required": ["voice_id"],
                    },
                ),
                self.set_voice,
            ),
            (
                ToolDefinition(
                    name="set_tts_model",
                    description="Switch the ElevenLabs model (e.g. eleven_turbo_v2_5, eleven_multilingual_v2).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "model": {
                                "type": "string",
                                "description": "Model ID",
                            },
                        },
                        "required": ["model"],
                    },
                ),
                self.set_model,
            ),
        ]

    async def speak(self, text: str, stream: bool = True) -> str:
        # speak() blocks until playback finishes — run off the event loop
        tts = self._get_tts()
        ok = await asyncio.to_thread(tts.speak, text, stream)
        return "Speaking." if ok else "TTS failed — check ELEVENLABS_API_KEY."

    async def list_voices(self) -> str:
        # network call — keep off the event loop
        tts = self._get_tts()
        voices = await asyncio.to_thread(tts.list_voices)
        if not voices:
            return "No voices found."
        lines = [f"Available ElevenLabs voices ({len(voices)}):"]
        for v in voices:
            cat = f" [{v['category']}]" if v.get("category") else ""
            lines.append(f"  {v['id']} — {v['name']}{cat}")
        return "\n".join(lines)

    async def set_voice(self, voice_id: str) -> str:
        self._get_tts().set_voice(voice_id)
        return f"Voice set to {voice_id}."

    async def set_model(self, model: str) -> str:
        self._get_tts().set_model(model)
        return f"TTS model set to {model}."
