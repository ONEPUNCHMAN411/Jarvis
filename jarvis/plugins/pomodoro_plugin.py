
import threading
import time

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


def _notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="JARVIS",
            timeout=10,
        )
    except Exception:
        logger.info(f"[Pomodoro] {title}: {message}")


class PomodoroSession:
    """Runs a single work/break cycle in a background thread."""

    def __init__(self, work_minutes: int, break_minutes: int, on_done=None):
        self.work_minutes = work_minutes
        self.break_minutes = break_minutes
        self._on_done = on_done
        self._stop = threading.Event()
        self._phase = "idle"
        self._end_time = None
        self._thread = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._phase = "stopped"

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def remaining_seconds(self) -> int:
        if self._end_time is None:
            return 0
        return max(0, int(self._end_time - time.time()))

    def _run(self) -> None:
        self._phase = "work"
        self._end_time = time.time() + self.work_minutes * 60
        _notify("Pomodoro started", f"Focus for {self.work_minutes} minutes!")
        while not self._stop.is_set():
            if time.time() >= self._end_time:
                break
            time.sleep(1)
        if self._stop.is_set():
            return
        _notify("Break time!", f"Take a {self.break_minutes}-minute break.")
        self._phase = "break"
        self._end_time = time.time() + self.break_minutes * 60
        while not self._stop.is_set():
            if time.time() >= self._end_time:
                break
            time.sleep(1)
        if not self._stop.is_set():
            self._phase = "done"
            _notify("Pomodoro complete!", "Break over -- ready for the next round.")
            if self._on_done:
                self._on_done()


class PomodoroPlugin(Plugin):
    """Pomodoro timer with customizable work/break cycles and desktop notifications."""

    def __init__(self):
        super().__init__("pomodoro")
        self._session = None
        self._completed = 0

    async def initialize(self) -> None:
        logger.info("PomodoroPlugin ready")

    async def shutdown(self) -> None:
        if self._session:
            self._session.stop()

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="start_pomodoro",
                    description=(
                        "Start a Pomodoro focus session. Default is 25 minutes work "
                        "followed by 5 minutes break. Desktop notifications fire when "
                        "each phase ends."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "work_minutes": {
                                "type": "integer",
                                "description": "Work duration in minutes. Default: 25",
                            },
                            "break_minutes": {
                                "type": "integer",
                                "description": "Break duration in minutes. Default: 5",
                            },
                        },
                    },
                ),
                self.start_pomodoro,
            ),
            (
                ToolDefinition(
                    name="stop_pomodoro",
                    description="Stop the active Pomodoro session.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.stop_pomodoro,
            ),
            (
                ToolDefinition(
                    name="pomodoro_status",
                    description=(
                        "Check the current Pomodoro session -- phase, time remaining, "
                        "and total sessions completed."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.pomodoro_status,
            ),
        ]

    async def start_pomodoro(self, work_minutes: int = 25, break_minutes: int = 5) -> str:
        if self._session and self._session.phase not in ("done", "stopped", "idle"):
            return (
                f"A session is already running ({self._session.phase} phase). "
                "Use stop_pomodoro first."
            )

        def _on_done() -> None:
            self._completed += 1
            self._session = None

        self._session = PomodoroSession(work_minutes, break_minutes, _on_done)
        self._session.start()
        return (
            f"Pomodoro started: {work_minutes}m work -> {break_minutes}m break. "
            "Desktop notifications will fire at each phase change."
        )

    async def stop_pomodoro(self) -> str:
        if not self._session or self._session.phase in ("done", "stopped", "idle"):
            return "No active Pomodoro session."
        self._session.stop()
        self._session = None
        return "Pomodoro session stopped."

    async def pomodoro_status(self) -> str:
        if not self._session or self._session.phase in ("done", "stopped", "idle"):
            return f"No active session. Completed this session: {self._completed}"
        rem = self._session.remaining_seconds
        mins, secs = divmod(rem, 60)
        return (
            f"Phase: {self._session.phase}\n"
            f"Time remaining: {mins}m {secs}s\n"
            f"Sessions completed: {self._completed}"
        )
