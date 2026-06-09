
import math

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

_COLORS = {
    "blue": "#3B9EFF", "green": "#2DE8B0", "amber": "#FFB454",
    "red": "#FF5C7A", "white": "#E9F1FF",
}


def _qc(name: str, a: int = 255) -> QColor:
    c = QColor(_COLORS.get(name, name))
    c.setAlpha(a)
    return c


class ScreenAnnotator(QWidget):
    """Transparent, click-through, always-on-top overlay that draws arrows,
    boxes, highlight points, and labels anywhere on the desktop. Coordinates
    are global screen pixels. Shapes auto-expire after their ttl (ms)."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._shapes: list[dict] = []
        self._phase = 0.0
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(33)

    def _virtual_geometry(self):
        rect = QRectF()
        for screen in QApplication.screens():
            rect = rect.united(QRectF(screen.geometry()))
        return rect.toRect()

    def _ensure_visible(self) -> None:
        self.setGeometry(self._virtual_geometry())
        if not self.isVisible():
            self.show()
        self.raise_()

    def _tick(self) -> None:
        if self._shapes:
            alive = []
            for s in self._shapes:
                if s["expires"] is None:
                    alive.append(s)
                else:
                    s["expires"] -= 33
                    if s["expires"] > 0:
                        alive.append(s)
            self._shapes = alive
            self._phase += 0.08
            self.update()
            if not self._shapes and self.isVisible():
                self.hide()

    def add_arrow(self, x1, y1, x2, y2, color="blue", label="", ttl=6000):
        self._shapes.append({"type": "arrow", "p": (x1, y1, x2, y2),
                             "color": color, "label": label, "expires": ttl})
        self._ensure_visible()

    def add_box(self, x, y, w, h, color="blue", label="", ttl=6000):
        self._shapes.append({"type": "box", "p": (x, y, w, h),
                             "color": color, "label": label, "expires": ttl})
        self._ensure_visible()

    def add_point(self, x, y, color="amber", label="", ttl=6000):
        self._shapes.append({"type": "point", "p": (x, y),
                             "color": color, "label": label, "expires": ttl})
        self._ensure_visible()

    def add_label(self, x, y, text, color="white", ttl=6000):
        self._shapes.append({"type": "label", "p": (x, y),
                             "color": color, "label": text, "expires": ttl})
        self._ensure_visible()

    def clear(self) -> None:
        self._shapes = []
        self.hide()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        ox, oy = self.geometry().x(), self.geometry().y()
        pulse = 0.5 + 0.5 * math.sin(self._phase)
        for s in self._shapes:
            col = _qc(s["color"])
            kind = s["type"]
            if kind == "arrow":
                x1, y1, x2, y2 = s["p"]
                self._draw_arrow(p, x1 - ox, y1 - oy, x2 - ox, y2 - oy, col, s["label"])
            elif kind == "box":
                x, y, w, h = s["p"]
                self._draw_box(p, x - ox, y - oy, w, h, col, s["label"], pulse)
            elif kind == "point":
                x, y = s["p"]
                self._draw_point(p, x - ox, y - oy, col, s["label"], pulse)
            elif kind == "label":
                x, y = s["p"]
                self._chip(p, x - ox, y - oy, s["label"], col)
        p.end()

    @staticmethod
    def _draw_arrow(p, x1, y1, x2, y2, col, label):
        pen = QPen(col, 3.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        ang = math.atan2(y2 - y1, x2 - x1)
        size = 17.0
        for da in (math.radians(152), math.radians(-152)):
            ax = x2 + size * math.cos(ang + da)
            ay = y2 + size * math.sin(ang + da)
            p.drawLine(QPointF(x2, y2), QPointF(ax, ay))
        if label:
            ScreenAnnotator._chip(p, x1 - 4, y1 - 26, label, col)

    @staticmethod
    def _draw_box(p, x, y, w, h, col, label, pulse):
        glow = QColor(col)
        glow.setAlpha(int(35 + 55 * pulse))
        p.setPen(QPen(glow, 6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x - 2, y - 2, w + 4, h + 4), 9, 9)
        p.setPen(QPen(col, 2.4))
        p.drawRoundedRect(QRectF(x, y, w, h), 6, 6)
        if label:
            ScreenAnnotator._chip(p, x, y - 26, label, col)

    @staticmethod
    def _draw_point(p, x, y, col, label, pulse):
        r = 13 + 9 * pulse
        ring = QColor(col)
        ring.setAlpha(int(200 * (1.0 - pulse * 0.55)))
        p.setPen(QPen(ring, 2.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x, y), r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(x, y), 5, 5)
        if label:
            ScreenAnnotator._chip(p, x + 16, y - 12, label, col)

    @staticmethod
    def _chip(p, x, y, text, col):
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        rect = QRectF(x, y, tw + 16, th + 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(8, 12, 22, 225))
        p.drawRoundedRect(rect, 7, 7)
        p.setPen(QPen(col, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 7, 7)
        p.setPen(QColor(233, 241, 255))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


_instance: "ScreenAnnotator | None" = None


def get_screen_annotator() -> "ScreenAnnotator":
    global _instance
    if _instance is None:
        _instance = ScreenAnnotator()
    return _instance
