import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class ConfidencePlugin(Plugin):
    """Ask JARVIS to self-assess its confidence in a claim or answer and display
    a certainty rating with reasoning. Works without logprobs."""

    def __init__(self):
        super().__init__("confidence")

    async def initialize(self):
        logger.info("ConfidencePlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="assess_confidence",
                description=(
                    "Self-assess confidence in the most recent answer or a specific claim. "
                    "Returns a structured certainty rating (High / Medium / Low / Uncertain) with reasons. "
                    "Use when user asks 'how confident are you?', 'are you sure about that?', "
                    "'what's your certainty?', 'how reliable is this answer?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "claim": {
                            "type": "string",
                            "description": "The specific claim or answer to assess. Leave empty to assess the last response.",
                            "default": "",
                        },
                    },
                },
            ), self.assess),
            (ToolDefinition(
                name="explain_uncertainty",
                description=(
                    "Identify what you do NOT know about a topic and what caveats apply. "
                    "Use when user asks 'what don't you know about this?', 'what could be wrong here?', "
                    "'what are the limits of your answer?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "The topic or statement to examine"},
                    },
                    "required": ["topic"],
                },
            ), self.explain_uncertainty),
        ]


    async def assess(self, claim: str = "", **_) -> str:
        subject = f'the claim: "{claim}"' if claim else "your most recent answer"
        return (
            f"Self-assess your confidence in {subject}.\n\n"
            "Respond using this exact structure:\n"
            "**Confidence: [High / Medium / Low / Uncertain]**\n"
            "**Why:** 1-2 sentences explaining the rating\n"
            "**What I know well:** bullet list of solid facts\n"
            "**What I am less sure about:** bullet list of gaps or assumptions\n"
            "**Recommendation:** Should the user verify this? Where?"
        )

    async def explain_uncertainty(self, topic: str, **_) -> str:
        return (
            f"Examine what you do NOT know about: {topic}\n\n"
            "Structure your response as:\n"
            "**Known gaps:** things you are explicitly uncertain about\n"
            "**Potential errors:** ways this answer could be wrong\n"
            "**Knowledge cutoff impact:** whether recency matters here\n"
            "**Suggested verification:** specific sources or steps to confirm"
        )
