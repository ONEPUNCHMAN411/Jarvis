
import threading
import time

import numpy as np
from loguru import logger

try:
    import mss as _mss
    from PIL import Image
    _HAS_MSS = True
except Exception:
    _HAS_MSS = False


class RegionWatcher:
    """Polls one or more screen rectangles and fires a one-shot alert when a
    region changes ('change') or stops changing after activity ('stable')."""

    def __init__(self, poll_seconds: float = 1.5):
        self._poll = poll_seconds
        self._watches: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self._next_id = 1

    def add(self, x: int, y: int, w: int, h: int, label: str = "",
            mode: str = "change", threshold: float = 0.04,
            stable_seconds: float = 3.0) -> int:
        if not _HAS_MSS:
            return -1
        with self._lock:
            wid = self._next_id
            self._next_id += 1
            self._watches[wid] = {
                "id": wid,
                "bbox": {"left": int(x), "top": int(y), "width": max(1, int(w)), "height": max(1, int(h))},
                "label": label or f"region {wid}",
                "mode": "stable" if mode == "stable" else "change",
                "threshold": float(threshold),
                "stable_seconds": float(stable_seconds),
                "last_sig": None,
                "was_changing": False,
                "stable_since": None,
                "fired": False,
            }
        self._ensure_running()
        return wid

    def list_watches(self) -> list[dict]:
        with self._lock:
            return [
                {"id": w["id"], "label": w["label"], "mode": w["mode"],
                 "bbox": w["bbox"]}
                for w in self._watches.values()
            ]

    def remove(self, wid: int | None = None) -> int:
        with self._lock:
            if wid is None:
                n = len(self._watches)
                self._watches.clear()
                return n
            return 1 if self._watches.pop(wid, None) is not None else 0

    def _ensure_running(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="JarvisRegionWatcher")
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            try:
                with _mss.mss() as sct:
                    with self._lock:
                        items = list(self._watches.values())
                    for w in items:
                        try:
                            sig = self._signature(sct, w["bbox"])
                        except Exception:
                            continue
                        self._process(w, sig)
            except Exception as e:
                logger.debug(f"RegionWatcher loop error: {e}")
            time.sleep(self._poll)
            with self._lock:
                if not self._watches:
                    self._running = False
                    break

    @staticmethod
    def _signature(sct, bbox) -> np.ndarray:
        shot = sct.grab(bbox)
        im = Image.frombytes("RGB", shot.size, shot.rgb).convert("L").resize((24, 24))
        return np.asarray(im, dtype=np.float32)

    def _process(self, w: dict, sig: np.ndarray) -> None:
        last = w["last_sig"]
        w["last_sig"] = sig
        if last is None:
            return
        diff = float(np.mean(np.abs(sig - last))) / 255.0
        now = time.time()
        if w["mode"] == "change":
            if diff >= w["threshold"] and not w["fired"]:
                w["fired"] = True
                self._fire(w, f"changed (delta {diff * 100:.0f}%)")
        else:  # stable — alert when it was moving and then settled
            if diff >= w["threshold"]:
                w["was_changing"] = True
                w["stable_since"] = None
            elif w["was_changing"]:
                if w["stable_since"] is None:
                    w["stable_since"] = now
                elif now - w["stable_since"] >= w["stable_seconds"] and not w["fired"]:
                    w["fired"] = True
                    self._fire(w, "finished (stopped changing)")

    def _fire(self, w: dict, detail: str) -> None:
        with self._lock:
            self._watches.pop(w["id"], None)
        label = w["label"]
        try:
            from plyer import notification
            notification.notify(
                title="JARVIS: Screen watch",
                message=f"{label}: {detail}",
                app_name="JARVIS",
                timeout=12,
            )
        except Exception:
            pass
        try:
            from jarvis.app import get_runtime
            rt = get_runtime()
            if rt is not None:
                rt._emit_ui_event({
                    "type": "log", "level": "info",
                    "message": f"Screen watch '{label}': {detail}",
                })
        except Exception:
            pass


_instance: "RegionWatcher | None" = None


def get_region_watcher() -> "RegionWatcher":
    global _instance
    if _instance is None:
        _instance = RegionWatcher()
    return _instance
