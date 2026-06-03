"""AI-powered conversation summarizer — extracts summary, action items, and key facts."""


import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger


@dataclass
class ConversationSummary:
    summary: str
    action_items: list[str]
    key_facts: list[str]
    message_count: int
    generated_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    def format(self) -> str:
        lines = [
            f"## Conversation Summary ({self.generated_at})",
            f"*{self.message_count} messages*\n",
            self.summary,
        ]
        if self.action_items:
            lines.append("\n### Action Items")
            for item in self.action_items:
                lines.append(f"- [ ] {item}")
        if self.key_facts:
            lines.append("\n### Key Facts")
            for fact in self.key_facts:
                lines.append(f"- {fact}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "action_items": self.action_items,
            "key_facts": self.key_facts,
            "message_count": self.message_count,
            "generated_at": self.generated_at,
        }


_SYSTEM_PROMPT = """You are a concise conversation analyst.
Given a conversation transcript, return a JSON object with exactly these keys:
  "summary"      : 2-4 sentence plain-English overview of what was discussed
  "action_items" : list of concrete tasks or follow-ups (empty list if none)
  "key_facts"    : list of important facts, decisions, or numbers mentioned

Return ONLY the JSON object. No markdown fences, no extra commentary."""


def _format_transcript(messages: list[Any]) -> str:
    parts = []
    for m in messages:
        role = getattr(m, "role", "unknown").upper()
        content = (getattr(m, "content", "") or "").strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


def _parse_json_response(text: str) -> dict:
    text = re.sub(r"^```[a-z]*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


async def summarize_conversation(
    messages: list[Any],
    provider: Any,
    max_messages: int = 40,
) -> ConversationSummary:
    """Summarize a list of Message objects using the given LLM provider.

    Trims to the most recent max_messages to stay within token budgets.
    """
    from jarvis.models import Message

    tail = messages[-max_messages:] if len(messages) > max_messages else messages
    transcript = _format_transcript(tail)

    if not transcript.strip():
        return ConversationSummary(
            summary="No conversation content to summarize.",
            action_items=[],
            key_facts=[],
            message_count=0,
        )

    prompt = Message(
        role="user",
        content=f"Summarize this conversation:\n\n{transcript}",
    )

    try:
        response = await asyncio.wait_for(
            provider.chat(
                [prompt],
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.2,
            ),
            timeout=60,
        )
    except asyncio.TimeoutError:
        logger.warning("summarize_conversation: provider timed out after 60s")
        return ConversationSummary(
            summary="Summary timed out — provider took too long.",
            action_items=[],
            key_facts=[],
            message_count=len(tail),
        )

    raw = (response.text or "").strip()
    try:
        data = _parse_json_response(raw)
    except Exception:
        logger.warning("summarize_conversation: could not parse JSON response")
        return ConversationSummary(
            summary=raw[:600] if raw else "Summary unavailable.",
            action_items=[],
            key_facts=[],
            message_count=len(tail),
        )

    return ConversationSummary(
        summary=data.get("summary", ""),
        action_items=[str(x) for x in data.get("action_items", [])],
        key_facts=[str(x) for x in data.get("key_facts", [])],
        message_count=len(tail),
    )


async def auto_summarize_if_long(
    messages: list[Any],
    provider: Any,
    threshold: int = 30,
) -> ConversationSummary | None:
    """Return a summary only when the conversation exceeds the threshold length.

    Returns None for short conversations so callers skip summary overhead.
    """
    if len(messages) < threshold:
        return None
    return await summarize_conversation(messages, provider)
