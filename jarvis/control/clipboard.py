import asyncio
from collections import deque
from loguru import logger
import pyperclip

class Clipboard:
    def __init__(self, history_size: int = 100):
        self.history = deque(maxlen=history_size)

    async def read(self) -> str:
        try:
            text = await asyncio.to_thread(pyperclip.paste)
            logger.debug(f"Read clipboard: {text[:50]}")
            return text
        except Exception as e:
            logger.error(f"Clipboard read error: {e}")
            raise

    async def write(self, text: str) -> None:
        try:
            await asyncio.to_thread(pyperclip.copy, text)
            self.history.append(text)
            logger.debug(f"Wrote to clipboard: {text[:50]}")
        except Exception as e:
            logger.error(f"Clipboard write error: {e}")
            raise

    async def clear(self) -> None:
        try:
            await asyncio.to_thread(pyperclip.copy, "")
            logger.debug("Clipboard cleared")
        except Exception as e:
            logger.error(f"Clipboard clear error: {e}")
            raise

    def get_history(self) -> list[str]:
        return list(self.history)

    def clear_history(self) -> None:
        self.history.clear()
        logger.debug("Clipboard history cleared")
