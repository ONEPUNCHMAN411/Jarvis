
import asyncio
from datetime import datetime, timedelta, timezone
from datetime import time as dtime

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition
from jarvis.brain.scheduler_util import parse_dt, free_slots


class SmartSchedulerPlugin(Plugin):
    """Find free time on your calendar and book meetings into open slots,
    reusing the connected Google Calendar."""

    def __init__(self):
        super().__init__("smart_scheduler")

    async def initialize(self) -> None:
        logger.info("SmartSchedulerPlugin ready")

    async def shutdown(self) -> None:
        pass

    def _calendar(self):
        from jarvis.app import get_runtime
        rt = get_runtime()
        if rt is None or rt.plugin_manager is None:
            return None
        cal = rt.plugin_manager.plugins.get("calendar")
        if cal is None or getattr(cal, "service", None) is None:
            return None
        return cal

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="find_free_slots",
                    description=(
                        "Find open time slots on the calendar for a given day and "
                        "duration. Use when the user says 'when am I free tomorrow?', "
                        "'find me a 30 minute slot today', 'what times are open?'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Day as YYYY-MM-DD (default today)"},
                            "duration_minutes": {"type": "integer", "description": "Slot length (default 30)"},
                            "work_start_hour": {"type": "integer", "description": "Earliest hour, 0-23 (default 9)"},
                            "work_end_hour": {"type": "integer", "description": "Latest hour, 0-23 (default 17)"},
                        },
                    },
                ),
                self.find_free_slots,
            ),
            (
                ToolDefinition(
                    name="schedule_in_free_slot",
                    description=(
                        "Find the first free slot of the given duration and book an "
                        "event there. Use when the user says 'schedule a 1 hour "
                        "meeting tomorrow', 'book focus time today', 'find time and "
                        "add it to my calendar'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Event title"},
                            "date": {"type": "string", "description": "Day as YYYY-MM-DD (default today)"},
                            "duration_minutes": {"type": "integer", "description": "Length (default 30)"},
                            "work_start_hour": {"type": "integer", "description": "Earliest hour (default 9)"},
                            "work_end_hour": {"type": "integer", "description": "Latest hour (default 17)"},
                        },
                        "required": ["title"],
                    },
                ),
                self.schedule_in_free_slot,
            ),
        ]

    def _window(self, date: str, work_start: int, work_end: int):
        local_tz = datetime.now().astimezone().tzinfo
        base = datetime.fromisoformat(date).date() if date else datetime.now(local_tz).date()
        win_start = datetime.combine(base, dtime(hour=int(work_start)), local_tz)
        win_end = datetime.combine(base, dtime(hour=int(work_end)), local_tz)
        day_start = datetime.combine(base, dtime(0, 0), local_tz)
        day_end = day_start + timedelta(days=1)
        return local_tz, win_start, win_end, day_start, day_end

    async def _busy(self, cal, day_start, day_end, local_tz):
        service = cal.service
        items = await asyncio.to_thread(
            lambda: service.events().list(
                calendarId="primary",
                timeMin=day_start.astimezone(timezone.utc).isoformat(),
                timeMax=day_end.astimezone(timezone.utc).isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute().get("items", [])
        )
        busy = []
        for e in items:
            s = e.get("start", {}).get("dateTime")
            en = e.get("end", {}).get("dateTime")
            if not s or not en:
                continue  # skip all-day events
            busy.append((parse_dt(s).astimezone(local_tz), parse_dt(en).astimezone(local_tz)))
        return busy

    async def find_free_slots(self, date="", duration_minutes=30,
                              work_start_hour=9, work_end_hour=17) -> str:
        cal = self._calendar()
        if cal is None:
            return "Google Calendar is not connected."
        try:
            local_tz, win_start, win_end, day_start, day_end = self._window(
                date, work_start_hour, work_end_hour)
            busy = await self._busy(cal, day_start, day_end, local_tz)
            slots = free_slots(busy, win_start, win_end, duration_minutes)
        except Exception as e:
            return f"Could not find free slots: {e}"
        if not slots:
            return f"No free {duration_minutes}-minute slots on {win_start.strftime('%A %b %d')}."
        lines = [f"Free {duration_minutes}-min slots on {win_start.strftime('%A %b %d')}:"]
        for s, e in slots:
            lines.append(f"  {s.strftime('%I:%M %p')} – {e.strftime('%I:%M %p')}")
        return "\n".join(lines)

    async def schedule_in_free_slot(self, title, date="", duration_minutes=30,
                                    work_start_hour=9, work_end_hour=17) -> str:
        cal = self._calendar()
        if cal is None:
            return "Google Calendar is not connected."
        try:
            local_tz, win_start, win_end, day_start, day_end = self._window(
                date, work_start_hour, work_end_hour)
            busy = await self._busy(cal, day_start, day_end, local_tz)
            slots = free_slots(busy, win_start, win_end, duration_minutes)
        except Exception as e:
            return f"Could not schedule: {e}"
        if not slots:
            return f"No free {duration_minutes}-minute slot to book on {win_start.strftime('%A %b %d')}."
        start = slots[0][0]
        end = start + timedelta(minutes=int(duration_minutes))
        start_utc = start.astimezone(timezone.utc).isoformat()
        end_utc = end.astimezone(timezone.utc).isoformat()
        result = await cal.create_event(title=title, start=start_utc, end=end_utc)
        return f"Booked '{title}' at {start.strftime('%A %b %d, %I:%M %p')}.\n{result}"
