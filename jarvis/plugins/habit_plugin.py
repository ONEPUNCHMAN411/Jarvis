
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class HabitPlugin(Plugin):
    """Habit tracker and time logger with streaks and weekly summaries."""

    def __init__(self):
        super().__init__("habits")
        self._store = None

    def _get(self):
        if self._store is None:
            from jarvis.brain.habit_store import get_habit_store
            self._store = get_habit_store()
        return self._store

    async def initialize(self) -> None:
        self._get()
        logger.info("HabitPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="add_habit",
                    description=(
                        "Create a new habit to track. Use when user says "
                        "'I want to track ...', 'help me build a habit of ...', "
                        "'I want to start ...', 'track my daily ...'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Habit name e.g. 'Meditate', 'Exercise', 'Read'",
                            },
                            "frequency": {
                                "type": "string",
                                "description": "'daily' or 'weekly' (default: daily)",
                            },
                            "unit": {
                                "type": "string",
                                "description": "Unit e.g. 'minutes', 'pages', 'times'",
                            },
                            "target": {
                                "type": "number",
                                "description": "Target amount per period (default: 1)",
                            },
                        },
                        "required": ["name"],
                    },
                ),
                self.add_habit,
            ),
            (
                ToolDefinition(
                    name="log_habit",
                    description=(
                        "Log that a habit was completed. Use when user says "
                        "'I meditated', 'done with my workout', 'I read today', "
                        "'mark [habit] as done', 'I completed ...'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "habit_id": {
                                "type": "string",
                                "description": "Habit ID from list_habits",
                            },
                            "value": {
                                "type": "number",
                                "description": "Amount completed (default: 1)",
                            },
                            "note": {
                                "type": "string",
                                "description": "Optional note about the session",
                            },
                        },
                        "required": ["habit_id"],
                    },
                ),
                self.log_habit,
            ),
            (
                ToolDefinition(
                    name="log_time",
                    description=(
                        "Log time spent on any activity. Use when user says "
                        "'I just spent 2 hours coding', 'log 30 minutes of reading', "
                        "'I worked on [project] for an hour'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "activity": {
                                "type": "string",
                                "description": "Activity name e.g. 'Coding', 'Reading'",
                            },
                            "minutes": {
                                "type": "number",
                                "description": "Time spent in minutes",
                            },
                            "note": {
                                "type": "string",
                                "description": "Optional note",
                            },
                        },
                        "required": ["activity", "minutes"],
                    },
                ),
                self.log_time,
            ),
            (
                ToolDefinition(
                    name="get_habit_summary",
                    description=(
                        "Show habit streaks, completions, and time breakdown. "
                        "Use when user says 'how am I doing?', 'show my habits', "
                        "'what is my streak?', 'how much time did I spend this week?'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "days": {
                                "type": "integer",
                                "description": "Look-back window in days (default 7)",
                            }
                        },
                    },
                ),
                self.get_summary,
            ),
            (
                ToolDefinition(
                    name="list_habits",
                    description="List all tracked habits with their IDs and targets.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_habits,
            ),
            (
                ToolDefinition(
                    name="remove_habit",
                    description="Remove a habit from tracking by its ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "habit_id": {
                                "type": "string",
                                "description": "Habit ID to remove",
                            }
                        },
                        "required": ["habit_id"],
                    },
                ),
                self.remove_habit,
            ),
        ]

    async def add_habit(
        self,
        name: str,
        frequency: str = "daily",
        unit: str = "times",
        target: float = 1.0,
    ) -> str:
        h = self._get().add_habit(
            name, frequency=frequency, unit=unit, target=target
        )
        return (
            f"Habit added: '{h.name}'  "
            f"({frequency}, target: {target} {unit})  [ID: {h.id}]"
        )

    async def log_habit(
        self, habit_id: str, value: float = 1.0, note: str = ""
    ) -> str:
        store = self._get()
        entry = store.log_habit(habit_id, value=value, note=note)
        if not entry:
            return (
                f"No habit found with ID '{habit_id}'. "
                "Use list_habits to see IDs."
            )
        habit = store._habits.get(habit_id)
        streak = store.get_streak(habit_id)
        name = habit.name if habit else habit_id
        unit = habit.unit if habit else "times"
        streak_str = f"  {streak} day streak!" if streak > 1 else ""
        return f"Logged '{name}' — {value} {unit}{streak_str}"

    async def log_time(
        self, activity: str, minutes: float, note: str = ""
    ) -> str:
        self._get().log_time(activity, minutes, note=note)
        hours = minutes / 60
        dur = f"{hours:.1f}h" if hours >= 1 else f"{int(minutes)}m"
        return f"Logged {dur} of '{activity}'."

    async def get_summary(self, days: int = 7) -> str:
        store = self._get()
        habit_data = store.get_summary(days=days)
        time_data = store.get_time_summary(days=days)
        lines = [f"Summary (last {days} days):"]
        if habit_data:
            lines.append("\nHabits:")
            for item in habit_data:
                h = item["habit"]
                streak = item["streak"]
                count = item["count"]
                flame = f"  {streak}d streak" if streak > 0 else ""
                lines.append(f"  {h.name}: {count}x completed{flame}")
        else:
            lines.append("\nNo habits tracked yet.")
        if time_data:
            lines.append("\nTime spent:")
            for item in time_data:
                mins = item["minutes"]
                hours = mins / 60
                dur = f"{hours:.1f}h" if hours >= 1 else f"{int(mins)}m"
                lines.append(f"  {item['activity']}: {dur}")
        else:
            lines.append("\nNo time logged yet.")
        return "\n".join(lines)

    async def list_habits(self) -> str:
        habits = self._get().list_habits()
        if not habits:
            return "No habits tracked. Use add_habit to start."
        lines = ["Tracked habits:"]
        for h in habits:
            lines.append(
                f"  [{h.id}] {h.name}  "
                f"({h.frequency}, target: {h.target} {h.unit})"
            )
        return "\n".join(lines)

    async def remove_habit(self, habit_id: str) -> str:
        if self._get().remove_habit(habit_id):
            return f"Habit [{habit_id}] removed."
        return f"No habit found with ID '{habit_id}'."
