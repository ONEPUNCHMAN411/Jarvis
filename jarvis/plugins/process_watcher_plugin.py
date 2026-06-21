import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class ProcessWatcherPlugin(Plugin):
    def __init__(self):
        super().__init__("process_watcher")

    async def initialize(self):
        from jarvis.brain.process_watcher import get_process_watcher
        get_process_watcher().start()
        logger.info("ProcessWatcherPlugin ready")

    async def shutdown(self):
        from jarvis.brain.process_watcher import get_process_watcher
        get_process_watcher().stop()

    def get_tools(self):
        return [
            (ToolDefinition(
                name="watch_process",
                description=(
                    "Start watching a process for CPU or RAM spikes. Fires a toast + Intel Feed "
                    "alert when the threshold is exceeded. "
                    "Use when user says 'alert me if Chrome uses more than 80% CPU', "
                    "'notify me when node.exe exceeds 2000 MB RAM', "
                    "'watch python for CPU spikes above 90%'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "process_name": {"type": "string", "description": "Process exe name, e.g. 'chrome.exe'"},
                        "metric": {"type": "string", "enum": ["cpu", "ram"]},
                        "threshold": {"type": "number", "description": "% for cpu, MB for ram"},
                        "cooldown_s": {"type": "integer", "default": 60, "description": "Seconds between repeated alerts"},
                    },
                    "required": ["process_name", "metric", "threshold"],
                },
            ), self.watch),
            (ToolDefinition(
                name="list_process_watches",
                description="List all active process spike watches.",
                parameters={"type": "object", "properties": {}},
            ), self.list_watches),
            (ToolDefinition(
                name="remove_process_watch",
                description="Remove a process watch by its ID or process name.",
                parameters={
                    "type": "object",
                    "properties": {"key": {"type": "string", "description": "Watch ID or process name"}},
                    "required": ["key"],
                },
            ), self.remove_watch),
        ]


    async def watch(self, process_name: str, metric: str, threshold: float, cooldown_s: int = 60) -> str:
        from jarvis.brain.process_watcher import get_process_watcher
        wid = await self._run(get_process_watcher().add, process_name, metric, threshold, cooldown_s)
        unit = "%" if metric == "cpu" else " MB"
        return f"Watching '{process_name}' — will alert when {metric.upper()} ≥ {threshold}{unit}. Watch ID: {wid}"

    async def list_watches(self, **_) -> str:
        from jarvis.brain.process_watcher import get_process_watcher
        watches = get_process_watcher().list_all()
        if not watches:
            return "No active process watches."
        lines = ["Active process watches:"]
        for w in watches:
            unit = "%" if w.metric == "cpu" else " MB"
            lines.append(f"  [{w.id}] {w.process_name}  {w.metric.upper()} ≥ {w.threshold}{unit}  cooldown {w.cooldown_s}s")
        return "\n".join(lines)

    async def remove_watch(self, key: str) -> str:
        from jarvis.brain.process_watcher import get_process_watcher
        ok = await self._run(get_process_watcher().remove, key)
        return f"Removed watch '{key}'." if ok else f"No watch matching '{key}'."
