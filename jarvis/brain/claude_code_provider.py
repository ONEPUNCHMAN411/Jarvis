"""
Claude Code provider — uses the locally-installed Claude Code CLI so users who
already have Claude Code running don't need to configure a separate API key.

Two modes (set in config / chosen in setup wizard):

  auto  — reads the stored Anthropic API key from Claude Code's config files
          and uses it with the full Claude API (tool use, streaming, all features).

  pipe  — spawns `claude --print "<prompt>"` as a subprocess and returns stdout.
          Works with zero config but has no tool-use support.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from collections.abc import Callable, Awaitable
from loguru import logger

from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse

# Credential discovery

def _candidate_config_paths() -> list[Path]:
    """Return possible locations where Claude Code stores the API key."""
    candidates: list[Path] = []

    # 1. Claude Code project settings (most common on Windows)
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates += [
            Path(appdata) / "Claude" / "config.json",
            Path(appdata) / "claude-code" / "config.json",
        ]

    # 2. ~/.claude/ (cross-platform default)
    home = Path.home()
    candidates += [
        home / ".claude" / "settings.json",
        home / ".claude" / "config.json",
        home / ".claude" / ".credentials.json",
    ]
    return candidates

def _extract_api_key_from_file(path: Path) -> str | None:
    """Try to read an API key out of a JSON config file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("apiKey", "api_key", "ANTHROPIC_API_KEY", "anthropicApiKey"):
            value = data.get(key)
            if value and isinstance(value, str) and value.startswith("sk-"):
                return value
    except Exception:
        pass
    return None

def find_claude_code_api_key() -> str | None:
    """
    Return a stored Anthropic API key from Claude Code's config, or None.
    Checks env vars first, then config files.
    """
    # Environment variable set by the user or by Claude Code itself
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if env_key and env_key.startswith("sk-"):
        logger.debug("Claude Code: using ANTHROPIC_API_KEY from environment")
        return env_key

    for path in _candidate_config_paths():
        if path.exists():
            key = _extract_api_key_from_file(path)
            if key:
                logger.debug(f"Claude Code: found API key in {path}")
                return key

    return None

def is_claude_cli_available() -> bool:
    """Return True if the `claude` CLI executable is on PATH."""
    return shutil.which("claude") is not None

# Auto-credentials mode

class ClaudeCodeAutoProvider(LLMProvider):
    """
    Full-featured Claude provider that reuses Claude Code's stored credentials.
    Falls back gracefully if no key is found at health-check time.
    """

    def __init__(self) -> None:
        self._inner: LLMProvider | None = None
        self._api_key: str | None = None

    @property
    def name(self) -> str:
        return "claude_code_auto"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def max_tokens(self) -> int:
        return 4096

    async def _ensure_inner(self) -> LLMProvider:
        if self._inner is not None:
            return self._inner
        # Lazy import to avoid circular deps
        from jarvis.brain.claude_provider import ClaudeProvider
        key = find_claude_code_api_key()
        if not key:
            raise RuntimeError(
                "Claude Code credentials not found. "
                "Install Claude Code and log in, or set ANTHROPIC_API_KEY."
            )
        self._api_key = key
        self._inner = ClaudeProvider(api_key=key)
        return self._inner

    async def health_check(self) -> bool:
        try:
            inner = await self._ensure_inner()
            return await inner.health_check()
        except Exception as exc:
            logger.warning(f"claude_code_auto health check failed: {exc}")
            return False

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
    ) -> AIResponse:
        inner = await self._ensure_inner()
        response = await inner.chat(messages, tools, system_prompt, temperature, category)
        return AIResponse(
            text=response.text,
            tool_calls=response.tool_calls,
            usage=response.usage,
            provider="claude_code_auto",
        )

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AIResponse:
        inner = await self._ensure_inner()
        response = await inner.stream_chat(
            messages, tools, system_prompt, temperature, category, on_chunk
        )
        return AIResponse(
            text=response.text,
            tool_calls=response.tool_calls,
            usage=response.usage,
            provider="claude_code_auto",
        )

# Subprocess/pipe mode

class ClaudeCodePipeProvider(LLMProvider):
    """
    Spawns `claude --print "<prompt>"` as a subprocess and returns the output.
    No tool use, no streaming — but requires zero API-key configuration.
    """

    _CLI_TIMEOUT = 60

    @property
    def name(self) -> str:
        return "claude_code_pipe"

    @property
    def supports_tools(self) -> bool:
        return False

    @property
    def max_tokens(self) -> int:
        return 4096

    async def health_check(self) -> bool:
        if not is_claude_cli_available():
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except Exception:
            return False

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
    ) -> AIResponse:
        prompt = self._build_prompt(messages, system_prompt)
        text = await self._run_claude_cli(prompt)
        return AIResponse(text=text, tool_calls=None, usage={}, provider="claude_code_pipe")

    def _build_prompt(self, messages: list[Message], system_prompt: str | None) -> str:
        parts: list[str] = []
        if system_prompt:
            parts.append(f"[System]\n{system_prompt}\n")
        for msg in messages:
            if msg.role == "system":
                continue
            role_label = "User" if msg.role == "user" else "Assistant"
            parts.append(f"[{role_label}]\n{msg.content or ''}")
        parts.append("[Assistant]")
        return "\n\n".join(parts)

    async def _run_claude_cli(self, prompt: str) -> str:
        cli = shutil.which("claude")
        if not cli:
            raise RuntimeError("claude CLI not found on PATH")

        proc = await asyncio.create_subprocess_exec(
            cli, "--print", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._CLI_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"claude CLI timed out after {self._CLI_TIMEOUT}s")

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {err}")

        return stdout.decode(errors="replace").strip()
