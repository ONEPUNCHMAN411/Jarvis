
import asyncio
import os

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class SlackPlugin(Plugin):
    """Slack integration: send messages, read channel history, list channels.
    Needs SLACK_BOT_TOKEN (set it via the Slack connector)."""

    def __init__(self):
        super().__init__("slack")
        self._client = None

    def _get(self):
        if self._client is None:
            from jarvis.brain.slack_client import get_slack
            self._client = get_slack()
        return self._client

    async def initialize(self) -> None:
        if not os.getenv("SLACK_BOT_TOKEN", ""):
            logger.warning(
                "SlackPlugin: SLACK_BOT_TOKEN not set — tools will error until configured"
            )
        else:
            logger.info("SlackPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="slack_send",
                    description=(
                        "Send a message to a Slack channel (by #name or channel ID). "
                        "Use when the user says 'send to Slack', 'post in #general', "
                        "'tell the team on Slack', or 'message ... on Slack'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "description": "Channel name (e.g. #general) or channel/user ID",
                            },
                            "message": {
                                "type": "string",
                                "description": "Message text to send",
                            },
                        },
                        "required": ["channel", "message"],
                    },
                ),
                self.slack_send,
            ),
            (
                ToolDefinition(
                    name="slack_read",
                    description=(
                        "Read recent messages from a Slack channel (by #name or ID). "
                        "Use when the user says 'what's happening in Slack', "
                        "'check #general', or 'show the latest Slack messages'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "description": "Channel name (e.g. #general) or channel ID",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of messages to fetch (default 10)",
                            },
                        },
                        "required": ["channel"],
                    },
                ),
                self.slack_read,
            ),
            (
                ToolDefinition(
                    name="slack_list_channels",
                    description="List Slack channels the bot can access, with their IDs.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.slack_list_channels,
            ),
        ]

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    async def _resolve(self, channel: str) -> str:
        if channel.startswith("#"):
            cid = await self._run(self._get().resolve_channel_id, channel)
            return cid or channel
        return channel

    async def slack_send(self, channel: str, message: str) -> str:
        target = await self._resolve(channel)
        res = await self._run(self._get().post_message, target, message)
        if not res.get("ok"):
            return f"Slack send failed: {res.get('error', 'unknown error')}"
        return f"Message sent to {channel}."

    async def slack_read(self, channel: str, limit: int = 10) -> str:
        target = await self._resolve(channel)
        res = await self._run(self._get().history, target, limit)
        if not res.get("ok"):
            return f"Slack read failed: {res.get('error', 'unknown error')}"
        msgs = res.get("messages", [])
        if not msgs:
            return f"No messages in {channel}."
        lines = [f"Recent messages in {channel}:"]
        for m in reversed(msgs):
            user = m.get("user", m.get("username", "?"))
            text = (m.get("text", "") or "")[:200]
            lines.append(f"  {user}: {text}")
        return "\n".join(lines)

    async def slack_list_channels(self, **_) -> str:
        res = await self._run(self._get().list_channels)
        if not res.get("ok"):
            return f"Slack error: {res.get('error', 'unknown error')}"
        chans = res.get("channels", [])
        if not chans:
            return "No channels found."
        lines = ["Slack channels:"]
        for c in sorted(chans, key=lambda x: x.get("name", "")):
            lines.append(f"  #{c.get('name')}  [ID: {c.get('id')}]")
        return "\n".join(lines)
