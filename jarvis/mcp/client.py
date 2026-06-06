"""
MCP client — connects to external MCP servers via stdio transport.

Each MCPClient manages one server process. Tools discovered from the server
are surfaced to the caller for registration into JARVIS's ToolRegistry.
"""


import asyncio
import json
import os
import subprocess

from loguru import logger

class MCPClient:
    def __init__(self, server_config: dict):
        self.name: str = server_config["name"]
        self.command: str = server_config["command"]
        self.args: list[str] = server_config.get("args", [])
        self.env: dict[str, str] = server_config.get("env", {})
        self._process: subprocess.Popen | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._read_task: asyncio.Task | None = None
        self._tools: list[dict] = []

    async def connect(self) -> None:
        # Strip env vars that could allow an MCP server config to override
        # critical runtime paths or exfiltrate credentials.
        _BLOCKED_ENV = {
            "PATH", "PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH",
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY",
            "MISTRAL_API_KEY", "GEMINI_API_KEY", "TEMP", "TMP",
        }
        safe_extra = {k: v for k, v in self.env.items() if k.upper() not in _BLOCKED_ENV}
        env = {**os.environ, **safe_extra}
        self._process = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader = self._process.stdout
        self._writer_raw = self._process.stdin
        self._read_task = asyncio.create_task(self._read_loop())

        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "jarvis", "version": "1.0.0"},
        })

        await self._send_notification("notifications/initialized", {})
        logger.info(f"MCP server '{self.name}' initialized")

    async def list_tools(self) -> list[dict]:
        result = await self._send_request("tools/list", {})
        raw_tools = result.get("tools", [])
        self._tools = []
        for tool in raw_tools:
            self._tools.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            })
        return self._tools

    async def call_tool(self, tool_name: str, args: dict) -> str:
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": args,
        })
        content = result.get("content", [])
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(json.dumps(item))
            else:
                parts.append(str(item))
        return "\n".join(parts) if parts else "(no output)"

    async def disconnect(self) -> None:
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._process.kill()
            self._process = None
        self._writer_raw = None
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    async def _send_request(self, method: str, params: dict) -> dict:
        self._request_id += 1
        req_id = self._request_id
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        await self._write_message(message)
        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"MCP request '{method}' timed out after 30s")

    async def _send_notification(self, method: str, params: dict) -> None:
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._write_message(message)

    async def _write_message(self, message: dict) -> None:
        if self._process is None or self._writer_raw is None:
            raise RuntimeError(f"MCP client '{self.name}' is not connected")
        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        data = (header + body).encode("utf-8")
        self._writer_raw.write(data)
        await self._writer_raw.drain()

    async def _read_loop(self) -> None:
        try:
            while True:
                header_line = await self._reader.readline()
                if not header_line:
                    break
                header = header_line.decode("utf-8").strip()
                if not header.startswith("Content-Length:"):
                    continue
                content_length = int(header.split(":")[1].strip())

                # Read the blank line separator
                await self._reader.readline()

                body = await self._reader.readexactly(content_length)
                message = json.loads(body.decode("utf-8"))

                if "id" in message and "result" in message:
                    req_id = message["id"]
                    future = self._pending.pop(req_id, None)
                    if future and not future.done():
                        future.set_result(message["result"])
                elif "id" in message and "error" in message:
                    req_id = message["id"]
                    future = self._pending.pop(req_id, None)
                    if future and not future.done():
                        error = message["error"]
                        future.set_exception(
                            RuntimeError(f"MCP error {error.get('code')}: {error.get('message')}")
                        )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"MCP read loop error for '{self.name}': {e}")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(e)
            self._pending.clear()
