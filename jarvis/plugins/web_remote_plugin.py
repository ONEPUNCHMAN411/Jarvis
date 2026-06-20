
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class WebRemotePlugin(Plugin):
    """Phone/LAN remote: run a tiny web server so you can talk to JARVIS from a
    phone or any device on the same Wi-Fi network."""

    def __init__(self):
        super().__init__("web_remote")

    async def initialize(self) -> None:
        logger.info("WebRemotePlugin ready (start it with start_web_remote)")

    async def shutdown(self) -> None:
        try:
            from jarvis.control.web_remote import get_web_remote_server
            get_web_remote_server().stop()
        except Exception:
            pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="start_web_remote",
                    description=(
                        "Start the phone/LAN web remote and return the URL to open "
                        "on a phone. Use when the user says 'start the phone remote', "
                        "'let me control you from my phone', 'enable the web remote'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "port": {
                                "type": "integer",
                                "description": "Optional port (default 8765)",
                            }
                        },
                    },
                ),
                self.start_web_remote,
            ),
            (
                ToolDefinition(
                    name="stop_web_remote",
                    description="Stop the phone/LAN web remote server.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.stop_web_remote,
            ),
            (
                ToolDefinition(
                    name="web_remote_status",
                    description="Report whether the web remote is running and its URL.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.web_remote_status,
            ),
        ]

    async def start_web_remote(self, port: int = 8765) -> str:
        from jarvis.control.web_remote import get_web_remote_server
        server = get_web_remote_server()
        if port and int(port) != server.port and not server.is_running():
            server.port = int(port)
        if server.start():
            return (
                f"Phone remote is live. On a device on the same Wi-Fi, open:\n"
                f"  {server.url()}\n"
                f"(Anyone on this network with the URL can send commands — "
                f"stop it with stop_web_remote when done.)"
            )
        return "Could not start the web remote (runtime not ready or port in use)."

    async def stop_web_remote(self, **_) -> str:
        from jarvis.control.web_remote import get_web_remote_server
        get_web_remote_server().stop()
        return "Web remote stopped."

    async def web_remote_status(self, **_) -> str:
        from jarvis.control.web_remote import get_web_remote_server
        server = get_web_remote_server()
        if server.is_running():
            return f"Web remote is running at {server.url()}"
        return "Web remote is not running. Start it with start_web_remote."
