import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

_TONES = {
    "formal": (
        "Rewrite the following text in a formal, professional register. "
        "Use complete sentences, precise vocabulary, and avoid contractions or colloquialisms."
    ),
    "casual": (
        "Rewrite the following text in a casual, conversational tone. "
        "Use everyday language, contractions, and a friendly first-person voice."
    ),
    "genz": (
        "Rewrite the following text in Gen-Z internet speak. "
        "Use current slang (no cap, lowkey, it's giving, slay, fr fr, bussin, etc.), "
        "informal spelling, and short punchy sentences."
    ),
    "hemingway": (
        "Rewrite the following text in Hemingway's style: short declarative sentences, "
        "simple words, active voice, no adverbs, no padding. Show, don't tell."
    ),
    "bullets": (
        "Rewrite the following text as a clean bullet-point list. "
        "Each bullet should be a single concise idea. Group related ideas under sub-bullets if helpful."
    ),
    "technical": (
        "Rewrite the following text in a precise, technical style suitable for developer documentation. "
        "Use exact terminology, avoid ambiguity, and structure information logically."
    ),
    "concise": (
        "Rewrite the following text to be as concise as possible. "
        "Remove every unnecessary word. Target 40-60% of the original length while preserving all key meaning."
    ),
    "persuasive": (
        "Rewrite the following text to be maximally persuasive. "
        "Lead with the strongest argument, use concrete evidence, anticipate objections, "
        "and end with a clear call to action."
    ),
}


class StyleTransferPlugin(Plugin):
    """Rewrite user text in a chosen tone: formal, casual, Gen-Z, Hemingway,
    bullets, technical, concise, or persuasive."""

    def __init__(self):
        super().__init__("style_transfer")

    async def initialize(self):
        logger.info("StyleTransferPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="rewrite_text",
                description=(
                    "Rewrite text in a chosen tone or style. "
                    "Tones: formal, casual, genz, hemingway, bullets, technical, concise, persuasive. "
                    "Use when user says 'rewrite this more formally', 'make this casual', "
                    "'summarise as bullet points', 'shorten this', 'make this more persuasive', "
                    "'write this like Hemingway', 'translate to Gen-Z speak'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The text to rewrite"},
                        "tone": {
                            "type": "string",
                            "enum": ["formal", "casual", "genz", "hemingway", "bullets", "technical", "concise", "persuasive"],
                            "description": "Target tone/style",
                        },
                        "preserve_meaning": {
                            "type": "boolean",
                            "default": True,
                            "description": "Keep all key information (true) or allow creative reinterpretation (false)",
                        },
                    },
                    "required": ["text", "tone"],
                },
            ), self.rewrite),
            (ToolDefinition(
                name="list_tones",
                description="List all available rewriting tones with descriptions.",
                parameters={"type": "object", "properties": {}},
            ), self.list_tones),
        ]


    async def rewrite(self, text: str, tone: str, preserve_meaning: bool = True, **_) -> str:
        instruction = _TONES.get(tone.lower())
        if not instruction:
            available = ", ".join(_TONES.keys())
            return f"Unknown tone '{tone}'. Available: {available}"
        meaning_note = " Preserve all key information and meaning." if preserve_meaning else " Creative reinterpretation is acceptable."
        return (
            f"{instruction}{meaning_note}\n\n"
            f"Original text:\n{text}\n\n"
            "Rewritten version:"
        )

    async def list_tones(self, **_) -> str:
        desc = {
            "formal": "Professional, complete sentences, precise vocabulary",
            "casual": "Friendly, conversational, contractions OK",
            "genz": "Current internet slang, no cap, lowkey, fr fr",
            "hemingway": "Short declarative sentences, simple words, active voice",
            "bullets": "Clean bullet-point list, one idea per bullet",
            "technical": "Developer-doc style, exact terminology, no ambiguity",
            "concise": "40-60% shorter, every word earns its place",
            "persuasive": "Lead with strongest argument, clear call to action",
        }
        lines = ["Available rewriting tones:"]
        for tone, d in desc.items():
            lines.append(f"  {tone} — {d}")
        return "\n".join(lines)
