"""
JARVIS Scheduler Plugin — task scheduling with cron-like and natural language support.
"""
import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

@dataclass
class ScheduledTask:
    """Represents a scheduled task."""
    id: str  # unique ID
    description: str
    schedule_type: str  # "once", "daily", "weekly", "every_n_minutes", "every_n_hours"
    schedule_value: str  # e.g., "10:30", "Monday", "30", "2"
    action: str  # what to do: "reminder", "run_code", "notification"
    action_data: dict = field(default_factory=dict)  # e.g., {"message": "...", "code": "..."}
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    next_run_at: str = ""
    last_run_at: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        """Create from dict."""
        return cls(**data)

class SchedulerPlugin(Plugin):
    """Task scheduler plugin with natural language scheduling support."""

    def __init__(self, data_dir: str = "data"):
        super().__init__("scheduler")
        self.enabled = True
        self.data_dir = Path(data_dir)
        self.tasks_file = self.data_dir / "scheduler.json"
        self.tasks: dict[str, ScheduledTask] = {}
        self.running = False
        self._scheduler_task = None

    async def initialize(self) -> None:
        """Initialize scheduler plugin."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        await self._load_tasks()
        # Start background scheduler loop
        self.running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler plugin initialized")

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        self.running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        await self._save_tasks()

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        """Return scheduler tools."""
        return [
            (
                ToolDefinition(
                    name="schedule_task",
                    description="Schedule a task with natural language support",
                    parameters={
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Task description (e.g., 'remind me to call mom')"
                            },
                            "schedule": {
                                "type": "string",
                                "description": "Schedule in natural language (e.g., 'every 30 minutes', 'daily at 9am', 'every Monday at 10:30', 'once at 3pm tomorrow')"
                            },
                            "action": {
                                "type": "string",
                                "description": "Action type: 'reminder', 'notification', 'run_code'"
                            },
                            "action_data": {
                                "type": "object",
                                "description": "Action-specific data (e.g., {'message': '...', 'code': '...'})"
                            },
                        },
                        "required": ["description", "schedule", "action"],
                    },
                ),
                self.schedule_task,
            ),
            (
                ToolDefinition(
                    name="list_scheduled_tasks",
                    description="List all scheduled tasks",
                    parameters={
                        "type": "object",
                        "properties": {
                            "filter": {
                                "type": "string",
                                "description": "Filter: 'enabled', 'disabled', 'all' (default: 'enabled')"
                            }
                        },
                    },
                ),
                self.list_scheduled_tasks,
            ),
            (
                ToolDefinition(
                    name="remove_scheduled_task",
                    description="Remove a scheduled task by ID",
                    parameters={
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string", "description": "Task ID"}
                        },
                        "required": ["task_id"],
                    },
                ),
                self.remove_scheduled_task,
            ),
            (
                ToolDefinition(
                    name="update_scheduled_task",
                    description="Update a scheduled task",
                    parameters={
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string", "description": "Task ID"},
                            "enabled": {
                                "type": "boolean",
                                "description": "Enable or disable the task"
                            },
                        },
                        "required": ["task_id"],
                    },
                ),
                self.update_scheduled_task,
            ),
        ]

    async def schedule_task(
        self,
        description: str,
        schedule: str,
        action: str,
        action_data: dict = None,
    ) -> str:
        """Schedule a new task."""
        try:
            if action_data is None:
                action_data = {}

            # Parse schedule string
            schedule_type, schedule_value = self._parse_schedule(schedule)
            if not schedule_type:
                return f"Error: Could not parse schedule '{schedule}'"

            # Generate task ID
            task_id = f"task_{int(datetime.now().timestamp() * 1000)}"

            # Calculate next run time
            next_run = self._calculate_next_run(schedule_type, schedule_value)

            task = ScheduledTask(
                id=task_id,
                description=description,
                schedule_type=schedule_type,
                schedule_value=schedule_value,
                action=action,
                action_data=action_data,
                next_run_at=next_run.isoformat(),
            )

            self.tasks[task_id] = task
            await self._save_tasks()
            logger.info(f"Scheduled task: {task_id} - {description}")
            return f"Task scheduled: {task_id}\nNext run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}"

        except Exception as e:
            logger.error(f"Schedule task error: {e}")
            return f"Error scheduling task: {str(e)}"

    async def list_scheduled_tasks(self, filter: str = "enabled") -> list[dict]:
        """List scheduled tasks."""
        try:
            result = []
            for task in self.tasks.values():
                if filter == "enabled" and not task.enabled:
                    continue
                if filter == "disabled" and task.enabled:
                    continue

                result.append({
                    "id": task.id,
                    "description": task.description,
                    "schedule": f"{task.schedule_type} {task.schedule_value}",
                    "action": task.action,
                    "enabled": task.enabled,
                    "next_run_at": task.next_run_at,
                    "last_run_at": task.last_run_at,
                })
            return result
        except Exception as e:
            logger.error(f"List tasks error: {e}")
            return [{"error": str(e)}]

    async def remove_scheduled_task(self, task_id: str) -> str:
        """Remove a scheduled task."""
        try:
            if task_id not in self.tasks:
                return f"Task not found: {task_id}"

            del self.tasks[task_id]
            await self._save_tasks()
            return f"Task removed: {task_id}"
        except Exception as e:
            logger.error(f"Remove task error: {e}")
            return f"Error removing task: {str(e)}"

    async def update_scheduled_task(self, task_id: str, enabled: bool = None) -> str:
        """Update a scheduled task."""
        try:
            if task_id not in self.tasks:
                return f"Task not found: {task_id}"

            task = self.tasks[task_id]
            if enabled is not None:
                task.enabled = enabled

            await self._save_tasks()
            status = "enabled" if task.enabled else "disabled"
            return f"Task updated: {task_id} is now {status}"
        except Exception as e:
            logger.error(f"Update task error: {e}")
            return f"Error updating task: {str(e)}"

    async def _scheduler_loop(self) -> None:
        """Background loop that checks for due tasks every 30 seconds."""
        while self.running:
            try:
                now = datetime.now()
                for task in list(self.tasks.values()):
                    if not task.enabled:
                        continue

                    if task.next_run_at:
                        next_run = datetime.fromisoformat(task.next_run_at)
                        if next_run <= now:
                            await self._execute_task(task)
                            # Schedule next occurrence
                            task.next_run_at = self._calculate_next_run(
                                task.schedule_type, task.schedule_value
                            ).isoformat()
                            task.last_run_at = now.isoformat()
                            await self._save_tasks()

                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(30)

    async def _execute_task(self, task: ScheduledTask) -> None:
        try:
            from jarvis.app import get_runtime
            from jarvis.models import UserTextEvent
            runtime = get_runtime()
            if runtime is None:
                logger.warning(f"Skipping task {task.id} — runtime not ready")
                return
            logger.info(f"Firing scheduled task: {task.id} - {task.description}")
            await runtime.async_runtime.bus.publish(
                UserTextEvent(text=f"[Scheduled] {task.description}")
            )
        except Exception as e:
            logger.error(f"Task execution error for {task.id}: {e}")

    def _parse_schedule(self, schedule: str) -> tuple[str, str]:
        """
        Parse natural language schedule string.
        Returns (schedule_type, schedule_value).
        """
        schedule = schedule.lower().strip()

        # Every N minutes: "every 30 minutes", "every 30m"
        if "every" in schedule and ("minute" in schedule or "m " in schedule):
            parts = schedule.split()
            try:
                minutes = int(parts[1])
                return ("every_n_minutes", str(minutes))
            except (IndexError, ValueError):
                return (None, None)

        # Every N hours: "every 2 hours", "every 2h"
        if "every" in schedule and ("hour" in schedule or "h " in schedule):
            parts = schedule.split()
            try:
                hours = int(parts[1])
                return ("every_n_hours", str(hours))
            except (IndexError, ValueError):
                return (None, None)

        # Daily at time: "daily at 9:30", "every day at 14:00"
        if "daily" in schedule or "every day" in schedule:
            if "at" in schedule:
                time_part = schedule.split("at")[-1].strip()
                return ("daily", time_part)
            return ("daily", "00:00")

        # Weekly on day: "every monday at 10:30", "weekly on friday at 3pm"
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for day in days:
            if day in schedule:
                if "at" in schedule:
                    time_part = schedule.split("at")[-1].strip()
                    return ("weekly", f"{day} {time_part}")
                return ("weekly", f"{day} 00:00")

        # Once at time/date: "once at 3pm", "once tomorrow at 10am"
        if "once" in schedule:
            if "at" in schedule:
                time_part = schedule.split("at")[-1].strip()
                return ("once", time_part)
            return (None, None)

        return (None, None)

    def _calculate_next_run(self, schedule_type: str, schedule_value: str) -> datetime:
        """Calculate next run time based on schedule."""
        now = datetime.now()

        if schedule_type == "every_n_minutes":
            minutes = int(schedule_value)
            return now + timedelta(minutes=minutes)

        if schedule_type == "every_n_hours":
            hours = int(schedule_value)
            return now + timedelta(hours=hours)

        if schedule_type == "daily":
            target_time = self._parse_time(schedule_value)
            next_run = now.replace(
                hour=target_time[0],
                minute=target_time[1],
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        if schedule_type == "weekly":
            day_part, time_part = schedule_value.rsplit(" ", 1)
            day_names = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            target_day = day_names.get(day_part.lower(), 0)
            target_time = self._parse_time(time_part)

            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7

            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(
                hour=target_time[0],
                minute=target_time[1],
                second=0,
                microsecond=0,
            )
            if days_ahead == 0 and next_run <= now:
                next_run += timedelta(days=7)
            return next_run

        if schedule_type == "once":
            target_time = self._parse_time(schedule_value)
            next_run = now.replace(
                hour=target_time[0],
                minute=target_time[1],
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        return now + timedelta(hours=1)

    def _parse_time(self, time_str: str) -> tuple[int, int]:
        """Parse time string like '9:30', '3pm', '14:00'."""
        time_str = time_str.strip().lower()

        # Handle "3pm", "9am" format
        if "am" in time_str or "pm" in time_str:
            is_pm = "pm" in time_str
            time_str = time_str.replace("am", "").replace("pm", "").strip()
            try:
                hour = int(time_str.split(":")[0])
                minute = int(time_str.split(":")[1]) if ":" in time_str else 0
                if is_pm and hour != 12:
                    hour += 12
                elif not is_pm and hour == 12:
                    hour = 0
                return (hour, minute)
            except (ValueError, IndexError):
                return (0, 0)

        # Handle "9:30", "14:00" format
        try:
            if ":" in time_str:
                hour, minute = time_str.split(":")
                return (int(hour), int(minute))
            else:
                return (int(time_str), 0)
        except (ValueError, IndexError):
            return (0, 0)

    async def _load_tasks(self) -> None:
        """Load tasks from JSON file."""
        try:
            if self.tasks_file.exists():
                content = await asyncio.to_thread(self.tasks_file.read_text)
                data = json.loads(content)
                for task_data in data:
                    task = ScheduledTask.from_dict(task_data)
                    self.tasks[task.id] = task
                logger.info(f"Loaded {len(self.tasks)} scheduled tasks")
        except Exception as e:
            logger.error(f"Load tasks error: {e}")

    async def _save_tasks(self) -> None:
        """Save tasks to JSON file."""
        try:
            data = [task.to_dict() for task in self.tasks.values()]
            content = json.dumps(data, indent=2)
            await asyncio.to_thread(self.tasks_file.write_text, content)
        except Exception as e:
            logger.error(f"Save tasks error: {e}")
