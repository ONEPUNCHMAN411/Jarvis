import json
from pathlib import Path
from loguru import logger

from jarvis.ssh.ssh_client import SSHClient, SSHConfig

_CONFIG_PATH = Path.home() / ".jarvis" / "ssh_servers.json"


class SSHManager:
    def __init__(self):
        self._configs: list[SSHConfig] = []
        self._clients: dict[str, SSHClient] = {}
        self._load()

    def _load(self) -> None:
        if _CONFIG_PATH.exists():
            try:
                data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                self._configs = [SSHConfig.from_dict(d) for d in data]
                logger.info(f"Loaded {len(self._configs)} SSH configs")
            except Exception as e:
                logger.warning(f"Failed to load SSH configs: {e}")

    def save(self) -> None:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = [c.to_dict() for c in self._configs]
        _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_configs(self) -> list[SSHConfig]:
        return list(self._configs)

    def set_configs(self, configs: list[dict]) -> None:
        self._configs = [SSHConfig.from_dict(d) for d in configs]
        self.save()

    def get_client(self, name: str) -> SSHClient | None:
        cfg = next((c for c in self._configs if c.name == name), None)
        if cfg is None:
            return None
        if name not in self._clients:
            self._clients[name] = SSHClient(cfg)
        return self._clients[name]

    def list_names(self) -> list[str]:
        return [c.name for c in self._configs if c.enabled]

    async def disconnect_all(self) -> None:
        for client in self._clients.values():
            if client.is_connected:
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.warning(f"Error disconnecting {client.name}: {e}")
        self._clients.clear()
