"""
Windows UI Automation reader for desktop app accessibility.

Uses pywinauto to read the accessibility tree of windows, enabling JARVIS
to understand what's on screen without relying solely on screenshots + vision.
"""

import asyncio
import ctypes
import math
from loguru import logger

try:
    from pywinauto import Desktop, Application
    from pywinauto.findwindows import ElementNotFoundError
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False

class AccessibilityReader:

    async def get_window_elements(
        self, title: str = "", max_elements: int = 50
    ) -> list[dict]:
        if not HAS_PYWINAUTO:
            return [{"error": "pywinauto not installed — run: pip install pywinauto"}]

        def _read():
            desktop = Desktop(backend="uia")
            if title:
                try:
                    window = desktop.window(title_re=f".*{title}.*", found_index=0)
                    wrapper = window.wrapper_object()
                except ElementNotFoundError:
                    return [{"error": f"No window found matching '{title}'"}]
            else:
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if not hwnd:
                    return [{"error": "No foreground window"}]
                from pywinauto import Application
                app = Application(backend="uia").connect(handle=hwnd)
                wrapper = app.top_window().wrapper_object()

            elements = []
            try:
                for child in wrapper.descendants():
                    if len(elements) >= max_elements:
                        break
                    try:
                        ctrl_type = child.element_info.control_type or ""
                        name = child.element_info.name or ""
                        if not name and ctrl_type in ("Pane", "Group", "Custom"):
                            continue
                        rect = child.rectangle()
                        elements.append({
                            "name": name[:80],
                            "type": ctrl_type,
                            "value": (child.get_value() if hasattr(child, "get_value") else "")[:200],
                            "bounds": {
                                "x": rect.left,
                                "y": rect.top,
                                "w": rect.width(),
                                "h": rect.height(),
                            },
                            "enabled": child.is_enabled(),
                        })
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Error reading descendants: {e}")

            return elements

        try:
            return await asyncio.to_thread(_read)
        except Exception as e:
            logger.error(f"Accessibility read failed: {e}")
            return [{"error": str(e)}]

    async def find_element(
        self, name: str, title: str = ""
    ) -> dict | None:
        elements = await self.get_window_elements(title=title, max_elements=100)
        name_lower = name.lower()
        for el in elements:
            if isinstance(el, dict) and "error" not in el:
                el_name = (el.get("name") or "").lower()
                if name_lower in el_name:
                    return el
        return None

    async def get_screen_text_description(self, max_elements: int = 30) -> str:
        """Get a readable text description of the current screen state.

        Returns a multi-line string describing:
        - Active window title and app
        - Focused element
        - Visible UI elements with names, types, and coordinates
        """
        parts = []

        # Get active window info
        try:
            win_info = await self.get_active_app()
            if win_info:
                parts.append(f"Active Window: \"{win_info.get('title', 'Unknown')}\"")
                if win_info.get('app'):
                    parts.append(f"Application: {win_info['app']}")
        except Exception as e:
            logger.debug(f"Error getting active window: {e}")

        # Get mouse position
        try:
            import pyautogui
            x, y = pyautogui.position()
            dist_from_center = math.sqrt((x - 960)**2 + (y - 540)**2)
            if dist_from_center < 200:
                position_desc = f"({x}, {y}) [near center]"
            else:
                position_desc = f"({x}, {y})"
            parts.append(f"Mouse position: {position_desc}")
        except Exception:
            pass

        # Get UI elements
        try:
            elements = await self.get_window_elements(title="", max_elements=max_elements)
            if elements and not any("error" in el for el in elements if isinstance(el, dict)):
                parts.append(f"\nVisible UI elements (top {len(elements)}):")
                for i, el in enumerate(elements, 1):
                    if isinstance(el, dict) and "error" not in el:
                        name = (el.get("name") or "")[:50]
                        type_ = el.get("type", "")
                        bounds = el.get("bounds", {})
                        x = bounds.get("x", 0)
                        y = bounds.get("y", 0)
                        w = bounds.get("w", 0)
                        h = bounds.get("h", 0)
                        enabled = el.get("enabled", True)
                        status = "" if enabled else " [disabled]"
                        if name or type_:
                            parts.append(f"  {i}. [{type_}] {name} at ({x}, {y}) {w}x{h}{status}")
                            # Add value if present and short
                            val = el.get("value", "")
                            if val and len(val) < 100:
                                parts.append(f"     Value: {val}")
        except Exception as e:
            logger.debug(f"Error getting UI elements: {e}")

        return "\n".join(parts) if parts else "Could not read screen state."

    async def click_by_name(self, name: str, title: str = "") -> str:
        """Find an element by name and click it."""
        def _click():
            if not HAS_PYWINAUTO:
                return "Error: pywinauto not installed"

            try:
                import pyautogui
                desktop = Desktop(backend="uia")
                if title:
                    try:
                        window = desktop.window(title_re=f".*{title}.*", found_index=0)
                        wrapper = window.wrapper_object()
                    except ElementNotFoundError:
                        return f"No window found matching '{title}'"
                else:
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if not hwnd:
                        return "No foreground window"
                    app = Application(backend="uia").connect(handle=hwnd)
                    wrapper = app.top_window().wrapper_object()

                # Find element by name
                name_lower = name.lower()
                found_el = None
                for child in wrapper.descendants():
                    if (child.element_info.name or "").lower() == name_lower:
                        found_el = child
                        break

                if not found_el:
                    return f"No element found with name '{name}'"

                # Click center of element
                rect = found_el.rectangle()
                cx = rect.left + rect.width() // 2
                cy = rect.top + rect.height() // 2
                pyautogui.click(cx, cy)
                return f"Clicked '{name}' at ({cx}, {cy})"

            except Exception as e:
                logger.error(f"Error clicking element: {e}")
                return f"Error: {e}"

        return await asyncio.to_thread(_click)

    async def get_active_app(self) -> dict:
        """Get title and app name of the currently active window."""
        def _get_active():
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if not hwnd:
                    return {}

                # Get window title
                length = ctypes.windll.user32.GetWindowTextLength(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowText(hwnd, buf, length + 1)
                title = buf.value or "Unknown"

                # Get process name
                app_name = "unknown"
                if HAS_PYWINAUTO:
                    try:
                        app = Application(backend="uia").connect(handle=hwnd)
                        app_name = str(app.process)
                    except Exception:
                        pass

                return {"title": title, "app": app_name}

            except Exception as e:
                logger.error(f"Error getting active app: {e}")
                return {}

        return await asyncio.to_thread(_get_active)
