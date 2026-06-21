import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class FileOrganizerPlugin(Plugin):
    def __init__(self):
        super().__init__("file_organizer")

    async def initialize(self):
        logger.info("FileOrganizerPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="scan_folder",
                description=(
                    "Scan a folder and return file list with name, extension, and size so you "
                    "can propose an organization plan. Call this first, then propose moves to the "
                    "user, then call apply_organization_plan only after they confirm. "
                    "Use when user says 'organize my Downloads', 'sort my files', 'clean up folder'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "folder": {"type": "string", "description": "Folder path, e.g. C:/Users/name/Downloads"},
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional filter, e.g. [\".pdf\", \".jpg\"]. Omit for all files.",
                        },
                    },
                    "required": ["folder"],
                },
            ), self.scan_folder),
            (ToolDefinition(
                name="apply_organization_plan",
                description=(
                    "Execute a list of file move operations. Each item needs 'src' (current path), "
                    "'dst' (destination path), and 'reason'. ONLY call after the user has seen "
                    "and approved the proposed plan."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "proposals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "src": {"type": "string"},
                                    "dst": {"type": "string"},
                                    "reason": {"type": "string"},
                                },
                                "required": ["src", "dst", "reason"],
                            },
                        },
                    },
                    "required": ["proposals"],
                },
            ), self.apply_plan),
        ]


    async def scan_folder(self, folder: str, extensions: list = None) -> str:
        from jarvis.brain.file_organizer import get_file_organizer
        files = await self._run(get_file_organizer().scan, folder, extensions)
        if not files:
            return f"No files found in '{folder}'."
        lines = [f"Found {len(files)} file(s) in {folder}:"]
        for f in files[:60]:
            lines.append(f"  {f['name']}  ({f['ext']}, {f['size_kb']} KB)")
        if len(files) > 60:
            lines.append(f"  … and {len(files) - 60} more.")
        lines.append("\nNow propose an organization plan, present it to the user, then call apply_organization_plan after approval.")
        return "\n".join(lines)

    async def apply_plan(self, proposals: list) -> str:
        from jarvis.brain.file_organizer import get_file_organizer
        res = await self._run(get_file_organizer().apply_plan, proposals)
        parts = []
        if res["moved"]:
            parts.append(f"Moved {len(res['moved'])} file(s):\n" + "\n".join(f"  {m}" for m in res["moved"]))
        if res["skipped"]:
            parts.append(f"Skipped (not found): {', '.join(res['skipped'])}")
        if res["errors"]:
            parts.append(f"Errors: {'; '.join(res['errors'])}")
        return "\n\n".join(parts) or "Nothing to move."
