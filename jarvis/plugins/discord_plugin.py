
import asyncio
import os

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class DiscordPlugin(Plugin):
    """Discord integration: send messages, read channels, send DMs."""

    def __init__(self):
        super().__init__("discord")
        self._client = None

    def _get(self):
        if self._client is None:
            from jarvis.brain.discord_client import get_discord
            self._client = get_discord()
        return self._client

    async def initialize(self) -> None:
        if not os.getenv("DISCORD_BOT_TOKEN", ""):
            logger.warning(
                "DiscordPlugin: DISCORD_BOT_TOKEN not set — "
                "tools will error until configured"
            )
        else:
            logger.info("DiscordPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="discord_send",
                    description=(
                        "Send a message to a Discord channel by channel ID. "
                        "Use when user says 'send to Discord', 'post in #general', "
                        "'message the team on Discord', 'tell Discord that ...'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "Discord channel ID (numeric string)",
                            },
                            "message": {
                                "type": "string",
                                "description": "Message content to send",
                            },
                        },
                        "required": ["channel_id", "message"],
                    },
                ),
                self.send_message,
            ),
            (
                ToolDefinition(
                    name="discord_read",
                    description=(
                        "Read recent messages from a Discord channel. "
                        "Use when user says 'what is happening in Discord?', "
                        "'check #general', 'show the latest Discord messages'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "Discord channel ID",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of messages to fetch (default 10)",
                            },
                        },
                        "required": ["channel_id"],
                    },
                ),
                self.read_channel,
            ),
            (
                ToolDefinition(
                    name="discord_dm",
                    description=(
                        "Send a direct message to a Discord user by user ID. "
                        "Use when user says 'DM [name] on Discord', "
                        "'send a direct message to ...'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "string",
                                "description": "Discord user ID (numeric string)",
                            },
                            "message": {
                                "type": "string",
                                "description": "Message content",
                            },
                        },
                        "required": ["user_id", "message"],
                    },
                ),
                self.send_dm,
            ),
            (
                ToolDefinition(
                    name="discord_list_servers",
                    description=(
                        "List all Discord servers the bot is in. "
                        "Use to find server IDs before listing channels."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_servers,
            ),
            (
                ToolDefinition(
                    name="discord_list_channels",
                    description=(
                        "List all text channels in a Discord server. "
                        "Use to find channel IDs before sending messages."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "guild_id": {
                                "type": "string",
                                "description": "Discord server (guild) ID",
                            }
                        },
                        "required": ["guild_id"],
                    },
                ),
                self.list_channels,
            ),
        ]

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
        except Exception as e:
            return f"Discord error: {e}"

    async def send_message(self, channel_id: str, message: str) -> str:
        result = await self._run(self._get().send_message, channel_id, message)
        if isinstance(result, str):
            return result
        return f"Message sent to channel {channel_id}."

    async def read_channel(self, channel_id: str, limit: int = 10) -> str:
        msgs = await self._run(self._get().get_messages, channel_id, limit)
        if isinstance(msgs, str):
            return msgs
        if not msgs:
            return "No messages found."
        lines = [f"Messages in channel {channel_id}:"]
        for m in msgs:
            author = m.get("author", {}).get("username", "?")
            content = m.get("content", "")[:200]
            ts = m.get("timestamp", "")[:16].replace("T", " ")
            lines.append(f"  [{ts}] {author}: {content}")
        return "\n".join(lines)

    async def send_dm(self, user_id: str, message: str) -> str:
        result = await self._run(self._get().send_dm, user_id, message)
        if isinstance(result, str):
            return result
        return f"DM sent to user {user_id}."

    async def list_servers(self) -> str:
        guilds = await self._run(self._get().get_guilds)
        if isinstance(guilds, str):
            return guilds
        if not guilds:
            return "Bot is not in any servers."
        lines = ["Discord servers:"]
        for g in guilds:
            lines.append(f"  {g['name']}  [ID: {g['id']}]")
        return "\n".join(lines)

    async def list_channels(self, guild_id: str) -> str:
        channels = await self._run(self._get().get_channels, guild_id)
        if isinstance(channels, str):
            return channels
        text_ch = [c for c in channels if c.get("type") == 0]
        if not text_ch:
            return f"No text channels found in server {guild_id}."
        lines = [f"Text channels in {guild_id}:"]
        for c in sorted(text_ch, key=lambda x: x.get("position", 0)):
            lines.append(f"  #{c['name']}  [ID: {c['id']}]")
        return "\n".join(lines)
