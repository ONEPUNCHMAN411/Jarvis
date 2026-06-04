"""
Text-based screen description for non-vision AI providers.

Instead of sending a screenshot image, extracts structured text describing:
- Active window title and application
- Focused element (what the user has selected/highlighted)
- Visible UI elements via Windows Accessibility API (pywinauto)
- Clipboard content
- Mouse cursor position
- Running processes relevant to current task
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

class ScreenReader:
    """Text-based screen description for non-vision providers."""

    async def describe_screen(self, max_elements: int = 30) -> str:
        """
        Returns a multi-line text description of the current screen state.
        Includes active window, focused element, and visible UI elements.
        """
        return await asyncio.to_thread(self._describe_screen_sync, max_elements)

    def _describe_screen_sync(self, max_elements: int = 30) -> str:
        """Synchronous screen description."""
        parts = []

        # Get active window info
        try:
            win_info = self._get_active_window_info_sync()
            if win_info:
                parts.append(f"Active Window: \"{win_info['title']}\"")
                parts.append(f"Application: {win_info['app_name']}")
                rect = win_info.get("rect", {})
                if rect:
                    parts.append(f"Window position: ({rect['x']}, {rect['y']}) "
                               f"size: ({rect['w']}x{rect['h']})")
        except Exception as e:
            logger.debug(f"Error getting active window info: {e}")

        # Get mouse position
        try:
            import pyautogui
            x, y = pyautogui.position()
            # Calculate if near center of typical screen
            dist_from_center = math.sqrt((x - 960)**2 + (y - 540)**2)
            if dist_from_center < 200:
                position_desc = f"({x}, {y}) [near center]"
            else:
                position_desc = f"({x}, {y})"
            parts.append(f"Mouse position: {position_desc}")
        except Exception:
            pass

        # Get focused element
        try:
            focused = self._get_focused_element_sync()
            if focused:
                parts.append(f"\nFocused element: {focused['name']} "
                           f"({focused['type']}) at ({focused['bounds']['x']}, "
                           f"{focused['bounds']['y']})")
                if focused.get("value"):
                    parts.append(f"Value: {focused['value'][:100]}")
        except Exception as e:
            logger.debug(f"Error getting focused element: {e}")

        # Get UI elements
        try:
            elements = self._get_window_elements_sync(max_elements=max_elements)
            if elements and not any("error" in el for el in elements if isinstance(el, dict)):
                parts.append(f"\nVisible UI elements (top {len(elements)}):")
                for i, el in enumerate(elements, 1):
                    if isinstance(el, dict) and "error" not in el:
                        name = el.get("name", "")[:50]
                        type_ = el.get("type", "")
                        bounds = el.get("bounds", {})
                        x = bounds.get("x", 0)
                        y = bounds.get("y", 0)
                        w = bounds.get("w", 0)
                        h = bounds.get("h", 0)
                        enabled = el.get("enabled", True)
                        status = "" if enabled else " [disabled]"
                        if name or type_:
                            parts.append(f"  {i}. [{type_}] {name} at ({x}, {y}) "
                                       f"{w}x{h}{status}")
                            # Add value if it exists
                            val = el.get("value", "")
                            if val and len(val) < 100:
                                parts.append(f"     Value: {val}")
        except Exception as e:
            logger.debug(f"Error getting UI elements: {e}")

        return "\n".join(parts) if parts else "Could not read screen state."

    async def get_active_window_info(self) -> dict:
        """Get info about the active/foreground window."""
        return await asyncio.to_thread(self._get_active_window_info_sync)

    def _get_active_window_info_sync(self) -> dict:
        """Synchronous version using ctypes."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return {}

            # Get window title (W suffix required on Python 3.14+)
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value or "Unknown"

            # Get window rect
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))

            # Get process name via pywinauto if available
            app_name = "unknown"
            if HAS_PYWINAUTO:
                try:
                    app = Application(backend="uia").connect(handle=hwnd)
                    app_name = app.process
                except Exception:
                    pass

            return {
                "title": title,
                "app_name": str(app_name),
                "pid": hwnd,
                "rect": {
                    "x": rect.left,
                    "y": rect.top,
                    "w": rect.right - rect.left,
                    "h": rect.bottom - rect.top,
                },
            }
        except Exception as e:
            logger.error(f"Error getting active window info: {e}")
            return {}

    async def get_focused_element(self) -> dict | None:
        """Get the currently focused UI element."""
        return await asyncio.to_thread(self._get_focused_element_sync)

    def _get_focused_element_sync(self) -> dict | None:
        """Synchronous version using pywinauto."""
        if not HAS_PYWINAUTO:
            return None

        try:
            desktop = Desktop(backend="uia")
            focused = desktop.element_from_point(0, 0)  # Get focused from UIA
            if not focused:
                return None

            el_info = focused.element_info
            rect = focused.rectangle()

            return {
                "name": el_info.name or "",
                "type": el_info.control_type or "",
                "value": (focused.get_value() if hasattr(focused, "get_value") else ""),
                "bounds": {
                    "x": rect.left,
                    "y": rect.top,
                    "w": rect.width(),
                    "h": rect.height(),
                },
            }
        except Exception as e:
            logger.debug(f"Error getting focused element: {e}")
            return None

    async def click_element_by_name(
        self, name: str, window_title: str = ""
    ) -> str:
        """Find and click an element by its accessibility name."""
        return await asyncio.to_thread(
            self._click_element_by_name_sync, name, window_title
        )

    def _click_element_by_name_sync(self, name: str, window_title: str = "") -> str:
        """Synchronous version."""
        if not HAS_PYWINAUTO:
            return "Error: pywinauto not installed — run: pip install pywinauto"

        try:
            import pyautogui

            desktop = Desktop(backend="uia")
            if window_title:
                try:
                    window = desktop.window(title_re=f".*{window_title}.*", found_index=0)
                    wrapper = window.wrapper_object()
                except ElementNotFoundError:
                    return f"No window found matching '{window_title}'"
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
            return f"Clicked element '{name}' at ({cx}, {cy})"

        except Exception as e:
            logger.error(f"Error clicking element: {e}")
            return f"Error: {e}"

    async def type_into_element(
        self, name: str, text: str, window_title: str = ""
    ) -> str:
        """Find an element by name and type text into it."""
        return await asyncio.to_thread(
            self._type_into_element_sync, name, text, window_title
        )

    def _type_into_element_sync(
        self, name: str, text: str, window_title: str = ""
    ) -> str:
        """Synchronous version."""
        if not HAS_PYWINAUTO:
            return "Error: pywinauto not installed — run: pip install pywinauto"

        try:
            desktop = Desktop(backend="uia")
            if window_title:
                try:
                    window = desktop.window(title_re=f".*{window_title}.*", found_index=0)
                    wrapper = window.wrapper_object()
                except ElementNotFoundError:
                    return f"No window found matching '{window_title}'"
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

            # Type into element
            found_el.type_keys(text)
            return f"Typed into element '{name}'"

        except Exception as e:
            logger.error(f"Error typing into element: {e}")
            return f"Error: {e}"

    def _get_window_elements_sync(self, max_elements: int = 50) -> list[dict]:
        """Get all UI elements in the active window."""
        if not HAS_PYWINAUTO:
            return [{"error": "pywinauto not installed — run: pip install pywinauto"}]

        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return [{"error": "No foreground window"}]

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
        except Exception as e:
            logger.error(f"Error getting window elements: {e}")
            return [{"error": str(e)}]
