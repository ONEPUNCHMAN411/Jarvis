import asyncio
import aiosqlite
import hashlib
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from loguru import logger
from jarvis.models import Message
from jarvis.brain.groq_provider import _model_caps as _groq_caps

# Try to load tiktoken for accurate token counts; fall back to char estimate
try:
    import tiktoken as _tiktoken
    _TK_ENC = _tiktoken.get_encoding("cl100k_base")
except Exception:
    _TK_ENC = None

class ConversationMemory:
    def __init__(self, db_path: str, max_messages: int = 40):
        self.db_path = Path(db_path)
        self.max_messages = max_messages
        self._messages: list[Message] = []
        self._lock = asyncio.Lock()
        self._tool_cache: dict[str, tuple[str, float]] = {}
        self._cache_ttl = 60.0
        self._summary: str = ""
        self._ai_client = None
        # Active session — changes when user starts a new chat
        self._session_id: str = self._new_session_id()
        self._session_title: str = ""   # set from first user message

    def set_ai_client(self, client) -> None:
        """Inject an AsyncAnthropic client so summarization can use Haiku."""
        self._ai_client = client
        logger.debug("ConversationMemory: AI client set for Haiku summarization")

    @staticmethod
    def _new_session_id() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]

    @property
    def session_id(self) -> str:
        return self._session_id

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    is_summary INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    message_count INTEGER DEFAULT 0
                )
                """
            )
            # Schema migrations for older DBs
            for col_sql in [
                "ALTER TABLE messages ADD COLUMN is_summary INTEGER DEFAULT 0",
            ]:
                try:
                    await db.execute(col_sql)
                    await db.commit()
                except Exception:
                    pass
            await db.commit()
        logger.info(f"Memory database initialized at {self.db_path}")

    def add_message(self, role: str, content: str) -> None:
        msg = Message(role=role, content=content)
        self._messages.append(msg)
        if role == "user" and not self._session_title:
            self._session_title = content[:80].replace("\n", " ")
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages :]

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count, using tiktoken when available."""
        if _TK_ENC is not None:
            try:
                return max(1, len(_TK_ENC.encode(text, disallowed_special=())))
            except Exception:
                pass
        # Fallback: approximately 4 characters per token
        return max(1, len(text) // 4)

    def get_context(self, max_tokens: int = 8000) -> list[Message]:
        total_tokens = 0
        context = []

        for msg in reversed(self._messages):
            content = msg.content or ""
            msg_tokens = self._estimate_tokens(content)
            if msg.tool_calls:
                msg_tokens += 200
            if msg.image_paths:
                msg_tokens += 500 * len(msg.image_paths)
            if total_tokens + msg_tokens > max_tokens:
                break
            context.append(msg)
            total_tokens += msg_tokens

        context.reverse()
        return context

    def get_context_for_provider(self, provider: str, model: str = "") -> list[Message]:
        token_budget = 8_000
        if provider == "groq":
            caps = _groq_caps(model)
            # Reserve ~25% for system prompt + response; use 75% for history
            token_budget = int(caps["ctx"] * 0.65)
        elif provider in ("claude", "openai", "gemini"):
            token_budget = 60_000
        elif provider == "mistral":
            token_budget = 20_000
        elif provider == "ollama":
            token_budget = 6_000
        elif provider == "llamacpp":
            token_budget = 24_000
        return self.get_context(max_tokens=token_budget)

    # Key-fact extraction patterns for extractive summarisation
    _FACT_PATTERNS: list[re.Pattern] = [
        re.compile(r"\b(write|implement|fix|change|create|build|add|remove|refactor)\s+(.{5,80})", re.I),
        re.compile(r"\bthe answer is\b(.{0,100})", re.I),
        re.compile(r"\bconfirmed?\b(.{0,80})", re.I),
        re.compile(r"\bdecided?\b(.{0,80})", re.I),
        re.compile(r"\busing\s+([\w\s]+?)\s+(?:for|to|as)\b(.{0,60})", re.I),
    ]

    def _extract_key_facts(self, content: str) -> list[str]:
        """Pull action/decision facts from a message with simple regex."""
        facts: list[str] = []
        for pat in self._FACT_PATTERNS:
            for m in pat.finditer(content):
                snippet = m.group(0).strip()
                if len(snippet) > 10:
                    facts.append(snippet[:120])
        return facts

    def compress_old_messages(self, summary_threshold: int = 40, keep_recent: int = 15) -> None:
        """
        When message count exceeds *summary_threshold*, summarise all but the
        most recent *keep_recent* messages into ``self._summary`` and remove
        the summarised messages from ``self._messages``.

        The summary uses extractive key-fact detection — no AI call required.
        """
        if len(self._messages) <= summary_threshold:
            return

        old_messages = self._messages[:-keep_recent]
        recent_messages = self._messages[-keep_recent:]

        lines: list[str] = ["[Conversation summary — earlier context]"]
        prev_user: str = ""
        for msg in old_messages:
            content = (msg.content or "").strip()
            if not content:
                continue
            if msg.role == "user":
                prev_user = content[:200]
                lines.append(f"User: {prev_user}")
            elif msg.role == "assistant":
                facts = self._extract_key_facts(content)
                if facts:
                    for f in facts[:3]:
                        lines.append(f"  • {f}")
                else:
                    # Fallback: first 150 chars of the reply
                    lines.append(f"  JARVIS: {content[:150]}")
                prev_user = ""

        self._summary = "\n".join(lines)
        self._messages = recent_messages
        logger.info(
            f"Compressed {len(old_messages)} old messages into summary "
            f"({len(self._summary)} chars); keeping {len(recent_messages)} recent."
        )

    def get_context_with_summary(
        self,
        max_tokens: int = 8000,
        summary_threshold: int = 40,
    ) -> list[Message]:
        """
        Like ``get_context()``, but when there are more than
        *summary_threshold* messages it first calls
        ``compress_old_messages()`` and prepends the running summary as a
        synthetic ``system`` message so the model has background context
        without burning the full token budget.
        """
        self.compress_old_messages(summary_threshold=summary_threshold)

        context = self.get_context(max_tokens=max_tokens)

        if self._summary:
            summary_msg = Message(role="system", content=self._summary)
            context = [summary_msg] + context

        return context

    def get_all_messages(self) -> list[Message]:
        return self._messages.copy()

    async def summarize_and_compress(self, keep_recent: int = 10) -> str:
        """Compress old messages into a summary using Haiku when available.

        Keeps the last *keep_recent* messages verbatim.
        Returns the summary text; updates self._messages in place.
        Used when the context window is getting full.
        """
        if len(self._messages) <= keep_recent:
            return ""

        old_messages = self._messages[:-keep_recent]

        # Build a plain-text transcript to feed to the summarizer
        transcript_lines: list[str] = []
        for msg in old_messages:
            content = (msg.content or "").strip()
            if not content:
                continue
            if len(content) > 600:
                content = content[:600] + "…"
            label = "User" if msg.role == "user" else "JARVIS"
            transcript_lines.append(f"{label}: {content}")
        transcript = "\n".join(transcript_lines)

        # Try AI summarization first
        if self._ai_client and transcript:
            from jarvis.brain.ai_summarizer import summarize_conversation
            ai_summary = await summarize_conversation(transcript, client=self._ai_client)
            if ai_summary:
                self._messages = self._messages[-keep_recent:]
                logger.info(
                    f"AI-compressed {len(old_messages)} messages into summary "
                    f"({len(ai_summary)} chars); keeping {keep_recent} recent."
                )
                return ai_summary

        # Fallback: simple extractive summary
        summary_lines = ["Earlier conversation summary:"]
        current_topic: str | None = None
        for msg in old_messages:
            content = (msg.content or "").strip()
            if not content:
                continue
            if len(content) > 500:
                content = content[:500] + "..."
            if msg.role == "user":
                summary_lines.append(f"- User asked: {content}")
                current_topic = content
            elif msg.role == "assistant":
                if current_topic:
                    summary_lines.append(f"  JARVIS responded: {content}")
                    current_topic = None

        return "\n".join(summary_lines)

    def _tool_cache_key(self, tool_name: str, args: dict) -> str:
        """Generate a cache key for a tool call."""
        args_str = ";".join(f"{k}={v}" for k, v in sorted(args.items()))
        cache_input = f"{tool_name}:{args_str}"
        return hashlib.md5(cache_input.encode(), usedforsecurity=False).hexdigest()

    def get_cached_tool_result(self, tool_name: str, args: dict) -> str | None:
        """Get a cached tool result if available and not expired."""
        # Skip caching for time-sensitive tools
        if tool_name in ("take_screenshot", "run_shell_command", "get_current_time"):
            return None

        key = self._tool_cache_key(tool_name, args)
        if key in self._tool_cache:
            result, timestamp = self._tool_cache[key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Cache hit for tool: {tool_name}")
                return result
            else:
                # Expired, remove it
                del self._tool_cache[key]
        return None

    def cache_tool_result(self, tool_name: str, args: dict, result: str) -> None:
        """Cache a tool result with timestamp."""
        # Skip caching for time-sensitive tools
        if tool_name in ("take_screenshot", "run_shell_command", "get_current_time"):
            return

        key = self._tool_cache_key(tool_name, args)
        self._tool_cache[key] = (result, time.time())

        # Limit cache size to 20 entries
        if len(self._tool_cache) > 20:
            # Remove oldest entry
            oldest_key = min(self._tool_cache.keys(),
                           key=lambda k: self._tool_cache[k][1])
            del self._tool_cache[oldest_key]

    async def save_to_db(self, session_id: str | None = None) -> None:
        sid = session_id or self._session_id
        if not self._messages:
            return
        title = self._session_title or (self._messages[0].content[:80] if self._messages else "")
        async with self._lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                for msg in self._messages:
                    is_summary = 1 if hasattr(msg, "is_summary") and msg.is_summary else 0
                    await db.execute(
                        "INSERT INTO messages (session_id, role, content, is_summary, timestamp) VALUES (?, ?, ?, ?, ?)",
                        (sid, msg.role, msg.content, is_summary, msg.timestamp),
                    )
                await db.execute(
                    """
                    INSERT INTO sessions (session_id, title, message_count, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(session_id) DO UPDATE SET
                        title = excluded.title,
                        message_count = excluded.message_count,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (sid, title, len(self._messages)),
                )
                await db.commit()
        logger.debug(f"Saved {len(self._messages)} messages to session {sid}")

    async def load_from_db(self, session_id: str | None = None) -> None:
        sid = session_id or self._session_id
        async with self._lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                cursor = await db.execute(
                    "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                    (sid, self.max_messages),
                )
                rows = await cursor.fetchall()
                self._messages = [Message(role=r[0], content=r[1]) for r in rows]
                # Load title
                cur2 = await db.execute("SELECT title FROM sessions WHERE session_id = ?", (sid,))
                row = await cur2.fetchone()
                self._session_title = row[0] if row else ""
        if session_id:
            self._session_id = session_id
        logger.debug(f"Loaded {len(self._messages)} messages from session {sid}")

    async def new_session(self) -> str:
        """Save current session and start a fresh one. Returns new session_id."""
        await self.save_to_db()
        self._session_id = self._new_session_id()
        self._session_title = ""
        self._messages = []
        self._summary = ""
        self._tool_cache.clear()
        logger.info(f"New chat session: {self._session_id}")
        return self._session_id

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        """Return sessions ordered by most recent first."""
        async with aiosqlite.connect(str(self.db_path)) as db:
            cursor = await db.execute(
                """
                SELECT session_id, title, created_at, updated_at, message_count
                FROM sessions
                WHERE message_count > 0
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
        return [
            {
                "session_id": r[0],
                "title": r[1] or "(untitled)",
                "created_at": r[2],
                "updated_at": r[3],
                "message_count": r[4],
            }
            for r in rows
        ]

    async def search_sessions(self, query: str, limit: int = 10) -> list[dict]:
        """Full-text search across all message content."""
        async with aiosqlite.connect(str(self.db_path)) as db:
            cursor = await db.execute(
                """
                SELECT DISTINCT m.session_id, s.title, s.updated_at,
                    substr(m.content, 1, 200) as snippet
                FROM messages m
                LEFT JOIN sessions s ON m.session_id = s.session_id
                WHERE m.content LIKE ? AND m.role != 'system'
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (f"%{query}%", limit),
            )
            rows = await cursor.fetchall()
        return [
            {
                "session_id": r[0],
                "title": r[1] or "(untitled)",
                "updated_at": r[2],
                "snippet": r[3],
            }
            for r in rows
        ]

    async def get_session_messages(self, session_id: str) -> list[dict]:
        """Return all messages for a given session."""
        async with aiosqlite.connect(str(self.db_path)) as db:
            cursor = await db.execute(
                "SELECT role, content, timestamp FROM messages WHERE session_id = ? AND is_summary = 0 ORDER BY timestamp ASC",
                (session_id,),
            )
            rows = await cursor.fetchall()
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]

    def clear(self) -> None:
        self._messages = []
        self._tool_cache.clear()
        self._summary = ""
        logger.debug("Conversation memory cleared")
