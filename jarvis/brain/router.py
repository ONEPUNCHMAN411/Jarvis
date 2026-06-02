import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from collections.abc import Callable, Awaitable
from loguru import logger
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse

_HEALTH_TTL = 300.0

# Response LRU cache
# Avoids redundant provider calls when the same user message is repeated
# within a short window (e.g. double-send, UI retry).
_RESPONSE_CACHE_MAX = 50
_RESPONSE_CACHE_TTL = 30.0

# Per-provider call timeout (seconds).
_PROVIDER_TIMEOUT: dict[str, int] = {
    "claude":            45,
    "openai":            45,
    "gemini":            45,
    "groq":              30,
    "mistral":           90,
    "ollama":            90,
    "openrouter":        45,
    "llamacpp":          180,
}

class ProviderRouter:
    def __init__(self, providers: dict[str, LLMProvider], order: list[str]):
        self._providers = providers
        self._order = order
        self._last_ok: dict[str, float] = {}
        self._ever_succeeded: set[str] = set()
        # LRU cache: OrderedDict key=(provider, msg_hash) -> (AIResponse, timestamp)
        self._response_cache: OrderedDict[tuple[str, str], tuple[AIResponse, float]] = OrderedDict()
        logger.info(f"Provider router initialized with order: {order}")

    # Internal cache helpers

    @staticmethod
    def _msg_hash(messages: list[Message]) -> str:
        """Stable hash of the last user message content."""
        for msg in reversed(messages):
            if msg.role == "user" and msg.content:
                return hashlib.md5(msg.content.encode("utf-8", errors="replace"), usedforsecurity=False).hexdigest()
        return ""

    def _cache_get(self, provider: str, msg_hash: str) -> AIResponse | None:
        """Return cached response if present and not expired; evict if stale."""
        key = (provider, msg_hash)
        if key not in self._response_cache:
            return None
        response, ts = self._response_cache[key]
        if time.monotonic() - ts > _RESPONSE_CACHE_TTL:
            del self._response_cache[key]
            return None
        # Move to end (most-recently-used)
        self._response_cache.move_to_end(key)
        return response

    def _cache_set(self, provider: str, msg_hash: str, response: AIResponse) -> None:
        """Store response in LRU cache, evicting oldest entry when full."""
        key = (provider, msg_hash)
        self._response_cache[key] = (response, time.monotonic())
        self._response_cache.move_to_end(key)
        while len(self._response_cache) > _RESPONSE_CACHE_MAX:
            self._response_cache.popitem(last=False)  # evict LRU

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        preferred_provider: str | None = None,
        category: str | None = None,
    ) -> AIResponse:
        provider_order = list(self._order)
        if preferred_provider and preferred_provider in provider_order:
            provider_order.remove(preferred_provider)
            provider_order.insert(0, preferred_provider)

        # Response cache check
        # Only cache non-tool, non-image messages (tools must execute; images vary).
        _has_tools = bool(tools)
        _has_images = any(getattr(m, "image_paths", None) for m in messages)
        _msg_hash = self._msg_hash(messages) if not _has_tools and not _has_images else ""
        if _msg_hash:
            _primary = provider_order[0] if provider_order else ""
            _cached = self._cache_get(_primary, _msg_hash)
            if _cached is not None:
                logger.debug(f"Response cache hit for provider={_primary}")
                return _cached

        now = time.monotonic()
        errors: list[str] = []
        for idx, provider_name in enumerate(provider_order):
            provider = self._providers.get(provider_name)
            if not provider:
                continue

            try:
                logger.debug(f"Trying provider: {provider_name}")

                if provider_name not in self._ever_succeeded:
                    recently_healthy = (now - self._last_ok.get(provider_name, 0)) < _HEALTH_TTL
                    if not recently_healthy:
                        health = await asyncio.wait_for(
                            provider.health_check(), timeout=8,
                        )
                        if not health:
                            msg = f"{provider_name}: health check failed"
                            logger.warning(msg)
                            errors.append(msg)
                            continue

                timeout = _PROVIDER_TIMEOUT.get(provider_name, 60)
                response = await asyncio.wait_for(
                    provider.chat(
                        messages,
                        tools=tools,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        category=category,
                    ),
                    timeout=timeout,
                )
                self._last_ok[provider_name] = time.monotonic()
                self._ever_succeeded.add(provider_name)
                logger.info(f"Got response from {provider_name}")
                # Store in cache (only for non-tool, non-image requests)
                if _msg_hash:
                    self._cache_set(provider_name, _msg_hash, response)
                return response

            except asyncio.TimeoutError:
                self._last_ok.pop(provider_name, None)
                self._ever_succeeded.discard(provider_name)
                msg = f"{provider_name}: timed out"
                logger.warning(msg)
                errors.append(msg)
            except Exception as e:
                self._last_ok.pop(provider_name, None)
                self._ever_succeeded.discard(provider_name)
                msg = f"{provider_name}: {type(e).__name__}: {e}"
                logger.warning("{}", msg)
                errors.append(msg)

        detail = "; ".join(errors) if errors else "no providers configured"
        logger.error("All AI providers failed — {}", detail)
        raise RuntimeError(
            f"JARVIS couldn't reach any AI provider.\n\n"
            f"Quick fix: open Settings and add an API key for Groq, Gemini, Mistral, or another provider.\n\n"
            f"Details: {detail}"
        )

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        preferred_provider: str | None = None,
        category: str | None = None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AIResponse:
        provider_order = list(self._order)
        if preferred_provider and preferred_provider in provider_order:
            provider_order.remove(preferred_provider)
            provider_order.insert(0, preferred_provider)

        now = time.monotonic()
        errors: list[str] = []
        for provider_name in provider_order:
            provider = self._providers.get(provider_name)
            if not provider:
                continue

            try:
                if provider_name not in self._ever_succeeded:
                    recently_healthy = (now - self._last_ok.get(provider_name, 0)) < _HEALTH_TTL
                    if not recently_healthy:
                        health = await asyncio.wait_for(provider.health_check(), timeout=8)
                        if not health:
                            errors.append(f"{provider_name}: health check failed")
                            continue

                timeout = _PROVIDER_TIMEOUT.get(provider_name, 60)
                response = await asyncio.wait_for(
                    provider.stream_chat(
                        messages, tools=tools, system_prompt=system_prompt,
                        temperature=temperature, category=category, on_chunk=on_chunk,
                    ),
                    timeout=timeout,
                )
                self._last_ok[provider_name] = time.monotonic()
                self._ever_succeeded.add(provider_name)
                return response

            except asyncio.TimeoutError:
                self._last_ok.pop(provider_name, None)
                self._ever_succeeded.discard(provider_name)
                errors.append(f"{provider_name}: timed out")
            except Exception as e:
                self._last_ok.pop(provider_name, None)
                self._ever_succeeded.discard(provider_name)
                errors.append(f"{provider_name}: {type(e).__name__}: {e}")

        detail = "; ".join(errors) if errors else "no providers configured"
        raise RuntimeError(
            f"JARVIS couldn't reach any AI provider.\n\n"
            f"Open Settings → AI Provider to configure one.\n\n"
            f"Details: {detail}"
        )

    async def get_available_providers(self) -> list[str]:
        async def _check(name: str, provider: LLMProvider) -> str | None:
            try:
                if name in self._ever_succeeded:
                    return name
                if await asyncio.wait_for(provider.health_check(), timeout=5):
                    return name
            except Exception:
                pass
            return None

        results = await asyncio.gather(
            *[_check(n, p) for n, p in self._providers.items()]
        )
        return [r for r in results if r is not None]
