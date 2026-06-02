import asyncio
import base64
import json
import os
from collections.abc import Callable, Awaitable
from loguru import logger
from anthropic import AsyncAnthropic, APIStatusError
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse, ToolCall

def _load_image_b64(path: str) -> str | None:
    """Read a PNG file and return its base64-encoded content, or None on failure."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode()
    except Exception:
        return None

def _image_block(path: str) -> dict | None:
    """Build an Anthropic image content block from a file path, or None if unreadable."""
    b64 = _load_image_b64(path)
    if b64 is None:
        return None
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": b64},
    }

class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5"):
        self.api_key = api_key
        self.model = model
        self.client = AsyncAnthropic(api_key=api_key)

    @property
    def name(self) -> str:
        return "claude"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def max_tokens(self) -> int:
        return 4096

    async def health_check(self) -> bool:
        if not self.api_key:
            raise ValueError("API key is not configured.")
        models = await self.client.models.list(limit=1)
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
                    logger.warning(f"Claude HTTP {status} on attempt {attempt+1}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                raise
            except Exception as e:
                last_err = e
                logger.error(f"Claude chat error: {e}")
                raise
        raise last_err  # type: ignore[misc]

    async def _do_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        system_prompt: str | None,
        temperature: float,
    ) -> AIResponse:
        # Convert JARVIS messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                # Anthropic takes system prompt as a top-level parameter
                continue

            if msg.role == "tool":
                # Build tool_result content — may include screenshot images
                if msg.image_paths:
                    tool_content: list | str = [{"type": "text", "text": msg.content}]
                    for img_path in msg.image_paths:
                        blk = _image_block(img_path)
                        if blk:
                            tool_content.append(blk)  # type: ignore[union-attr]
                else:
                    tool_content = msg.content
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": tool_content,
                        }
                    ],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    # tool_calls in JARVIS models is stored in OpenAI-compatible dict
                    # format: {"id": ..., "type": "function",
                    #          "function": {"name": ..., "arguments": "<json>"}}
                    # OR as a ToolCall object with .id/.name/.args attributes.
                    if isinstance(tc, dict):
                        tc_id = tc["id"]
                        if "function" in tc:
                            # OpenAI-style format (what app.py stores)
                            tc_name = tc["function"]["name"]
                            raw_args = tc["function"].get("arguments", "{}")
                            tc_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        else:
                            # Simple dict format (legacy)
                            tc_name = tc.get("name", "")
                            tc_args = tc.get("args", {})
                    else:
                        tc_id = tc.id
                        tc_name = tc.name
                        tc_args = tc.args

                    content.append({
                        "type": "tool_use",
                        "id": tc_id,
                        "name": tc_name,
                        "input": tc_args,
                    })
                anthropic_messages.append({"role": "assistant", "content": content})
            elif msg.role == "user" and msg.image_paths:
                # User message with screenshot(s) attached
                user_content: list = [{"type": "text", "text": msg.content or ""}]
                for img_path in msg.image_paths:
                    blk = _image_block(img_path)
                    if blk:
                        user_content.append(blk)
                anthropic_messages.append({"role": "user", "content": user_content})
            else:
                anthropic_messages.append({"role": msg.role, "content": msg.content or ""})

        kwargs: dict = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            anthropic_tools = []
            for t in tools:
                anthropic_tools.append({
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                })
            # NOTE: Do NOT add the native computer_20241022 tool here.
            # JARVIS has its own custom "computer" tool that handles all desktop
            # actions (screenshot, click, type, etc.) and embeds screenshots
            # directly in the conversation.  Adding the native beta tool creates
            # a duplicate tool name which breaks tool dispatch.
            kwargs["tools"] = anthropic_tools

        response = await self.client.messages.create(**kwargs)

        text = ""
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    args=block.input if isinstance(block.input, dict) else {},
                ))

        return AIResponse(
            text=text,
            tool_calls=tool_calls if tool_calls else None,
            usage={
                "prompt_tokens":     response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
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
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                continue
            if msg.role == "tool":
                if msg.image_paths:
                    tool_content: list | str = [{"type": "text", "text": msg.content}]
                    for img_path in msg.image_paths:
                        blk = _image_block(img_path)
                        if blk:
                            tool_content.append(blk)
                else:
                    tool_content = msg.content
                anthropic_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": msg.tool_call_id, "content": tool_content}],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    if isinstance(tc, dict):
                        tc_id = tc["id"]
                        if "function" in tc:
                            tc_name = tc["function"]["name"]
                            raw_args = tc["function"].get("arguments", "{}")
                            tc_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        else:
                            tc_name = tc.get("name", "")
                            tc_args = tc.get("args", {})
                    else:
                        tc_id = tc.id
                        tc_name = tc.name
                        tc_args = tc.args
                    content.append({"type": "tool_use", "id": tc_id, "name": tc_name, "input": tc_args})
                anthropic_messages.append({"role": "assistant", "content": content})
            elif msg.role == "user" and msg.image_paths:
                user_content: list = [{"type": "text", "text": msg.content or ""}]
                for img_path in msg.image_paths:
                    blk = _image_block(img_path)
                    if blk:
                        user_content.append(blk)
                anthropic_messages.append({"role": "user", "content": user_content})
            else:
                anthropic_messages.append({"role": msg.role, "content": msg.content or ""})

        kwargs: dict = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [
                {"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("parameters", {"type": "object", "properties": {}})}
                for t in tools
            ]

        text = ""
        tool_calls: list[ToolCall] = []
        input_tokens = 0
        output_tokens = 0

        async with self.client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        text += event.delta.text
                        if on_chunk:
                            await on_chunk(event.delta.text)
                    elif hasattr(event.delta, "partial_json"):
                        pass
                elif event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        tool_calls.append(ToolCall(
                            id=event.content_block.id,
                            name=event.content_block.name,
                            args={},
                        ))
                elif event.type == "content_block_stop":
                    pass

            final_message = await stream.get_final_message()
            input_tokens = final_message.usage.input_tokens
            output_tokens = final_message.usage.output_tokens
            for block in final_message.content:
                if block.type == "tool_use" and block.input:
                    for tc in tool_calls:
                        if tc.id == block.id:
                            tc.args = block.input if isinstance(block.input, dict) else {}

        return AIResponse(
            text=text,
            tool_calls=tool_calls if tool_calls else None,
            usage={"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
            provider=self.name,
        )
