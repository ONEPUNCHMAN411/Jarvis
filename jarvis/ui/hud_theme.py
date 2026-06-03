"""JARVIS Stark HUD Theme — Iron Man / Stark Industries aesthetic.
Provides: CircularGauge, MiniSparkline, HUDSystemPanel,
          HUDClockWidget, HUDIntelFeed, stark_stylesheet()
"""

import collections
import datetime
import math

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QSize
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen,
    QRadialGradient, QLinearGradient, QBrush,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QScrollArea, QListWidget, QListWidgetItem,
)

try:
    import psutil as _psutil
    _HAS_PSUTIL = True
except ImportError:
    _psutil = None
    _HAS_PSUTIL = False


# ── Palette ────────────────────────────────────────────────────────────────────

class P:
    """Aurora v2 — neutral graphite chrome with a restrained violet accent.

    Surfaces are neutral slate; PRIMARY violet appears only on focus,
    selection, and live-state highlights so it never overwhelms.
    """
    PRIMARY = "#3B9EFF"   # accent — focus/selection/highlights only
    MINT    = "#2DE8B0"   # success / live data
    ICE     = "#5BC8FF"   # informational accent, gauges
    RED     = "#FF5C7A"   # error
    AMBER   = "#FFB454"   # warning
    GREEN   = "#2DE8B0"   # legacy alias → MINT
    CYAN    = "#5BC8FF"   # legacy alias → ICE (old code references P.CYAN)
    TEXT    = "#DFE5F0"
    MUTED   = "#7C879D"
    BG      = "#07090F"   # neutral near-black
    PANEL   = "rgba(10, 14, 22, 0.28)"
    BORDER  = "rgba(148, 163, 184, 0.06)"
    FONT    = "Cascadia Code"
    FONT_UI = "Segoe UI Variable"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _c(h: str, a: int = 255) -> QColor:
    """Build a QColor from a hex string, with optional alpha 0-255."""
    col = QColor(h)
    col.setAlpha(a)
    return col


def _gauge_color(v: float) -> QColor:
    """Return cyan / amber / red depending on load level 0-1."""
    if v < 0.60:
        return _c(P.CYAN)
    if v < 0.85:
        return _c(P.AMBER)
    return _c(P.RED)


# ── CircularGauge ──────────────────────────────────────────────────────────────

class CircularGauge(QWidget):
    """Stark-style radial arc gauge.

    Arc sweeps from 7-o'clock (225°) clockwise 270° to 5-o'clock.
    Color transitions cyan → amber → red as load rises.
    """

    # Qt arc angles: 0° = 3-o'clock, positive = CCW, units = 1/16 degree
    _START = 225 * 16   # 7-o'clock position
    _SPAN  = -270 * 16  # clockwise sweep

    def __init__(self, label: str = "CPU", d: int = 110, parent=None):
        super().__init__(parent)
        self._label  = label
        self._value  = 0.0   # current displayed value 0.0–1.0
        self._target = 0.0   # animated target
        self.setFixedSize(d, d)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 fps

    def set_value(self, v: float) -> None:
        self._target = max(0.0, min(1.0, v))

    # ── Animation ──────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        diff = self._target - self._value
        self._value += diff * 0.12
        self.update()

    # ── Painting ───────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h  = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r  = min(w, h) / 2 - 10
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        v  = self._value

        # Background track
        pen = QPen(_c(P.CYAN, 28), 6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, self._START, self._SPAN)

        # Filled arc
        if v > 0.002:
            span = int(self._SPAN * v)
            arc_pen = QPen(_gauge_color(v), 6)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(arc_pen)
            p.drawArc(rect, self._START, span)

            # Tip glow dot  (angle: 225 - v*270 degrees, measuring CCW from 3-o'clock)
            tip_rad = math.radians(225.0 - v * 270.0)
            tx = cx + math.cos(tip_rad) * r
            ty = cy - math.sin(tip_rad) * r
            grad = QRadialGradient(QPointF(tx, ty), 8)
            glow = _gauge_color(v)
            grad.setColorAt(0.0, glow)
            grad.setColorAt(1.0, _c(P.CYAN, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(tx, ty), 6, 6)

        # Centre percentage
        p.setPen(_c(P.TEXT))
        p.setFont(QFont(P.FONT_UI, 12, QFont.Weight.DemiBold))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{int(v * 100)}%")

        # Label below centre
        p.setPen(_c(P.MUTED))
        p.setFont(QFont(P.FONT_UI, 8))
        lrect = QRectF(cx - r, cy + r * 0.38, r * 2, 18)
        p.drawText(lrect, Qt.AlignmentFlag.AlignCenter, self._label)

        p.end()


# ── MiniSparkline ──────────────────────────────────────────────────────────────

class MiniSparkline(QWidget):
    """Tiny scrolling network / IO graph — push() new samples."""

    def __init__(self, label: str = "NET", color: str = P.CYAN,
                 maxlen: int = 60, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._buf   = collections.deque([0.0] * maxlen, maxlen=maxlen)
        self._peak  = 1.0
        self.setMinimumSize(120, 48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def push(self, value: float) -> None:
        self._buf.append(value)
        if value > self._peak:
            self._peak = value
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h  = self.width(), self.height()
        buf   = list(self._buf)
        n     = len(buf)
        if n < 2:
            return
        peak = max(self._peak, 1.0)

        xs = [i * w / (n - 1) for i in range(n)]
        ys = [h - 4 - (v / peak) * (h - 8) for v in buf]

        # Build path
        path = QPainterPath()
        path.moveTo(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:]):
            path.lineTo(x, y)

        # Filled area under curve
        fill = QPainterPath(path)
        fill.lineTo(w, h)
        fill.lineTo(0, h)
        fill.closeSubpath()
        fc = QColor(self._color)
        fc.setAlpha(35)
        p.setBrush(QBrush(fc))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(fill)

        # Line
        lpen = QPen(QColor(self._color), 1.5)
        lpen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(lpen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Label + current value
        p.setPen(_c(P.MUTED))
        p.setFont(QFont(P.FONT, 7))
        cur = buf[-1]
        if cur < 1000:
            val_str = f"{cur:.1f} MB/s"
        else:
            val_str = f"{cur / 1000:.2f} GB/s"
        p.drawText(2, h - 2, f"{self._label}  {val_str}")
        p.end()


# ── HUDSystemPanel ─────────────────────────────────────────────────────────────

class HUDSystemPanel(QFrame):
    """Three circular gauges (CPU / RAM / DISK) + two sparklines (TX / RX).
    Polls psutil every second when available."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hudSystemPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(12, 8, 12, 8)
        vbox.setSpacing(6)

        # Section title
        title = QLabel("System")
        title.setStyleSheet(
            f"color:{P.MUTED};"
            f"font-family:'{P.FONT_UI}';"
            "font-size:10px;"
            "letter-spacing:1px;"
            "font-weight:600;"
        )
        vbox.addWidget(title)

        # Gauge row
        gauge_row = QHBoxLayout()
        gauge_row.setSpacing(8)
        self._cpu  = CircularGauge("CPU",  100)
        self._ram  = CircularGauge("RAM",  100)
        self._disk = CircularGauge("DISK", 100)
        for g in (self._cpu, self._ram, self._disk):
            gauge_row.addWidget(g, alignment=Qt.AlignmentFlag.AlignHCenter)
        vbox.addLayout(gauge_row)

        # Network sparklines
        self._tx = MiniSparkline("TX", P.CYAN)
        self._rx = MiniSparkline("RX", P.GREEN)
        vbox.addWidget(self._tx)
        vbox.addWidget(self._rx)

        # Live activity log — fills the remaining column height
        log_title = QLabel("Log")
        log_title.setStyleSheet(
            f"color:{P.MUTED};"
            f"font-family:'{P.FONT_UI}';"
            "font-size:10px;"
            "letter-spacing:1px;"
            "font-weight:600;"
            "margin-top:6px;"
        )
        vbox.addWidget(log_title)

        self._log = QListWidget()
        self._log.setWordWrap(True)
        self._log.setStyleSheet(
            "QListWidget {"
            "  background: rgba(7, 9, 15, 0.55);"
            "  border: 1px solid rgba(148, 163, 184, 0.05);"
            "  border-radius: 8px;"
            f" font-family: '{P.FONT}', Consolas, monospace;"
            "  font-size: 10px;"
            "}"
            "QListWidget::item { padding: 2px 6px; border: none; }"
        )
        self._log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._log.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._log.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        vbox.addWidget(self._log, 1)

        self._log_colors = {
            "error":   QColor(P.RED),
            "warning": QColor(P.AMBER),
            "tool":    QColor(P.ICE),
            "ok":      QColor(P.MINT),
            "info":    QColor(P.MUTED),
        }

        # Poll timer — 1 s interval
        self._prev_net = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1000)
        self._poll()  # initial reading

    def add_log(self, level: str, message: str) -> None:
        """Append a runtime log line to the sidebar feed."""
        try:
            while self._log.count() >= 200:
                self._log.takeItem(0)
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            item = QListWidgetItem(f"{ts}  {message}")
            item.setForeground(self._log_colors.get(level, self._log_colors["info"]))
            self._log.addItem(item)
            self._log.scrollToBottom()
        except Exception:
            pass

    def _poll(self) -> None:
        if not _HAS_PSUTIL:
            return
        try:
            self._cpu.set_value(_psutil.cpu_percent(interval=None) / 100.0)

            vm = _psutil.virtual_memory()
            self._ram.set_value(vm.percent / 100.0)

            for path in ("C:/", "C:\\", "/"):
                try:
                    du = _psutil.disk_usage(path)
                    self._disk.set_value(du.percent / 100.0)
                    break
                except Exception:
                    continue

            net = _psutil.net_io_counters()
            if self._prev_net is not None:
                self._tx.push((net.bytes_sent - self._prev_net.bytes_sent) / 1e6)
                self._rx.push((net.bytes_recv - self._prev_net.bytes_recv) / 1e6)
            self._prev_net = net
        except Exception:
            pass


# ── HUDClockWidget ─────────────────────────────────────────────────────────────

class HUDClockWidget(QWidget):
    """Two-line clock: time over date, rendered cleanly with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        t = QTimer(self)
        t.timeout.connect(self.update)
        t.start(500)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        now = datetime.datetime.now()
        w, h = self.width(), self.height()

        # Time (top, prominent)
        p.setPen(_c(P.TEXT))
        p.setFont(QFont(P.FONT_UI, 12, QFont.Weight.DemiBold))
        p.drawText(
            QRectF(0, 0, w, h * 0.58),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            now.strftime("%H:%M:%S"),
        )

        # Date (below, muted)
        p.setPen(_c(P.MUTED))
        p.setFont(QFont(P.FONT_UI, 8))
        p.drawText(
            QRectF(0, h * 0.54, w, h * 0.46),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            now.strftime("%a, %b %d"),
        )
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(132, 38)


# ── HUDIntelFeed ───────────────────────────────────────────────────────────────

class HUDIntelFeed(QFrame):
    """Scrolling event / intel log — styled like a terminal feed."""

    _COLORS: dict[str, str] = {
        "ok":    P.GREEN,
        "warn":  P.AMBER,
        "error": P.RED,
        "info":  P.CYAN,
        "muted": P.MUTED,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hudIntelFeed")

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(10, 8, 10, 6)
        vbox.setSpacing(4)

        # Section title
        title = QLabel("Intel feed")
        title.setStyleSheet(
            f"color:{P.MUTED};"
            f"font-family:'{P.FONT_UI}';"
            "font-size:10px;"
            "letter-spacing:1px;"
            "font-weight:600;"
        )
        vbox.addWidget(title)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")
        vbox.addWidget(scroll, 1)

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._feed  = QVBoxLayout(self._inner)
        self._feed.setContentsMargins(0, 0, 0, 0)
        self._feed.setSpacing(2)
        self._feed.addStretch()
        scroll.setWidget(self._inner)
        self._scroll   = scroll
        self._entries: list[QLabel] = []

    def add(self, text: str, tag: str = "info") -> None:
        """Append a new line to the feed. tag: info | ok | warn | error | muted"""
        color = self._COLORS.get(tag, P.TEXT)
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        lbl = QLabel(
            f"<span style='color:{P.MUTED}'>{ts}</span>"
            f"  <span style='color:{color}'>{text}</span>"
        )
        lbl.setFont(QFont(P.FONT, 8))
        lbl.setWordWrap(True)
        lbl.setStyleSheet("background: transparent;")
        # Insert before the trailing stretch
        idx = self._feed.count() - 1
        self._feed.insertWidget(idx, lbl)
        self._entries.append(lbl)
        # Keep at most 120 entries
        while len(self._entries) > 120:
            old = self._entries.pop(0)
            self._feed.removeWidget(old)
            old.deleteLater()
        # Auto-scroll to bottom after layout settles
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))


# ── Stylesheet ─────────────────────────────────────────────────────────────────

def stark_stylesheet() -> str:
    """Return the complete Aurora v2 QSS stylesheet (neutral graphite + violet accent)."""
    A = P.PRIMARY
    return f"""
    /* ══════════════════════════════════════════════════════════════
       JARVIS — Aurora v2
       Neutral graphite surfaces; violet reserved for focus/selection.
       Bg: #07090F   Panels: rgba(13,17,27,0.85)   Accent: #3B9EFF
       Radii: panels 12px · controls 8px
       ══════════════════════════════════════════════════════════════ */

    QMainWindow, QWidget {{
        background: transparent;
        color: {P.TEXT};
        font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
        font-size: 13px;
    }}
    QSplitter::handle {{ background: transparent; }}

    /* ── Header ──────────────────────────────────────────────────── */
    QFrame#headerPanel {{
        background: rgba(8, 12, 20, 0.38);
        border: 1px solid rgba(148, 163, 184, 0.06);
        border-radius: 12px;
    }}

    /* ── Panels ──────────────────────────────────────────────────── */
    QFrame#panel, QFrame#chatPanel, QFrame#hudSystemPanel,
    QFrame#hudIntelFeed, QFrame#providerCard {{
        background: {P.PANEL};
        border: 1px solid {P.BORDER};
        border-radius: 12px;
    }}
    QFrame#providerCard {{
        background: rgba(10, 15, 24, 0.22);
    }}
    QFrame#providerCard:hover {{
        border-color: rgba(59, 158, 255, 0.30);
    }}
    QWidget#heroPanel {{
        background: transparent;
        border: none;
    }}
    QFrame#inputFrame {{
        background: rgba(10, 14, 22, 0.38);
        border: 1px solid rgba(148, 163, 184, 0.06);
        border-radius: 10px;
    }}
    QFrame#inputFrame:focus-within {{
        border-color: rgba(59, 158, 255, 0.45);
    }}
    QWidget#statusBar {{
        background: rgba(6, 10, 18, 0.32);
        border: 1px solid rgba(148, 163, 184, 0.04);
        border-radius: 8px;
    }}

    /* ── Typography roles ────────────────────────────────────────── */
    QLabel#title {{
        color: {P.TEXT};
        font-size: 17px;
        font-weight: 600;
    }}
    QLabel#subtitle {{
        color: {P.MUTED};
        font-size: 11px;
    }}
    QLabel#panelTitle {{
        color: {P.MUTED};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QLabel#heroStatus {{
        color: {P.TEXT};
        font-size: 15px;
        font-weight: 600;
        letter-spacing: 2px;
    }}
    QLabel#muted {{
        color: {P.MUTED};
        font-size: 11px;
    }}
    QLabel#key {{
        color: {P.ICE};
        font-family: "{P.FONT}", Consolas, monospace;
        font-size: 11px;
    }}
    QLabel#helpTip {{
        color: {P.MUTED};
        background: rgba(148, 163, 184, 0.05);
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 11px;
    }}

    /* ── Status chips ────────────────────────────────────────────── */
    QLabel#statusChip {{
        background: rgba(59, 158, 255, 0.10);
        border: 1px solid rgba(59, 158, 255, 0.05);
        border-radius: 9px;
        padding: 3px 12px;
        color: #A6D0FF;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#modeChip {{
        background: rgba(148, 163, 184, 0.06);
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 9px;
        padding: 3px 12px;
        color: #AEB7C9;
        font-size: 11px;
        font-weight: 500;
    }}

    /* ── Chat surfaces ───────────────────────────────────────────── */
    QTextEdit#chatDisplay {{
        background: rgba(6, 9, 15, 0.25);
        border: 1px solid rgba(148, 163, 184, 0.07);
        border-radius: 10px;
        padding: 10px;
        font-size: 14px;
        selection-background-color: rgba(59, 158, 255, 0.30);
    }}
    QTextEdit#msgInput {{
        background: transparent;
        border: none;
        font-size: 14px;
        selection-background-color: rgba(59, 158, 255, 0.30);
    }}
    QTextEdit, QPlainTextEdit {{
        background: rgba(9, 12, 19, 0.55);
        color: {P.TEXT};
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 8px;
        selection-background-color: rgba(59, 158, 255, 0.30);
    }}

    /* ── Buttons ─────────────────────────────────────────────────── */
    QPushButton {{
        background: rgba(226, 232, 240, 0.04);
        color: #D5DCE8;
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 8px;
        padding: 6px 14px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: rgba(59, 158, 255, 0.12);
        border-color: rgba(59, 158, 255, 0.45);
        color: #FFFFFF;
    }}
    QPushButton:pressed {{
        background: rgba(59, 158, 255, 0.20);
    }}
    QPushButton:disabled {{
        color: rgba(124, 135, 157, 0.45);
        background: rgba(226, 232, 240, 0.02);
        border-color: rgba(148, 163, 184, 0.07);
    }}
    QPushButton:focus {{
        border: 1px solid rgba(59, 158, 255, 0.05);
        outline: none;
    }}
    QToolButton {{
        background: transparent;
        color: {P.MUTED};
        border: 1px solid transparent;
        border-radius: 7px;
        padding: 4px 8px;
    }}
    QToolButton:hover {{
        background: rgba(148, 163, 184, 0.10);
        color: {P.TEXT};
    }}

    /* ── Inputs ──────────────────────────────────────────────────── */
    QLineEdit {{
        background: rgba(17, 21, 33, 0.80);
        color: {P.TEXT};
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 8px;
        padding: 6px 10px;
        selection-background-color: rgba(59, 158, 255, 0.30);
    }}
    QLineEdit:focus {{
        border-color: rgba(59, 158, 255, 0.55);
        background: rgba(17, 21, 33, 1.0);
    }}
    QComboBox {{
        background: rgba(17, 21, 33, 0.80);
        color: {P.TEXT};
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 8px;
        padding: 5px 10px;
    }}
    QComboBox:hover {{ border-color: rgba(148, 163, 184, 0.30); }}
    QComboBox:focus {{ border-color: rgba(59, 158, 255, 0.55); }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid rgba(148, 163, 184, 0.65);
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background: #11141D;
        color: {P.TEXT};
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 8px;
        padding: 4px;
        selection-background-color: rgba(59, 158, 255, 0.16);
    }}
    QSpinBox, QDoubleSpinBox {{
        background: rgba(17, 21, 33, 0.80);
        color: {P.TEXT};
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 7px;
        padding: 4px 8px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: rgba(59, 158, 255, 0.55); }}

    /* ── Checkboxes / radios ─────────────────────────────────────── */
    QCheckBox, QRadioButton {{
        color: {P.TEXT};
        spacing: 8px;
        font-size: 12px;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 4px;
        background: rgba(17, 21, 33, 0.70);
    }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border-color: rgba(59, 158, 255, 0.55);
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {A};
        border-color: {A};
    }}

    /* ── Sliders / progress ──────────────────────────────────────── */
    QSlider::groove:horizontal {{
        height: 4px;
        background: rgba(148, 163, 184, 0.14);
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {A};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 14px;
        height: 14px;
        margin: -5px 0;
        background: {P.TEXT};
        border: 2px solid {A};
        border-radius: 8px;
    }}
    QProgressBar {{
        background: rgba(148, 163, 184, 0.10);
        border: none;
        border-radius: 4px;
        height: 8px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background: {A};
        border-radius: 4px;
    }}

    /* ── Tabs ────────────────────────────────────────────────────── */
    QTabWidget::pane {{
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 10px;
        background: rgba(13, 17, 27, 0.60);
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {P.MUTED};
        padding: 7px 16px;
        margin-right: 4px;
        border: 1px solid transparent;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        font-weight: 600;
        font-size: 12px;
    }}
    QTabBar::tab:hover {{ color: {P.TEXT}; }}
    QTabBar::tab:selected {{
        color: #BBDBFF;
        background: rgba(59, 158, 255, 0.08);
        border: 1px solid rgba(59, 158, 255, 0.05);
        border-bottom: 2px solid {A};
    }}

    /* ── Lists / tables ──────────────────────────────────────────── */
    QListWidget, QTreeWidget, QTableWidget, QTreeView, QListView {{
        background: rgba(9, 12, 19, 0.55);
        color: {P.TEXT};
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 8px;
        outline: none;
        alternate-background-color: rgba(148, 163, 184, 0.03);
    }}
    QListWidget::item, QTreeWidget::item, QTreeView::item {{
        padding: 4px 8px;
        border-radius: 5px;
    }}
    QListWidget::item:hover, QTreeWidget::item:hover, QTreeView::item:hover {{
        background: rgba(148, 163, 184, 0.07);
    }}
    QListWidget::item:selected, QTreeWidget::item:selected, QTreeView::item:selected {{
        background: rgba(59, 158, 255, 0.16);
        color: #FFFFFF;
    }}
    QHeaderView::section {{
        background: rgba(17, 21, 33, 0.95);
        color: {P.MUTED};
        border: none;
        border-bottom: 1px solid rgba(148, 163, 184, 0.05);
        padding: 6px 10px;
        font-weight: 600;
        font-size: 11px;
    }}

    /* ── Menus ───────────────────────────────────────────────────── */
    QMenu {{
        background: #11141D;
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 10px;
        padding: 6px;
        font-size: 12px;
    }}
    QMenu::item {{
        color: {P.TEXT};
        padding: 7px 20px 7px 13px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: rgba(59, 158, 255, 0.14);
        color: #FFFFFF;
    }}
    QMenu::separator {{
        height: 1px;
        background: rgba(148, 163, 184, 0.12);
        margin: 5px 10px;
    }}

    /* ── Scrollbars ──────────────────────────────────────────────── */
    QScrollBar:vertical {{
        background: transparent;
        width: 7px;
        margin: 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(148, 163, 184, 0.22);
        border-radius: 3px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: rgba(59, 158, 255, 0.45); }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 7px;
        margin: 0 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(148, 163, 184, 0.22);
        border-radius: 3px;
        min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: rgba(59, 158, 255, 0.45); }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* ── Dialogs / misc ──────────────────────────────────────────── */
    QDialog {{
        background: #0B0E16;
        border: 1px solid rgba(148, 163, 184, 0.05);
    }}
    QGroupBox {{
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 9px;
        margin-top: 12px;
        padding-top: 10px;
        font-weight: 600;
        color: {P.MUTED};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {P.MUTED};
        font-size: 11px;
    }}
    QToolTip {{
        background: #11141D;
        color: {P.TEXT};
        border: 1px solid rgba(148, 163, 184, 0.05);
        border-radius: 7px;
        padding: 5px 9px;
        font-size: 11px;
    }}
    """
