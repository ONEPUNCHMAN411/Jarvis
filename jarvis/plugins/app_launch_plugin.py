import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class AppLaunchPlugin(Plugin):
    """Save named app launch sequences ('work mode', 'gaming setup') and run
    them with one voice command — opens apps in order, then optionally restores
    a saved window layout."""

    def __init__(self):
        super().__init__("app_launch")

    async def initialize(self):
        logger.info("AppLaunchPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="save_launch_sequence",
                description=(
                    "Save a named launch sequence that opens multiple apps in order. "
                    "Use when user says 'save my work mode', 'create a gaming setup that opens Steam and Discord', "
                    "'remember this as my morning routine'. "
                    "Each app needs 'path' (exe path or 'start AppName' for Start-menu apps) "
                    "and optional 'delay_ms' between launches (default 800 ms)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "apps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "args": {"type": "array", "items": {"type": "string"}},
                                    "delay_ms": {"type": "integer"},
                                },
                                "required": ["path"],
                            },
                        },
                        "workspace": {"type": "string", "description": "Saved workspace to restore after launch (optional)"},
                    },
                    "required": ["name", "description", "apps"],
                },
            ), self.save_sequence),
            (ToolDefinition(
                name="run_launch_sequence",
                description=(
                    "Run a saved launch sequence by name. "
                    "Use when user says 'start work mode', 'launch gaming setup', 'run morning routine'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ), self.run_sequence),
            (ToolDefinition(
                name="list_launch_sequences",
                description="List all saved launch sequences.",
                parameters={"type": "object", "properties": {}},
            ), self.list_sequences),
            (ToolDefinition(
                name="delete_launch_sequence",
                description="Delete a saved launch sequence by name or ID.",
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ), self.delete_sequence),
        ]


    async def save_sequence(self, name: str, description: str, apps: list, workspace: str = None) -> str:
        from jarvis.brain.app_launch import get_app_launch_store
        seq = await self._run(get_app_launch_store().add, name, description, apps, workspace)
        ws = f" + workspace '{seq.workspace}'" if seq.workspace else ""
        return f"Saved launch sequence '{seq.name}' ({len(seq.apps)} apps{ws}). Say 'run {seq.name}' to launch."

    async def run_sequence(self, name: str) -> str:
        from jarvis.brain.app_launch import get_app_launch_store
        res = await self._run(get_app_launch_store().run, name)
        if not res["ok"]:
            return res["error"]
        parts = [f"Started {len(res['launched'])} app(s): {', '.join(res['launched'])}."]
        if res["errors"]:
            parts.append(f"Errors: {'; '.join(res['errors'])}")
        if res["workspace"]:
            await asyncio.sleep(2.5)
            try:
                from jarvis.control.workspace import get_workspace_manager
                r = await self._run(get_workspace_manager().restore_layout, res["workspace"])
                if r.get("ok"):
                    parts.append(f"Restored workspace '{res['workspace']}'.")
            except Exception as e:
                parts.append(f"(workspace restore skipped: {e})")
        return "  ".join(parts)

    async def list_sequences(self, **_) -> str:
        from jarvis.brain.app_launch import get_app_launch_store
        seqs = get_app_launch_store().list_all()
        if not seqs:
            return "No launch sequences saved yet. Say 'save a work mode that opens VSCode and Chrome' to create one."
        lines = ["Saved launch sequences:"]
        for s in seqs:
            ws = f"  +workspace '{s.workspace}'" if s.workspace else ""
            lines.append(f"  [{s.id}] {s.name} — {s.description} ({len(s.apps)} apps{ws})")
        return "\n".join(lines)

    async def delete_sequence(self, name: str) -> str:
        from jarvis.brain.app_launch import get_app_launch_store
        ok = await self._run(get_app_launch_store().delete, name)
        return f"Deleted '{name}'." if ok else f"No sequence named '{name}'."
