
import json
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from pathlib import Path

from loguru import logger

_HABIT_FILE = Path.home() / ".jarvis" / "habits.json"
_TIME_FILE = Path.home() / ".jarvis" / "time_log.json"


@dataclass
class Habit:
    id: str
    name: str
    frequency: str = "daily"
    unit: str = "times"
    target: float = 1.0
    created: str = field(default_factory=lambda: date.today().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Habit":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class HabitEntry:
    id: str
    habit_id: str
    date: str
    value: float = 1.0
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HabitEntry":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class TimeEntry:
    id: str
    activity: str
    minutes: float
    date: str
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TimeEntry":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


class HabitStore:
    """JSON-backed habit tracker and time logger."""

    def __init__(self):
        self._habits: dict[str, Habit] = {}
        self._entries: list[HabitEntry] = []
        self._time_log: list[TimeEntry] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if _HABIT_FILE.exists():
            try:
                data = json.loads(_HABIT_FILE.read_text(encoding="utf-8"))
                for d in data.get("habits", []):
                    h = Habit.from_dict(d)
                    self._habits[h.id] = h
                for d in data.get("entries", []):
                    self._entries.append(HabitEntry.from_dict(d))
                logger.debug(f"HabitStore: loaded {len(self._habits)} habits")
            except Exception as e:
                logger.warning(f"HabitStore load error: {e}")
        if _TIME_FILE.exists():
            try:
                data = json.loads(_TIME_FILE.read_text(encoding="utf-8"))
                for d in data:
                    self._time_log.append(TimeEntry.from_dict(d))
            except Exception as e:
                logger.warning(f"TimeLog load error: {e}")

    def _save(self) -> None:
        try:
            _HABIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            _HABIT_FILE.write_text(
                json.dumps(
                    {
                        "habits": [h.to_dict() for h in self._habits.values()],
                        "entries": [e.to_dict() for e in self._entries],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            _TIME_FILE.write_text(
                json.dumps([t.to_dict() for t in self._time_log], indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"HabitStore save error: {e}")

    def add_habit(
        self,
        name: str,
        frequency: str = "daily",
        unit: str = "times",
        target: float = 1.0,
    ) -> Habit:
        with self._lock:
            h = Habit(
                id=uuid.uuid4().hex[:8],
                name=name,
                frequency=frequency,
                unit=unit,
                target=target,
            )
            self._habits[h.id] = h
            self._save()
            return h

    def list_habits(self) -> list[Habit]:
        with self._lock:
            return list(self._habits.values())

    def remove_habit(self, habit_id: str) -> bool:
        with self._lock:
            if habit_id in self._habits:
                del self._habits[habit_id]
                self._entries = [
                    e for e in self._entries if e.habit_id != habit_id
                ]
                self._save()
                return True
        return False

    def log_habit(
        self, habit_id: str, value: float = 1.0, note: str = ""
    ) -> HabitEntry | None:
        with self._lock:
            if habit_id not in self._habits:
                return None
            entry = HabitEntry(
                id=uuid.uuid4().hex[:8],
                habit_id=habit_id,
                date=date.today().isoformat(),
                value=value,
                note=note,
            )
            self._entries.append(entry)
            self._save()
            return entry

    def get_streak(self, habit_id: str) -> int:
        logged = {e.date for e in self._entries if e.habit_id == habit_id}
        streak = 0
        check = date.today()
        while check.isoformat() in logged:
            streak += 1
            check -= timedelta(days=1)
        return streak

    def get_summary(self, days: int = 7) -> list[dict]:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        with self._lock:
            result = []
            for h in self._habits.values():
                recent = [
                    e for e in self._entries
                    if e.habit_id == h.id and e.date >= cutoff
                ]
                result.append({
                    "habit": h,
                    "count": len(recent),
                    "total": sum(e.value for e in recent),
                    "streak": self.get_streak(h.id),
                })
            return result

    def log_time(
        self, activity: str, minutes: float, note: str = ""
    ) -> TimeEntry:
        with self._lock:
            entry = TimeEntry(
                id=uuid.uuid4().hex[:8],
                activity=activity,
                minutes=minutes,
                date=datetime.now().isoformat(timespec="minutes"),
                note=note,
            )
            self._time_log.append(entry)
            self._save()
            return entry

    def get_time_summary(self, days: int = 7) -> list[dict]:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        with self._lock:
            by_activity: dict[str, float] = {}
            for e in self._time_log:
                if e.date[:10] >= cutoff:
                    by_activity[e.activity] = (
                        by_activity.get(e.activity, 0) + e.minutes
                    )
            return sorted(
                [{"activity": a, "minutes": m} for a, m in by_activity.items()],
                key=lambda x: x["minutes"],
                reverse=True,
            )


_inst: HabitStore | None = None
_lock = threading.Lock()


def get_habit_store() -> HabitStore:
    global _inst
    if _inst is None:
        with _lock:
            if _inst is None:
                _inst = HabitStore()
    return _inst
