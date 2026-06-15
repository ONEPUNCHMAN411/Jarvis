"""
Global hotkey registration via pynput.

Listens for Ctrl+Shift+J (configurable) in the background and fires a callback
so the user can wake JARVIS from any application without speaking the wake phrase.
"""

from loguru import logger

try:
    from pynput import keyboard as _pynput_keyboard
    _PYNPUT_AVAILABLE = True
except Exception:
    _PYNPUT_AVAILABLE = False

class GlobalHotkey:
    """Register a global hotkey that fires on every press, regardless of focus."""

    def __init__(self, hotkey: str = "<ctrl>+<shift>+j", callback=None):
        self._hotkey_str = hotkey
        self._callback = callback
        self._listener = None
        self._hotkey = None

    def start(self) -> bool:
        if not _PYNPUT_AVAILABLE:
            logger.warning("pynput not available — global hotkey disabled")
            return False
        try:
            self._hotkey = _pynput_keyboard.HotKey(
                _pynput_keyboard.HotKey.parse(self._hotkey_str),
                self._on_activate,
            )

            def _on_press(key):
                try:
                    self._hotkey.press(self._listener.canonical(key))
                except Exception:
                    pass

            def _on_release(key):
                try:
                    self._hotkey.release(self._listener.canonical(key))
                except Exception:
                    pass

            self._listener = _pynput_keyboard.Listener(
                on_press=_on_press,
                on_release=_on_release,
            )
            self._listener.daemon = True
            self._listener.start()
            logger.info(f"Global hotkey registered: {self._hotkey_str}")
            return True
        except Exception as exc:
            logger.warning(f"Global hotkey registration failed: {exc}")
            return False

    def stop(self) -> None:
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _on_activate(self) -> None:
        if self._callback:
            try:
                self._callback()
            except Exception as exc:
                logger.debug(f"Hotkey callback error: {exc}")
