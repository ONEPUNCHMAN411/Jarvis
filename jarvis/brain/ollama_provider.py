import asyncio
import json
from collections.abc import Callable, Awaitable
from loguru import logger
import ollama
from jarvis.brain.message_format import messages_to_openai
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse, ToolCall

class OllamaProvider(LLMProvider):
    def __init__(
        self,
        model: str = "llama3.1:8b",
        coding_model: str | None = None,
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
    ):
        self.model = model
        self.coding_model = coding_model
        self.base_url = base_url
        self.timeout = timeout
        self.client = ollama.AsyncClient(host=base_url)

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def max_tokens(self) -> int:
        return 4096

    async def health_check(self) -> bool:
        try:
            response = await asyncio.wait_for(
                self.client.list(), timeout=self.timeout
            )
            return response is not None
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
    ) -> AIResponse:
        try:
            target_model = self.model
            if category == "coding" and self.coding_model:
                target_model = self.coding_model
                logger.info(f"Ollama: Coding context detected. Swapping to {target_model}")

            formatted_messages = messages_to_openai(messages, system_prompt)

            kwargs = {
                "model": target_model,
                "messages": formatted_messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_ctx": 16384
                },
            }

            if tools:
                # Ollama requires the OpenAI-style {"type":"function","function":{...}} wrapper
                kwargs["tools"] = [
                    {"type": "function", "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    }}
                    for t in tools
                ]

            response = await asyncio.wait_for(
                self.client.chat(**kwargs), timeout=self.timeout
            )

            # Support both dict-style (old ollama lib) and attribute-style (new)
            msg = response.message if hasattr(response, "message") else response.get("message", {})

            tool_calls: list[ToolCall] = []
            raw_tool_calls = (
                msg.tool_calls if hasattr(msg, "tool_calls") else (msg or {}).get("tool_calls")
            ) or []
            for i, tc in enumerate(raw_tool_calls):
                if hasattr(tc, "function"):
                    # Pydantic object (ollama >= 0.3)
                    name = tc.function.name if hasattr(tc.function, "name") else ""
                    args = tc.function.arguments if hasattr(tc.function, "arguments") else {}
                    tc_id = getattr(tc, "id", None) or f"call_{i}"
                else:
                    # Dict-style fallback
                    fn = tc.get("function", {})
                    name = fn.get("name", "") or tc.get("name", "")
                    args = fn.get("arguments", {}) or tc.get("arguments", {})
                    tc_id = tc.get("id", f"call_{i}")
                if name:
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    tool_calls.append(ToolCall(id=tc_id, name=name, args=args or {}))

            content = (
                msg.content if hasattr(msg, "content") else (msg or {}).get("content", "")
            ) or ""

            return AIResponse(
                text=content,
                tool_calls=tool_calls if tool_calls else None,
                usage=response.get("usage", {}) if hasattr(response, "get") else {},
                provider=self.name,
            )

        except asyncio.TimeoutError:
            logger.error(f"Ollama request timeout ({self.timeout}s)")
            raise
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
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
        target_model = self.model
        if category == "coding" and self.coding_model:
            target_model = self.coding_model

        formatted_messages = messages_to_openai(messages, system_prompt)
        kwargs = {
            "model": target_model,
            "messages": formatted_messages,
            "stream": True,
            "options": {"temperature": temperature, "num_ctx": 16384},
        }
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("parameters", {})}}
                for t in tools
            ]

        text = ""
        tool_calls: list[ToolCall] = []

        stream = await self.client.chat(**kwargs)
        async for chunk in stream:
            msg = chunk.message if hasattr(chunk, "message") else chunk.get("message", {})
            content = (msg.content if hasattr(msg, "content") else (msg or {}).get("content", "")) or ""
            if content:
                text += content
                if on_chunk:
                    await on_chunk(content)

            raw_tc = (msg.tool_calls if hasattr(msg, "tool_calls") else (msg or {}).get("tool_calls")) or []
            for i, tc in enumerate(raw_tc):
                if hasattr(tc, "function"):
                    name = tc.function.name if hasattr(tc.function, "name") else ""
                    args = tc.function.arguments if hasattr(tc.function, "arguments") else {}
                    tc_id = getattr(tc, "id", None) or f"call_{i}"
                else:
                    fn = tc.get("function", {})
                    name = fn.get("name", "") or tc.get("name", "")
                    args = fn.get("arguments", {}) or tc.get("arguments", {})
                    tc_id = tc.get("id", f"call_{i}")
                if name:
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    tool_calls.append(ToolCall(id=tc_id, name=name, args=args or {}))

        return AIResponse(
            text=text,
            tool_calls=tool_calls if tool_calls else None,
            usage={},
            provider=self.name,
        )
