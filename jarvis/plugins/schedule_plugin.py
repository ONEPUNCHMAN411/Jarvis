from loguru import logger
from jarvis.brain.schedule_store import get_schedule_store, ScheduledPrompt
from jarvis.models import ToolDefinition
from jarvis.plugins.base import Plugin

_DAY_ALIASES: dict = {
    "daily": ["daily"],
    "everyday": ["daily"],
    "weekdays": ["mon", "tue", "wed", "thu", "fri"],
    "weekends": ["sat", "sun"],
    "monday": ["mon"], "tuesday": ["tue"], "wednesday": ["wed"],
    "thursday": ["thu"], "friday": ["fri"], "saturday": ["sat"], "sunday": ["sun"],
}


def _parse_days(raw: str) -> list:
    low = raw.lower().strip()
    if low in _DAY_ALIASES:
        return _DAY_ALIASES[low]
    valid = {"mon", "tue", "wed", "thu", "fri", "sat", "sun", "daily"}
    parts = [p.strip()[:3] for p in low.replace(",", " ").split()]
    return [p for p in parts if p in valid] or ["daily"]


def _parse_time(raw: str) -> str:
    raw = raw.strip()
    if len(raw) == 5 and raw[2] == ":":
        return raw
    if ":" not in raw:
        if raw.isdigit() and 0 <= int(raw) <= 23:
            return f"{int(raw):02d}:00"
    return raw


class SchedulePlugin(Plugin):
    def __init__(self):
        super().__init__("schedule")

    def get_tools(self):
        return [
            (ToolDefinition(
                name="add_schedule",
                description=(
                    "Schedule a prompt to fire automatically at a recurring time. "
                    "Example: every weekday at 8:30am get a morning briefing with weather, news, and tasks."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Label for this schedule (e.g. 'Morning Briefing')"},
                        "prompt": {"type": "string", "description": "The exact message JARVIS sends to itself at fire time"},
                        "time": {"type": "string", "description": "24h time string HH:MM (e.g. '08:30')"},
                        "days": {"type": "string", "description": "When to run: 'daily', 'weekdays', 'weekends', or 'mon,wed,fri'"},
                    },
                    "required": ["name", "prompt", "time", "days"],
                },
            ), self._add_schedule),
            (ToolDefinition(
                name="list_schedules",
                description="List all scheduled prompts with their status and next-fire info",
                parameters={"type": "object", "properties": {}},
            ), self._list_schedules),
            (ToolDefinition(
                name="remove_schedule",
                description="Delete a scheduled prompt by name or ID",
                parameters={
                    "type": "object",
                    "properties": {
                        "schedule_id": {"type": "string", "description": "Schedule name or ID"},
                    },
                    "required": ["schedule_id"],
                },
            ), self._remove_schedule),
            (ToolDefinition(
                name="toggle_schedule",
                description="Pause or resume a schedule without deleting it",
                parameters={
                    "type": "object",
                    "properties": {
                        "schedule_id": {"type": "string", "description": "Schedule name or ID"},
                    },
                    "required": ["schedule_id"],
                },
            ), self._toggle_schedule),
            (ToolDefinition(
                name="run_schedule_now",
                description="Fire a scheduled prompt immediately, regardless of its set time",
                parameters={
                    "type": "object",
                    "properties": {
                        "schedule_id": {"type": "string", "description": "Schedule name or ID"},
                    },
                    "required": ["schedule_id"],
                },
            ), self._run_now),
        ]

    async def initialize(self):
        store = get_schedule_store()
        store.register_callback(self._fire_schedule)
        store.start()

    async def shutdown(self):
        get_schedule_store().stop()

    def _fire_schedule(self, schedule: ScheduledPrompt):
        from jarvis.app import get_runtime
        from jarvis.models import Message

        runtime = get_runtime()

        async def _run():
            provider_name = next(iter(runtime.provider_router._order), None)
            if not provider_name:
                return
            provider = runtime.provider_router._providers.get(provider_name)
            if not provider:
                return
            resp = await provider.chat(
                [Message(role="user", content=schedule.prompt)],
                temperature=0.7,
            )
            summary = resp.text.strip()
            try:
                from plyer import notification
                notification.notify(
                    title=f"JARVIS: {schedule.name}",
                    message=summary[:200].replace("\n", " "),
                    app_name="JARVIS",
                    timeout=10,
                )
            except Exception:
                pass
            logger.info(f"Schedule '{schedule.name}' fired: {summary[:80]}")

        runtime.async_runtime.submit(_run())

    async def _add_schedule(self, name: str, prompt: str, time: str, days: str) -> str:
        time_clean = _parse_time(time)
        if len(time_clean) != 5 or time_clean[2] != ":":
            return f"Invalid time '{time}'. Use HH:MM format, e.g. '09:00'."
        days_list = _parse_days(days)
        s = get_schedule_store().add(name=name, prompt=prompt, time_str=time_clean, days=days_list)
        return (
            f"Schedule **'{s.name}'** created (ID: `{s.id}`).\n"
            f"Fires at **{time_clean}** on **{', '.join(days_list)}**.\n"
            f"Prompt: _{prompt[:100]}_"
        )

    async def _list_schedules(self) -> str:
        schedules = get_schedule_store().list_all()
        if not schedules:
            return "No schedules yet. Use `add_schedule` to create one."
        lines = [f"**{len(schedules)} schedule(s):**\n"]
        for s in schedules:
            icon = "✅" if s.enabled else "⏸"
            last = s.last_run[:10] if s.last_run else "never"
            lines.append(f"{icon} **{s.name}** `{s.id}`  {s.time_str} on {', '.join(s.days)} | runs: {s.run_count} | last: {last}")
            lines.append(f"   _{s.prompt[:80]}_\n")
        return "\n".join(lines)

    async def _remove_schedule(self, schedule_id: str) -> str:
        ok = get_schedule_store().delete(schedule_id)
        return f"Removed schedule '{schedule_id}'." if ok else f"Schedule '{schedule_id}' not found."

    async def _toggle_schedule(self, schedule_id: str) -> str:
        result = get_schedule_store().toggle(schedule_id)
        if result is None:
            return f"Schedule '{schedule_id}' not found."
        state = "enabled ✅" if result else "paused ⏸"
        return f"Schedule {state}."

    async def _run_now(self, schedule_id: str) -> str:
        s = get_schedule_store().fire_now(schedule_id)
        if not s:
            return f"Schedule '{schedule_id}' not found."
        return f"Fired **'{s.name}'** now. Response incoming..."
