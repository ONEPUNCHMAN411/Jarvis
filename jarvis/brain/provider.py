from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable
from jarvis.models import Message, AIResponse

class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
    ) -> AIResponse:
        pass

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        category: str | None = None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AIResponse:
        response = await self.chat(messages, tools, system_prompt, temperature, category)
        if on_chunk and response.text:
            await on_chunk(response.text)
        return response

    @abstractmethod
    async def health_check(self) -> bool:
        pass

    @property
    @abstractmethod
    def supports_tools(self) -> bool:
        pass

    @property
    @abstractmethod
    def max_tokens(self) -> int:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass
