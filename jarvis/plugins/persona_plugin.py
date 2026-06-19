import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class PersonaPlugin(Plugin):
    def __init__(self):
        super().__init__("persona")

    async def initialize(self):
        logger.info("PersonaPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="set_persona",
                description=(
                    "Switch JARVIS to a conversation persona that changes tone, focus, and temperature. "
                    "Built-in options: 'Coder' (terse, technical), 'Tutor' (patient, step-by-step), "
                    "'Coach' (Socratic, questioning), 'Assistant' (default balanced). "
                    "Use when user says 'switch to coder mode', 'act as my tutor', 'be my coach', "
                    "'change persona', 'go back to default', 'reset persona'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Persona name"}},
                    "required": ["name"],
                },
            ), self.set_persona),
            (ToolDefinition(
                name="list_personas",
                description="List all available personas (built-in and custom).",
                parameters={"type": "object", "properties": {}},
            ), self.list_personas),
            (ToolDefinition(
                name="save_custom_persona",
                description=(
                    "Save a custom persona with a name, description, and system prompt. "
                    "Use when user says 'save this as a persona called X', 'create a persona for Y'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "system_prompt": {"type": "string"},
                        "temperature": {"type": "number", "default": 0.7},
                    },
                    "required": ["name", "description", "system_prompt"],
                },
            ), self.save_persona),
            (ToolDefinition(
                name="delete_persona",
                description="Delete a custom persona by name (built-in personas cannot be deleted).",
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ), self.delete_persona),
            (ToolDefinition(
                name="current_persona",
                description="Show the currently active persona and its system prompt.",
                parameters={"type": "object", "properties": {}},
            ), self.current_persona),
        ]


    async def set_persona(self, name: str, **_) -> str:
        from jarvis.brain.persona_store import get_persona_store
        p = await self._run(get_persona_store().set_active, name)
        if not p:
            return f"No persona named '{name}'. Use list_personas to see available options."
        return (
            f"Switched to persona: {p.name}\n"
            f"Description: {p.description}\n"
            f"Temperature: {p.temperature}\n\n"
            f"SYSTEM PROMPT NOW ACTIVE:\n{p.system_prompt}\n\n"
            "Apply this persona to all subsequent responses in this conversation."
        )

    async def list_personas(self, **_) -> str:
        from jarvis.brain.persona_store import get_persona_store
        store = get_persona_store()
        personas = await self._run(store.list_all)
        active = store.get_active()
        lines = ["Available personas:"]
        for p in personas:
            marker = " <- active" if (active and active.name == p.name) else ""
            tag = " [built-in]" if p.builtin else " [custom]"
            lines.append(f"  {p.name}{tag}{marker} — {p.description}  (temp={p.temperature})")
        return "\n".join(lines)

    async def save_persona(self, name: str, description: str, system_prompt: str, temperature: float = 0.7, **_) -> str:
        from jarvis.brain.persona_store import get_persona_store
        p = await self._run(get_persona_store().add, name, description, system_prompt, temperature)
        return f"Saved persona '{p.name}'. Say 'switch to {p.name}' to activate it."

    async def delete_persona(self, name: str, **_) -> str:
        from jarvis.brain.persona_store import get_persona_store
        ok = await self._run(get_persona_store().delete, name)
        return f"Deleted persona '{name}'." if ok else f"No custom persona named '{name}' (built-ins cannot be deleted)."

    async def current_persona(self, **_) -> str:
        from jarvis.brain.persona_store import get_persona_store
        p = get_persona_store().get_active()
        if not p:
            return "No persona active (using default JARVIS behavior)."
        return f"Active persona: {p.name}\n{p.description}\nTemperature: {p.temperature}\n\nSystem prompt:\n{p.system_prompt}"
