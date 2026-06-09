
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class MemoryPlugin(Plugin):
    """Remember/recall/forget facts in long-term memory."""

    def __init__(self):
        super().__init__("memory")
        self._ltm = None

    def _store(self):
        if self._ltm is None:
            from jarvis.brain.long_term_memory import get_long_term_memory
            self._ltm = get_long_term_memory()
        return self._ltm

    async def initialize(self) -> None:
        try:
            self._store()
            logger.info(f"MemoryPlugin ready ({self._ltm.count()} memories stored)")
        except ImportError as e:
            self.enabled = False
            logger.warning(f"MemoryPlugin disabled: {e}")

    async def shutdown(self) -> None:
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="remember",
                    description=(
                        "Store a fact or piece of information in long-term memory "
                        "so it can be recalled in future conversations."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The information to remember",
                            },
                            "category": {
                                "type": "string",
                                "description": "Optional category tag (e.g. 'preference', 'fact', 'task')",
                            },
                        },
                        "required": ["text"],
                    },
                ),
                self.remember,
            ),
            (
                ToolDefinition(
                    name="recall",
                    description="Search long-term memory for stored facts related to a query.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "What to search for in memory",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of results to return (default 5)",
                            },
                        },
                        "required": ["query"],
                    },
                ),
                self.recall,
            ),
            (
                ToolDefinition(
                    name="forget",
                    description="Delete a specific memory by its ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "memory_id": {
                                "type": "string",
                                "description": "The memory ID to delete (from recall results)",
                            },
                        },
                        "required": ["memory_id"],
                    },
                ),
                self.forget,
            ),
            (
                ToolDefinition(
                    name="list_memories",
                    description="List all stored long-term memories.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_memories,
            ),
        ]

    async def remember(self, text: str, category: str | None = None) -> str:
        meta = {"category": category} if category else {}
        mid = self._store().add(text, metadata=meta)
        return f"Remembered (id: {mid[:8]}): {text[:80]}"

    async def recall(self, query: str, top_k: int = 5) -> str:
        results = self._store().search(query, top_k=top_k)
        if not results:
            return f"No memories found related to '{query}'."
        lines = [f"Found {len(results)} relevant memories:"]
        for r in results:
            lines.append(f"  [{r['score']:.2f}] {r['text']}")
        return "\n".join(lines)

    async def forget(self, memory_id: str) -> str:
        ok = self._store().delete(memory_id)
        if ok:
            return f"Memory {memory_id[:8]} deleted."
        return f"Memory '{memory_id}' not found."

    async def list_memories(self) -> str:
        memories = self._store().list_all()
        if not memories:
            return "No memories stored yet."
        lines = [f"Total memories: {len(memories)}"]
        for m in memories:
            created = m["metadata"].get("created", "")[:10]
            cat = m["metadata"].get("category", "")
            tag = f" [{cat}]" if cat else ""
            lines.append(f"  {m['id'][:8]}{tag} ({created}): {m['text'][:80]}")
        return "\n".join(lines)
