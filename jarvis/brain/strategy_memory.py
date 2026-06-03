import asyncio
import json
from pathlib import Path

_MAX_ENTRIES_PER_CATEGORY = 200

class StrategyMemory:
    def __init__(self, path: Path | None = None):
        self.path = path or (Path.home() / ".jarvis" / "strategy_memory.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()
        self._dirty = False

    def record(
        self,
        category: str,
        provider: str,
        tools_used: list[str],
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        success: bool,
    ) -> None:
        entries = self._data.setdefault(category, [])
        entries.append(
            {
                "provider": provider,
                "tools_used": list(tools_used),
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "success": success,
            }
        )
        if len(entries) > _MAX_ENTRIES_PER_CATEGORY:
            self._data[category] = entries[-_MAX_ENTRIES_PER_CATEGORY:]
        self._dirty = True

    async def flush(self) -> None:
        if not self._dirty:
            return
        await asyncio.to_thread(self._save)
        self._dirty = False

    def pick(self, category: str, available_providers: list[str]) -> dict | None:
        entries = [
            entry
            for entry in self._data.get(category, [])
            if entry["success"] and entry["provider"] in available_providers
        ]
        if not entries:
            return None

        def score(entry: dict) -> tuple[int, int, int]:
            total_tokens = entry["prompt_tokens"] + entry["completion_tokens"]
            return (entry["latency_ms"], total_tokens, len(entry["tools_used"]))

        return min(entries, key=score)

    def _load(self) -> dict:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        return {}

    def _save(self) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2)
