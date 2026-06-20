
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class WorkspacePlugin(Plugin):
    """Save and restore window layouts — snapshot where your app windows are,
    then snap them all back later ('set up my coding workspace')."""

    def __init__(self):
        super().__init__("workspace")
        self._mgr = None

    def _get(self):
        if self._mgr is None:
            from jarvis.control.workspace import get_workspace_manager
            self._mgr = get_workspace_manager()
        return self._mgr

    async def initialize(self) -> None:
        logger.info("WorkspacePlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="save_workspace",
                    description=(
                        "Save the current arrangement of all open windows under a "
                        "name. Use when the user says 'save this layout', 'remember "
                        "my workspace', 'save my coding setup as <name>'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Name for this layout"}
                        },
                        "required": ["name"],
                    },
                ),
                self.save_workspace,
            ),
            (
                ToolDefinition(
                    name="restore_workspace",
                    description=(
                        "Restore a saved window layout — move and resize windows back "
                        "to their saved positions. Use when the user says 'set up my "
                        "coding workspace', 'restore my <name> layout'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Saved layout name"}
                        },
                        "required": ["name"],
                    },
                ),
                self.restore_workspace,
            ),
            (
                ToolDefinition(
                    name="list_workspaces",
                    description="List saved window layouts and how many windows each has.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_workspaces,
            ),
            (
                ToolDefinition(
                    name="delete_workspace",
                    description="Delete a saved window layout by name.",
                    parameters={
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                ),
                self.delete_workspace,
            ),
        ]

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    async def save_workspace(self, name: str) -> str:
        res = await self._run(self._get().save_layout, name)
        if not res.get("ok"):
            return res.get("error", "Could not save workspace.")
        return f"Saved workspace '{name}' with {res['count']} window(s)."

    async def restore_workspace(self, name: str) -> str:
        res = await self._run(self._get().restore_layout, name)
        if not res.get("ok"):
            return res.get("error", "Could not restore workspace.")
        return f"Restored '{name}': repositioned {res['restored']} of {res['total']} window(s)."

    async def list_workspaces(self, **_) -> str:
        layouts = await self._run(self._get().list_layouts)
        if not layouts:
            return "No saved workspaces yet."
        lines = ["Saved workspaces:"]
        for name, count in layouts.items():
            lines.append(f"  • {name}  ({count} windows)")
        return "\n".join(lines)

    async def delete_workspace(self, name: str) -> str:
        ok = await self._run(self._get().delete_layout, name)
        return f"Deleted workspace '{name}'." if ok else f"No workspace named '{name}'."
