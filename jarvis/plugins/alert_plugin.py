
import uuid

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class AlertPlugin(Plugin):
    """Smart alerts: time-based, file-watching, and interval reminders."""

    def __init__(self):
        super().__init__("alerts")
        self._engine = None

    def _get(self):
        if self._engine is None:
            from jarvis.brain.alert_engine import get_alert_engine
            self._engine = get_alert_engine()
        return self._engine

    async def initialize(self) -> None:
        try:
            eng = self._get()
            eng.start()
            logger.info("AlertPlugin ready")
        except Exception as e:
            logger.error(f"AlertPlugin init error: {e}")

    async def shutdown(self) -> None:
        if self._engine:
            self._engine.stop()

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="set_time_alert",
                    description=(
                        "Set a desktop notification alert to fire at a specific date and time. "
                        "Use when the user says things like 'remind me at 3pm', "
                        "'alert me tomorrow at 9am', 'notify me on June 15 at noon'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "What to display in the notification",
                            },
                            "datetime": {
                                "type": "string",
                                "description": "ISO 8601 datetime, e.g. '2025-06-15T09:00:00'",
                            },
                            "repeat": {
                                "type": "boolean",
                                "description": "Fire every day at that time (default false)",
                            },
                        },
                        "required": ["label", "datetime"],
                    },
                ),
                self.set_time_alert,
            ),
            (
                ToolDefinition(
                    name="set_file_alert",
                    description=(
                        "Watch a file or folder and notify when it appears (file_exists) "
                        "or when its contents change (file_changed). "
                        "Use for 'tell me when the build finishes', 'notify me when report.pdf appears'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Notification message to display",
                            },
                            "path": {
                                "type": "string",
                                "description": "Absolute path to the file or directory to watch",
                            },
                            "watch_type": {
                                "type": "string",
                                "description": "'file_exists' or 'file_changed'",
                            },
                        },
                        "required": ["label", "path", "watch_type"],
                    },
                ),
                self.set_file_alert,
            ),
            (
                ToolDefinition(
                    name="set_interval_alert",
                    description=(
                        "Set a repeating reminder that fires every N minutes/hours. "
                        "Use for 'remind me to drink water every hour', 'ping me every 30 minutes'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Notification message",
                            },
                            "minutes": {
                                "type": "number",
                                "description": "Interval in minutes",
                            },
                        },
                        "required": ["label", "minutes"],
                    },
                ),
                self.set_interval_alert,
            ),
            (
                ToolDefinition(
                    name="list_alerts",
                    description="List all active alerts and reminders.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_alerts,
            ),
            (
                ToolDefinition(
                    name="remove_alert",
                    description="Remove/cancel an alert by its ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "alert_id": {
                                "type": "string",
                                "description": "Alert ID from list_alerts",
                            }
                        },
                        "required": ["alert_id"],
                    },
                ),
                self.remove_alert,
            ),
        ]

    async def set_time_alert(
        self, label: str, datetime: str, repeat: bool = False
    ) -> str:
        from jarvis.brain.alert_engine import Alert
        alert = Alert(
            id=uuid.uuid4().hex[:8],
            kind="time",
            label=label,
            params={"datetime": datetime},
            repeat=repeat,
        )
        self._get().add_alert(alert)
        rep = " (repeating daily)" if repeat else ""
        return f"Time alert set{rep}: '{label}' at {datetime}  [ID: {alert.id}]"

    async def set_file_alert(
        self, label: str, path: str, watch_type: str = "file_changed"
    ) -> str:
        from jarvis.brain.alert_engine import Alert
        if watch_type not in ("file_exists", "file_changed"):
            watch_type = "file_changed"
        alert = Alert(
            id=uuid.uuid4().hex[:8],
            kind=watch_type,
            label=label,
            params={"path": path},
            repeat=(watch_type == "file_changed"),
        )
        self._get().add_alert(alert)
        return f"File alert set ({watch_type}): '{label}' watching {path}  [ID: {alert.id}]"

    async def set_interval_alert(self, label: str, minutes: float) -> str:
        from jarvis.brain.alert_engine import Alert
        seconds = minutes * 60
        alert = Alert(
            id=uuid.uuid4().hex[:8],
            kind="interval",
            label=label,
            params={"seconds": seconds},
            repeat=True,
        )
        self._get().add_alert(alert)
        return f"Interval alert set: '{label}' every {minutes:.0f} min  [ID: {alert.id}]"

    async def list_alerts(self) -> str:
        alerts = self._get().list_alerts()
        if not alerts:
            return "No active alerts."
        kind_icon = {
            "time": "🕐",
            "file_exists": "📁",
            "file_changed": "📝",
            "interval": "🔁",
        }
        lines = ["Active alerts:"]
        for a in alerts:
            icon = kind_icon.get(a.kind, "🔔")
            rep = " [repeat]" if a.repeat else ""
            lines.append(f"  {icon} [{a.id}] {a.label}  ({a.kind}){rep}")
            if a.kind == "time":
                lines.append(f"       at {a.params.get('datetime', '?')}")
            elif a.kind in ("file_exists", "file_changed"):
                lines.append(f"       path: {a.params.get('path', '?')}")
            elif a.kind == "interval":
                mins = a.params.get("seconds", 0) / 60
                lines.append(f"       every {mins:.0f} min")
        return "\n".join(lines)

    async def remove_alert(self, alert_id: str) -> str:
        if self._get().remove_alert(alert_id):
            return f"Alert {alert_id} removed."
        return f"No alert found with ID '{alert_id}'."
