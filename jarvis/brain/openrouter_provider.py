import json
from collections.abc import Callable, Awaitable
from loguru import logger
from openai import AsyncOpenAI
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse, ToolCall

class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "meta-llama/llama-3.1-8b-instruct:free"):
        self.api_key = api_key
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    @property
    def name(self) -> str:
        return "openrouter"

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
        try:
            formatted_messages = [
                {"role": msg.role, "content": msg.content} for msg in messages
            ]

            if system_prompt:
                formatted_messages.insert(0, {"role": "system", "content": system_prompt})

            kwargs = {
                "model": self.model,
                "messages": formatted_messages,
                "temperature": temperature,
            }

            if tools:
                kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

            response = await self.client.chat.completions.create(**kwargs)

            tool_calls = []
            if response.choices[0].message.tool_calls:
                for tc in response.choices[0].message.tool_calls:
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            args=json.loads(tc.function.arguments),
                        )
                    )

            return AIResponse(
                text=response.choices[0].message.content or "",
                tool_calls=tool_calls if tool_calls else None,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                },
                provider=self.name,
            )

        except Exception as e:
            logger.error(f"OpenRouter chat error: {e}")
            raise

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AIResponse:
        formatted_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
        if system_prompt:
            formatted_messages.insert(0, {"role": "system", "content": system_prompt})

        kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        text = ""
        tool_calls_map: dict[int, dict] = {}

        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
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
            usage={},
            provider=self.name,
        )
