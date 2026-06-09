"""
Background screen monitor that periodically captures screenshots,
sends them to a lightweight LLM for analysis, and emits proactive
help suggestions via the event bus.
"""


import asyncio
import json
import time

from loguru import logger

from jarvis.models import ProactiveHelpEvent

_ANALYSIS_PROMPT = (
    "You are JARVIS, an AI assistant. Look at this screenshot of the user's screen. "
    "Determine if the user appears stuck, is making an error, or could benefit from help. "
    "Only suggest if genuinely helpful — do NOT suggest for normal browsing, watching "
    "videos, or routine activity.\n\n"
    "Reply with ONLY valid JSON (no markdown):\n"
    '{"should_offer": true/false, "suggestion": "short helpful suggestion", '
    '"category": "one of: error, stuck, optimization, writing, coding, form"}'
)

class ScreenWatcher:
    def __init__(
        self,
        bus,
        screen_service,
        provider_router,
        config: dict,
    ):
        self._bus = bus
        self._screen = screen_service
        self._router = provider_router
        self._config = config

        self._enabled: bool = config.get("enabled", False)
        self._interval: float = float(config.get("interval_seconds", 15))
        self._quiet_apps: list[str] = [a.lower() for a in config.get("quiet_apps", [])]
        self._max_per_hour: int = config.get("max_suggestions_per_hour", 12)

        self._task: asyncio.Task | None = None
        self._last_suggestion_time: float = 0
        self._consecutive_dismissals: int = 0
        self._dismissed_categories: dict[str, float] = {}
        self._suggestion_times: list[float] = []
        self._previous_screenshot: bytes | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled and self._task is None:
            self.start()
        elif not enabled and self._task is not None:
            self.stop()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        if not self._enabled:
            return
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("Screen watcher started")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        logger.info("Screen watcher stopped")

    def record_dismissal(self, category: str) -> None:
        self._consecutive_dismissals += 1
        self._dismissed_categories[category] = time.monotonic()
        if self._consecutive_dismissals >= 5:
            logger.info("Screen watcher paused after 5 consecutive dismissals")
            self.set_enabled(False)

    def record_acceptance(self) -> None:
        self._consecutive_dismissals = 0

    async def _watch_loop(self) -> None:
        try:
            await asyncio.sleep(self._interval)
            while self._enabled:
                try:
                    await self._check_screen()
                except Exception as e:
                    logger.debug(f"Screen watcher check failed: {e}")

                effective_interval = self._interval
                if self._consecutive_dismissals >= 3:
                    effective_interval = max(60.0, self._interval * 2)

                await asyncio.sleep(effective_interval)
        except asyncio.CancelledError:
            pass

    async def _check_screen(self) -> None:
        now = time.monotonic()
        if now - self._last_suggestion_time < 30:
            return

        self._suggestion_times = [t for t in self._suggestion_times if now - t < 3600]
        if len(self._suggestion_times) >= self._max_per_hour:
            return

        if self._quiet_apps and self._screen:
            try:
                active = self._screen.get_active_window_title()
                if active and any(q in active.lower() for q in self._quiet_apps):
                    return
            except Exception:
                pass

        try:
            screenshot_path = await self._screen.take_screenshot()
        except Exception:
            return

        if not screenshot_path:
            return

        from jarvis.models import Message
        analysis_messages = [
            Message(role="user", content=_ANALYSIS_PROMPT, image_paths=[screenshot_path]),
        ]

        try:
            response = await asyncio.wait_for(
                self._router.chat(
                    analysis_messages,
                    tools=None,
                    system_prompt=None,
                    temperature=0.3,
                ),
                timeout=15,
            )
        except Exception as e:
            logger.debug(f"Screen watcher LLM call failed: {e}")
            return

        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return

        if not result.get("should_offer", False):
            return

        suggestion = result.get("suggestion", "")
        category = result.get("category", "general")

        if not suggestion:
            return

        dismissed_at = self._dismissed_categories.get(category, 0)
        if now - dismissed_at < 300:
            return

        self._last_suggestion_time = now
        self._suggestion_times.append(now)

        await self._bus.publish(
            ProactiveHelpEvent(
                suggestion=suggestion,
                category=category,
                screenshot_path=screenshot_path,
            )
        )
        logger.info(f"Proactive suggestion: [{category}] {suggestion}")
