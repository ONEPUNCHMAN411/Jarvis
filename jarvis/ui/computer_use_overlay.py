"""
Computer-use overlay — a fullscreen transparent border that glows when JARVIS
is actively controlling the computer (mouse, keyboard, shell, app launch, etc.).
"""

import ctypes
import math

from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QRectF, Qt, QTimer, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

# Tools that count as "computer use"
COMPUTER_USE_TOOLS = frozenset({
    "computer",
    "run_shell_command",
    "launch_app",
    "close_app",
    "take_screenshot",
    "browser_navigate",
    "write_file",
    "write_clipboard",
    "set_volume",
    "focus_window",
})

def _apply_layered_style(hwnd: int) -> None:
    """Set WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE so the
    border doesn't intercept mouse/keyboard and doesn't steal focus."""
    try:
        GWL_EXSTYLE       = -20
        WS_EX_LAYERED     = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE  = 0x08000000
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE,
            style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE,
        )
    except Exception:
        pass

class ComputerUseOverlay(QWidget):
    """Fullscreen transparent overlay that draws a glowing border + label
    when JARVIS is actively using computer-control tools."""

    def __init__(self):
        super().__init__()
        self._active = False
        self._opacity = 0.0          # animated 0→1
        self._phase = 0.0            # animation ticker
        self._tool_name = ""         # currently executing tool
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._fade_out)

        # Hard safety fallback: dismiss after 40 s in case on_tool_end is never called
        # (e.g. an unhandled exception exits the tool loop before publishing ToolResultEvent)
        self._safety_timer = QTimer(self)
        self._safety_timer.setSingleShot(True)
        self._safety_timer.timeout.connect(self._fade_out)

        # Fade animation
        self._fade_anim = QPropertyAnimation(self, b"overlayOpacity", self)
        self._fade_anim.setDuration(350)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Pulse animation (60 fps while visible)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowTransparentForInput
        )

    # Public API

    def on_tool_start(self, tool_name: str) -> None:
        """Called when a computer-use tool begins executing."""
        if tool_name not in COMPUTER_USE_TOOLS:
            return
        self._tool_name = tool_name
        self._active = True
        self._dismiss_timer.stop()
        # Reset safety timer every time a new tool starts
        self._safety_timer.start(40_000)
        self._cover_screen()
        if not self.isVisible():
            self.show()
            _apply_layered_style(int(self.winId()))
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        if not self._pulse_timer.isActive():
            self._pulse_timer.start(16)

    def on_tool_end(self, tool_name: str) -> None:
        """Called when a tool finishes. Starts a short dismiss delay."""
        if tool_name not in COMPUTER_USE_TOOLS:
            return
        # Keep the border visible for 1.2 s after the last tool finishes
        # so rapid successive tool calls don't cause flicker.
        self._dismiss_timer.start(1200)

    # Internals

    def _cover_screen(self) -> None:
        try:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                if geo.width() > 0 and geo.height() > 0:
                    self.setGeometry(geo)
        except Exception:
            pass

    def _fade_out(self) -> None:
        self._active = False
        self._safety_timer.stop()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setDuration(600)
        self._fade_anim.start()

    def _tick(self) -> None:
        self._phase += 0.04
        if self._opacity <= 0.0 and not self._active:
            self._pulse_timer.stop()
            self.hide()
            return
        self.update()

    # Animated property

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, val: float) -> None:
        self._opacity = max(0.0, min(val, 1.0))
        self.update()

    overlayOpacity = pyqtProperty(float, fget=_get_opacity, fset=_set_opacity)

    # Paint

    def paintEvent(self, event) -> None:
        try:
            self._paint_inner(event)
        except Exception:
            pass

    def _paint_inner(self, event) -> None:
        if self._opacity <= 0.01:
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        op = self._opacity

        # Animated border thickness + glow
        pulse = 0.5 + 0.5 * math.sin(self._phase * 2.0)
        border_w = 3.0 + pulse * 1.5          # 3–4.5 px
        glow_alpha = int((45 + 25 * pulse) * op)
        border_alpha = int((180 + 75 * pulse) * op)

        # Main accent: JARVIS cyan (#00E5FF)
        accent = QColor(0, 229, 255, border_alpha)
        accent_glow = QColor(0, 229, 255, glow_alpha)

        # Outer glow (wide, soft)
        for i, (bw, alpha_mult) in enumerate([(12, 0.25), (8, 0.4), (5, 0.6)]):
            pen = QPen(QColor(0, 229, 255, int(glow_alpha * alpha_mult)), bw)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            margin = bw / 2
            painter.drawRect(QRectF(margin, margin, w - bw, h - bw))

        # Main border
        pen = QPen(accent, border_w)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        m = border_w / 2
        painter.drawRect(QRectF(m, m, w - border_w, h - border_w))

        # Scanning line animation (travels along the border)
        scan_t = (self._phase * 0.3) % 1.0
        perimeter = 2 * (w + h)
        scan_pos = scan_t * perimeter
        scan_len = 120
        self._draw_scan_segment(painter, w, h, scan_pos, scan_len, op)

        # Top-centre label: "JARVIS · COMPUTER USE"
        label_text = f"JARVIS · COMPUTER USE"
        if self._tool_name:
            pretty = self._tool_name.replace("_", " ").upper()
            label_text = f"JARVIS · {pretty}"

        # Label background pill
        painter.setFont(QFont("Segoe UI Variable", 10, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label_text) + 32
        th = fm.height() + 14
        lx = (w - tw) / 2
        ly = 6

        pill_bg = QColor(10, 14, 39, int(230 * op))
        pill_border = QColor(0, 229, 255, int(120 * op))
        painter.setPen(QPen(pill_border, 1.2))
        painter.setBrush(pill_bg)
        painter.drawRoundedRect(QRectF(lx, ly, tw, th), 8, 8)

        # Label text
        painter.setPen(QColor(0, 229, 255, int(240 * op)))
        painter.drawText(
            QRectF(lx, ly, tw, th),
            Qt.AlignmentFlag.AlignCenter,
            label_text,
        )

        # Corner accents (HUD-style brackets)
        arm = 28
        gap = 4
        corner_pen = QPen(QColor(0, 229, 255, int(200 * op)), 2.2)
        corner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(corner_pen)
        # Top-left
        painter.drawLine(gap, gap, gap + arm, gap)
        painter.drawLine(gap, gap, gap, gap + arm)
        # Top-right
        painter.drawLine(w - gap - arm, gap, w - gap, gap)
        painter.drawLine(w - gap, gap, w - gap, gap + arm)
        # Bottom-left
        painter.drawLine(gap, h - gap, gap + arm, h - gap)
        painter.drawLine(gap, h - gap, gap, h - gap - arm)
        # Bottom-right
        painter.drawLine(w - gap - arm, h - gap, w - gap, h - gap)
        painter.drawLine(w - gap, h - gap, w - gap, h - gap - arm)

    def _draw_scan_segment(self, painter, w, h, pos, length, opacity):
        """Draw a brighter segment that travels around the border perimeter."""
        if w <= 0 or h <= 0:
            return
        pen = QPen(QColor(56, 189, 248, int(200 * opacity)), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        # Walk pos..pos+length along the perimeter path
        segments = [
            (0,     0, 0,  w, 0,  w),          # top edge
            (w,     w, 0,  w, h,  h),          # right edge
            (w + h, w, h,  0, h,  w),          # bottom edge (reversed)
            (2*w+h, 0, h,  0, 0,  h),          # left edge (reversed)
        ]
        perimeter = 2 * (w + h)
        for seg_start, x1, y1, x2, y2, seg_len in segments:
            seg_end = seg_start + seg_len
            # Clip the scan segment to this edge
            s = max(pos, seg_start)
            e = min(pos + length, seg_end)
            if s >= e:
                # Also handle wrap-around
                s2 = max(pos - perimeter, seg_start)
                e2 = min(pos + length - perimeter, seg_end)
                if s2 < e2:
                    s, e = s2, e2
                else:
                    continue
            t1 = (s - seg_start) / seg_len if seg_len else 0
            t2 = (e - seg_start) / seg_len if seg_len else 0
            px1 = x1 + (x2 - x1) * t1
            py1 = y1 + (y2 - y1) * t1
            px2 = x1 + (x2 - x1) * t2
            py2 = y1 + (y2 - y1) * t2
            painter.drawLine(int(px1), int(py1), int(px2), int(py2))
