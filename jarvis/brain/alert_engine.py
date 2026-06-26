
import json
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

_ALERTS_FILE = Path.home() / ".jarvis" / "alerts.json"

_NOTIFY_AVAILABLE = False
try:
    from plyer import notification as _plyer_notif
    _NOTIFY_AVAILABLE = True
except Exception:
    pass


@dataclass
class Alert:
    id: str
    kind: str          # "time" | "file_exists" | "file_changed" | "interval"
    label: str
    params: dict
    repeat: bool = False
    _last_fired: float = field(default=0.0, repr=False)
    _file_mtime: float = field(default=0.0, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["last_fired"] = self._last_fired
        d["file_mtime"] = self._file_mtime
        del d["_last_fired"]
        del d["_file_mtime"]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Alert":
        a = cls(
            id=d["id"],
            kind=d["kind"],
            label=d["label"],
            params=d.get("params", {}),
            repeat=d.get("repeat", False),
        )
        a._last_fired = d.get("last_fired", 0.0)
        a._file_mtime = d.get("file_mtime", 0.0)
        return a


class AlertEngine:
    """Background thread that fires desktop notifications when alert conditions are met."""

    def __init__(
        self,
        interval: int = 30,
        notify_fn: Callable[[str, str], None] | None = None,
    ):
        self._interval = interval
        self._alerts: dict[str, Alert] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._notify = notify_fn or self._default_notify
        self._load()

    # Persistence

    def _load(self) -> None:
        if not _ALERTS_FILE.exists():
            return
        try:
            data = json.loads(_ALERTS_FILE.read_text(encoding="utf-8"))
            for d in data:
                a = Alert.from_dict(d)
                self._alerts[a.id] = a
            logger.debug(f"AlertEngine: loaded {len(self._alerts)} alerts")
        except Exception as e:
            logger.warning(f"AlertEngine: failed to load alerts: {e}")

    def _save(self) -> None:
        try:
            _ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = [a.to_dict() for a in self._alerts.values()]
            _ALERTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"AlertEngine: failed to save alerts: {e}")

    # Public API

    def add_alert(self, alert: Alert) -> None:
        with self._lock:
            self._alerts[alert.id] = alert
            self._save()

    def remove_alert(self, alert_id: str) -> bool:
        with self._lock:
            if alert_id in self._alerts:
                del self._alerts[alert_id]
                self._save()
                return True
        return False

    def list_alerts(self) -> list[Alert]:
        with self._lock:
            return list(self._alerts.values())

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="AlertEngine"
        )
        self._thread.start()
        logger.info("AlertEngine started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("AlertEngine stopped")

    # Background loop

    def _loop(self) -> None:
        while not self._stop_event.wait(timeout=self._interval):
            self._tick()

    def _tick(self) -> None:
        now = time.time()
        to_remove: list[str] = []
        with self._lock:
            for alert in list(self._alerts.values()):
                try:
                    if self._should_fire(alert, now):
                        self._fire(alert)
                        alert._last_fired = now
                        if not alert.repeat:
                            to_remove.append(alert.id)
                except Exception as e:
                    logger.warning(f"AlertEngine tick error for {alert.id}: {e}")
            for aid in to_remove:
                del self._alerts[aid]
            if to_remove:
                self._save()

    def _should_fire(self, alert: Alert, now: float) -> bool:
        if alert._last_fired > 0 and not alert.repeat:
            return False

        kind = alert.kind
        p = alert.params

        if kind == "time":
            target_str = p.get("datetime", "")
            try:
                target = datetime.fromisoformat(target_str).timestamp()
                return now >= target and alert._last_fired < target
            except Exception:
                return False

        elif kind == "file_exists":
            path = Path(p.get("path", ""))
            return path.exists()

        elif kind == "file_changed":
            path = Path(p.get("path", ""))
            if not path.exists():
                return False
            mtime = path.stat().st_mtime
            if alert._file_mtime == 0.0:
                alert._file_mtime = mtime
                return False
            if mtime != alert._file_mtime:
                alert._file_mtime = mtime
                return True
            return False

        elif kind == "interval":
            seconds = float(p.get("seconds", 3600))
            if alert._last_fired == 0.0:
                return True
            return (now - alert._last_fired) >= seconds

        return False

    def _fire(self, alert: Alert) -> None:
        logger.info(f"AlertEngine firing: [{alert.id}] {alert.label}")
        try:
            self._notify(alert.label, alert.kind)
        except Exception as e:
            logger.warning(f"AlertEngine notify error: {e}")

    @staticmethod
    def _default_notify(title: str, message: str) -> None:
        if _NOTIFY_AVAILABLE:
            _plyer_notif.notify(
                title="JARVIS Alert",
                message=title,
                app_name="JARVIS",
                timeout=8,
            )
        else:
            logger.warning(f"ALERT: {title} ({message})")


# Singleton

_inst: AlertEngine | None = None
_lock = threading.Lock()


def get_alert_engine() -> AlertEngine:
    global _inst
    if _inst is None:
        with _lock:
            if _inst is None:
                _inst = AlertEngine()
    return _inst
