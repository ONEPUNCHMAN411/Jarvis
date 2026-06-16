
from datetime import datetime, timedelta


def parse_dt(s: str) -> datetime:
    """Parse a Google Calendar ISO datetime (handles a trailing Z)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def free_slots(busy, win_start: datetime, win_end: datetime, duration_min: int):
    """Return free (start, end) gaps of at least duration_min within the window,
    given a list of (start, end) busy intervals (all timezone-aware)."""
    dur = timedelta(minutes=max(1, int(duration_min)))
    clipped = []
    for s, e in busy:
        s = max(s, win_start)
        e = min(e, win_end)
        if e > s:
            clipped.append((s, e))
    clipped.sort(key=lambda iv: iv[0])

    merged = []
    for s, e in clipped:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    slots = []
    cursor = win_start
    for s, e in merged:
        if s - cursor >= dur:
            slots.append((cursor, s))
        cursor = max(cursor, e)
    if win_end - cursor >= dur:
        slots.append((cursor, win_end))
    return slots
