
import os
import threading

_AVAILABLE = False
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    _AVAILABLE = True
except ImportError:
    pass

_SCOPE = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)


class SpotifyController:
    """Thin wrapper around the Spotify Web API via spotipy."""

    def __init__(self):
        self._client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        self._client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        self._redirect = "http://localhost:8888/callback"
        self._sp: "spotipy.Spotify" | None = None
        self._lock = threading.Lock()

    def _client(self) -> "spotipy.Spotify":
        if not _AVAILABLE:
            raise RuntimeError("spotipy not installed: pip install spotipy")
        if not (self._client_id and self._client_secret):
            raise RuntimeError(
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars. "
                "Create a free app at developer.spotify.com."
            )
        with self._lock:
            if self._sp is None:
                auth = SpotifyOAuth(
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                    redirect_uri=self._redirect,
                    scope=_SCOPE,
                    open_browser=True,
                )
                self._sp = spotipy.Spotify(auth_manager=auth)
        return self._sp

    def now_playing(self) -> dict:
        pb = self._client().current_playback()
        if not pb or not pb.get("item"):
            return {"playing": False}
        item = pb["item"]
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        prog = pb.get("progress_ms", 0) // 1000
        dur = item.get("duration_ms", 0) // 1000
        return {
            "playing": pb.get("is_playing", False),
            "track": item.get("name", ""),
            "artist": artists,
            "album": item.get("album", {}).get("name", ""),
            "progress": f"{prog // 60}:{prog % 60:02d}",
            "duration": f"{dur // 60}:{dur % 60:02d}",
        }

    def play_pause(self) -> str:
        pb = self._client().current_playback()
        if pb and pb.get("is_playing"):
            self._client().pause_playback()
            return "paused"
        self._client().start_playback()
        return "playing"

    def next_track(self) -> None:
        self._client().next_track()

    def prev_track(self) -> None:
        self._client().previous_track()

    def set_volume(self, pct: int) -> None:
        self._client().volume(max(0, min(100, int(pct))))

    def play_query(self, query: str) -> dict:
        hits = self._client().search(q=query, type="track", limit=1)
        tracks = hits.get("tracks", {}).get("items", [])
        if not tracks:
            return {"success": False, "error": f"No track found for: {query!r}"}
        t = tracks[0]
        self._client().start_playback(uris=[t["uri"]])
        artists = ", ".join(a["name"] for a in t.get("artists", []))
        return {"success": True, "track": t["name"], "artist": artists}


_inst: SpotifyController | None = None
_lock = threading.Lock()


def get_spotify() -> SpotifyController:
    global _inst
    if _inst is None:
        with _lock:
            if _inst is None:
                _inst = SpotifyController()
    return _inst
