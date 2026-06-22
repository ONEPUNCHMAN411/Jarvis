
import threading


class TestRunner:
    """Holds a test plan (list of steps) and accumulates pass/fail results so the
    assistant can run through an app's buttons/features and report back."""

    def __init__(self):
        self._name = ""
        self._steps: list[dict] = []
        self._lock = threading.Lock()

    def start(self, name: str, steps: list) -> dict:
        with self._lock:
            self._name = name or "App test"
            self._steps = [
                {"desc": str(s).strip(), "status": "pending", "note": ""}
                for s in steps if str(s).strip()
            ]
        return {"ok": True, "count": len(self._steps), "name": self._name}

    def record(self, step, status: str, note: str = "") -> dict:
        status = (status or "").strip().lower()
        if status not in ("pass", "fail", "skip", "blocked"):
            status = "fail"
        with self._lock:
            target = None
            if isinstance(step, int) or (isinstance(step, str) and step.strip().isdigit()):
                idx = int(step) - 1
                if 0 <= idx < len(self._steps):
                    target = self._steps[idx]
            if target is None:
                q = str(step).strip().lower()
                for s in self._steps:
                    if q and q in s["desc"].lower():
                        target = s
                        break
            if target is None:
                target = {"desc": str(step).strip(), "status": "pending", "note": ""}
                self._steps.append(target)
            target["status"] = status
            target["note"] = note or ""
            return {"ok": True, "desc": target["desc"], "status": status}

    def report(self) -> dict:
        with self._lock:
            counts = {"pass": 0, "fail": 0, "skip": 0, "blocked": 0, "pending": 0}
            for s in self._steps:
                counts[s["status"]] = counts.get(s["status"], 0) + 1
            return {"name": self._name, "steps": [dict(s) for s in self._steps], "counts": counts}

    def clear(self) -> None:
        with self._lock:
            self._name = ""
            self._steps = []


_instance: "TestRunner | None" = None


def get_test_runner() -> "TestRunner":
    global _instance
    if _instance is None:
        _instance = TestRunner()
    return _instance
