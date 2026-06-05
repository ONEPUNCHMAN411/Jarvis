import asyncio
import subprocess
import os
from pathlib import Path
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

class FileManagerPlugin(Plugin):
    """File management plugin with listing, reading, creating, and searching."""

    def __init__(self):
        super().__init__("file_manager")
        self.enabled = True

    async def initialize(self) -> None:
        """Initialize file manager plugin."""
        logger.info("File manager plugin initialized")

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        """Return file manager tools."""
        return [
            (
                ToolDefinition(
                    name="list_files",
                    description="List files in a directory",
                    parameters={
                        "type": "object",
                        "properties": {
                            "directory": {"type": "string", "description": "Directory path"}
                        },
                        "required": ["directory"],
                    },
                ),
                self.list_files,
            ),
            (
                ToolDefinition(
                    name="read_file",
                    description="Read the contents of a file",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"}
                        },
                        "required": ["path"],
                    },
                ),
                self.read_file,
            ),
            (
                ToolDefinition(
                    name="create_file",
                    description="Create a new file with content",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                            "content": {"type": "string", "description": "File content"},
                        },
                        "required": ["path", "content"],
                    },
                ),
                self.create_file,
            ),
            (
                ToolDefinition(
                    name="search_files",
                    description="Search for files matching a pattern",
                    parameters={
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "File pattern (e.g., *.txt)"},
                            "directory": {"type": "string", "description": "Search directory"},
                        },
                        "required": ["pattern", "directory"],
                    },
                ),
                self.search_files,
            ),
            (
                ToolDefinition(
                    name="delete_file",
                    description="Delete a file",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"}
                        },
                        "required": ["path"],
                    },
                ),
                self.delete_file,
            ),
            (
                ToolDefinition(
                    name="smart_search_files",
                    description="Search for files using Windows Everything (fast) or os.walk fallback",
                    parameters={
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "File pattern or name (e.g., *.py, document.pdf)"},
                            "directory": {
                                "type": "string",
                                "description": "Optional search root directory (defaults to user home)"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum results to return (default: 100)"
                            },
                        },
                        "required": ["pattern"],
                    },
                ),
                self.smart_search_files,
            ),
        ]

    async def list_files(self, directory: str) -> list[dict]:
        """List files in a directory."""
        try:
            path = Path(directory).expanduser()
            if not path.exists():
                return [{"error": f"Directory not found: {directory}"}]

            if not path.is_dir():
                return [{"error": f"Not a directory: {directory}"}]

            files = []
            for item in sorted(path.iterdir()):
                files.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                })
            return files
        except Exception as e:
            logger.error(f"List files error: {e}")
            return [{"error": str(e)}]

    async def read_file(self, path: str) -> str:
        """Read a file."""
        try:
            file_path = Path(path).expanduser()
            if not file_path.exists():
                return f"File not found: {path}"

            if not file_path.is_file():
                return f"Not a file: {path}"

            content = await asyncio.to_thread(file_path.read_text)
            return content[:5000]
        except Exception as e:
            logger.error(f"Read file error: {e}")
            return f"Failed to read file: {str(e)}"

    async def create_file(self, path: str, content: str) -> str:
        """Create a file."""
        try:
            file_path = Path(path).expanduser()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(file_path.write_text, content)
            return f"File created: {path}"
        except Exception as e:
            logger.error(f"Create file error: {e}")
            return f"Failed to create file: {str(e)}"

    async def search_files(self, pattern: str, directory: str) -> list[str]:
        """Search for files matching a pattern."""
        try:
            path = Path(directory).expanduser()
            if not path.exists():
                return [f"Directory not found: {directory}"]

            matches = []
            for match in path.glob(pattern):
                matches.append(str(match))
            return matches[:50]
        except Exception as e:
            logger.error(f"Search files error: {e}")
            return [f"Search error: {str(e)}"]

    async def delete_file(self, path: str) -> str:
        """Delete a file."""
        try:
            file_path = Path(path).expanduser()
            if not file_path.exists():
                return f"File not found: {path}"

            await asyncio.to_thread(file_path.unlink)
            return f"File deleted: {path}"
        except Exception as e:
            logger.error(f"Delete file error: {e}")
            return f"Failed to delete file: {str(e)}"

    async def smart_search_files(
        self, pattern: str, directory: str = None, max_results: int = 100
    ) -> list[str]:
        """
        Search for files using Windows Everything (fast) or os.walk fallback.
        Everything must be installed and running for fast search.
        Falls back to os.walk if Everything is unavailable.
        """
        try:
            # Try Windows Everything first (fast indexed search)
            result = await self._search_with_everything(pattern, directory, max_results)
            if result is not None:
                return result

            # Fallback to os.walk (slower but always available)
            return await self._search_with_oswalk(pattern, directory, max_results)

        except Exception as e:
            logger.error(f"Smart search error: {e}")
            return [f"Search error: {str(e)}"]

    async def _search_with_everything(
        self, pattern: str, directory: str = None, max_results: int = 100
    ) -> list[str] | None:
        """
        Search using Windows Everything CLI (es.exe).
        Returns list of paths if successful, None if Everything is unavailable.
        """
        try:
            # Check if Everything CLI is available
            check = await asyncio.to_thread(
                subprocess.run,
                ["es.exe", "-version"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if check.returncode != 0:
                return None  # Everything not available

            # Build query
            search_pattern = f"*{pattern}*" if "*" not in pattern else pattern
            if not search_pattern.startswith("*"):
                search_pattern = f"*{search_pattern}"
            if not search_pattern.endswith("*"):
                search_pattern = f"{search_pattern}*"

            # Run Everything search
            result = await asyncio.to_thread(
                subprocess.run,
                ["es.exe", "-n", str(max_results), search_pattern],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                matches = [
                    line.strip()
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                ]

                # Filter by directory if specified
                if directory:
                    dir_path = Path(directory).expanduser()
                    matches = [
                        m
                        for m in matches
                        if str(dir_path) in m or m.startswith(str(dir_path))
                    ]

                logger.info(f"Everything search found {len(matches)} matches")
                return matches[:max_results]

            return None

        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            # Everything not available or errored
            return None

    async def _search_with_oswalk(
        self, pattern: str, directory: str = None, max_results: int = 100
    ) -> list[str]:
        """
        Fallback search using os.walk.
        Supports glob patterns and simple wildcards.
        """
        try:
            search_dir = Path(directory).expanduser() if directory else Path.home()

            if not search_dir.exists():
                return [f"Directory not found: {directory}"]

            # Normalize pattern for matching
            if "*" not in pattern and "?" not in pattern:
                search_pattern = f"*{pattern}*"
            else:
                search_pattern = pattern

            matches = []

            def search_recursive(root: Path):
                """Recursively search directory."""
                try:
                    for item in root.iterdir():
                        if len(matches) >= max_results:
                            return

                        # Check if name matches pattern
                        if self._match_pattern(item.name, search_pattern):
                            matches.append(str(item))

                        # Recurse into directories
                        if item.is_dir():
                            try:
                                search_recursive(item)
                            except (PermissionError, OSError):
                                pass
                except (PermissionError, OSError):
                    pass

            # Run search in thread to avoid blocking
            await asyncio.to_thread(search_recursive, search_dir)

            logger.info(f"os.walk search found {len(matches)} matches")
            return matches

        except Exception as e:
            logger.error(f"os.walk search error: {e}")
            return [f"Search error: {str(e)}"]

    def _match_pattern(self, filename: str, pattern: str) -> bool:
        """
        Match filename against a pattern with * and ? wildcards.
        Case-insensitive on Windows.
        """
        import fnmatch

        return fnmatch.fnmatch(filename.lower(), pattern.lower())
