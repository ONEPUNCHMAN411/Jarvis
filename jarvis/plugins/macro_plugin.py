import asyncio
import json

from jarvis.brain.macro_store import MacroStep, get_macro_store
from jarvis.brain.macro_executor import run_macro
from jarvis.models import ToolDefinition
from jarvis.plugins.base import Plugin

_SYSTEM_PROMPT = """You are a macro generation assistant. The user will describe a desktop automation task.
Output ONLY a JSON array of steps. Each step has:
  {"action": "<action>", "params": {<key>: <value>}}

Supported actions:
  type          - params: text (string to type)
  hotkey        - params: keys (list or "ctrl+c" style string)
  press         - params: key (single key name)
  click         - params: x, y (optional screen coords; omit to click at current pos)
  double_click  - params: x, y (optional)
  right_click   - params: x, y (optional)
  move          - params: x, y
  scroll        - params: clicks (positive=up, negative=down), x, y (optional)
  wait          - params: seconds (float)
  write_line    - params: text (types text then presses Enter)
  open_app      - params: path (executable path), wait (seconds to wait after open)
  run_command   - params: command (shell command string), wait (seconds)
  screenshot_region - params: x, y, width, height

Example for "open Notepad and type Hello World":
[
  {"action": "open_app", "params": {"path": "notepad.exe", "wait": 1.5}},
  {"action": "type", "params": {"text": "Hello World"}}
]

Output only the JSON array, no explanation."""


class MacroPlugin(Plugin):
    def __init__(self):
        super().__init__("macro")

    def get_tools(self):
        return [
            (ToolDefinition(
                name="create_macro",
                description="Create an automation macro from a plain English description. JARVIS will generate the steps automatically.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Short name for the macro (e.g. 'Open GitHub')"},
                        "description": {"type": "string", "description": "What the macro does"},
                        "task": {"type": "string", "description": "Plain English description of the automation task"},
                    },
                    "required": ["name", "description", "task"],
                },
            ), self._create_macro),
            (ToolDefinition(
                name="run_macro",
                description="Run a saved macro by name or ID. The macro will execute after a short delay.",
                parameters={
                    "type": "object",
                    "properties": {
                        "macro_id": {"type": "string", "description": "Macro name or ID"},
                        "delay": {"type": "number", "description": "Seconds to wait before starting (default 2)"},
                    },
                    "required": ["macro_id"],
                },
            ), self._run_macro),
            (ToolDefinition(
                name="list_macros",
                description="List all saved automation macros",
                parameters={"type": "object", "properties": {}},
            ), self._list_macros),
            (ToolDefinition(
                name="delete_macro",
                description="Delete a saved macro by name or ID",
                parameters={
                    "type": "object",
                    "properties": {
                        "macro_id": {"type": "string", "description": "Macro name or ID"},
                    },
                    "required": ["macro_id"],
                },
            ), self._delete_macro),
            (ToolDefinition(
                name="inspect_macro",
                description="Show the steps of a saved macro",
                parameters={
                    "type": "object",
                    "properties": {
                        "macro_id": {"type": "string", "description": "Macro name or ID"},
                    },
                    "required": ["macro_id"],
                },
            ), self._inspect_macro),
        ]

    async def _create_macro(self, name: str, description: str, task: str) -> str:
        from jarvis.app import get_runtime
        from jarvis.models import Message

        runtime = get_runtime()
        provider_name = next(iter(runtime.provider_router._order), None)
        if not provider_name:
            return "No AI provider available."
        provider = runtime.provider_router._providers.get(provider_name)
        if not provider:
            return "No AI provider available."

        messages = [
            Message(role="user", content=f"System: {_SYSTEM_PROMPT}\n\nTask: {task}"),
        ]
        resp = await provider.chat(messages, temperature=0.2)
        raw = resp.text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return f"Failed to parse macro steps from AI response: {e}\n\nRaw:\n{raw[:300]}"

        if not isinstance(data, list) or len(data) == 0:
            return "AI returned an empty or invalid step list."

        steps = [MacroStep(action=s["action"], params=s.get("params", {})) for s in data]
        macro = get_macro_store().add(name=name, description=description, steps=steps)
        return (
            f"Macro **'{macro.name}'** created (ID: `{macro.id}`) with **{len(steps)} steps**.\n"
            f"Say `run_macro {macro.name}` to execute it, or open Macros from the chat window."
        )

    async def _run_macro(self, macro_id: str, delay: float = 2.0) -> str:
        ok, msg = await asyncio.to_thread(run_macro, macro_id, delay)
        return msg

    async def _list_macros(self) -> str:
        macros = get_macro_store().list_all()
        if not macros:
            return "No macros saved yet. Ask JARVIS to create one!"
        lines = [f"**{len(macros)} macro(s):**\n"]
        for m in macros:
            last = m.last_run[:10] if m.last_run else "never"
            lines.append(f"  **{m.name}** `{m.id}`  {len(m.steps)} steps | runs: {m.run_count} | last: {last}")
            lines.append(f"   _{m.description}_\n")
        return "\n".join(lines)

    async def _delete_macro(self, macro_id: str) -> str:
        ok = get_macro_store().delete(macro_id)
        return f"Deleted macro '{macro_id}'." if ok else f"Macro '{macro_id}' not found."

    async def _inspect_macro(self, macro_id: str) -> str:
        m = get_macro_store().get(macro_id)
        if not m:
            return f"Macro '{macro_id}' not found."
        lines = [f"**{m.name}** — {m.description}\n"]
        for i, step in enumerate(m.steps, 1):
            params_str = ", ".join(f"{k}={v}" for k, v in step.params.items())
            lines.append(f"  {i:02d}. [{step.action}] {params_str}")
        return "\n".join(lines)
