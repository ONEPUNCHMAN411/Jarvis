import asyncio
from loguru import logger
import psutil

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

try:
    import screen_brightness_control as sbc
    HAS_BRIGHTNESS = True
except ImportError:
    HAS_BRIGHTNESS = False

class SystemControl:
    def __init__(self):
        self.has_audio = HAS_PYCAW
        self.has_brightness = HAS_BRIGHTNESS

    async def get_volume(self) -> int:
        if not self.has_audio:
            logger.warning("pycaw not available for volume control")
            return 0

        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, None, None)
            volume = interface.GetMasterVolumeLevelScalar()
            return int(volume * 100)
        except Exception as e:
            logger.error(f"Get volume error: {e}")
            return 0

    async def set_volume(self, level: int) -> None:
        if not self.has_audio:
            logger.warning("pycaw not available for volume control")
            return

        try:
            level = max(0, min(100, level))
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, None, None)
            interface.SetMasterVolumeLevelScalar(level / 100.0, None)
            logger.info(f"Volume set to {level}%")
        except Exception as e:
            logger.error(f"Set volume error: {e}")
            raise

    async def get_brightness(self) -> int:
        if not self.has_brightness:
            logger.warning("screen_brightness_control not available")
            return 0

        try:
            brightness = await asyncio.to_thread(sbc.get_brightness)
            if isinstance(brightness, list):
                return brightness[0]
            return brightness
        except Exception as e:
            logger.error(f"Get brightness error: {e}")
            return 0

    async def set_brightness(self, level: int) -> None:
        if not self.has_brightness:
            logger.warning("screen_brightness_control not available")
            return

        try:
            level = max(0, min(100, level))
            await asyncio.to_thread(sbc.set_brightness, level)
            logger.info(f"Brightness set to {level}%")
        except Exception as e:
            logger.error(f"Set brightness error: {e}")
            raise

    async def get_system_info(self) -> dict:
        try:
            cpu_percent = await asyncio.to_thread(psutil.cpu_percent, interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used": memory.used,
                "memory_total": memory.total,
                "disk_percent": disk.percent,
                "disk_used": disk.used,
                "disk_total": disk.total,
            }
        except Exception as e:
            logger.error(f"Get system info error: {e}")
            return {}

    async def shutdown(self, delay: int = 0) -> None:
        logger.warning(f"System shutdown scheduled in {delay}s")
        await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(__import__("os").system, "shutdown /s /t 1")
        except Exception as e:
            logger.error(f"Shutdown error: {e}")

    async def restart(self, delay: int = 0) -> None:
        logger.warning(f"System restart scheduled in {delay}s")
        await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(__import__("os").system, "shutdown /r /t 1")
        except Exception as e:
            logger.error(f"Restart error: {e}")

    async def lock_screen(self) -> None:
        logger.info("Locking screen")
        try:
            await asyncio.to_thread(__import__("os").system, "rundll32.exe user32.dll,LockWorkStation")
        except Exception as e:
            logger.error(f"Lock screen error: {e}")
