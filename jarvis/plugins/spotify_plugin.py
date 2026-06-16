
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class SpotifyPlugin(Plugin):
    """Control Spotify: now playing, play/pause, skip, volume, search & play."""

    def __init__(self):
        super().__init__("spotify")
        self._ctrl = None

    def _get(self):
        if self._ctrl is None:
            from jarvis.brain.spotify_controller import get_spotify
            self._ctrl = get_spotify()
        return self._ctrl

    async def initialize(self) -> None:
        from jarvis.brain.spotify_controller import _AVAILABLE
        if not _AVAILABLE:
            logger.warning("SpotifyPlugin: spotipy not installed — tools disabled")
        else:
            logger.info("SpotifyPlugin ready")

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="spotify_now_playing",
                    description="Show the currently playing Spotify track and progress.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.now_playing,
            ),
            (
                ToolDefinition(
                    name="spotify_play_pause",
                    description="Toggle Spotify play/pause.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.play_pause,
            ),
            (
                ToolDefinition(
                    name="spotify_next",
                    description="Skip to the next track on Spotify.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.next_track,
            ),
            (
                ToolDefinition(
                    name="spotify_previous",
                    description="Go back to the previous Spotify track.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.prev_track,
            ),
            (
                ToolDefinition(
                    name="spotify_volume",
                    description="Set Spotify volume (0-100).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "percent": {
                                "type": "integer",
                                "description": "Volume level 0-100",
                            },
                        },
                        "required": ["percent"],
                    },
                ),
                self.set_volume,
            ),
            (
                ToolDefinition(
                    name="spotify_play",
                    description=(
                        "Search for a song by name and/or artist and play it. "
                        "Examples: 'Blinding Lights', 'Hotel California Eagles'"
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Track name and/or artist",
                            },
                        },
                        "required": ["query"],
                    },
                ),
                self.play_query,
            ),
        ]

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: fn(*args))
        except Exception as e:
            return f"Spotify error: {e}"

    async def now_playing(self) -> str:
        info = await self._run(self._get().now_playing)
        if isinstance(info, str):
            return info
        if not info.get("playing"):
            return "Spotify is not currently playing."
        return (
            f"Now playing: {info['track']}\n"
            f"Artist:   {info['artist']}\n"
            f"Album:    {info['album']}\n"
            f"Progress: {info['progress']} / {info['duration']}"
        )

    async def play_pause(self) -> str:
        state = await self._run(self._get().play_pause)
        return f"Spotify {state}." if isinstance(state, str) else str(state)

    async def next_track(self) -> str:
        result = await self._run(self._get().next_track)
        return "Skipped to next track." if result is None else str(result)

    async def prev_track(self) -> str:
        result = await self._run(self._get().prev_track)
        return "Went back to previous track." if result is None else str(result)

    async def set_volume(self, percent: int) -> str:
        result = await self._run(self._get().set_volume, percent)
        return f"Volume set to {percent}%." if result is None else str(result)

    async def play_query(self, query: str) -> str:
        r = await self._run(self._get().play_query, query)
        if isinstance(r, str):
            return r
        if r.get("success"):
            return f"Now playing: {r['track']} by {r['artist']}"
        return f"Spotify: {r.get('error', 'unknown error')}"
