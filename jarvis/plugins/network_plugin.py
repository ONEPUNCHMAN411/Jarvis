
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class NetworkPlugin(Plugin):
    """Network utilities: ping, port scan, subnet sweep, public IP."""

    def __init__(self):
        super().__init__("network")

    async def initialize(self) -> None:
        logger.info("NetworkPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="ping_host",
                    description=(
                        "Ping a hostname or IP address and report whether it is reachable "
                        "and its average latency. Use for 'is google.com up?', "
                        "'ping 192.168.1.1', 'check if my server is alive'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "host": {
                                "type": "string",
                                "description": "Hostname or IP address to ping",
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of ping packets to send (default 3)",
                            },
                        },
                        "required": ["host"],
                    },
                ),
                self.ping_host,
            ),
            (
                ToolDefinition(
                    name="check_port",
                    description=(
                        "Check if a specific TCP port is open on a host. "
                        "Use for 'is port 443 open on example.com?', 'check SSH on my server'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "host": {
                                "type": "string",
                                "description": "Hostname or IP",
                            },
                            "port": {
                                "type": "integer",
                                "description": "TCP port number",
                            },
                        },
                        "required": ["host", "port"],
                    },
                ),
                self.check_port,
            ),
            (
                ToolDefinition(
                    name="scan_ports",
                    description=(
                        "Scan common ports on a host and return which ones are open. "
                        "Checks 16 standard ports: 21, 22, 23, 25, 53, 80, 110, 143, "
                        "443, 445, 3306, 3389, 5432, 6379, 8080, 8443."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "host": {
                                "type": "string",
                                "description": "Hostname or IP address to scan",
                            }
                        },
                        "required": ["host"],
                    },
                ),
                self.scan_ports,
            ),
            (
                ToolDefinition(
                    name="scan_network",
                    description=(
                        "Sweep the local subnet to discover all alive hosts. "
                        "Pings all 254 addresses in the /24 subnet. "
                        "Leave subnet blank to auto-detect from local IP."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "subnet": {
                                "type": "string",
                                "description": "Subnet prefix like '192.168.1' (optional — auto-detected)",
                            }
                        },
                    },
                ),
                self.scan_network,
            ),
            (
                ToolDefinition(
                    name="get_public_ip",
                    description="Get the machine's current public (external) IP address.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.get_public_ip,
            ),
        ]

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
        except Exception as e:
            return f"Network error: {e}"

    async def ping_host(self, host: str, count: int = 3) -> str:
        from jarvis.brain.network_scanner import ping_host
        r = await self._run(ping_host, host, count)
        if isinstance(r, str):
            return r
        status = "✅ alive" if r["alive"] else "❌ unreachable"
        latency = f"  avg latency: {r['latency_ms']:.1f} ms" if r["latency_ms"] else ""
        return f"{host}: {status}{latency}"

    async def check_port(self, host: str, port: int) -> str:
        from jarvis.brain.network_scanner import check_port
        r = await self._run(check_port, host, port)
        if isinstance(r, str):
            return r
        status = "open ✅" if r["open"] else "closed ❌"
        return f"{host}:{port} — {status}"

    async def scan_ports(self, host: str) -> str:
        from jarvis.brain.network_scanner import scan_ports
        open_ports = await self._run(scan_ports, host)
        if isinstance(open_ports, str):
            return open_ports
        if not open_ports:
            return f"{host}: no common ports open."
        port_list = ", ".join(str(p["port"]) for p in open_ports)
        return f"{host} — open ports: {port_list}"

    async def scan_network(self, subnet: str = "") -> str:
        from jarvis.brain.network_scanner import scan_network
        alive = await self._run(scan_network, subnet or None)
        if isinstance(alive, str):
            return alive
        if not alive:
            return "No hosts found on the network."
        host_list = "\n".join(f"  • {ip}" for ip in alive)
        return f"Found {len(alive)} host(s):\n{host_list}"

    async def get_public_ip(self) -> str:
        from jarvis.brain.network_scanner import get_public_ip
        return await self._run(get_public_ip)
