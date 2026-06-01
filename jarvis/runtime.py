import asyncio
import threading
from concurrent.futures import Future

from jarvis.event_bus import EventBus

class AsyncRuntimeService:
    """Owns a dedicated asyncio loop for background assistant work."""

    def __init__(self):
        self.bus = EventBus()
        self._loop = None
        self._thread = None
        self._started = threading.Event()

    @property
    def loop(self):
        return self._loop

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._started.clear()

        def runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._started.set()
            self._loop.run_forever()

            pending = asyncio.all_tasks(self._loop)
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.close()

        self._thread = threading.Thread(
            target=runner,
            name="JarvisAsyncRuntime",
            daemon=True,
        )
        self._thread.start()
        self._started.wait(timeout=5)
        if self._loop is None:
            raise RuntimeError("Async runtime failed to start")

    def submit(self, coroutine) -> Future:
        if self._loop is None:
            raise RuntimeError("Async runtime not started")
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def stop(self) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None
