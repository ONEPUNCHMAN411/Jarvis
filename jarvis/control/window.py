"""
Window management — list, focus, minimize, maximize, close windows.
Uses pygetwindow (bundled with pyautogui) + ctypes for reliable focus.
"""

import asyncio
import ctypes
import ctypes.wintypes
from loguru import logger

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False

def _force_foreground(hwnd: int) -> bool:
    """
    SetForegroundWindow often fails if the calling process isn't the foreground.
    This workaround attaches to the foreground thread's input queue first.
    """
    user32 = ctypes.windll.user32
    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_hwnd = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)

    if fg_thread != current_thread:
        user32.AttachThreadInput(fg_thread, current_thread, True)

    # Restore if minimized
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    result = user32.SetForegroundWindow(hwnd)

    if fg_thread != current_thread:
        user32.AttachThreadInput(fg_thread, current_thread, False)

    return bool(result)

class WindowControl:

    async def list_windows(self) -> list[dict]:
        """Return visible windows with title and handle."""
        if not HAS_PYGETWINDOW:
            return [{"error": "pygetwindow not installed"}]

        def _list():
            results = []
            for win in gw.getAllWindows():
                if win.title and win.visible and win.title.strip():
                    results.append({
                        "title": win.title,
                        "hwnd": win._hWnd,
                        "x": win.left,
                        "y": win.top,
                        "width": win.width,
                        "height": win.height,
                    })
            return results

        return await asyncio.to_thread(_list)

    async def get_active_window(self) -> str:
        """Return the title of the currently focused window."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or "(no title)"
        except Exception as e:
            logger.error(f"Get active window failed: {e}")
            return "(unknown)"

    async def focus_window(self, title: str) -> bool:
        """
        Fuzzy-match a window by title substring and bring it to the foreground.
        Returns True if a window was found and focused.
        """
        if not HAS_PYGETWINDOW:
            logger.warning("pygetwindow not available")
            return False

        def _focus():
            title_lower = title.lower().strip()
            # Exact match first
            for win in gw.getAllWindows():
                if win.title and win.title.lower().strip() == title_lower:
                    return _force_foreground(win._hWnd)
            # Substring match
            for win in gw.getAllWindows():
                if win.title and title_lower in win.title.lower():
                    return _force_foreground(win._hWnd)
            return False

        try:
            result = await asyncio.to_thread(_focus)
            if result:
                logger.info(f"Focused window matching '{title}'")
            else:
                logger.warning(f"No window found matching '{title}'")
            return result
        except Exception as e:
            logger.error(f"Focus window failed: {e}")
            return False

    async def minimize_window(self, title: str) -> bool:
        """Minimize a window by title."""
        if not HAS_PYGETWINDOW:
            return False
        try:
            wins = gw.getWindowsWithTitle(title)
            if wins:
                await asyncio.to_thread(wins[0].minimize)
                return True
            return False
        except Exception as e:
            logger.error(f"Minimize failed: {e}")
            return False

    async def maximize_window(self, title: str) -> bool:
        """Maximize a window by title."""
        if not HAS_PYGETWINDOW:
            return False
        try:
            wins = gw.getWindowsWithTitle(title)
            if wins:
                await asyncio.to_thread(wins[0].maximize)
                return True
            return False
        except Exception as e:
            logger.error(f"Maximize failed: {e}")
            return False
