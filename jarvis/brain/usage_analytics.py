import ctypes
import ctypes.wintypes
import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_PATH = Path.home() / ".jarvis" / "usage_analytics.json"
_SAMPLE_S = 60.0


class UsageAnalytics:
    """Tracks foreground window focus per minute and persists a rolling
    30-day log. Generates daily totals and weekly heatmaps per app."""

    def __init__(self):
        self._data: dict = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._u32 = ctypes.windll.user32
        self._load()

    def _load(self):
        if _PATH.exists():
            try:
                self._data = json.loads(_PATH.read_text("utf-8"))
            except Exception:
                self._data = {}

    def _save(self):
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(self._data, indent=2), "utf-8")

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="usage-analytics")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._sample()
            except Exception:
                pass
            time.sleep(_SAMPLE_S)

    def _sample(self):
        hwnd = self._u32.GetForegroundWindow()
        if not hwnd:
            return
        ln = self._u32.GetWindowTextLengthW(hwnd)
        if not ln:
            return
        pid = ctypes.wintypes.DWORD()
        self._u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = "Unknown"
        try:
            import psutil
            app = psutil.Process(pid.value).name()
        except Exception:
            pass
        day = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            day_data = self._data.setdefault(day, {})
            day_data[app] = day_data.get(app, 0) + 1
        if int(time.time()) % 600 < 60:
            with self._lock:
                self._save()
            self._prune()

    def _prune(self):
        cutoff = (datetime.now() - timedelta(days=31)).strftime("%Y-%m-%d")
        with self._lock:
            to_del = [d for d in self._data if d < cutoff]
            for d in to_del:
                del self._data[d]

    def daily_report(self, days: int = 7) -> list[dict]:
        result = []
        today = datetime.now().date()
        with self._lock:
            for i in range(days):
                day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                totals = self._data.get(day, {})
                sorted_apps = sorted(totals.items(), key=lambda x: x[1], reverse=True)
                result.append({"date": day, "apps": sorted_apps, "total_min": sum(totals.values())})
        return result

    def weekly_heatmap(self) -> dict[str, dict[str, int]]:
        """Return {app: {YYYY-MM-DD: minutes}} for top 10 apps over last 7 days."""
        today = datetime.now().date()
        days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        totals_by_app: dict[str, int] = defaultdict(int)
        with self._lock:
            for d in days:
                for app, mins in self._data.get(d, {}).items():
                    totals_by_app[app] += mins
        top_apps = sorted(totals_by_app.keys(), key=lambda a: totals_by_app[a], reverse=True)[:10]
        heatmap = {}
        with self._lock:
            for app in top_apps:
                heatmap[app] = {d: self._data.get(d, {}).get(app, 0) for d in reversed(days)}
        return heatmap


_analytics: UsageAnalytics | None = None


def get_usage_analytics() -> UsageAnalytics:
    global _analytics
    if _analytics is None:
        _analytics = UsageAnalytics()
    return _analytics
