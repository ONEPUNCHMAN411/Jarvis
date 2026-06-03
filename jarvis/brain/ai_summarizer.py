"""Lightweight Claude Haiku utilities for internal JARVIS tasks.

Used for background work (conversation summarization, quick classification)
where latency matters and a fast, cheap model is appropriate.
"""

import os
from loguru import logger

_MODEL = "claude-haiku-4-5"
_SUMMARY_MAX_TOKENS = 600

async def summarize_conversation(messages_text: str, client=None) -> str:
    """Use Haiku to compress old conversation history into bullet points.

    Args:
        messages_text: Formatted conversation to summarize.
        client: Optional AsyncAnthropic instance. Falls back to
                ANTHROPIC_API_KEY env var if not provided.

    Returns:
        Summary string, or empty string on failure/no key.
    """
    from anthropic import AsyncAnthropic, APIStatusError

    if client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return ""
        client = AsyncAnthropic(api_key=key)

    try:
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=_SUMMARY_MAX_TOKENS,
            system=(
                "You are a concise conversation summarizer. "
                "Extract only decisions made, tasks completed, user preferences, and key facts. "
                "Output plain bullet points. No preamble, no headers, no filler."
            ),
            messages=[{
                "role": "user",
                "content": (
                    "Summarize this conversation (bullet points only — decisions, tasks, facts):\n\n"
                    + messages_text
                ),
            }],
        )
        text = response.content[0].text if response.content else ""
        logger.debug(f"AI summarizer produced {len(text)} chars")
        return text
    except APIStatusError as exc:
        logger.debug(f"Haiku summarization API error {exc.status_code}: {exc.message}")
        return ""
    except Exception as exc:
        logger.debug(f"Haiku summarization failed: {exc}")
        return ""
