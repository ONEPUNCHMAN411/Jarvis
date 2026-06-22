import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class MacroCombinerPlugin(Plugin):
    def __init__(self):
        super().__init__("macro_combiner")

    async def initialize(self):
        logger.info("MacroCombinerPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="combine_macros",
                description=(
                    "Combine two or more existing macros into a single new macro. "
                    "The steps from each source macro are concatenated in order, with "
                    "an optional pause between each macro's block. "
                    "Use when user says 'chain macro A and B into one', "
                    "'combine work mode and focus routine', 'merge my two macros'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "macro_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Names or IDs of macros to combine, in order",
                            "minItems": 2,
                        },
                        "new_name": {"type": "string", "description": "Name for the combined macro"},
                        "new_description": {"type": "string", "description": "Description of the combined macro"},
                        "delay_ms_between": {
                            "type": "integer",
                            "default": 500,
                            "description": "Milliseconds to pause between each source macro's steps",
                        },
                    },
                    "required": ["macro_names", "new_name", "new_description"],
                },
            ), self.combine),
            (ToolDefinition(
                name="list_combinable_macros",
                description="List all saved macros available to combine.",
                parameters={"type": "object", "properties": {}},
            ), self.list_macros),
        ]


    async def combine(self, macro_names: list, new_name: str, new_description: str, delay_ms_between: int = 500) -> str:
        from jarvis.brain.macro_store import get_macro_store, MacroStep

        def _do():
            store = get_macro_store()
            combined_steps = []
            missing = []
            for name in macro_names:
                m = store.get(name)
                if not m:
                    missing.append(name)
                    continue
                combined_steps.extend(m.steps)
                if delay_ms_between > 0 and name != macro_names[-1]:
                    combined_steps.append(MacroStep(action="sleep", params={"ms": delay_ms_between}))
            if missing:
                return f"Could not find macros: {', '.join(missing)}. Use list_combinable_macros to check names."
            new_macro = store.add(new_name, new_description, combined_steps)
            return f"Created combined macro '{new_macro.name}' [{new_macro.id}] with {len(combined_steps)} steps from {len(macro_names)} source(s)."

        return await self._run(_do)

    async def list_macros(self, **_) -> str:
        from jarvis.brain.macro_store import get_macro_store
        macros = await self._run(get_macro_store().list_all)
        if not macros:
            return "No macros saved yet."
        lines = ["Available macros:"]
        for m in macros:
            lines.append(f"  [{m.id}] {m.name} — {m.description} ({len(m.steps)} steps)")
        return "\n".join(lines)
