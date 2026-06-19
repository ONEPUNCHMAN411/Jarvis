import asyncio
import os
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

_MAX_BYTES = 200_000


class CodeReviewPlugin(Plugin):
    def __init__(self):
        super().__init__("code_review")

    async def initialize(self):
        logger.info("CodeReviewPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="review_code_file",
                description=(
                    "Read a source file and return its contents with review instructions. "
                    "Produces a structured review: bugs, edge cases, performance, security, style, summary. "
                    "Use when user says 'review this file', 'check my code', "
                    "'find bugs in X.py', 'do a code review of this'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Absolute or relative path to the source file"},
                        "focus": {
                            "type": "string",
                            "description": "Optional focus: 'bugs', 'performance', 'security', 'style', or 'all'",
                            "default": "all",
                        },
                    },
                    "required": ["file_path"],
                },
            ), self.review_file),
            (ToolDefinition(
                name="review_code_snippet",
                description=(
                    "Review a code snippet pasted directly. "
                    "Use when user pastes code and asks 'review this', 'what's wrong here?', "
                    "'any issues with this code?'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "language": {"type": "string", "default": ""},
                        "focus": {"type": "string", "default": "all"},
                    },
                    "required": ["code"],
                },
            ), self.review_snippet),
            (ToolDefinition(
                name="explain_code_file",
                description=(
                    "Read a file and explain what it does in plain English — architecture, "
                    "key functions, data flow, dependencies. "
                    "Use when user says 'explain this file', 'what does X.py do?', 'walk me through this'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "detail_level": {"type": "string", "enum": ["brief", "detailed"], "default": "detailed"},
                    },
                    "required": ["file_path"],
                },
            ), self.explain_file),
        ]


    def _read(self, path: str) -> str:
        p = os.path.abspath(path)
        if not os.path.exists(p):
            raise FileNotFoundError(f"File not found: {p}")
        size = os.path.getsize(p)
        if size > _MAX_BYTES:
            raise ValueError(f"File too large ({size // 1024} KB). Max 200 KB.")
        return open(p, encoding="utf-8", errors="ignore").read()

    async def review_file(self, file_path: str, focus: str = "all", **_) -> str:
        try:
            code = await self._run(self._read, file_path)
        except Exception as e:
            return str(e)
        lang = os.path.splitext(file_path)[1].lstrip(".")
        focus_note = f" Pay special attention to {focus}." if focus != "all" else ""
        return (
            f"File: {file_path}  ({len(code.splitlines())} lines, {lang})\n\n"
            f"```{lang}\n{code}\n```\n\n"
            f"Perform a thorough code review of the file above.{focus_note}\n"
            "Structure your findings under these headings:\n"
            "**Bugs / Logic Errors** — anything that causes incorrect behavior\n"
            "**Edge Cases** — inputs or states not handled\n"
            "**Performance** — unnecessary work, O(n^2), missing caches\n"
            "**Security** — injection risks, exposed secrets, unsafe deserialization\n"
            "**Style & Maintainability** — naming, duplication, dead code\n"
            "**Summary** — one-paragraph verdict and top 3 priority fixes"
        )

    async def review_snippet(self, code: str, language: str = "", focus: str = "all", **_) -> str:
        lang = language or "text"
        focus_note = f" Pay special attention to {focus}." if focus != "all" else ""
        return (
            f"```{lang}\n{code}\n```\n\n"
            f"Review the snippet above.{focus_note} "
            "Use the same structure: Bugs, Edge Cases, Performance, Security, Style, Summary."
        )

    async def explain_file(self, file_path: str, detail_level: str = "detailed", **_) -> str:
        try:
            code = await self._run(self._read, file_path)
        except Exception as e:
            return str(e)
        lang = os.path.splitext(file_path)[1].lstrip(".")
        depth = "a brief overview" if detail_level == "brief" else "a detailed explanation covering architecture, key functions, data flow, and external dependencies"
        return (
            f"File: {file_path}  ({len(code.splitlines())} lines)\n\n"
            f"```{lang}\n{code}\n```\n\n"
            f"Provide {depth} of the code above in plain English."
        )
