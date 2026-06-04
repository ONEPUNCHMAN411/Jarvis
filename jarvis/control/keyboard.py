import asyncio
from loguru import logger
from pynput.keyboard import Controller, Key

class Keyboard:
    def __init__(self):
        self.controller = Controller()

    async def type_text(self, text: str, interval: float = 0.02) -> None:
        logger.debug(f"Typing: {text[:50]}")
        # Fast path: clipboard paste for text > 10 chars (100x faster)
        if len(text) > 10:
            try:
                import subprocess, os
                # Pass text via env variable — avoids all quoting/escaping issues.
                env = os.environ.copy()

                # Save current clipboard
                proc = subprocess.run(
                    ["powershell", "-c", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=2,
                )
                old_clip = proc.stdout.rstrip('\n')

                # Set clipboard to our text
                env["_JCLIP"] = text
                subprocess.run(
                    ["powershell", "-c", "Set-Clipboard -Value $env:_JCLIP"],
                    env=env, timeout=2, capture_output=True,
                )
                await asyncio.sleep(0.05)

                # Ctrl+V paste
                await self.hotkey("ctrl", "v")
                await asyncio.sleep(0.1)

                # Restore old clipboard
                if old_clip:
                    env["_JCLIP"] = old_clip
                    subprocess.run(
                        ["powershell", "-c", "Set-Clipboard -Value $env:_JCLIP"],
                        env=env, timeout=2, capture_output=True,
                    )
                logger.debug("Fast-typed via clipboard paste")
                return
            except Exception as exc:
                logger.debug(f"Clipboard paste failed, falling back to char-by-char: {exc}")

        # Slow fallback: character-by-character
        try:
            for char in text:
                await asyncio.to_thread(self.controller.type, char)
                if interval > 0:
                    await asyncio.sleep(interval)
        except Exception as e:
            logger.error(f"Type error: {e}")
            raise

    async def press_key(self, key_name: str) -> None:
        logger.debug(f"Pressing key: {key_name}")
        try:
            key_map = {
                "enter": Key.enter,
                "space": Key.space,
                "backspace": Key.backspace,
                "delete": Key.delete,
                "tab": Key.tab,
                "escape": Key.esc,
                "esc": Key.esc,
                "home": Key.home,
                "end": Key.end,
                "page_up": Key.page_up,
                "page_down": Key.page_down,
                "up": Key.up,
                "down": Key.down,
                "left": Key.left,
                "right": Key.right,
                "ctrl": Key.ctrl,
                "shift": Key.shift,
                "alt": Key.alt,
                "cmd": Key.cmd,
                "win": Key.cmd,
                "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4,
                "f5": Key.f5, "f6": Key.f6, "f7": Key.f7, "f8": Key.f8,
                "f9": Key.f9, "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
            }

            # Handle combo keys like "ctrl+c", "alt+tab"
            parts = [p.strip().lower() for p in key_name.split("+")]
            if len(parts) > 1:
                await self.hotkey(*parts)
                return

            key = key_map.get(parts[0])
            if key is None:
                # Try as a character key
                if len(parts[0]) == 1:
                    await asyncio.to_thread(self.controller.press, parts[0])
                    await asyncio.sleep(0.1)
                    await asyncio.to_thread(self.controller.release, parts[0])
                else:
                    logger.warning(f"Unknown key: {key_name}")
                return

            await asyncio.to_thread(self.controller.press, key)
            await asyncio.sleep(0.1)
            await asyncio.to_thread(self.controller.release, key)

        except Exception as e:
            logger.error(f"Key press error: {e}")
            raise

    async def hotkey(self, *keys: str) -> None:
        logger.debug(f"Hotkey: {'+'.join(keys)}")
        try:
            key_map = {
                "ctrl": Key.ctrl,
                "shift": Key.shift,
                "alt": Key.alt,
                "cmd": Key.cmd,
            }

            pressed_keys = []
            for key_name in keys[:-1]:
                key = key_map.get(key_name.lower(), key_name)
                await asyncio.to_thread(self.controller.press, key)
                pressed_keys.append(key)

            last_raw = keys[-1].lower()
            special_tail = {
                "enter": Key.enter,
                "space": Key.space,
                "tab": Key.tab,
                "escape": Key.esc,
                "esc": Key.esc,
                "backspace": Key.backspace,
                "delete": Key.delete,
                "home": Key.home,
                "end": Key.end,
                "page_up": Key.page_up,
                "page_down": Key.page_down,
                "up": Key.up,
                "down": Key.down,
                "left": Key.left,
                "right": Key.right,
                "f1": Key.f1,
                "f2": Key.f2,
                "f3": Key.f3,
                "f4": Key.f4,
                "f5": Key.f5,
                "f6": Key.f6,
                "f7": Key.f7,
                "f8": Key.f8,
                "f9": Key.f9,
                "f10": Key.f10,
                "f11": Key.f11,
                "f12": Key.f12,
            }
            last_mapped = special_tail.get(last_raw)
            if last_mapped is not None:
                await asyncio.to_thread(self.controller.press, last_mapped)
                await asyncio.sleep(0.08)
                await asyncio.to_thread(self.controller.release, last_mapped)
            elif len(last_raw) == 1:
                await asyncio.to_thread(self.controller.press, last_raw)
                await asyncio.sleep(0.08)
                await asyncio.to_thread(self.controller.release, last_raw)
            else:
                logger.warning(f"Unknown hotkey tail key: {last_raw}")

            for key in reversed(pressed_keys):
                await asyncio.to_thread(self.controller.release, key)

        except Exception as e:
            logger.error(f"Hotkey error: {e}")
            raise
