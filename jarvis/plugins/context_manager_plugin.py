import asyncio
import json
import threading
from pathlib import Path
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

_STATS_PATH = Path.home() / ".jarvis" / "context_stats.json"


class ContextManagerPlugin(Plugin):
    """Track estimated token usage across the conversation. When context grows large,
    auto-compact by summarising old messages into a compact digest."""

    def __init__(self):
        super().__init__("context_manager")
        self._char_total = 0
        self._msg_count = 0
        self._lock = threading.Lock()
        self._compact_threshold = 0.70
        self._model_limit = 200_000

    async def initialize(self):
        self._load_stats()
        logger.info("ContextManagerPlugin ready")

    async def shutdown(self):
        self._save_stats()

    def _load_stats(self):
        if _STATS_PATH.exists():
            try:
                data = json.loads(_STATS_PATH.read_text("utf-8"))
                self._model_limit = data.get("model_limit", 200_000)
                self._compact_threshold = data.get("compact_threshold", 0.70)
            except Exception:
                pass

    def _save_stats(self):
        _STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATS_PATH.write_text(json.dumps({
            "model_limit": self._model_limit,
            "compact_threshold": self._compact_threshold,
        }, indent=2), "utf-8")

    def track(self, char_count: int):
        with self._lock:
            self._char_total += char_count
            self._msg_count += 1

    def _estimate_tokens(self) -> int:
        return int(self._char_total / 4)

    def _usage_pct(self) -> float:
        return min(1.0, self._estimate_tokens() / max(1, self._model_limit))

    def get_tools(self):
        return [
            (ToolDefinition(
                name="get_context_stats",
                description=(
                    "Show estimated token usage for the current conversation and how full the context window is. "
                    "Use when user asks 'how full is your context?', 'how much context is left?', "
                    "'are you running out of memory?'."
                ),
                parameters={"type": "object", "properties": {}},
            ), self.get_stats),
            (ToolDefinition(
                name="compact_context",
                description=(
                    "Produce a compact summary of the conversation so far to free context space. "
                    "Returns a digest you should treat as the new conversation memory. "
                    "Use when user says 'compact the context', 'summarise what we've discussed', "
                    "'free up context space', or when context is above 70% full."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "keep_last_n": {
                            "type": "integer",
                            "default": 5,
                            "description": "Keep the N most recent exchanges verbatim; summarise everything before them.",
                        },
                    },
                },
            ), self.compact_context),
            (ToolDefinition(
                name="set_context_limit",
                description="Configure the model context limit and auto-compact threshold.",
                parameters={
                    "type": "object",
                    "properties": {
                        "model_limit_tokens": {
                            "type": "integer",
                            "description": "Total token limit of the active model (e.g. 200000 for Claude)",
                        },
                        "compact_threshold_pct": {
                            "type": "number",
                            "description": "Auto-compact when usage exceeds this fraction (0.0-1.0, default 0.70)",
                        },
                    },
                },
            ), self.set_limit),
        ]


    async def get_stats(self, **_) -> str:
        tokens = self._estimate_tokens()
        pct = self._usage_pct() * 100
        bar_filled = int(pct / 5)
        bar = "[" + "#" * bar_filled + "-" * (20 - bar_filled) + "]"
        status = "OK" if pct < 60 else ("GETTING FULL" if pct < 80 else "NEAR LIMIT — consider compacting")
        return (
            f"Context usage: {bar} {pct:.1f}%\n"
            f"Estimated tokens used: ~{tokens:,}\n"
            f"Model limit: {self._model_limit:,} tokens\n"
            f"Status: {status}\n"
            f"Auto-compact threshold: {self._compact_threshold * 100:.0f}%\n\n"
            "Note: Token estimate is approximate (chars/4). Use compact_context to free space."
        )

    async def compact_context(self, keep_last_n: int = 5, **_) -> str:
        return (
            f"Compact the conversation context now. Keep the last {keep_last_n} exchanges "
            "verbatim and summarise everything before them into a compact digest.\n\n"
            "Format your compact digest as:\n"
            "## CONTEXT DIGEST\n"
            "**Session goal:** one sentence\n"
            "**Key decisions:** bullet list\n"
            "**Important facts established:** bullet list\n"
            "**Files / tools used:** bullet list\n"
            "**Current state:** one paragraph\n\n"
            "After producing the digest, treat it as your conversation memory going forward "
            "and discard the earlier message history."
        )

    async def set_limit(self, model_limit_tokens: int = None, compact_threshold_pct: float = None, **_) -> str:
        if model_limit_tokens:
            self._model_limit = model_limit_tokens
        if compact_threshold_pct is not None:
            self._compact_threshold = max(0.1, min(1.0, compact_threshold_pct))
        self._save_stats()
        return f"Context settings updated: limit={self._model_limit:,} tokens, compact threshold={self._compact_threshold*100:.0f}%"
