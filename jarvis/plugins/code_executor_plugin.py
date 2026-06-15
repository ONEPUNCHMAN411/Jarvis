
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition
from jarvis.brain.code_executor import CodeExecutor


class CodeExecutorPlugin(Plugin):
    """Execute Python, shell, and JavaScript from JARVIS chat."""

    def __init__(self):
        super().__init__("code_executor")
        self._exec = CodeExecutor()

    async def initialize(self) -> None:
        logger.info("CodeExecutorPlugin ready")

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="run_python",
                    description=(
                        "Execute a Python code snippet and return its output. "
                        "Runs in an isolated subprocess (15s timeout). "
                        "Good for math, file ops, data processing, scripting."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python source code to execute",
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Max seconds (1-15, default 15)",
                            },
                        },
                        "required": ["code"],
                    },
                ),
                self.run_python,
            ),
            (
                ToolDefinition(
                    name="run_shell",
                    description=(
                        "Execute a shell command and return stdout/stderr. "
                        "30s timeout. Use for CLI tasks, system info, running programs."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to run",
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Max seconds (1-30, default 30)",
                            },
                        },
                        "required": ["command"],
                    },
                ),
                self.run_shell,
            ),
            (
                ToolDefinition(
                    name="run_javascript_node",
                    description=(
                        "Run JavaScript via Node.js and return its output. "
                        "Returns an error if Node.js is not installed."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "JavaScript source code",
                            },
                        },
                        "required": ["code"],
                    },
                ),
                self.run_javascript,
            ),
        ]

    async def run_python(self, code: str, timeout: int = 15) -> str:
        result = await self._exec.run_python(code, timeout=timeout)
        return self._exec.format_result(result)

    async def run_shell(self, command: str, timeout: int = 30) -> str:
        result = await self._exec.run_shell(command, timeout=timeout)
        return self._exec.format_result(result)

    async def run_javascript(self, code: str) -> str:
        result = await self._exec.run_javascript(code)
        return self._exec.format_result(result)
