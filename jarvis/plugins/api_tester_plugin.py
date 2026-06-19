
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


def _format_response(res: dict) -> str:
    if not res.get("ok"):
        return f"Request failed: {res.get('error', 'unknown error')}"
    lines = [f"{res['status']} {res['reason']}  ({res['elapsed_ms']} ms)"]
    h = res.get("headers", {})
    for k in ("content-type", "content-length", "server"):
        if k in h:
            lines.append(f"{k}: {h[k]}")
    body = res.get("body", "")
    if len(body) > 3000:
        body = body[:3000] + "\n…(truncated)"
    lines.append("")
    lines.append(body or "(empty body)")
    return "\n".join(lines)


class ApiTesterPlugin(Plugin):
    """Postman-style HTTP request tool — send requests, inspect responses, and
    save named requests to reuse later."""

    def __init__(self):
        super().__init__("api_tester")
        self._store = None

    def _get(self):
        if self._store is None:
            from jarvis.brain.api_tester import get_request_store
            self._store = get_request_store()
        return self._store

    async def initialize(self) -> None:
        logger.info("ApiTesterPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="api_request",
                    description=(
                        "Send an HTTP request and return the status, headers, and "
                        "body. Use when the user says 'call this API', 'GET this URL', "
                        "'POST this JSON to ...', 'test this endpoint'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "method": {"type": "string", "description": "GET, POST, PUT, PATCH, DELETE"},
                            "url": {"type": "string"},
                            "headers": {"type": "object", "description": "Optional headers object"},
                            "params": {"type": "object", "description": "Optional query params object"},
                            "body": {"type": "string", "description": "Optional request body (JSON string or raw text)"},
                        },
                        "required": ["method", "url"],
                    },
                ),
                self.api_request,
            ),
            (
                ToolDefinition(
                    name="save_request",
                    description="Save a named API request to reuse later (a collection entry).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "method": {"type": "string"},
                            "url": {"type": "string"},
                            "headers": {"type": "object"},
                            "params": {"type": "object"},
                            "body": {"type": "string"},
                        },
                        "required": ["name", "method", "url"],
                    },
                ),
                self.save_request,
            ),
            (
                ToolDefinition(
                    name="run_saved_request",
                    description="Run a previously saved API request by name.",
                    parameters={
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                ),
                self.run_saved_request,
            ),
            (
                ToolDefinition(
                    name="list_saved_requests",
                    description="List saved API requests.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_saved_requests,
            ),
            (
                ToolDefinition(
                    name="delete_saved_request",
                    description="Delete a saved API request by name.",
                    parameters={
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                ),
                self.delete_saved_request,
            ),
        ]

    async def api_request(self, method, url, headers=None, params=None, body=None) -> str:
        from jarvis.brain.api_tester import send_request
        res = await send_request(method, url, headers, params, body)
        return _format_response(res)

    async def save_request(self, name, method, url, headers=None, params=None, body=None) -> str:
        spec = {"method": method, "url": url, "headers": headers or {},
                "params": params or {}, "body": body or ""}
        self._get().save(name, spec)
        return f"Saved request '{name}' ({method.upper()} {url})."

    async def run_saved_request(self, name) -> str:
        spec = self._get().get(name)
        if not spec:
            return f"No saved request named '{name}'."
        from jarvis.brain.api_tester import send_request
        res = await send_request(spec["method"], spec["url"], spec.get("headers"),
                                 spec.get("params"), spec.get("body"))
        return f"[{name}]\n" + _format_response(res)

    async def list_saved_requests(self, **_) -> str:
        data = self._get().list_all()
        if not data:
            return "No saved requests."
        lines = ["Saved requests:"]
        for n, s in data.items():
            lines.append(f"  • {n}: {s.get('method', '?').upper()} {s.get('url', '')}")
        return "\n".join(lines)

    async def delete_saved_request(self, name) -> str:
        ok = self._get().delete(name)
        return f"Deleted '{name}'." if ok else f"No saved request named '{name}'."
