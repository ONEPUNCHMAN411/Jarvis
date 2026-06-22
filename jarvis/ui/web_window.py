"""Embedded React UI host for JARVIS.

Replaces *only* the main chat window with a React single-page app rendered in a
``QWebEngineView``.  The entire Python backend (runtime, 50 plugins, voice,
tray, hotkeys, overlays) is untouched — this is a thin, GUI-thread-safe proxy:

  * every dict pushed through ``runtime.bridge.event_received`` is forwarded to
    JavaScript as a JSON string on the ``event`` signal, and
  * every command the native ``AdvancedChatWindow`` calls on the runtime is
    exposed here as a ``@pyqtSlot`` so the React app can call it over
    ``QWebChannel``.

Launch behind the ``JARVIS_WEB=1`` flag so the native UI stays the default and
fallback.  Set ``JARVIS_WEB_DEV=1`` to load the Vite dev server
(``npm run dev`` in ``jarvis/webui``) instead of the built bundle.
"""


import json
import os
import sys
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel


class JarvisWebBridge(QObject):
    """Two-way bridge between the React app and the JARVIS runtime.

    JS → Python: the ``@pyqtSlot`` methods below (dict/list arguments arrive as
    JSON strings to stay robust across Qt/QWebChannel versions).

    Python → JS: ``push(payload)`` serialises a runtime event dict to JSON and
    emits it on ``event``; the React bridge parses it and fans it out.
    """

    # JSON string carrying a runtime event payload.
    event = pyqtSignal(str)

    def __init__(self, runtime, window: "WebChatWindow"):
        super().__init__()
        self._runtime = runtime
        self._window = window

    # -- Python → JS ------------------------------------------------------
    def push(self, payload: dict) -> None:
        """Forward a runtime event dict to JavaScript (GUI thread)."""
        try:
            self.event.emit(json.dumps(payload, default=str))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            logger.warning(f"web bridge: could not serialise event: {exc}")

    # -- JS → Python: conversation ---------------------------------------
    @pyqtSlot(str)
    def sendText(self, text: str) -> None:
        self._runtime.send_text(text)

    @pyqtSlot()
    def triggerVoice(self) -> None:
        self._runtime.trigger_voice_capture()

    @pyqtSlot()
    def cancel(self) -> None:
        self._runtime.cancel_request()

    # -- JS → Python: sessions / history ---------------------------------
    @pyqtSlot()
    def loadChatHistory(self) -> None:
        self._runtime.load_chat_history()

    @pyqtSlot()
    def newSession(self) -> None:
        self._runtime.new_chat_session()

    @pyqtSlot()
    def listSessions(self) -> None:
        self._runtime.list_chat_sessions()

    @pyqtSlot(str)
    def loadSession(self, session_id: str) -> None:
        self._runtime.load_session(session_id)

    # -- JS → Python: settings / providers -------------------------------
    @pyqtSlot(str)
    def applySettings(self, settings_json: str) -> None:
        try:
            settings = json.loads(settings_json)
        except (TypeError, ValueError) as exc:
            logger.warning(f"web bridge: bad settings JSON: {exc}")
            return
        if isinstance(settings, dict):
            self._runtime.apply_settings(settings)

    @pyqtSlot(str)
    def testProvider(self, provider_name: str) -> None:
        self._runtime.test_provider(provider_name)

    @pyqtSlot(str, str)
    def previewVoice(self, profile_id: str, custom_json: str) -> None:
        custom = None
        if custom_json:
            try:
                custom = json.loads(custom_json)
            except (TypeError, ValueError):
                custom = None
        self._runtime.preview_voice(profile_id, custom)

    @pyqtSlot(bool)
    def setBackgroundState(self, backgrounded: bool) -> None:
        self._runtime.set_background_state(backgrounded)

    # -- JS → Python: plugins / status -----------------------------------
    @pyqtSlot()
    def listPlugins(self) -> None:
        self._runtime.list_plugins()

    @pyqtSlot(str)
    def enablePlugin(self, name: str) -> None:
        self._runtime.enable_plugin(name)

    @pyqtSlot(str)
    def disablePlugin(self, name: str) -> None:
        self._runtime.disable_plugin(name)

    @pyqtSlot()
    def getStatus(self) -> None:
        self._runtime.get_status()

    # -- JS → Python: window controls (frameless custom titlebar) --------
    @pyqtSlot()
    def minimizeWindow(self) -> None:
        self._window.showMinimized()

    @pyqtSlot()
    def toggleMaximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    @pyqtSlot()
    def closeWindow(self) -> None:
        self._window.close()

    @pyqtSlot()
    def enterOrbOnly(self) -> None:
        self._window.enter_orb_only()

    @pyqtSlot()
    def exitOrbOnly(self) -> None:
        self._window.exit_orb_only()

    @pyqtSlot(int, int)
    def dragWindow(self, dx: int, dy: int) -> None:
        """Move the (frameless orb-only) window by a delta — JS-driven drag."""
        w = self._window
        w.move(w.x() + int(dx), w.y() + int(dy))

    @pyqtSlot(str)
    def setUiMode(self, mode: str) -> None:
        """Persist the chosen UI (react|legacy) and relaunch into it."""
        target = "legacy" if mode == "legacy" else "react"
        try:
            s = dict(getattr(self._runtime, "settings", {}) or {})
            s["ui_mode"] = target
            self._runtime.apply_settings(s)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"setUiMode: could not persist preference: {exc}")
        self._window.relaunch(target)

    @pyqtSlot()
    def ready(self) -> None:
        """The React app has mounted and subscribed — replay initial state."""
        self._runtime.get_status()
        self._runtime.list_plugins()
        self._runtime.load_chat_history()
        self._runtime.list_chat_sessions()
        # settings_loaded is emitted by the runtime once it is ready; if the
        # runtime is already up, surface the current settings immediately.
        if getattr(self._runtime, "settings", None) is not None:
            self.push({"type": "settings_loaded", "settings": self._runtime.settings})
        if getattr(self._runtime, "ready", False):
            self.push({"type": "runtime_ready"})


def _webui_dist_index() -> Path:
    """Resolve the built React bundle's index.html, dev tree or frozen EXE."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "jarvis" / "webui" / "dist" / "index.html"
    # jarvis/ui/web_window.py -> parents[1] == jarvis/
    return Path(__file__).resolve().parents[1] / "webui" / "dist" / "index.html"


class WebChatWindow(QMainWindow):
    """Main JARVIS window backed by an embedded React app."""

    def __init__(self, runtime, demo_mode: bool = False):
        super().__init__()
        self.runtime = runtime
        self.demo_mode = demo_mode
        self.overlay_window = None  # parity with AdvancedChatWindow (hotkey path)
        self._orb_only = False
        self._normal_geom = None

        self.setWindowTitle("JARVIS")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)

        # Allow the qrc:// QWebChannel script + local assets to load from a
        # file:// page (the single biggest WebEngine footgun for this setup).
        s = self.view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        # WebGL + accelerated canvas for the Three.js 3D orb centerpiece.
        s.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)

        # Register the bridge on a channel named "jarvis" (the React side
        # connects to channel.objects.jarvis — the name MUST match).
        self.channel = QWebChannel(self.view.page())
        self.bridge = JarvisWebBridge(runtime, self)
        self.channel.registerObject("jarvis", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # Forward every runtime event dict to the React app.
        runtime.bridge.event_received.connect(self.bridge.push)

        self._load_ui()

    def _load_ui(self) -> None:
        if os.getenv("JARVIS_WEB_DEV") == "1":
            url = QUrl("http://localhost:5173")
            logger.info("WebChatWindow: loading Vite dev server at localhost:5173")
        else:
            index = _webui_dist_index()
            if not index.exists():
                logger.error(
                    f"WebChatWindow: built UI not found at {index} — "
                    "run `npm run build` in jarvis/webui (or set JARVIS_WEB_DEV=1)."
                )
            url = QUrl.fromLocalFile(str(index))
            logger.info(f"WebChatWindow: loading {url.toString()}")
        self.view.load(url)

    # -- orb-only floating mode (parity with the legacy UI) ---------------
    def enter_orb_only(self) -> None:
        if self._orb_only:
            return
        self._orb_only = True
        self._normal_geom = self.geometry()
        # Transparent, frameless, always-on-top floating orb.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.view.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        self.setMinimumSize(0, 0)
        self.resize(300, 300)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - 330, screen.bottom() - 340)
        self.show()
        self.bridge.push({"type": "orb_only", "on": True})

    def exit_orb_only(self) -> None:
        if not self._orb_only:
            return
        self._orb_only = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.view.page().setBackgroundColor(QColor("#070b14"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.setWindowFlag(Qt.WindowType.Tool, False)
        self.setMinimumSize(960, 640)
        if self._normal_geom is not None:
            self.setGeometry(self._normal_geom)
        else:
            self.resize(1280, 820)
        self.show()
        self.raise_()
        self.activateWindow()
        self.bridge.push({"type": "orb_only", "on": False})

    def relaunch(self, mode: str) -> None:
        """Restart the app into the chosen UI (react|legacy)."""
        import subprocess

        env = dict(os.environ)
        env.pop("JARVIS_WEB", None)
        if mode == "legacy":
            env["JARVIS_NATIVE"] = "1"
        else:
            env.pop("JARVIS_NATIVE", None)
        if getattr(sys, "frozen", False):
            args, cwd = [sys.executable], None
        else:
            args = [sys.executable, "-m", "jarvis"]
            cwd = str(Path(__file__).resolve().parents[2])
        try:
            subprocess.Popen(args, env=env, cwd=cwd, close_fds=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"relaunch failed: {exc}")
            return
        QApplication.instance().quit()

    # -- hotkey / overlay compatibility (main() expects these) ------------
    def _restore_from_overlay(self) -> None:
        """Bring the window forward — mirrors AdvancedChatWindow's API used by
        the global Ctrl+Shift+J hotkey handler."""
        if self._orb_only:
            self.exit_orb_only()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):  # noqa: N802 (Qt signature)
        # Let the app/runtime shut down cleanly via main()'s runtime.stop().
        super().closeEvent(event)
