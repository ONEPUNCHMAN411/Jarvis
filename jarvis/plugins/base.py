from abc import ABC, abstractmethod
from jarvis.models import ToolDefinition

class Plugin(ABC):
    """Base class for all JARVIS plugins."""

    def __init__(self, name: str):
        self.name = name
        self.enabled = True

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the plugin (setup credentials, connections, etc)."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        pass

    @abstractmethod
    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        """Return list of (ToolDefinition, handler) tuples."""
        pass

    async def health_check(self) -> bool:
        """Check if plugin is healthy."""
        return self.enabled
