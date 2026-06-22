"""
Live subtitle overlay window.

Always-on-top, transparent, click-through window positioned at the bottom
of the screen — shows live transcription chunks as they arrive, fading out
older text, styled like professional closed captions.
"""

from collections import deque
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QFont, QFontMetrics, QPainterPath
from PyQt6.QtWidgets import QWidget, QApplication


_MAX_LINES = 3          # lines visible at once
_LINE_TTL_MS = 8000     # how long each line stays before fading
_FADE_MS = 600
_FONT_SIZE = 18
_PADDING_H = 24
_PADDING_V = 14
_BG_COLOR = QColor(8, 8, 18, 210)      # near-black, 82% opacity
_TEXT_COLOR = QColor(240, 248, 255)     # almost white
_ACCENT_COLOR = QColor(0, 200, 232)     # JARVIS cyan for timestamps
_MAX_LINE_CHARS = 90                    # wrap at this many characters


class SubtitleOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self._lines: deque[dict] = deque(maxlen=_MAX_LINES)
        self._opacity = 1.0
        self._visible = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._font = QFont("Segoe UI", _FONT_SIZE, QFont.Weight.Medium)
        self._small_font = QFont("Segoe UI", 10, QFont.Weight.Normal)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timeout)

        self._position_at_bottom()

    def push_text(self, text: str) -> None:
        """Add a new transcription chunk to the subtitle display."""
        for line in _wrap(text, _MAX_LINE_CHARS):
            self._lines.append({"text": line, "age_ms": 0})

        self._update_geometry()
        if not self._visible:
            self.show()
            self._visible = True

        self._hide_timer.stop()
        self._hide_timer.start(_LINE_TTL_MS + _FADE_MS)
        self.update()

    def clear(self) -> None:
        self._lines.clear()
        self.hide()
        self._visible = False

    def paintEvent(self, event):
        if not self._lines:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()

        # Background pill
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 12, 12)
        painter.fillPath(path, _BG_COLOR)

        # Text lines — oldest at top, newest at bottom
        painter.setFont(self._font)
        fm = QFontMetrics(self._font)
        line_h = fm.height() + 6
        y = _PADDING_V

        lines = list(self._lines)
        n = len(lines)
        for idx, entry in enumerate(lines):
            # Older lines are more transparent
            alpha = 1.0
            if n > 1 and idx < n - 1:
                alpha = 0.55 + 0.45 * (idx / (n - 1))
            color = QColor(_TEXT_COLOR)
            color.setAlphaF(alpha * self._opacity)
            painter.setPen(color)
            painter.drawText(_PADDING_H, y + fm.ascent(), entry["text"])
            y += line_h

        painter.end()

    def _update_geometry(self) -> None:
        fm = QFontMetrics(self._font)
        line_h = fm.height() + 6
        lines = list(self._lines)
        if not lines:
            return

        max_w = max(fm.horizontalAdvance(l["text"]) for l in lines)
        w = min(max_w + _PADDING_H * 2, self._screen_width() - 80)
        h = line_h * len(lines) + _PADDING_V * 2

        screen_w = self._screen_width()
        screen_h = self._screen_height()
        x = (screen_w - w) // 2
        y = screen_h - h - 80  # 80px above taskbar
        self.setGeometry(x, y, w, h)

    def _position_at_bottom(self) -> None:
        self.setGeometry(200, 800, 800, 100)

    def _screen_width(self) -> int:
        screen = QApplication.primaryScreen()
        return screen.geometry().width() if screen else 1920

    def _screen_height(self) -> int:
        screen = QApplication.primaryScreen()
        return screen.geometry().height() if screen else 1080

    def _on_hide_timeout(self) -> None:
        self._lines.clear()
        self.hide()
        self._visible = False


def _wrap(text: str, max_chars: int) -> list[str]:
    """Break text into lines of at most max_chars, splitting on word boundaries."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text[:max_chars]]
