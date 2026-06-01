from loguru import logger
from jarvis.plugins.base import Plugin

class PluginManager:
    """Manages plugin lifecycle and tool registration."""

    def __init__(self):
        self.plugins: dict[str, Plugin] = {}

    async def register_plugin(self, plugin: Plugin) -> None:
        """Register and initialize a plugin."""
        try:
            await plugin.initialize()
            self.plugins[plugin.name] = plugin
            logger.info(f"Registered plugin: {plugin.name}")
        except Exception as e:
            logger.error(f"Failed to register plugin {plugin.name}: {e}")
            raise

    async def unregister_plugin(self, name: str) -> None:
        """Shutdown and unregister a plugin."""
        if name in self.plugins:
            plugin = self.plugins[name]
            try:
                await plugin.shutdown()
                del self.plugins[name]
                logger.info(f"Unregistered plugin: {name}")
            except Exception as e:
                logger.error(f"Error unregistering plugin {name}: {e}")

    def get_tools_for_registry(self) -> list[tuple]:
        """Get all tools from all plugins for registry."""
        tools = []
        for plugin in self.plugins.values():
            if plugin.enabled:
                tools.extend(plugin.get_tools())
        return tools

    async def shutdown_all(self) -> None:
        """Shutdown all plugins."""
        for name in list(self.plugins.keys()):
            await self.unregister_plugin(name)
