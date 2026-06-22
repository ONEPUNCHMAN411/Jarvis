
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class RegionWatcherPlugin(Plugin):
    """Watch a rectangular screen area and get alerted when it changes, or when
    it stops changing (e.g. a download/render/progress bar finishing)."""

    def __init__(self):
        super().__init__("region_watcher")

    async def initialize(self) -> None:
        logger.info("RegionWatcherPlugin ready")

    async def shutdown(self) -> None:
        try:
            from jarvis.control.region_watcher import get_region_watcher
            get_region_watcher().remove(None)
        except Exception:
            pass

    def _mgr(self):
        from jarvis.control.region_watcher import get_region_watcher
        return get_region_watcher()

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="watch_screen_region",
                    description=(
                        "Watch a rectangular area of the screen and alert when it "
                        "changes, or when it settles after activity. Coordinates are "
                        "screen pixels (top-left x,y plus width,height). mode='change' "
                        "fires on the first change; mode='stable' fires when the area "
                        "stops changing (good for 'tell me when this download/render "
                        "finishes'). Take a screenshot first to find coordinates."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"}, "y": {"type": "integer"},
                            "width": {"type": "integer"}, "height": {"type": "integer"},
                            "label": {"type": "string", "description": "Friendly name for the alert"},
                            "mode": {"type": "string", "description": "'change' or 'stable' (default change)"},
                        },
                        "required": ["x", "y", "width", "height"],
                    },
                ),
                self.watch_screen_region,
            ),
            (
                ToolDefinition(
                    name="list_region_watches",
                    description="List the active screen-region watches.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_region_watches,
            ),
            (
                ToolDefinition(
                    name="stop_region_watch",
                    description="Stop a screen-region watch by id, or all of them if no id is given.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "watch_id": {"type": "integer", "description": "Optional id; omit to stop all"}
                        },
                    },
                ),
                self.stop_region_watch,
            ),
        ]

    async def watch_screen_region(self, x, y, width, height, label="", mode="change") -> str:
        wid = self._mgr().add(int(x), int(y), int(width), int(height), label=label, mode=mode)
        if wid < 0:
            return "Screen capture is unavailable (mss not installed)."
        kind = "stops changing" if mode == "stable" else "changes"
        return f"Watching '{label or f'region {wid}'}' (#{wid}); I'll alert you when it {kind}."

    async def list_region_watches(self, **_) -> str:
        watches = self._mgr().list_watches()
        if not watches:
            return "No active screen-region watches."
        lines = ["Active screen watches:"]
        for w in watches:
            b = w["bbox"]
            lines.append(f"  #{w['id']}  {w['label']}  [{w['mode']}]  "
                         f"({b['left']},{b['top']} {b['width']}x{b['height']})")
        return "\n".join(lines)

    async def stop_region_watch(self, watch_id: int | None = None) -> str:
        n = self._mgr().remove(int(watch_id) if watch_id is not None else None)
        if watch_id is not None:
            return f"Stopped watch #{watch_id}." if n else f"No watch #{watch_id}."
        return f"Stopped {n} watch(es)."
