
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


_PRIORITY_ICON = {"high": "🔴", "normal": "🟡", "low": "🟢"}


class TodoPlugin(Plugin):
    """To-do list with natural language task adding and priority support."""

    def __init__(self):
        super().__init__("todos")
        self._store = None

    def _get(self):
        if self._store is None:
            from jarvis.brain.todo_store import get_todo_store
            self._store = get_todo_store()
        return self._store

    async def initialize(self) -> None:
        self._get()
        logger.info("TodoPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="add_todo",
                    description=(
                        "Add an item to the to-do list. "
                        "ALWAYS use this when the user says things like: "
                        "'remind me to ...', 'I need to ...', 'add ... to my list', "
                        "'don't let me forget to ...', 'put ... on my to-do', "
                        "'I have to ...', 'make a note to ...'. "
                        "Supports priority (high/normal/low), optional due date, and tags."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The task description",
                            },
                            "priority": {
                                "type": "string",
                                "description": "'high', 'normal', or 'low' (default: normal)",
                            },
                            "due": {
                                "type": "string",
                                "description": "Optional due date as ISO string e.g. '2025-06-20'",
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of tags for categorization",
                            },
                        },
                        "required": ["text"],
                    },
                ),
                self.add_todo,
            ),
            (
                ToolDefinition(
                    name="list_todos",
                    description=(
                        "Show the current to-do list. "
                        "Use when user asks 'what's on my list?', 'show my tasks', "
                        "'what do I need to do?', 'my to-dos'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "show_done": {
                                "type": "boolean",
                                "description": "Include completed items (default false)",
                            },
                            "priority": {
                                "type": "string",
                                "description": "Filter by priority: 'high', 'normal', or 'low'",
                            },
                        },
                    },
                ),
                self.list_todos,
            ),
            (
                ToolDefinition(
                    name="complete_todo",
                    description=(
                        "Mark a to-do item as complete. "
                        "Use when user says 'done with ...', 'I finished ...', 'mark ... complete'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "todo_id": {
                                "type": "string",
                                "description": "ID of the todo from list_todos",
                            }
                        },
                        "required": ["todo_id"],
                    },
                ),
                self.complete_todo,
            ),
            (
                ToolDefinition(
                    name="remove_todo",
                    description="Permanently remove a to-do item by ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "todo_id": {
                                "type": "string",
                                "description": "ID of the todo to remove",
                            }
                        },
                        "required": ["todo_id"],
                    },
                ),
                self.remove_todo,
            ),
            (
                ToolDefinition(
                    name="search_todos",
                    description="Search to-do items by keyword or tag.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search term to match against task text or tags",
                            }
                        },
                        "required": ["query"],
                    },
                ),
                self.search_todos,
            ),
        ]

    def _fmt_todo(self, t) -> str:
        icon = _PRIORITY_ICON.get(t.priority, "🟡")
        done = "~~" if t.done else ""
        due = f"  📅 {t.due}" if t.due else ""
        tags = f"  🏷 {', '.join(t.tags)}" if t.tags else ""
        return f"  {icon} [{t.id}] {done}{t.text}{done}{due}{tags}"

    async def add_todo(
        self,
        text: str,
        priority: str = "normal",
        due: str = "",
        tags: list = None,
    ) -> str:
        t = self._get().add(text, priority=priority, due=due, tags=tags or [])
        icon = _PRIORITY_ICON.get(t.priority, "🟡")
        return f"Added to-do {icon}: '{t.text}'  [ID: {t.id}]"

    async def list_todos(
        self, show_done: bool = False, priority: str = ""
    ) -> str:
        items = self._get().list_todos(
            show_done=show_done,
            priority=priority or None,
        )
        if not items:
            if show_done:
                return "No to-do items found."
            return "Your to-do list is empty! Use add_todo to add tasks."
        header = "To-Do List:" if not priority else f"To-Do List ({priority} priority):"
        lines = [header]
        for t in items:
            lines.append(self._fmt_todo(t))
        total = len(items)
        done_count = sum(1 for t in items if t.done)
        if show_done:
            lines.append(f"\n{done_count}/{total} completed")
        return "\n".join(lines)

    async def complete_todo(self, todo_id: str) -> str:
        if self._get().complete(todo_id):
            t = self._get().get(todo_id)
            return f"✅ Marked complete: '{t.text if t else todo_id}'"
        return f"No todo found with ID '{todo_id}'."

    async def remove_todo(self, todo_id: str) -> str:
        if self._get().remove(todo_id):
            return f"Removed todo [{todo_id}]."
        return f"No todo found with ID '{todo_id}'."

    async def search_todos(self, query: str) -> str:
        results = self._get().search(query)
        if not results:
            return f"No todos matching '{query}'."
        lines = [f"Search results for '{query}':"]
        for t in results:
            lines.append(self._fmt_todo(t))
        return "\n".join(lines)
