import asyncio
import json
from collections.abc import Callable, Awaitable
from loguru import logger
from google import genai
from google.genai import types
from jarvis.brain.provider import LLMProvider
from jarvis.models import Message, AIResponse, ToolCall

class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.0-flash",
        oauth_token_path: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self._oauth_token_path = oauth_token_path
        if oauth_token_path:
            self.client = self._build_oauth_client(oauth_token_path)
        else:
            self.client = genai.Client(api_key=api_key)

    @staticmethod
    def _build_oauth_client(token_path: str):
        """Build a genai.Client authenticated via a saved OAuth token."""
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        with open(token_path, "r", encoding="utf-8") as f:
            token_data = json.load(f)

        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return genai.Client(credentials=creds)

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def max_tokens(self) -> int:
        return 8192

    async def health_check(self) -> bool:
        if not self.api_key and not self._oauth_token_path:
            raise ValueError("Gemini: no API key or OAuth token configured.")
        result = await asyncio.to_thread(
            lambda: self.client.models.get(model=self.model)
        )
        return result is not None

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
    ) -> AIResponse:
        try:
            formatted_messages = []
            if system_prompt:
                formatted_messages.append(types.Content(role="user", parts=[types.Part.from_text(text=system_prompt)]))

            for msg in messages:
                role = "user" if msg.role == "user" else "model"
                formatted_messages.append(types.Content(role=role, parts=[types.Part.from_text(text=msg.content)]))

            config_args = {"temperature": temperature}

            if tools:
                tool_list = []
                for t in tools:
                    func_decl = types.FunctionDeclaration(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=t.get("parameters", {"type": "OBJECT"}),
                    )
                    tool_list.append(types.Tool(function_declarations=[func_decl]))
                config_args["tools"] = tool_list

            config = types.GenerateContentConfig(**config_args)

            response = await asyncio.to_thread(
                lambda: self.client.models.generate_content(
                    model=self.model,
                    contents=formatted_messages,
                    config=config,
                )
            )

            tool_calls = []
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        # Extract arguments safely as dict
                        args = part.function_call.args if isinstance(part.function_call.args, dict) else {}
                        tool_calls.append(
                            ToolCall(
                                id=part.function_call.name,
                                name=part.function_call.name,
                                args=args,
                            )
                        )

            return AIResponse(
                text=response.text if response.text else "",
                tool_calls=tool_calls if tool_calls else None,
                usage={
                    "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                    "completion_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
                },
                provider=self.name,
            )

        except Exception as e:
            logger.error(f"Gemini chat error: {e}")
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
        formatted_messages = []
        if system_prompt:
            formatted_messages.append(types.Content(role="user", parts=[types.Part.from_text(text=system_prompt)]))

        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            formatted_messages.append(types.Content(role=role, parts=[types.Part.from_text(text=msg.content)]))

        config_args = {"temperature": temperature}
        if tools:
            tool_list = []
            for t in tools:
                func_decl = types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=t.get("parameters", {"type": "OBJECT"}),
                )
                tool_list.append(types.Tool(function_declarations=[func_decl]))
            config_args["tools"] = tool_list

        config = types.GenerateContentConfig(**config_args)

        text = ""
        tool_calls: list[ToolCall] = []

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()  # safe in async context

        def _stream_sync():
            try:
                for chunk in self.client.models.generate_content_stream(
                    model=self.model,
                    contents=formatted_messages,
                    config=config,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        asyncio.ensure_future(asyncio.to_thread(_stream_sync))
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            if chunk.text:
                text += chunk.text
                if on_chunk:
                    await on_chunk(chunk.text)
            if chunk.candidates and chunk.candidates[0].content.parts:
                for part in chunk.candidates[0].content.parts:
                    if part.function_call:
                        args = part.function_call.args if isinstance(part.function_call.args, dict) else {}
                        tool_calls.append(ToolCall(id=part.function_call.name, name=part.function_call.name, args=args))

        return AIResponse(
            text=text,
            tool_calls=tool_calls if tool_calls else None,
            usage={},
            provider=self.name,
        )
