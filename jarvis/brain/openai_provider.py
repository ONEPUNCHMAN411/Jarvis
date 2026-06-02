import asyncio
import json
from collections.abc import Callable, Awaitable
from loguru import logger
from openai import AsyncOpenAI, APIStatusError
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse, ToolCall

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None):
        self.api_key = api_key
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def max_tokens(self) -> int:
        return 4096

    async def health_check(self) -> bool:
        if not self.api_key:
            raise ValueError("API key is not configured.")
        models = await self.client.models.list()
        return models is not None

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
    ) -> AIResponse:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                return await self._do_chat(messages, tools, system_prompt, temperature)
            except APIStatusError as e:
                last_err = e
                status = getattr(e, "status_code", 0)
                if status in (429, 503, 502, 500):
                    wait = 2 ** attempt
                    logger.warning(f"OpenAI HTTP {status} on attempt {attempt+1}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                raise
            except Exception as e:
                last_err = e
                logger.error(f"OpenAI chat error: {e}")
                raise
        raise last_err  # type: ignore[misc]

    async def _do_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        system_prompt: str | None,
        temperature: float,
    ) -> AIResponse:
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            m: dict = {"role": msg.role, "content": msg.content or ""}
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            formatted_messages.append(m)

        kwargs: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }

        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        response = await self.client.chat.completions.create(**kwargs)

        tool_calls: list[ToolCall] = []
        if response.choices[0].message.tool_calls:
            for tc in response.choices[0].message.tool_calls:
                try:
                    raw = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    args = raw if isinstance(raw, dict) else {}
                except (json.JSONDecodeError, ValueError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    args=args,
                ))

        return AIResponse(
            text=response.choices[0].message.content or "",
            tool_calls=tool_calls if tool_calls else None,
            usage={
                "prompt_tokens":     response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
            provider=self.name,
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
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            m: dict = {"role": msg.role, "content": msg.content or ""}
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            formatted_messages.append(m)

        kwargs: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        text = ""
        tool_calls_map: dict[int, dict] = {}
        usage = {}

        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                if chunk.usage:
                    usage = {"prompt_tokens": chunk.usage.prompt_tokens, "completion_tokens": chunk.usage.completion_tokens}
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text += delta.content
                if on_chunk:
                    await on_chunk(delta.content)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {"id": tc_delta.id or "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_calls_map[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_map[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_map[idx]["arguments"] += tc_delta.function.arguments

        tool_calls: list[ToolCall] = []
        for tc_data in tool_calls_map.values():
            try:
                args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            tool_calls.append(ToolCall(id=tc_data["id"], name=tc_data["name"], args=args))

        return AIResponse(
            text=text,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            provider=self.name,
        )
