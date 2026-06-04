import asyncio
from loguru import logger
import pyautogui

class Mouse:
    def __init__(self, failsafe: bool = False):
        # Disabled by default — corner-triggered FailSafeException would surface
        # as a tool failure and confuse the AI into a retry loop.
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = 0.05

    async def move(self, x: int, y: int, duration: float = 0.2) -> None:
        logger.debug(f"Moving mouse to ({x}, {y})")
        try:
            await asyncio.to_thread(pyautogui.moveTo, x, y, duration=duration)
        except Exception as e:
            logger.error(f"Mouse move error: {e}")
            raise

    async def click(self, x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.1) -> None:
        logger.debug(f"Clicking at ({x}, {y}) - {button} ({clicks}x)")
        try:
            await asyncio.to_thread(
                pyautogui.click, x, y, clicks=clicks, interval=interval, button=button
            )
        except Exception as e:
            logger.error(f"Mouse click error: {e}")
            raise

    async def double_click(self, x: int, y: int, button: str = "left") -> None:
        logger.debug(f"Double clicking at ({x}, {y})")
        await self.click(x, y, button=button, clicks=2, interval=0.1)

    async def right_click(self, x: int, y: int) -> None:
        logger.debug(f"Right clicking at ({x}, {y})")
        await self.click(x, y, button="right", clicks=1)

    async def triple_click(self, x: int, y: int) -> None:
        """Triple click to select an entire line."""
        logger.debug(f"Triple clicking at ({x}, {y})")
        await self.click(x, y, button="left", clicks=3, interval=0.05)

    async def scroll(self, x: int, y: int, clicks: int, direction: str = "down") -> None:
        logger.debug(f"Scrolling {direction} at ({x}, {y}) - {clicks}x")
        try:
            # pyautogui: positive = scroll up, negative = scroll down
            if direction in ["down", "right"]:
                amount = -clicks
            else:
                amount = clicks
            await asyncio.to_thread(pyautogui.scroll, amount, x=x, y=y)
        except Exception as e:
            logger.error(f"Scroll error: {e}")
            raise

    async def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 1.0, button: str = "left") -> None:
        logger.debug(f"Dragging from ({x1}, {y1}) to ({x2}, {y2})")
        try:
            await asyncio.to_thread(
                pyautogui.drag, x2 - x1, y2 - y1, duration=duration, button=button
            )
        except Exception as e:
            logger.error(f"Drag error: {e}")
            raise

    async def get_position(self) -> tuple[int, int]:
        try:
            pos = await asyncio.to_thread(pyautogui.position)
            return pos
        except Exception as e:
            logger.error(f"Get position error: {e}")
            raise
