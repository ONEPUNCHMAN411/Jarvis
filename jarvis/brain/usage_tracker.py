
import threading

from loguru import logger

_CTX_WINDOWS: dict[str, int] = {
    "claude":           200_000,
    "claude_code_auto": 200_000,
    "claude_code_pipe": 200_000,
    "openai":           128_000,
    "gemini":         1_000_000,
    "groq":              32_768,
    "mistral":           32_000,
    "ollama":             8_192,
    "llamacpp":          32_768,
    "openrouter":       128_000,
}


class UsageTracker:
    """Tracks per-session token usage and context window fill."""

    def __init__(self):
        self._last_prompt_tokens: int = 0
        self._session_completion_tokens: int = 0
        self._provider: str = ""
        self._model: str = ""

    def record(
        self,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "",
    ) -> None:
        self._provider = provider
        self._model = model
        # Use the actual reported value — not a running max — so ctx% stays
        # accurate when switching providers or when history is trimmed.
        self._last_prompt_tokens = prompt_tokens
        self._session_completion_tokens += completion_tokens
        logger.debug(f"UsageTracker: {provider} prompt={prompt_tokens} comp={completion_tokens}")

    def get_context_window(self, provider: str, model: str = "") -> int:
        if provider == "groq" and model:
            try:
                from jarvis.brain.groq_provider import _model_caps
                return _model_caps(model)["ctx"]
            except Exception:
                pass
        return _CTX_WINDOWS.get(provider, 8_192)

    def get_usage_pct(self, provider: str = "", model: str = "") -> float:
        prov = provider or self._provider
        mod = model or self._model
        ctx = self.get_context_window(prov, mod)
        used = self._last_prompt_tokens
        if not ctx or not used:
            return 0.0
        return min(100.0, used * 100 / ctx)

    def get_tokens_used(self) -> int:
        return self._last_prompt_tokens

    def get_stats(self) -> dict:
        return {
            "last_prompt_tokens": self._last_prompt_tokens,
            "session_completion_tokens": self._session_completion_tokens,
            "provider": self._provider,
            "model": self._model,
        }

    def reset(self) -> None:
        self._last_prompt_tokens = 0
        self._session_completion_tokens = 0
        logger.debug("UsageTracker reset")


_tracker: UsageTracker | None = None
_tracker_lock = threading.Lock()


def get_usage_tracker() -> UsageTracker:
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = UsageTracker()
    return _tracker
