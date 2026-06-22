
import asyncio
import json

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class BlenderPlugin(Plugin):
    """Control Blender: inspect the scene and run bpy Python to model, animate,
    light, and render. Requires Blender open with the BlenderMCP addon server."""

    def __init__(self):
        super().__init__("blender")
        self._client = None

    def _get(self):
        if self._client is None:
            from jarvis.brain.blender_client import get_blender
            self._client = get_blender()
        return self._client

    async def initialize(self) -> None:
        logger.info("BlenderPlugin ready (connects on first use, port 9876)")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="blender_get_scene_info",
                    description=(
                        "Get the current Blender scene: objects, materials, and "
                        "stats. Inspect this before modifying so you know what "
                        "exists. Use when the user says 'what's in my Blender scene' "
                        "or 'list the objects in Blender'."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.get_scene_info,
            ),
            (
                ToolDefinition(
                    name="blender_get_object_info",
                    description=(
                        "Get details (location, rotation, scale, mesh, materials) "
                        "of one object in the Blender scene by name."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Object name"}
                        },
                        "required": ["name"],
                    },
                ),
                self.get_object_info,
            ),
            (
                ToolDefinition(
                    name="blender_execute_code",
                    description=(
                        "Run Python (bpy) code inside Blender to create or modify "
                        "objects, materials, modifiers, animation, lighting, and to "
                        "render. Write complete, valid bpy code. Use when the user "
                        "says 'in Blender, make a ...', 'add a cube', 'create a "
                        "low-poly tree', or 'render the scene'. Inspect the scene "
                        "first if unsure what exists."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python bpy code to execute in Blender",
                            }
                        },
                        "required": ["code"],
                    },
                ),
                self.execute_code,
            ),
            (
                ToolDefinition(
                    name="blender_screenshot",
                    description=(
                        "Capture a screenshot of the Blender 3D viewport to see the "
                        "current result. Returns the saved image path."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.screenshot,
            ),
        ]

    async def _cmd(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    @staticmethod
    def _err(resp: dict) -> str | None:
        if resp.get("status") == "error":
            return f"Blender error: {resp.get('message', 'unknown error')}"
        return None

    async def get_scene_info(self, **_) -> str:
        resp = await self._cmd(self._get().get_scene_info)
        err = self._err(resp)
        if err:
            return err
        return "Blender scene:\n" + json.dumps(resp.get("result", resp), indent=2)[:1800]

    async def get_object_info(self, name: str) -> str:
        resp = await self._cmd(self._get().get_object_info, name)
        err = self._err(resp)
        if err:
            return err
        return json.dumps(resp.get("result", resp), indent=2)[:1800]

    async def execute_code(self, code: str) -> str:
        resp = await self._cmd(self._get().execute_code, code)
        err = self._err(resp)
        if err:
            return err
        result = resp.get("result", {})
        out = result.get("result", "") if isinstance(result, dict) else str(result)
        return "Executed in Blender." + (f" Output: {out}" if out else "")

    async def screenshot(self, **_) -> str:
        resp = await self._cmd(self._get().get_viewport_screenshot)
        err = self._err(resp)
        if err:
            return err
        result = resp.get("result", {})
        path = result.get("path") if isinstance(result, dict) else None
        return f"Viewport captured: {path}" if path else "Viewport screenshot taken."
