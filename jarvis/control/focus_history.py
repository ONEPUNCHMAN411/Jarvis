import ctypes
import ctypes.wintypes
import threading
import time
from dataclasses import dataclass
from datetime import datetime

_POLL_S = 5.0
_MAX = 30


@dataclass
class FocusEntry:
    app_name: str
    window_title: str
    exe_path: str
    timestamp: str
    ts_epoch: float


class FocusHistoryTracker:
    """Polls the foreground window every 5 s, stores last 30 unique titles."""

    def __init__(self):
        self._entries: list[FocusEntry] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_title = ""
        self._u32 = ctypes.windll.user32

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="focus-hist")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._sample()
            except Exception:
                pass
            time.sleep(_POLL_S)

    def _sample(self):
        hwnd = self._u32.GetForegroundWindow()
        if not hwnd:
            return
        ln = self._u32.GetWindowTextLengthW(hwnd)
        if not ln:
            return
        buf = ctypes.create_unicode_buffer(ln + 1)
        self._u32.GetWindowTextW(hwnd, buf, ln + 1)
        title = buf.value.strip()
        if not title or title == self._last_title:
            return
        self._last_title = title
        pid = ctypes.wintypes.DWORD()
        self._u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app_name, exe_path = "Unknown", ""
        try:
            import psutil
            p = psutil.Process(pid.value)
            app_name = p.name()
            exe_path = p.exe()
        except Exception:
            pass
        entry = FocusEntry(
            app_name=app_name,
            window_title=title,
            exe_path=exe_path,
            timestamp=datetime.now().isoformat(),
            ts_epoch=time.time(),
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > _MAX:
                self._entries.pop(0)

    def get_history(self, limit: int = 30) -> list[FocusEntry]:
        with self._lock:
            return list(reversed(self._entries[-limit:]))

    def get_at_time(self, hour: int, minute: int) -> list[FocusEntry]:
        now = datetime.now()
        target_epoch = now.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()
        with self._lock:
            return [e for e in self._entries if abs(e.ts_epoch - target_epoch) <= 600]

    def refocus(self, query: str) -> bool:
        with self._lock:
            candidates = [
                e for e in reversed(self._entries)
                if query.lower() in e.app_name.lower() or query.lower() in e.window_title.lower()
            ]
        if not candidates:
            return False
        target_title = candidates[0].window_title[:40]
        found = [False]
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def _cb(hwnd, _):
            ln = self._u32.GetWindowTextLengthW(hwnd)
            if not ln:
                return True
            b = ctypes.create_unicode_buffer(ln + 1)
            self._u32.GetWindowTextW(hwnd, b, ln + 1)
            if target_title in b.value:
                self._u32.ShowWindow(hwnd, 9)
                self._u32.SetForegroundWindow(hwnd)
                found[0] = True
                return False
            return True

        try:
            self._u32.EnumWindows(CB(_cb), 0)
        except Exception:
            pass
        return found[0]


_tracker: FocusHistoryTracker | None = None


def get_focus_tracker() -> FocusHistoryTracker:
    global _tracker
    if _tracker is None:
        _tracker = FocusHistoryTracker()
    return _tracker
