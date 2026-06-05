"""JARVIS local HTTP API — lets you drive JARVIS without the Qt UI.

Endpoints
---------
POST /chat          {"text": "show todo panel"}
                    Sends a message as if the user typed it in the chat.

POST /tool          {"tool": "show_panel", "args": {"panel": "todo"}}
                    Directly invokes a registered tool by name and returns result.

GET  /tools         List all registered tool names.
GET  /status        Runtime status (ready, provider, etc.).

Usage
-----
    curl -s http://localhost:8765/status
    curl -s -X POST http://localhost:8765/chat \
         -H "Content-Type: application/json" \
         -d '{"text": "show todo panel"}'
    curl -s -X POST http://localhost:8765/tool \
         -H "Content-Type: application/json" \
         -d '{"tool": "show_panel", "args": {"panel": "todo"}}'
"""

import json
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from jarvis.app import JarvisRuntime


_DEFAULT_PORT = 8765


class LocalAPIServer:
    """Thin aiohttp wrapper that exposes the JarvisRuntime over HTTP."""

    def __init__(self, runtime: "JarvisRuntime", port: int = _DEFAULT_PORT) -> None:
        self._runtime = runtime
        self._port = port
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/status", self._handle_status)
        app.router.add_get("/tools", self._handle_tools)
        app.router.add_post("/chat", self._handle_chat)
        app.router.add_post("/tool", self._handle_tool)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self._port)
        await site.start()
        logger.info(f"JARVIS local API listening on http://127.0.0.1:{self._port}")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("JARVIS local API stopped")

    def _check_origin(self, request: web.Request) -> "web.Response | None":
        """Reject requests whose Origin header is not null or localhost.

        Browser-initiated cross-origin requests carry an Origin header;
        curl and local scripts do not, so they pass through fine.
        """
        origin = request.headers.get("Origin", "")
        if origin and not any(origin.startswith(p) for p in (
            "http://localhost", "https://localhost",
            "http://127.0.0.1", "https://127.0.0.1",
        )):
            return _error("Cross-origin requests not allowed", 403)
        return None

    async def _handle_status(self, request: web.Request) -> web.Response:
        rt = self._runtime
        providers = []
        if rt.provider_router:
            providers = list(rt.provider_router._providers.keys())
        return _json({"ready": rt.ready, "providers": providers, "port": self._port})

    async def _handle_tools(self, request: web.Request) -> web.Response:
        rt = self._runtime
        if not rt.tool_registry:
            return _json({"tools": []})
        names = [d["name"] for d in rt.tool_registry.get_definitions()]
        return _json({"tools": names})

    async def _handle_chat(self, request: web.Request) -> web.Response:
        """Send a text message as if the user typed it."""
        if (blocked := self._check_origin(request)):
            return blocked
        try:
            body = await request.json()
        except Exception:
            return _error("Body must be JSON with a 'text' field", 400)

        text = body.get("text", "").strip()
        if not text:
            return _error("'text' is required and must not be empty", 400)

        if not self._runtime.ready:
            return _error("Runtime not ready yet — try again in a moment", 503)

        self._runtime.send_text(text)
        return _json({"ok": True, "message": f"Message queued: {text!r}"})

    async def _handle_tool(self, request: web.Request) -> web.Response:
        """Directly call a registered tool by name."""
        if (blocked := self._check_origin(request)):
            return blocked
        try:
            body = await request.json()
        except Exception:
            return _error("Body must be JSON with 'tool' and optional 'args'", 400)

        tool_name = body.get("tool", "").strip()
        args: dict = body.get("args", {})

        if not tool_name:
            return _error("'tool' is required", 400)

        rt = self._runtime
        if not rt.ready:
            return _error("Runtime not ready yet — try again in a moment", 503)

        if not rt.tool_registry:
            return _error("Tool registry unavailable", 503)

        known = [d["name"] for d in rt.tool_registry.get_definitions()]
        if tool_name not in known:
            return _error(f"Unknown tool {tool_name!r}. Available: {known}", 404)

        try:
            result = await rt.tool_registry.execute(tool_name, args)
        except TypeError as exc:
            return _error(f"Bad args for {tool_name!r}: {exc}", 400)
        except Exception as exc:
            logger.exception(f"Tool {tool_name!r} raised an error")
            return _error(f"Tool error: {exc}", 500)

        return _json({"ok": True, "tool": tool_name, "result": result})


def _json(data: dict, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False, default=str),
        content_type="application/json",
        status=status,
    )


def _error(message: str, status: int = 400) -> web.Response:
    return _json({"ok": False, "error": message}, status)
