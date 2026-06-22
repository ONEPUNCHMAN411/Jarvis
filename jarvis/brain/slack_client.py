
import json
import os
import threading
import urllib.parse
import urllib.request

_API = "https://slack.com/api/"


class SlackClient:
    """Minimal Slack Web API client (chat.postMessage, conversations.*).

    Requires a bot token in SLACK_BOT_TOKEN with scopes: chat:write,
    channels:read, channels:history (and groups:* for private channels).
    """

    def __init__(self, token: str | None = None):
        self._token = token or os.getenv("SLACK_BOT_TOKEN", "")

    def _call(self, method: str, params: dict, post: bool = True) -> dict:
        if not self._token:
            return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}
        url = _API + method
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            if post:
                data = json.dumps(params).encode("utf-8")
                headers["Content-Type"] = "application/json; charset=utf-8"
                req = urllib.request.Request(url, data=data, headers=headers)
            else:
                if params:
                    url = url + "?" + urllib.parse.urlencode(params)
                req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def post_message(self, channel: str, text: str) -> dict:
        return self._call("chat.postMessage", {"channel": channel, "text": text})

    def history(self, channel: str, limit: int = 10) -> dict:
        return self._call(
            "conversations.history",
            {"channel": channel, "limit": limit},
            post=False,
        )

    def list_channels(self, limit: int = 200) -> dict:
        return self._call(
            "conversations.list",
            {"limit": limit, "types": "public_channel,private_channel"},
            post=False,
        )

    def resolve_channel_id(self, name: str) -> "str | None":
        name = name.lstrip("#").strip().lower()
        data = self.list_channels()
        if not data.get("ok"):
            return None
        for ch in data.get("channels", []):
            if ch.get("name", "").lower() == name:
                return ch.get("id")
        return None


_instance: "SlackClient | None" = None
_lock = threading.Lock()


def get_slack() -> "SlackClient":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = SlackClient()
    return _instance
