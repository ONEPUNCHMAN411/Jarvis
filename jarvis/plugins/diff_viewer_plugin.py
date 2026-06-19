import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class DiffViewerPlugin(Plugin):
    """Compute and display before/after diffs for files or text. Preview edits before
    applying; apply targeted replacements with a confirm step."""

    def __init__(self):
        super().__init__("diff_viewer")

    async def initialize(self):
        logger.info("DiffViewerPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="diff_files",
                description=(
                    "Show a unified diff between two files. "
                    "Use when user says 'show differences between X and Y', 'what changed between these files?', "
                    "'compare file A to file B'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_a": {"type": "string", "description": "Path to first file (before)"},
                        "file_b": {"type": "string", "description": "Path to second file (after)"},
                        "context_lines": {"type": "integer", "default": 3},
                    },
                    "required": ["file_a", "file_b"],
                },
            ), self.diff_files),
            (ToolDefinition(
                name="preview_file_edit",
                description=(
                    "Show a diff preview of replacing old_text with new_text in a file WITHOUT writing it. "
                    "Always call this before apply_file_edit so the user can see what will change. "
                    "Use when user says 'show me what would change if...', 'preview this edit'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "old_text": {"type": "string", "description": "Exact text to replace (must exist verbatim in the file)"},
                        "new_text": {"type": "string", "description": "Replacement text"},
                    },
                    "required": ["file_path", "old_text", "new_text"],
                },
            ), self.preview_edit),
            (ToolDefinition(
                name="apply_file_edit",
                description=(
                    "Replace old_text with new_text in a file. "
                    "Call preview_file_edit first, present the diff to the user, then call this after approval. "
                    "Use when user confirms an edit: 'yes apply that', 'go ahead', 'make that change'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["file_path", "old_text", "new_text"],
                },
            ), self.apply_edit),
            (ToolDefinition(
                name="diff_text",
                description=(
                    "Show a diff between two text strings. "
                    "Use when user pastes before/after text and wants to see what changed."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "before": {"type": "string"},
                        "after": {"type": "string"},
                        "label_before": {"type": "string", "default": "before"},
                        "label_after": {"type": "string", "default": "after"},
                    },
                    "required": ["before", "after"],
                },
            ), self.diff_text),
        ]


    async def diff_files(self, file_a: str, file_b: str, context_lines: int = 3, **_) -> str:
        from jarvis.brain.diff_viewer import get_diff_viewer
        res = await self._run(get_diff_viewer().diff_files, file_a, file_b, context_lines)
        if not res["ok"]:
            return f"Error: {res['error']}"
        if not res["diff"]:
            return "Files are identical."
        return f"{res['changed_lines']} line(s) changed:\n\n```diff\n{res['diff']}\n```"

    async def preview_edit(self, file_path: str, old_text: str, new_text: str, **_) -> str:
        from jarvis.brain.diff_viewer import get_diff_viewer
        res = await self._run(get_diff_viewer().preview_edit, file_path, old_text, new_text)
        if not res["ok"]:
            return f"Preview failed: {res['error']}"
        if not res["diff"]:
            return "No changes (old_text and new_text are identical)."
        return f"Preview of edit to {file_path} ({res['changed_lines']} line(s) affected):\n\n```diff\n{res['diff']}\n```\n\nConfirm with 'apply that edit' or call apply_file_edit to proceed."

    async def apply_edit(self, file_path: str, old_text: str, new_text: str, **_) -> str:
        from jarvis.brain.diff_viewer import get_diff_viewer
        res = await self._run(get_diff_viewer().apply_edit, file_path, old_text, new_text)
        return res["message"] if res["ok"] else f"Error: {res['error']}"

    async def diff_text(self, before: str, after: str, label_before: str = "before", label_after: str = "after", **_) -> str:
        from jarvis.brain.diff_viewer import get_diff_viewer
        res = await self._run(get_diff_viewer().diff_strings, before, after, label_before, label_after)
        if not res["diff"]:
            return "Texts are identical."
        return f"{res['changed_lines']} line(s) changed:\n\n```diff\n{res['diff']}\n```"
