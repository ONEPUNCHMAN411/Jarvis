import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

_PATH = Path.home() / ".jarvis" / "schedules.json"
_lock = threading.Lock()

_DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass
class ScheduledPrompt:
    id: str
    name: str
    prompt: str
    time_str: str
    days: list
    enabled: bool = True
    last_run: str | None = None
    run_count: int = 0


class ScheduleStore:
    def __init__(self):
        self._schedules: list[ScheduledPrompt] = []
        self._callbacks: list[Callable] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._load()

    def _load(self):
        if _PATH.exists():
            try:
                raw = json.loads(_PATH.read_text(encoding="utf-8"))
                self._schedules = [ScheduledPrompt(**s) for s in raw]
            except Exception:
                self._schedules = []

    def _save(self):
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(
            json.dumps([asdict(s) for s in self._schedules], indent=2),
            encoding="utf-8",
        )

    def add(self, name: str, prompt: str, time_str: str, days: list) -> ScheduledPrompt:
        with _lock:
            s = ScheduledPrompt(
                id=str(uuid.uuid4())[:8],
                name=name,
                prompt=prompt,
                time_str=time_str,
                days=days,
            )
            self._schedules.append(s)
            self._save()
            return s

    def list_all(self) -> list[ScheduledPrompt]:
        with _lock:
            return list(self._schedules)

    def get(self, schedule_id: str) -> ScheduledPrompt | None:
        with _lock:
            for s in self._schedules:
                if s.id == schedule_id or s.name.lower() == schedule_id.lower():
                    return s
            return None

    def delete(self, schedule_id: str) -> bool:
        with _lock:
            for i, s in enumerate(self._schedules):
                if s.id == schedule_id or s.name.lower() == schedule_id.lower():
                    self._schedules.pop(i)
                    self._save()
                    return True
            return False

    def toggle(self, schedule_id: str) -> bool | None:
        with _lock:
            for s in self._schedules:
                if s.id == schedule_id or s.name.lower() == schedule_id.lower():
                    s.enabled = not s.enabled
                    self._save()
                    return s.enabled
            return None

    def _should_fire(self, s: ScheduledPrompt, now: datetime) -> bool:
        if not s.enabled:
            return False
        try:
            hh, mm = map(int, s.time_str.split(":"))
        except ValueError:
            return False
        if now.hour != hh or now.minute != mm:
            return False
        if s.last_run:
            try:
                last = datetime.fromisoformat(s.last_run)
                if last.date() == now.date():
                    return False
            except ValueError:
                pass
        if "daily" in s.days:
            return True
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        return day_names[now.weekday()] in s.days

    def _tick(self):
        while not self._stop.wait(30):
            now = datetime.now()
            with _lock:
                to_fire = [s for s in self._schedules if self._should_fire(s, now)]
                for s in to_fire:
                    s.last_run = now.isoformat()
                    s.run_count += 1
                if to_fire:
                    self._save()
            for s in to_fire:
                for cb in list(self._callbacks):
                    try:
                        cb(s)
                    except Exception:
                        pass

    def register_callback(self, fn: Callable):
        self._callbacks.append(fn)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._tick, daemon=True, name="jarvis-scheduler")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def fire_now(self, schedule_id: str) -> ScheduledPrompt | None:
        s = self.get(schedule_id)
        if not s:
            return None
        with _lock:
            s.last_run = datetime.now().isoformat()
            s.run_count += 1
            self._save()
        for cb in list(self._callbacks):
            try:
                cb(s)
            except Exception:
                pass
        return s


_store: ScheduleStore | None = None


def get_schedule_store() -> ScheduleStore:
    global _store
    if _store is None:
        _store = ScheduleStore()
    return _store
