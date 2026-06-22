
import threading

from loguru import logger


class DictationManager:
    """Voice dictation: capture one spoken phrase using JARVIS's shared speech
    engine and type it straight into whatever app is focused."""

    def __init__(self):
        self._busy = False

    async def dictate_once(self) -> str:
        from jarvis.app import get_runtime
        runtime = get_runtime()
        if runtime is None or getattr(runtime, "voice_manager", None) is None:
            return "Voice subsystem is not ready yet."
        vm = runtime.voice_manager
        if not getattr(vm, "is_running", False):
            return "Voice capture is not running."
        if self._busy:
            return "Dictation is already in progress."

        self._busy = True
        paused = False
        text = ""
        try:
            await vm.stop_listening()
            paused = True
            try:
                vm._drain_stale_audio()
            except Exception:
                pass
            text = await vm._capture_phrase()
        except Exception as e:
            logger.warning(f"Dictation capture failed: {e}")
            return f"Dictation error: {e}"
        finally:
            self._busy = False
            if paused and getattr(vm, "enabled", False):
                try:
                    await vm.start_listening()
                except Exception:
                    pass

        if not text or not text.strip():
            return "Didn't catch anything to type."

        clean = text.strip()
        try:
            from jarvis.control.keyboard import Keyboard
            await Keyboard().type_text(clean)
        except Exception as e:
            return f"Heard '{clean}' but could not type it: {e}"
        return f"Dictated: {clean}"


_instance: "DictationManager | None" = None
_lock = threading.Lock()


def get_dictation_manager() -> "DictationManager":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = DictationManager()
    return _instance
