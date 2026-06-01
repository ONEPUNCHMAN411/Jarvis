import asyncio
import inspect
from collections import deque
from typing import Any, Callable
from loguru import logger

class EventBus:
    def __init__(self, history_size: int = 100):
        self._subscribers: dict[type, list[Callable]] = {}
        self._history: deque = deque(maxlen=history_size)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__name__} to {event_type.__name__}")

    def unsubscribe(self, event_type: type, handler: Callable) -> None:
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(handler)
            logger.debug(f"Unsubscribed {handler.__name__} from {event_type.__name__}")

    async def publish(self, event: Any) -> None:
        event_type = type(event)
        self._history.append(event)
        quiet_events = {"MicLevelEvent", "RuntimeLogEvent"}

        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            if event_type.__name__ not in quiet_events:
                logger.debug(f"No handlers for {event_type.__name__}")
            return

        if event_type.__name__ not in quiet_events:
            logger.debug(f"Publishing {event_type.__name__} to {len(handlers)} handlers")

        tasks = []
        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                tasks.append(handler(event))
            else:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in sync handler {handler.__name__}: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error in async handler: {result}")

    def get_history(self, event_type: type | None = None) -> list:
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if isinstance(e, event_type)]
