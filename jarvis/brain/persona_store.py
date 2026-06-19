import json
from dataclasses import dataclass, asdict
from pathlib import Path


_PATH = Path.home() / ".jarvis" / "personas.json"

_BUILT_IN = [
    {
        "name": "Assistant",
        "description": "Balanced, helpful, concise — the default JARVIS mode.",
        "system_prompt": "You are JARVIS, a helpful AI assistant. Be clear, concise, and practical.",
        "temperature": 0.7,
        "builtin": True,
    },
    {
        "name": "Coder",
        "description": "Expert software engineer. Terse, precise, code-first answers.",
        "system_prompt": (
            "You are JARVIS in Coder mode — an expert software engineer. "
            "Give direct, code-first answers. Prefer short snippets over long explanations. "
            "Use technical terminology without definition. Skip pleasantries."
        ),
        "temperature": 0.3,
        "builtin": True,
    },
    {
        "name": "Tutor",
        "description": "Patient teacher. Explains step-by-step, checks understanding.",
        "system_prompt": (
            "You are JARVIS in Tutor mode — a patient, encouraging teacher. "
            "Break down concepts step by step using analogies and examples. "
            "After explaining, ask a follow-up question to check understanding."
        ),
        "temperature": 0.7,
        "builtin": True,
    },
    {
        "name": "Coach",
        "description": "Executive coach. Asks questions, challenges assumptions, motivates.",
        "system_prompt": (
            "You are JARVIS in Coach mode — an executive coach who asks powerful questions "
            "rather than giving direct answers. Challenge assumptions, surface blind spots, "
            "and help the user think through decisions themselves. Be concise and direct."
        ),
        "temperature": 0.8,
        "builtin": True,
    },
]


@dataclass
class Persona:
    name: str
    description: str
    system_prompt: str
    temperature: float = 0.7
    builtin: bool = False


class PersonaStore:
    def __init__(self):
        self._custom: list[Persona] = []
        self._active: str | None = None
        self._load()

    def _load(self):
        if _PATH.exists():
            try:
                data = json.loads(_PATH.read_text("utf-8"))
                self._custom = [Persona(**p) for p in data.get("custom", [])]
                self._active = data.get("active")
            except Exception:
                pass

    def _save(self):
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps({
            "custom": [asdict(p) for p in self._custom],
            "active": self._active,
        }, indent=2), "utf-8")

    def list_all(self) -> list[Persona]:
        return [Persona(**p) for p in _BUILT_IN] + self._custom

    def get(self, name: str) -> Persona | None:
        for p in self.list_all():
            if p.name.lower() == name.lower():
                return p
        return None

    def set_active(self, name: str) -> Persona | None:
        p = self.get(name)
        if p:
            self._active = p.name
            self._save()
        return p

    def get_active(self) -> Persona | None:
        return self.get(self._active) if self._active else None

    def add(self, name: str, description: str, system_prompt: str, temperature: float = 0.7) -> Persona:
        idx = next((i for i, p in enumerate(self._custom) if p.name.lower() == name.lower()), None)
        persona = Persona(name=name, description=description, system_prompt=system_prompt, temperature=temperature)
        if idx is not None:
            self._custom[idx] = persona
        else:
            self._custom.append(persona)
        self._save()
        return persona

    def delete(self, name: str) -> bool:
        for i, p in enumerate(self._custom):
            if p.name.lower() == name.lower():
                self._custom.pop(i)
                if self._active and self._active.lower() == name.lower():
                    self._active = None
                self._save()
                return True
        return False


_store: PersonaStore | None = None


def get_persona_store() -> PersonaStore:
    global _store
    if _store is None:
        _store = PersonaStore()
    return _store
