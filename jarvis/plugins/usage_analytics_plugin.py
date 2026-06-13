import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class UsageAnalyticsPlugin(Plugin):
    def __init__(self):
        super().__init__("usage_analytics")

    async def initialize(self):
        from jarvis.brain.usage_analytics import get_usage_analytics
        get_usage_analytics().start()
        logger.info("UsageAnalyticsPlugin ready")

    async def shutdown(self):
        from jarvis.brain.usage_analytics import get_usage_analytics
        get_usage_analytics().stop()

    def get_tools(self):
        return [
            (ToolDefinition(
                name="get_usage_report",
                description=(
                    "Show a daily breakdown of time spent per app for the last N days. "
                    "Use when user asks 'how did I spend my time today?', "
                    "'show me my app usage this week', 'what have I been using most?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"days": {"type": "integer", "default": 7}},
                },
            ), self.usage_report),
            (ToolDefinition(
                name="get_weekly_heatmap",
                description=(
                    "Show a heatmap of the top 10 apps across the last 7 days (minutes per day). "
                    "Use when user asks 'show me my weekly usage heatmap', "
                    "'which apps did I use most this week?'."
                ),
                parameters={"type": "object", "properties": {}},
            ), self.weekly_heatmap),
        ]


    async def usage_report(self, days: int = 7, **_) -> str:
        from jarvis.brain.usage_analytics import get_usage_analytics
        report = await self._run(get_usage_analytics().daily_report, days)
        lines = [f"App usage — last {days} day(s):"]
        for day_data in report:
            total = day_data["total_min"]
            if not total:
                continue
            lines.append(f"\n  {day_data['date']}  ({total} min total)")
            for app, mins in day_data["apps"][:8]:
                bar = "█" * min(int(mins / max(total, 1) * 20), 20)
                lines.append(f"    {app:<28} {bar} {mins} min")
        return "\n".join(lines) if len(lines) > 1 else "No usage data recorded yet."

    async def weekly_heatmap(self, **_) -> str:
        from jarvis.brain.usage_analytics import get_usage_analytics
        heatmap = await self._run(get_usage_analytics().weekly_heatmap)
        if not heatmap:
            return "No weekly usage data yet."
        lines = ["Weekly app usage heatmap (minutes per day):"]
        dates = list(next(iter(heatmap.values())).keys()) if heatmap else []
        header = f"  {'App':<28}" + "".join(f"  {d[5:]}" for d in dates)
        lines.append(header)
        for app, day_mins in heatmap.items():
            row = f"  {app:<28}" + "".join(f"  {str(m).rjust(5)}" for m in day_mins.values())
            lines.append(row)
        return "\n".join(lines)
