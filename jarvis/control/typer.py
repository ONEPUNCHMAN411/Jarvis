"""General-purpose text typer with WPM control and reliable window focus."""


import asyncio
import random
import time

import pyautogui


def _human_delay(base: float) -> float:
    r = random.random()
    if r < 0.03:
        return base * random.uniform(8, 25)
    elif r < 0.12:
        return base * random.uniform(1.8, 3.5)
    elif r < 0.28:
        return base * random.uniform(0.4, 0.7)
    return max(0.01, base * random.gauss(1.0, 0.22))


def _type_char(ch: str) -> None:
    if ch == "\n":
        pyautogui.press("enter")
    elif ch == "\t":
        pyautogui.press("tab")
    else:
        try:
            pyautogui.write(ch, interval=0)
        except Exception:
            try:
                import pyperclip
                pyperclip.copy(ch)
                pyautogui.hotkey("ctrl", "v")
            except Exception:
                pass


def _type_string_sync(text: str, base_delay: float, humanize: bool,
                       stop_flag: list) -> int:
    typed = 0
    for ch in text:
        if stop_flag[0]:
            break
        _type_char(ch)
        typed += 1
        delay = _human_delay(base_delay) if humanize else base_delay
        if ch == "\n" and humanize:
            delay += base_delay * random.uniform(1.5, 5.0)
        time.sleep(max(0.008, delay))
    return typed


def _find_window(title_fragment: str) -> int | None:
    try:
        import win32gui
        result = [None]

        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if title_fragment.lower() in t.lower():
                    result[0] = hwnd

        win32gui.EnumWindows(cb, None)
        return result[0]
    except Exception:
        return None


def _focus_hwnd(hwnd: int) -> bool:
    try:
        import win32gui, win32con, win32process, win32api
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        fg = win32gui.GetForegroundWindow()
        fg_tid = win32process.GetWindowThreadProcessId(fg)[0]
        my_tid = win32api.GetCurrentThreadId()
        if fg_tid and fg_tid != my_tid:
            win32process.AttachThreadInput(fg_tid, my_tid, True)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            win32process.AttachThreadInput(fg_tid, my_tid, False)
        else:
            win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.35)
        return True
    except Exception:
        return False


async def type_text_at_wpm(
    text: str,
    wpm: int = 45,
    window_title: str | None = None,
    humanize: bool = True,
    countdown: int = 3,
) -> dict:
    """Type text at the given WPM into the focused or named window.

    Works with any application that accepts keyboard input — documents,
    forms, browsers, chat apps, text editors, and so on.

    window_title: optional fragment of the target window's title bar text.
    If provided, JARVIS will focus that window before typing starts.

    countdown: seconds to wait before typing begins, giving the user time
    to click the target window.

    Returns {"success": bool, "chars_typed": int, "message": str}.
    """
    if not text:
        return {"success": False, "chars_typed": 0, "message": "No text provided."}

    base_delay = 60.0 / (max(1, wpm) * 5)
    hwnd = None

    if window_title:
        hwnd = _find_window(window_title)
        if not hwnd:
            return {
                "success": False,
                "chars_typed": 0,
                "message": f"Window '{window_title}' not found.",
            }

    for _ in range(countdown, 0, -1):
        await asyncio.sleep(1)

    if hwnd:
        if not _focus_hwnd(hwnd):
            return {
                "success": False,
                "chars_typed": 0,
                "message": f"Could not focus window '{window_title}'.",
            }
        await asyncio.sleep(0.2)

    stop_flag = [False]
    loop = asyncio.get_running_loop()
    chars = await loop.run_in_executor(
        None,
        lambda: _type_string_sync(text, base_delay, humanize, stop_flag),
    )

    return {
        "success": True,
        "chars_typed": chars,
        "message": f"Typed {chars} characters at ~{wpm} WPM.",
    }
