
import os
import threading

import httpx

_BASE = "https://discord.com/api/v10"


class DiscordClient:
    """Thin Discord REST API wrapper for JARVIS plugin use."""

    def __init__(self, token: str = ""):
        self._token = token or os.getenv("DISCORD_BOT_TOKEN", "")
        self._headers: dict[str, str] = {}
        if self._token:
            self._headers = {
                "Authorization": f"Bot {self._token}",
                "Content-Type": "application/json",
            }

    def _check(self) -> None:
        if not self._token:
            raise RuntimeError(
                "Set DISCORD_BOT_TOKEN in your environment. "
                "Create a bot at discord.com/developers/applications"
            )

    def send_message(self, channel_id: str, content: str) -> dict:
        self._check()
        with httpx.Client(headers=self._headers, timeout=10) as c:
            r = c.post(
                f"{_BASE}/channels/{channel_id}/messages",
                json={"content": content},
            )
            r.raise_for_status()
            return r.json()

    def get_messages(self, channel_id: str, limit: int = 10) -> list[dict]:
        self._check()
        with httpx.Client(headers=self._headers, timeout=10) as c:
            r = c.get(
                f"{_BASE}/channels/{channel_id}/messages",
                params={"limit": min(limit, 50)},
            )
            r.raise_for_status()
            return r.json()

    def get_guilds(self) -> list[dict]:
        self._check()
        with httpx.Client(headers=self._headers, timeout=10) as c:
            r = c.get(f"{_BASE}/users/@me/guilds")
            r.raise_for_status()
            return r.json()

    def get_channels(self, guild_id: str) -> list[dict]:
        self._check()
        with httpx.Client(headers=self._headers, timeout=10) as c:
            r = c.get(f"{_BASE}/guilds/{guild_id}/channels")
            r.raise_for_status()
            return r.json()

    def create_dm(self, user_id: str) -> dict:
        self._check()
        with httpx.Client(headers=self._headers, timeout=10) as c:
            r = c.post(
                f"{_BASE}/users/@me/channels",
                json={"recipient_id": user_id},
            )
            r.raise_for_status()
            return r.json()

    def send_dm(self, user_id: str, content: str) -> dict:
        channel = self.create_dm(user_id)
        return self.send_message(channel["id"], content)


_inst: DiscordClient | None = None
_lock = threading.Lock()


def get_discord() -> DiscordClient:
    global _inst
    if _inst is None:
        with _lock:
            if _inst is None:
                _inst = DiscordClient()
    return _inst
