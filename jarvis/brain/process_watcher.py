import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class ProcessWatch:
    id: str
    process_name: str
    metric: str
    threshold: float
    cooldown_s: int
    _last_alert: float = field(default=0.0, repr=False)


class ProcessWatcher:
    _POLL = 3.0

    def __init__(self):
        self._watches: list[ProcessWatch] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="proc-watcher")
        self._thread.start()

    def stop(self):
        self._running = False

    def add(self, process_name: str, metric: str, threshold: float, cooldown_s: int = 60) -> str:
        wid = str(uuid.uuid4())[:8]
        with self._lock:
            self._watches.append(ProcessWatch(
                id=wid,
                process_name=process_name.lower(),
                metric=metric.lower(),
                threshold=threshold,
                cooldown_s=cooldown_s,
            ))
        return wid

    def remove(self, key: str) -> bool:
        with self._lock:
            for i, w in enumerate(self._watches):
                if w.id == key or w.process_name == key.lower():
                    self._watches.pop(i)
                    return True
        return False

    def list_all(self) -> list[ProcessWatch]:
        with self._lock:
            return list(self._watches)

    def _loop(self):
        while self._running:
            try:
                self._check()
            except Exception:
                pass
            time.sleep(self._POLL)

    def _check(self):
        import psutil
        now = time.time()
        with self._lock:
            watches = list(self._watches)
        by_name: dict[str, list] = {}
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            try:
                by_name.setdefault(proc.info["name"].lower(), []).append(proc)
            except Exception:
                pass
        for w in watches:
            if now - w._last_alert < w.cooldown_s:
                continue
            for proc in by_name.get(w.process_name, []):
                try:
                    val = proc.cpu_percent(interval=None) if w.metric == "cpu" else proc.memory_info().rss / (1024 * 1024)
                    if val >= w.threshold:
                        w._last_alert = now
                        self._alert(w, val)
                        break
                except Exception:
                    pass

    def _alert(self, w: ProcessWatch, value: float):
        unit = "%" if w.metric == "cpu" else " MB"
        msg = f"{w.process_name} {w.metric.upper()} spike: {value:.1f}{unit} (threshold {w.threshold}{unit})"
        try:
            import plyer
            plyer.notification.notify(title="JARVIS — Process Alert", message=msg, timeout=8)
        except Exception:
            pass
        try:
            from jarvis.app import get_runtime
            rt = get_runtime()
            if rt:
                rt._emit_ui_event({"type": "intel", "text": msg, "level": "warning"})
        except Exception:
            pass


_watcher: ProcessWatcher | None = None


def get_process_watcher() -> ProcessWatcher:
    global _watcher
    if _watcher is None:
        _watcher = ProcessWatcher()
    return _watcher
