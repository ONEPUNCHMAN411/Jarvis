import ctypes
import ctypes.wintypes

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from jarvis.ui.orb_3d import create_orb_widget
from jarvis.ui.overlay_modes import compute_overlay_geometry

def _remove_dwm_border(hwnd: int) -> None:
    """
    Remove the 1-px DWM border that Windows 11 draws around every frameless
    window — even ones with WA_TranslucentBackground / NoDropShadowWindowHint.
    Uses DWMWA_BORDER_COLOR = DWMWA_COLOR_NONE (0xFFFFFFFE) + extended styles.
    Safe no-op on Windows 10 and non-Windows platforms.
    """
    try:
        DWMWA_BORDER_COLOR = 34          # Windows 11+ attribute id
        DWMWA_COLOR_NONE   = 0xFFFFFFFE  # sentinel meaning "no border"
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_BORDER_COLOR,
            ctypes.byref(ctypes.c_int(DWMWA_COLOR_NONE)),
            ctypes.sizeof(ctypes.c_int),
        )
    except Exception:
        pass  # Not Windows 11, or DWM not available
    try:
        # Add WS_EX_LAYERED | WS_EX_NOACTIVATE so DWM treats this as a
        # pure layered/transparent window and skips all border drawing.
        GWL_EXSTYLE      = -20
        WS_EX_LAYERED    = 0x00080000
        WS_EX_NOACTIVATE = 0x08000000
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED | WS_EX_NOACTIVATE)
    except Exception:
        pass

class OrbOverlayWindow(QWidget):
    restore_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.overlay_mode = "floating"
        self._drag_offset = QPoint()
        self._dragging = False
        self._click_through = False
        self._transparent_flag = getattr(Qt.WindowType, "WindowTransparentForInput", None)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setFixedSize(560, 560)

        self.orb = create_orb_widget(compact=True)
        self.orb.setParent(self)
        self.orb.setGeometry(self.rect())

        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._update_click_through_state)
        self._hover_timer.start(150)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Remove the DWM 1-px border after the native window handle exists.
        # Must be called each time the window is shown (handle may change).
        _remove_dwm_border(int(self.winId()))

    def paintEvent(self, event) -> None:
        try:
            painter = QPainter(self)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        self.orb.setGeometry(self.rect())
        super().resizeEvent(event)

    def apply_mode(self, mode: str) -> None:
        self.overlay_mode = mode if mode in {"floating", "smart_overlay", "docked"} else "floating"
        self._set_click_through(self.overlay_mode == "smart_overlay")
        self.reposition()

    def reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        geometry = compute_overlay_geometry(
            screen_width=available.width(),
            screen_height=available.height(),
            orb_size=self.width(),
            mode=self.overlay_mode,
        )
        self.setGeometry(
            available.x() + geometry.x,
            available.y() + geometry.y,
            geometry.width,
            geometry.height,
        )

    def set_status(self, status: str) -> None:
        self.orb.set_status(status)

    def set_audio_level(self, level: float, speech_detected: bool, mode: str) -> None:
        self.orb.set_audio_level(level, speech_detected, mode)

    def set_response_style(self, style: str) -> None:
        self.orb.set_response_style(style)

    def show_overlay(self) -> None:
        self.reposition()
        self.show()
        self.raise_()

    def _update_click_through_state(self) -> None:
        if self.overlay_mode != "smart_overlay":
            if self._click_through:
                self._set_click_through(False)
            return
        hovered = self.frameGeometry().contains(QCursor.pos())
        self._set_click_through(not hovered)

    def _set_click_through(self, enabled: bool) -> None:
        if self._transparent_flag is None or self._click_through == enabled:
            self._click_through = enabled
            return
        current_geometry = self.geometry()
        self.setWindowFlag(self._transparent_flag, enabled)
        self._click_through = enabled
        self.show()
        self.setGeometry(current_geometry)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._click_through:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self.overlay_mode != "docked":
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.restore_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(10, 14, 39, 0.95);
                border: 1px solid rgba(0, 229, 255, 0.18);
                border-radius: 10px;
                padding: 6px;
                font-family: "Segoe UI Variable", "Segoe UI";
                font-size: 13px;
            }
            QMenu::item {
                color: #E2E8F0;
                padding: 8px 20px 8px 12px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background: rgba(0, 229, 255, 0.10);
                color: #00E5FF;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(51, 65, 85, 0.35);
                margin: 4px 8px;
            }
            QMenu::indicator {
                width: 14px;
                height: 14px;
                margin-left: 6px;
            }
            QMenu::indicator:checked {
                background: rgba(0, 229, 255, 0.20);
                border: 1px solid rgba(0, 229, 255, 0.50);
                border-radius: 4px;
            }
            QMenu::indicator:unchecked {
                background: rgba(15, 23, 42, 0.40);
                border: 1px solid rgba(51, 65, 85, 0.50);
                border-radius: 4px;
            }
        """)
        for mode, label in (
            ("floating", "Floating"),
            ("smart_overlay", "Smart overlay"),
            ("docked", "Docked"),
        ):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.overlay_mode == mode)
            action.triggered.connect(lambda _checked=False, selected=mode: self.apply_mode(selected))
        menu.addSeparator()
        menu.addAction("Open console", self.restore_requested.emit)
        menu.addAction("Quit", self.quit_requested.emit)
        menu.exec(event.globalPos())
