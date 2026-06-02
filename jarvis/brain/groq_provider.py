import asyncio
import json
from collections.abc import Callable, Awaitable
from loguru import logger
from groq import AsyncGroq, APIStatusError
from jarvis.brain.image_utils import load_image_data_url
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse, ToolCall

# Context windows and recommended max_tokens per model.
# Free-tier models are marked — the SDK doesn't care, but prompts can adapt.
_MODEL_CAPS: dict[str, dict] = {
    # Llama 3.3
    "llama-3.3-70b-versatile":       {"ctx": 128_000, "max_out": 32_768, "vision": False, "free": True},
    "llama-3.3-70b-specdec":         {"ctx": 8_192,   "max_out": 8_192,  "vision": False, "free": True},
    # Llama 3.1
    "llama-3.1-70b-versatile":       {"ctx": 128_000, "max_out": 32_768, "vision": False, "free": True},
    "llama-3.1-8b-instant":          {"ctx": 128_000, "max_out": 8_192,  "vision": False, "free": True},
    # Llama 3.2 (vision-capable)
    "llama-3.2-90b-vision-preview":  {"ctx": 8_192,   "max_out": 8_192,  "vision": True,  "free": True},
    "llama-3.2-11b-vision-preview":  {"ctx": 8_192,   "max_out": 8_192,  "vision": True,  "free": True},
    "llama-3.2-3b-preview":          {"ctx": 8_192,   "max_out": 8_192,  "vision": False, "free": True},
    "llama-3.2-1b-preview":          {"ctx": 8_192,   "max_out": 8_192,  "vision": False, "free": True},
    # Llama 3
    "llama3-70b-8192":               {"ctx": 8_192,   "max_out": 4_096,  "vision": False, "free": True},
    "llama3-8b-8192":                {"ctx": 8_192,   "max_out": 4_096,  "vision": False, "free": True},
    # Mixtral
    "mixtral-8x7b-32768":            {"ctx": 32_768,  "max_out": 4_096,  "vision": False, "free": True},
    # Gemma
    "gemma2-9b-it":                  {"ctx": 8_192,   "max_out": 4_096,  "vision": False, "free": True},
    "gemma-7b-it":                   {"ctx": 8_192,   "max_out": 4_096,  "vision": False, "free": True},
    # Compound beta
    "llama-3.3-70b-versatile-compound-beta": {"ctx": 128_000, "max_out": 8_192, "vision": False, "free": False},
}

_DEFAULT_MAX_OUT = 4_096

def _model_caps(model: str) -> dict:
    return _MODEL_CAPS.get(model, {"ctx": 8_192, "max_out": _DEFAULT_MAX_OUT, "vision": False, "free": False})

def _is_vision_model(model: str) -> bool:
    return _model_caps(model)["vision"]

def get_vision_models() -> frozenset[str]:
    return frozenset(name for name, caps in _MODEL_CAPS.items() if caps["vision"])

def get_small_ctx_models(threshold: int = 8_192) -> frozenset[str]:
    return frozenset(name for name, caps in _MODEL_CAPS.items() if caps["ctx"] <= threshold)

def _messages_to_groq(
    messages: list[Message],
    system_prompt: str | None,
    model: str,
) -> list[dict]:
    """Convert JARVIS messages to Groq's OpenAI-compatible format.

    For vision models, user image_paths are encoded inline.
    For non-vision models, image_paths are silently dropped.
    """
    is_vision = _is_vision_model(model)
    formatted: list[dict] = []

    if system_prompt:
        formatted.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg.role == "user" and msg.image_paths and is_vision:
            content: list[dict] = [{"type": "text", "text": msg.content or ""}]
            for path in msg.image_paths:
                data_url = load_image_data_url(path)
                if data_url:
                    content.append({"type": "image_url", "image_url": {"url": data_url}})
            formatted.append({"role": "user", "content": content})

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

class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self.client = AsyncGroq(api_key=api_key)

    @property
    def name(self) -> str:
        return "groq"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return _is_vision_model(self.model)

    @property
    def max_tokens(self) -> int:
        return _model_caps(self.model)["max_out"]

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
                    logger.warning(f"Groq HTTP {status} on attempt {attempt+1}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Groq API error {status}: {e}")
                raise
            except Exception as e:
                last_err = e
                logger.error(f"Groq chat error: {e}")
                raise
        raise last_err  # type: ignore[misc]

    async def _do_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        system_prompt: str | None,
        temperature: float,
    ) -> AIResponse:
        formatted_messages = _messages_to_groq(messages, system_prompt, self.model)

        kwargs: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }

        if tools and not _is_vision_model(self.model):
            # Groq vision models don't support tool_use simultaneously
            groq_tools = []
            for t in tools:
                fn: dict = {
                    "name": t["name"],
                    "description": t.get("description", ""),
                }
                params = t.get("parameters", {})
                if params:
                    fn["parameters"] = _clean_schema(params)
                groq_tools.append({"type": "function", "function": fn})
            kwargs["tools"] = groq_tools

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
        formatted_messages = _messages_to_groq(messages, system_prompt, self.model)
        kwargs: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if tools and not _is_vision_model(self.model):
            groq_tools = []
            for t in tools:
                fn: dict = {"name": t["name"], "description": t.get("description", "")}
                params = t.get("parameters", {})
                if params:
                    fn["parameters"] = _clean_schema(params)
                groq_tools.append({"type": "function", "function": fn})
            kwargs["tools"] = groq_tools

        text = ""
        tool_calls_map: dict[int, dict] = {}
        usage = {}

        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                if hasattr(chunk, "x_groq") and chunk.x_groq and hasattr(chunk.x_groq, "usage"):
                    u = chunk.x_groq.usage
                    usage = {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens}
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

def _clean_schema(schema: dict) -> dict:
    """Strip JSON-Schema keys Groq doesn't accept."""
    ALLOWED_TOP = {"type", "properties", "required", "description", "enum",
                   "items", "anyOf", "oneOf", "allOf", "not", "additionalProperties"}
    ALLOWED_PROP = {"type", "description", "enum", "items", "anyOf",
                    "oneOf", "allOf", "not", "properties", "required",
                    "minimum", "maximum", "default"}
    result = {k: v for k, v in schema.items() if k in ALLOWED_TOP}
    if "properties" in result:
        result["properties"] = {
            k: {pk: pv for pk, pv in prop.items() if pk in ALLOWED_PROP}
            for k, prop in result["properties"].items()
        }
    return result
