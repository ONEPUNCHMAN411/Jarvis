import asyncio
import os
import shlex
import subprocess
from pathlib import Path
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class DryRunPlugin(Plugin):
    """Preview shell commands and file writes before executing them.
    Shows what would happen — files affected, directories created, output expected —
    without making any changes."""

    def __init__(self):
        super().__init__("dryrun")

    async def initialize(self):
        logger.info("DryRunPlugin ready")

    async def shutdown(self):
        pass

    def get_tools(self):
        return [
            (ToolDefinition(
                name="preview_shell_command",
                description=(
                    "Parse and analyse a shell command to show what it would do without running it. "
                    "Reports: command type, files/paths affected, potential risks, safe to run yes/no. "
                    "Use when user says 'what would this command do?', 'preview this command', "
                    "'is it safe to run X?', 'dry run this'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to analyse"},
                        "shell": {"type": "string", "enum": ["cmd", "powershell", "bash"], "default": "cmd"},
                    },
                    "required": ["command"],
                },
            ), self.preview_shell),
            (ToolDefinition(
                name="preview_file_write",
                description=(
                    "Show what would happen if a file were written — whether it exists, its current size, "
                    "and a diff if the new content is provided. Does NOT write anything. "
                    "Use when about to write a file and user wants to preview first."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "new_content": {
                            "type": "string",
                            "description": "Content that would be written. Omit to just show file status.",
                            "default": "",
                        },
                    },
                    "required": ["file_path"],
                },
            ), self.preview_write),
            (ToolDefinition(
                name="preview_python",
                description=(
                    "Run a Python snippet in dry-run mode: validate syntax and report what it would import "
                    "or call, but do NOT execute side effects. "
                    "Use when user wants to check Python code before running it."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                    },
                    "required": ["code"],
                },
            ), self.preview_python),
        ]


    def _analyse_shell(self, command: str, shell: str) -> str:
        cmd = command.strip()
        lines = ["Command analysis (DRY RUN — nothing executed):"]
        lines.append(f"  Shell: {shell}")
        lines.append(f"  Command: {cmd}")

        risk_keywords = {
            "rm": "DELETES files", "del": "DELETES files", "rmdir": "DELETES directory",
            "format": "FORMATS disk", "mkfs": "FORMATS disk",
            "dd": "LOW-LEVEL write — can overwrite disk",
            "reg delete": "DELETES registry key", "regedit": "modifies registry",
            "> ": "OVERWRITES file", ">>": "appends to file",
            "shutdown": "SHUTS DOWN system", "reboot": "REBOOTS system",
            "curl": "network request", "wget": "network request", "Invoke-WebRequest": "network request",
            "pip install": "installs package", "npm install": "installs package",
            "git push": "pushes to remote", "git reset": "modifies git history",
        }
        risks = [label for kw, label in risk_keywords.items() if kw.lower() in cmd.lower()]

        try:
            parts = shlex.split(cmd, posix=False)
            lines.append(f"  Tokens: {parts}")
        except Exception:
            pass

        if risks:
            lines.append(f"  Risks: {'; '.join(risks)}")
            lines.append("  Safe to run: REVIEW CAREFULLY")
        else:
            lines.append("  Risks: none detected")
            lines.append("  Safe to run: likely yes (manual review still recommended)")

        lines.append("\nAnalyse this command fully and explain in plain English what it does, step by step.")
        return "\n".join(lines)

    def _analyse_write(self, file_path: str, new_content: str) -> str:
        p = Path(file_path)
        exists = p.exists()
        lines = ["File write preview (DRY RUN — nothing written):"]
        lines.append(f"  Path: {file_path}")
        if exists:
            size = p.stat().st_size
            lines.append(f"  Current file: EXISTS ({size:,} bytes, {size // 1024} KB)")
            if new_content:
                lines.append(f"  New content: {len(new_content):,} chars ({len(new_content.splitlines())} lines)")
                lines.append("  Action: OVERWRITE existing file")
                old_lines = p.read_text(errors="ignore").splitlines()
                new_lines = new_content.splitlines()
                added = sum(1 for l in new_lines if l not in old_lines)
                removed = sum(1 for l in old_lines if l not in new_lines)
                lines.append(f"  Estimated changes: ~{added} lines added, ~{removed} lines removed")
        else:
            lines.append("  Current file: DOES NOT EXIST")
            parent = p.parent
            if not parent.exists():
                lines.append(f"  Will create directory: {parent}")
            if new_content:
                lines.append(f"  Action: CREATE new file ({len(new_content):,} chars)")
        return "\n".join(lines)

    def _analyse_python(self, code: str) -> str:
        import ast
        lines = ["Python dry-run analysis:"]
        try:
            tree = ast.parse(code)
            imports = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
            calls = [ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call) and hasattr(n, "func")]
            lines.append(f"  Syntax: VALID")
            if imports:
                lines.append(f"  Imports: {', '.join(imports[:10])}")
            if calls:
                lines.append(f"  Top-level calls: {', '.join(calls[:10])}")
            risky = [c for c in calls if any(r in c for r in ("open", "write", "delete", "remove", "exec", "eval", "subprocess", "os.system"))]
            if risky:
                lines.append(f"  Potentially side-effecting calls: {', '.join(risky)}")
        except SyntaxError as e:
            lines.append(f"  Syntax: INVALID — {e}")
        return "\n".join(lines)

    async def preview_shell(self, command: str, shell: str = "cmd", **_) -> str:
        return await self._run(self._analyse_shell, command, shell)

    async def preview_write(self, file_path: str, new_content: str = "", **_) -> str:
        return await self._run(self._analyse_write, file_path, new_content)

    async def preview_python(self, code: str, **_) -> str:
        return await self._run(self._analyse_python, code)
