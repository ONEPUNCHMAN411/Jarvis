import json
from collections.abc import Callable, Awaitable
from loguru import logger

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from jarvis.brain.image_utils import load_image_data_url
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse, ToolCall

def _messages_to_openai(
    messages: list[Message],
    system_prompt: str | None,
    has_vision: bool = False,
) -> list[dict]:
    """Convert JARVIS messages to OpenAI-compatible format.

    When has_vision=True, user messages with image_paths are serialized as
    multipart content (text + image_url) so llama-server with --mmproj can
    process screenshots alongside text.
    """
    formatted: list[dict] = []

    if system_prompt:
        formatted.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg.role == "user":
            if has_vision and getattr(msg, "image_paths", None):
                parts: list[dict] = []
                for path in msg.image_paths:
                    data_url = load_image_data_url(path)
                    if data_url:
                        parts.append({"type": "image_url", "image_url": {"url": data_url}})
                if msg.content:
                    parts.append({"type": "text", "text": msg.content})
                formatted.append({"role": "user", "content": parts})
                continue
            formatted.append({
                "role": "user",
                "content": msg.content if msg.content is not None else "",
            })

        elif msg.role == "assistant":
            entry: dict = {"role": "assistant"}
            if msg.tool_calls:
                entry["content"] = msg.content if msg.content else None
                entry["tool_calls"] = msg.tool_calls
            else:
                entry["content"] = msg.content if msg.content is not None else ""
            formatted.append(entry)

        elif msg.role == "tool":
            entry = {
                "role": "tool",
                "content": msg.content if msg.content is not None else "",
            }
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            formatted.append(entry)

        else:
            formatted.append({
                "role": msg.role,
                "content": msg.content if msg.content is not None else "",
            })

    return formatted

def _tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert tool definitions to OpenAI function-calling format."""
    openai_tools = []
    for t in tools:
        fn: dict = {
            "name": t["name"],
            "description": t.get("description", ""),
        }
        params = t.get("parameters", {})
        if params:
            fn["parameters"] = params
        openai_tools.append({"type": "function", "function": fn})
    return openai_tools

class LlamaCppProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080/v1",
        model: str = "local",
        timeout: int = 120,
        has_mmproj: bool = False,
    ):
        if httpx is None:
            raise ImportError(
                "httpx is required for LlamaCppProvider. "
                "Install it with: pip install httpx"
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.has_mmproj = has_mmproj
        # Non-streaming: 120s total. Streaming: 600s read timeout to survive
        # long image encoding or extended thinking phases.
        self.timeout_non_streaming = httpx.Timeout(connect=10.0, read=timeout, write=30.0, pool=10.0)
        self.timeout_streaming = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)

    @property
    def name(self) -> str:
        return "llamacpp"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return self.has_mmproj

    @property
    def max_tokens(self) -> int:
        return 16384

    async def health_check(self) -> bool:
        # Strip /v1 suffix — /health lives at the server root, not under /v1
        server_root = self.base_url.removesuffix("/v1").removesuffix("/v1/")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(f"{server_root}/health")
                # 200 = fully loaded; 503 = still loading model (treat as not ready)
                if response.status_code == 200:
                    return True
                logger.debug(f"llamacpp /health returned {response.status_code} — not ready yet")
                return False
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.debug("llamacpp health check: server not reachable")
            return False
        except Exception as exc:
            logger.debug(f"llamacpp health check failed: {exc}")
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
            return await self._do_chat(
                messages, tools, system_prompt, temperature
            )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error(f"LlamaCpp connection error: {e}")
            raise ConnectionError(
                "llama-server is not running. Start it from Settings → Local AI"
            ) from e
        except Exception as e:
            logger.error(f"LlamaCpp chat error: {e}")
            raise

    async def _do_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        system_prompt: str | None,
        temperature: float,
    ) -> AIResponse:
        formatted_messages = _messages_to_openai(messages, system_prompt, has_vision=self.has_mmproj)

        payload: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            # Disable Qwen3 extended thinking. Without this the model can spend
            # 100–200 s in silent thinking before the first visible token arrives.
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        if tools:
            payload["tools"] = _tools_to_openai(tools)

        async with httpx.AsyncClient(timeout=self.timeout_non_streaming) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        tool_calls: list[ToolCall] = []
        message_data = data.get("choices", [{}])[0].get("message", {})

        if "tool_calls" in message_data and message_data["tool_calls"]:
            for tc in message_data["tool_calls"]:
                try:
                    raw = (
                        json.loads(tc.get("function", {}).get("arguments", "{}"))
                        if tc.get("function", {}).get("arguments")
                        else {}
                    )
                    args = raw if isinstance(raw, dict) else {}
                except (json.JSONDecodeError, ValueError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("function", {}).get("name", ""),
                    args=args,
                ))

        return AIResponse(
            text=message_data.get("content", ""),
            tool_calls=tool_calls if tool_calls else None,
            usage=data.get("usage", {}),
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
        try:
            return await self._do_stream_chat(
                messages, tools, system_prompt, temperature, on_chunk
            )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error(f"LlamaCpp stream connection error: {e}")
            raise ConnectionError(
                "llama-server is not running. Start it from Settings → Local AI"
            ) from e
        except Exception as e:
            logger.error(f"LlamaCpp stream error: {e}")
            raise

    async def _do_stream_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        system_prompt: str | None,
        temperature: float,
        on_chunk: Callable[[str], Awaitable[None]] | None,
    ) -> AIResponse:
        formatted_messages = _messages_to_openai(messages, system_prompt, has_vision=self.has_mmproj)

        payload: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        if tools:
            payload["tools"] = _tools_to_openai(tools)

        text = ""
        usage = {}

        async with httpx.AsyncClient(timeout=self.timeout_streaming) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        if "usage" in chunk:
                            usage = chunk["usage"]
                        continue

                    delta = choices[0].get("delta", {})
                    # `content` = visible output; `reasoning_content` = thinking tokens.
                    # We only forward visible output to the user.
                    content = delta.get("content") or ""
                    if content:
                        text += content
                        if on_chunk:
                            await on_chunk(content)

        return AIResponse(
            text=text,
            tool_calls=None,
            usage=usage,
            provider=self.name,
        )
