import asyncio
from dataclasses import dataclass
from loguru import logger


@dataclass
class SSHConfig:
    name: str
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    key_path: str = ""
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "key_path": self.key_path,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SSHConfig":
        return cls(
            name=d.get("name", ""),
            host=d.get("host", ""),
            port=d.get("port", 22),
            username=d.get("username", ""),
            password=d.get("password", ""),
            key_path=d.get("key_path", ""),
            enabled=d.get("enabled", True),
        )


class SSHCommandResult:
    def __init__(self, stdout: str, stderr: str, exit_code: int):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.success = exit_code == 0

    def __str__(self) -> str:
        out = self.stdout.strip()
        err = self.stderr.strip()
        if out and err:
            return f"{out}\n[stderr]: {err}"
        return out or err or "(no output)"


class SSHClient:
    def __init__(self, config: SSHConfig):
        self._cfg = config
        self._conn = None
        self._connected = False

    @property
    def name(self) -> str:
        return self._cfg.name

    @property
    def is_connected(self) -> bool:
        return self._connected and self._conn is not None

    async def connect(self) -> None:
        try:
            import asyncssh
        except ImportError:
            raise RuntimeError(
                "asyncssh not installed. Run: pip install asyncssh"
            )
        kwargs: dict = {
            "host": self._cfg.host,
            "port": self._cfg.port,
            "username": self._cfg.username,
            "known_hosts": None,
        }
        if self._cfg.key_path:
            kwargs["client_keys"] = [self._cfg.key_path]
            if self._cfg.password:
                kwargs["passphrase"] = self._cfg.password
        elif self._cfg.password:
            kwargs["password"] = self._cfg.password
        self._conn = await asyncssh.connect(**kwargs)
        self._connected = True
        logger.info(f"SSH connected: {self._cfg.name} ({self._cfg.host})")

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            await self._conn.wait_closed()
        self._conn = None
        self._connected = False
        logger.info(f"SSH disconnected: {self._cfg.name}")

    async def execute(self, command: str, timeout: float = 30.0) -> SSHCommandResult:
        if not self.is_connected:
            await self.connect()
        result = await asyncio.wait_for(
            self._conn.run(command, check=False),
            timeout=timeout,
        )
        return SSHCommandResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.exit_status or 0,
        )

    async def read_file(self, remote_path: str) -> str:
        if not self.is_connected:
            await self.connect()
        async with self._conn.start_sftp_client() as sftp:
            async with sftp.open(remote_path, "r") as f:
                return await f.read()

    async def write_file(self, remote_path: str, content: str) -> None:
        if not self.is_connected:
            await self.connect()
        async with self._conn.start_sftp_client() as sftp:
            async with sftp.open(remote_path, "w") as f:
                await f.write(content)

    async def list_dir(self, remote_path: str = ".") -> list[str]:
        if not self.is_connected:
            await self.connect()
        async with self._conn.start_sftp_client() as sftp:
            entries = await sftp.listdir(remote_path)
            return sorted(entries)

    async def upload(self, local_path: str, remote_path: str) -> None:
        if not self.is_connected:
            await self.connect()
        async with self._conn.start_sftp_client() as sftp:
            await sftp.put(local_path, remote_path)

    async def download(self, remote_path: str, local_path: str) -> None:
        if not self.is_connected:
            await self.connect()
        async with self._conn.start_sftp_client() as sftp:
            await sftp.get(remote_path, local_path)
