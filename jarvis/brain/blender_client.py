
import json
import socket
import threading


class BlenderClient:
    """Talks to the BlenderMCP addon socket server running inside Blender.

    Setup: install/enable the BlenderMCP addon, press N in the 3D viewport,
    open the 'BlenderMCP' tab and click 'Start MCP Server'
    (default host 127.0.0.1, port 9876).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9876, timeout: float = 30.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _send(self, command: dict) -> dict:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
            sock.sendall(json.dumps(command).encode("utf-8"))
            chunks: list[bytes] = []
            while True:
                try:
                    data = sock.recv(8192)
                except socket.timeout:
                    break
                if not data:
                    break
                chunks.append(data)
                try:
                    return json.loads(b"".join(chunks).decode("utf-8"))
                except json.JSONDecodeError:
                    continue
            raw = b"".join(chunks).decode("utf-8")
            return json.loads(raw) if raw else {"status": "error", "message": "Empty response"}
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def command(self, ctype: str, params: dict | None = None) -> dict:
        try:
            return self._send({"type": ctype, "params": params or {}})
        except ConnectionRefusedError:
            return {
                "status": "error",
                "message": (
                    "Could not reach Blender. Is Blender open with the BlenderMCP "
                    "addon server started on port 9876?"
                ),
            }
        except Exception as e:
            return {"status": "error", "message": f"Blender connection error: {e}"}

    def get_scene_info(self) -> dict:
        return self.command("get_scene_info")

    def get_object_info(self, name: str) -> dict:
        return self.command("get_object_info", {"name": name})

    def execute_code(self, code: str) -> dict:
        return self.command("execute_code", {"code": code})

    def get_viewport_screenshot(self, max_size: int = 800) -> dict:
        return self.command("get_viewport_screenshot", {"max_size": max_size})


_instance: "BlenderClient | None" = None
_lock = threading.Lock()


def get_blender() -> "BlenderClient":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = BlenderClient()
    return _instance
