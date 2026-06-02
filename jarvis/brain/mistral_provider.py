import asyncio
import json
from collections.abc import Callable, Awaitable
from loguru import logger
import httpx
from jarvis.brain.image_utils import load_image_data_url
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse, ToolCall

# Mistral rate-limit / server-error status codes worth retrying once.
_RETRYABLE = {429, 500, 502, 503, 504}
_RETRY_DELAY = 2.0

def _vision_content(text: str, image_paths: list[str]) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": text or ""}]
    for path in image_paths:
        data_url = load_image_data_url(path)
        if data_url:
            # Pixtral expects {"type": "image_url", "image_url": {"url": "data:..."}}
            content.append({"type": "image_url", "image_url": {"url": data_url}})
    return content

def _messages_to_mistral(
    messages: list[Message],
    system_prompt: str | None = None,
    model: str = "",
) -> list[dict]:
    formatted: list[dict] = []
    if system_prompt:
        formatted.append({"role": "system", "content": system_prompt})

    is_vision = "pixtral" in (model or "").lower()

    for msg in messages:
        # User message (possibly with images for Pixtral)
        if msg.role == "user" and msg.image_paths:
            if is_vision:
                formatted.append(
                    {
                        "role": "user",
                        "content": _vision_content(msg.content or "", msg.image_paths),
                    }
                )
            else:
                # Non-vision model with images: add a system note
                content_text = msg.content or ""
                note = "\n[Note: Screenshot was provided but this model cannot process images. Use describe_screen_text() tool instead.]"
                formatted.append(
                    {
                        "role": "user",
                        "content": content_text + note,
                    }
                )
            continue

        # Tool result message
        if msg.role == "tool":
            entry: dict = {
                "role": "tool",
                "content": msg.content if msg.content is not None else "",
            }
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            formatted.append(entry)
            # Pixtral: attach visual observation as follow-up user message
            if is_vision and msg.image_paths:
                formatted.append(
                    {
                        "role": "user",
                        "content": _vision_content(
                            f"Visual observation from tool result: {msg.content or ''}",
                            msg.image_paths,
                        ),
                    }
                )
            continue

        # Assistant message (may carry tool_calls)
        if msg.role == "assistant":
            entry = {"role": "assistant"}
            if msg.tool_calls:
                # Mistral requires content to be null (not "") when tool_calls present
                entry["content"] = msg.content if msg.content else None
                entry["tool_calls"] = msg.tool_calls
            else:
                entry["content"] = msg.content if msg.content is not None else ""
            formatted.append(entry)
            continue

        # Everything else (system etc.)
        entry = {
            "role": msg.role,
            "content": msg.content if msg.content is not None else "",
        }
        if msg.tool_call_id:
            entry["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            entry["tool_calls"] = msg.tool_calls
        formatted.append(entry)

    return formatted

def _parse_error_body(body: bytes | str) -> str:
    """Extract a human-readable error message from a Mistral error response."""
    try:
        data = json.loads(body)
        # {"error": {"message": "..."}} or {"message": "..."} or {"detail": "..."}
        if isinstance(data, dict):
            if "error" in data:
                err = data["error"]
                if isinstance(err, dict):
                    return err.get("message", str(err))
                return str(err)
            return data.get("message") or data.get("detail") or str(data)
    except Exception:
        pass
    return (body.decode() if isinstance(body, bytes) else str(body))[:300]

class MistralProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "mistral-small-latest",
        timeout: int = 90,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = "https://api.mistral.ai/v1"

    @property
    def name(self) -> str:
        return "mistral"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def max_tokens(self) -> int:
        return 32768

    def _is_vision_model(self) -> bool:
        """Check if this model supports vision (Pixtral models)."""
        return "pixtral" in (self.model or "").lower()

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=8,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Mistral health check failed: {e}")
            return False

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
    ) -> AIResponse:
        if not self.api_key:
            raise ValueError("Mistral API key not configured")

        formatted_messages = _messages_to_mistral(messages, system_prompt, self.model)

        payload: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": min(max(temperature, 0.0), 1.0),
            "max_tokens": 4096,
        }

        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]
            payload["tool_choice"] = "auto"

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=self.timeout,
                    )

                    if response.status_code in _RETRYABLE and attempt == 0:
                        err_msg = _parse_error_body(response.content)
                        logger.warning(
                            f"Mistral {response.status_code} on attempt 1: {err_msg} — retrying in {_RETRY_DELAY}s"
                        )
                        await asyncio.sleep(_RETRY_DELAY)
                        continue

                    if response.status_code != 200:
                        raise RuntimeError(
                            f"Mistral API error {response.status_code}: {_parse_error_body(response.content)}"
                        )

                    data = response.json()
                    choice = data["choices"][0]
                    message = choice["message"]

                    tool_calls: list[ToolCall] = []
                    if message.get("tool_calls"):
                        for tc in message["tool_calls"]:
                            fn = tc["function"]
                            args = fn["arguments"]
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except Exception:
                                    args = {}
                            tool_calls.append(
                                ToolCall(
                                    id=tc.get("id", f"call_mistral_{len(tool_calls)}"),
                                    name=fn["name"],
                                    args=args,
                                )
                            )

                    return AIResponse(
                        text=message.get("content") or "",
                        tool_calls=tool_calls if tool_calls else None,
                        usage=data.get("usage", {}),
                        provider=self.name,
                    )

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exc = e
                if attempt == 0:
                    logger.warning(f"Mistral network error on attempt 1: {e} — retrying")
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                raise
            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"Mistral chat error: {e}")
                raise

        raise last_exc or RuntimeError("Mistral chat failed after retries")

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AIResponse:
        if not self.api_key:
            raise ValueError("Mistral API key not configured")

        formatted_messages = _messages_to_mistral(messages, system_prompt, self.model)
        payload: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": min(max(temperature, 0.0), 1.0),
            "max_tokens": 4096,
            "stream": True,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"

        text = ""
        tool_calls_map: dict[int, dict] = {}
        usage: dict = {}

        last_exc: Exception | None = None
        for attempt in range(2):
            text = ""
            tool_calls_map = {}
            usage = {}
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=self.timeout,
                    ) as response:
                        if response.status_code in _RETRYABLE and attempt == 0:
                            body = await response.aread()
                            logger.warning(
                                f"Mistral stream {response.status_code} on attempt 1 — retrying"
                            )
                            await asyncio.sleep(_RETRY_DELAY)
                            continue

                        if response.status_code != 200:
                            body = await response.aread()
                            raise RuntimeError(
                                f"Mistral API error {response.status_code}: {_parse_error_body(body)}"
                            )

                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            if data.get("usage"):
                                usage = data["usage"]
                            choices = data.get("choices", [])
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            chunk_text = delta.get("content") or ""
                            if chunk_text:
                                text += chunk_text
                                if on_chunk:
                                    await on_chunk(chunk_text)
                            if delta.get("tool_calls"):
                                for tc_delta in delta["tool_calls"]:
                                    idx = tc_delta.get("index", 0)
                                    if idx not in tool_calls_map:
                                        tool_calls_map[idx] = {
                                            "id": tc_delta.get("id", ""),
                                            "name": "",
                                            "arguments": "",
                                        }
                                    if tc_delta.get("id"):
                                        tool_calls_map[idx]["id"] = tc_delta["id"]
                                    fn = tc_delta.get("function", {})
                                    if fn.get("name"):
                                        tool_calls_map[idx]["name"] = fn["name"]
                                    if fn.get("arguments"):
                                        tool_calls_map[idx]["arguments"] += fn["arguments"]
                # Successful stream — break retry loop
                break

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exc = e
                if attempt == 0:
                    logger.warning(f"Mistral stream network error on attempt 1: {e} — retrying")
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                raise
            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"Mistral stream_chat error: {e}")
                raise

        tool_calls: list[ToolCall] = []
        for i, tc_data in sorted(tool_calls_map.items()):
            try:
                args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            tc_id = tc_data["id"] or f"call_mistral_{i}"
            tool_calls.append(ToolCall(id=tc_id, name=tc_data["name"], args=args))

        return AIResponse(
            text=text,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            provider=self.name,
        )
