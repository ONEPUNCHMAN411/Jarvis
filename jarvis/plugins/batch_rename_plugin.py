import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class BatchRenamePlugin(Plugin):
    def __init__(self):
        super().__init__("batch_rename")

    async def initialize(self):
        logger.info("BatchRenamePlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="scan_files_for_rename",
                description=(
                    "Scan a folder and read content hints from images (EXIF metadata), "
                    "PDFs (first-page text), and documents so you can propose meaningful "
                    "new filenames. Call this first, present the rename plan to the user, "
                    "then call apply_batch_rename only after they confirm. "
                    "Use when user says 'rename my files based on content', "
                    "'AI rename my downloads', 'clean up these filenames'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "folder": {"type": "string", "description": "Folder path to scan"},
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional filter e.g. [\".jpg\", \".pdf\"]. Omit for all.",
                        },
                    },
                    "required": ["folder"],
                },
            ), self.scan),
            (ToolDefinition(
                name="apply_batch_rename",
                description=(
                    "Execute file rename operations. Each proposal needs 'src' (current full path) "
                    "and 'dst' (new full path including new filename). "
                    "ONLY call after the user has seen and approved the plan."
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
                                },
                                "required": ["src", "dst"],
                            },
                        },
                    },
                    "required": ["proposals"],
                },
            ), self.apply),
        ]


    async def scan(self, folder: str, extensions: list = None) -> str:
        from jarvis.brain.batch_renamer import get_batch_renamer
        files = await self._run(get_batch_renamer().scan, folder, extensions)
        if not files:
            return f"No files found in '{folder}'."
        lines = [f"Found {len(files)} file(s) in {folder}:"]
        for f in files[:50]:
            hint_str = f"\n    ↳ {f['content_hint'][:120]}" if f["content_hint"] else ""
            lines.append(f"  {f['name']}  ({f['ext']}, {f['size_kb']} KB){hint_str}")
        if len(files) > 50:
            lines.append(f"  … and {len(files) - 50} more.")
        lines.append(
            "\nPropose clear, descriptive filenames based on the content hints above. "
            "Present the plan to the user, then call apply_batch_rename after approval."
        )
        return "\n".join(lines)

    async def apply(self, proposals: list) -> str:
        from jarvis.brain.batch_renamer import get_batch_renamer
        res = await self._run(get_batch_renamer().apply, proposals)
        parts = []
        if res["renamed"]:
            parts.append(f"Renamed {len(res['renamed'])} file(s):\n" + "\n".join(f"  {r}" for r in res["renamed"]))
        if res["skipped"]:
            parts.append(f"Skipped (not found): {', '.join(res['skipped'])}")
        if res["errors"]:
            parts.append(f"Errors: {'; '.join(res['errors'])}")
        return "\n\n".join(parts) or "Nothing renamed."
