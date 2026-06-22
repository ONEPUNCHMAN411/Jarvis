
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class VaultPlugin(Plugin):
    """Encrypt and decrypt files (and text) with a password — AES via Fernet,
    PBKDF2 key derivation. Encrypted files get a .vault extension."""

    def __init__(self):
        super().__init__("vault")

    async def initialize(self) -> None:
        logger.info("VaultPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="encrypt_file",
                    description=(
                        "Password-encrypt a file. Writes a .vault file next to it. "
                        "Use when the user says 'encrypt this file', 'lock this "
                        "document', 'protect this with a password'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File to encrypt"},
                            "password": {"type": "string", "description": "Password"},
                            "output": {"type": "string", "description": "Optional output path"},
                        },
                        "required": ["path", "password"],
                    },
                ),
                self.encrypt_file,
            ),
            (
                ToolDefinition(
                    name="decrypt_file",
                    description=(
                        "Decrypt a .vault file with its password. Use when the user "
                        "says 'decrypt this', 'unlock this file', 'open my encrypted file'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "The .vault file"},
                            "password": {"type": "string", "description": "Password"},
                            "output": {"type": "string", "description": "Optional output path"},
                        },
                        "required": ["path", "password"],
                    },
                ),
                self.decrypt_file,
            ),
            (
                ToolDefinition(
                    name="encrypt_text",
                    description="Encrypt a short piece of text with a password; returns a token string.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "password": {"type": "string"},
                        },
                        "required": ["text", "password"],
                    },
                ),
                self.encrypt_text,
            ),
            (
                ToolDefinition(
                    name="decrypt_text",
                    description="Decrypt a token string produced by encrypt_text, using the password.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "token": {"type": "string"},
                            "password": {"type": "string"},
                        },
                        "required": ["token", "password"],
                    },
                ),
                self.decrypt_text,
            ),
        ]

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    async def encrypt_file(self, path: str, password: str, output: str = "") -> str:
        from jarvis.brain.vault import encrypt_file as _enc
        res = await self._run(_enc, path, password, output or None)
        if not res.get("ok"):
            return res.get("error", "Encryption failed.")
        return f"Encrypted → {res['out']}  ({res['size']} bytes). Keep your password safe — it cannot be recovered."

    async def decrypt_file(self, path: str, password: str, output: str = "") -> str:
        from jarvis.brain.vault import decrypt_file as _dec
        res = await self._run(_dec, path, password, output or None)
        if not res.get("ok"):
            return res.get("error", "Decryption failed.")
        return f"Decrypted → {res['out']}  ({res['size']} bytes)."

    async def encrypt_text(self, text: str, password: str) -> str:
        from jarvis.brain.vault import encrypt_text as _enc
        try:
            token = await self._run(_enc, text, password)
        except Exception as e:
            return f"Encryption failed: {e}"
        return f"Encrypted token:\n{token}"

    async def decrypt_text(self, token: str, password: str) -> str:
        from jarvis.brain.vault import decrypt_text as _dec
        try:
            return await self._run(_dec, token, password)
        except Exception:
            return "Wrong password or invalid token."
