"""
Bridges MCP server tools into JARVIS's ToolRegistry.

Each MCP server's tools are namespaced as mcp_{server_name}_{tool_name}
to avoid collisions with built-in tools.
"""


from loguru import logger

from jarvis.brain.tools import ToolRegistry
from jarvis.mcp.client import MCPClient
from jarvis.models import ToolDefinition

class MCPToolBridge:
    def __init__(self, tool_registry: ToolRegistry):
        self.registry = tool_registry
        self.clients: dict[str, MCPClient] = {}

    async def register_server(self, server_config: dict) -> int:
        client = MCPClient(server_config)
        await client.connect()
        self.clients[server_config["name"]] = client

        tools = await client.list_tools()
        count = 0
        for tool_def in tools:
            server_name = server_config["name"]
            original_name = tool_def["name"]
            namespaced_name = f"mcp_{server_name}_{original_name}"

            async def _handler(_c=client, _n=original_name, **kwargs):
                return await _c.call_tool(_n, kwargs)

            self.registry.register(
                ToolDefinition(
                    name=namespaced_name,
                    description=f"[MCP:{server_name}] {tool_def['description']}",
                    parameters=tool_def["parameters"],
                ),
                _handler,
            )
            count += 1
            logger.debug(f"Registered MCP tool: {namespaced_name}")

        return count

    async def shutdown(self) -> None:
        for name, client in self.clients.items():
            try:
                await client.disconnect()
                logger.info(f"MCP server '{name}' disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting MCP server '{name}': {e}")
        self.clients.clear()
