import math

from PyQt6.QtCore import (
    QEasingCurve, QPointF, QRectF, QPropertyAnimation,
    QTimer, Qt, pyqtProperty,
)
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen,
    QRadialGradient, QLinearGradient, QRegion,
)
from PyQt6.QtWidgets import QPushButton, QSizePolicy, QWidget

STATUS_COLORS = {
    "idle":         QColor("#00E5FF"),   # cyan accent — matches header/branding
    "listening":    QColor("#38BDF8"),   # sky-400 — active capture
    "transcribing": QColor("#FBBF24"),  # amber-400 — processing speech
    "thinking":     QColor("#818CF8"),  # indigo-400 — AI reasoning
    "speaking":     QColor("#34D399"),  # emerald-400 — delivering response
    "error":        QColor("#FB7185"),  # rose-400 — error state
}

def _mix_colors(left: QColor, right: QColor, weight: float) -> QColor:
    weight = max(0.0, min(weight, 1.0))
    return QColor(
        int(left.red()   + (right.red()   - left.red())   * weight),
        int(left.green() + (right.green() - left.green()) * weight),
        int(left.blue()  + (right.blue()  - left.blue())  * weight),
        int(left.alpha() + (right.alpha() - left.alpha()) * weight),
    )

class AnimatedButton(QPushButton):
    """
    HUD button: hover fill + diagonal shimmer + ripple on click.
    No idle timer — zero CPU at rest.
    """

    def __init__(self, text: str, accent: str = "#00E5FF", parent=None):
        super().__init__(text, parent)
        self._accent = QColor(accent)
        self._hover_progress = 0.0
        self._press_progress = 0.0
        self._ripple_progress = 0.0
        self._shimmer_x = -0.5          # normalised position across button width
        self._ripple_ox = 0.0
        self._ripple_oy = 0.0

        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(160)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._press_anim = QPropertyAnimation(self, b"pressProgress", self)
        self._press_anim.setDuration(80)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutQuart)

        self._ripple_anim = QPropertyAnimation(self, b"rippleProgress", self)
        self._ripple_anim.setDuration(380)
        self._ripple_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._shimmer_anim = QPropertyAnimation(self, b"shimmerX", self)
        self._shimmer_anim.setDuration(480)
        self._shimmer_anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(34)

    def enterEvent(self, event) -> None:
        self._run_anim(self._hover_anim, self._hover_progress, 1.0)
        # Shimmer sweeps left→right once on hover enter — only runs for 480ms
        self._shimmer_anim.stop()
        self._shimmer_x = -0.3
        self._run_anim(self._shimmer_anim, -0.3, 1.3)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._run_anim(self._hover_anim, self._hover_progress, 0.0)
        self._run_anim(self._press_anim, self._press_progress, 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._run_anim(self._press_anim, self._press_progress, 1.0)
        pos = event.position()
        self._ripple_ox, self._ripple_oy = pos.x(), pos.y()
        self._ripple_anim.stop()
        self._ripple_progress = 0.0
        self._run_anim(self._ripple_anim, 0.0, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._run_anim(self._press_anim, self._press_progress, 0.0)
        super().mouseReleaseEvent(event)

    def _run_anim(self, anim: QPropertyAnimation, start: float, end: float) -> None:
        anim.stop()
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.start()

    def get_hover_progress(self) -> float:   return self._hover_progress
    def set_hover_progress(self, v: float):  self._hover_progress = v; self.update()
    def get_press_progress(self) -> float:   return self._press_progress
    def set_press_progress(self, v: float):  self._press_progress = v; self.update()
    def get_ripple_progress(self) -> float:  return self._ripple_progress
    def set_ripple_progress(self, v: float): self._ripple_progress = v; self.update()
    def get_shimmer_x(self) -> float:        return self._shimmer_x
    def set_shimmer_x(self, v: float):       self._shimmer_x = v; self.update()

    hoverProgress  = pyqtProperty(float, fget=get_hover_progress,  fset=set_hover_progress)
    pressProgress  = pyqtProperty(float, fget=get_press_progress,  fset=set_press_progress)
    rippleProgress = pyqtProperty(float, fget=get_ripple_progress, fset=set_ripple_progress)
    shimmerX       = pyqtProperty(float, fget=get_shimmer_x,       fset=set_shimmer_x)

    # Paint
    def paintEvent(self, event) -> None:
        # Guard: Ctrl+C or app shutdown can deliver a KeyboardInterrupt into
        # Qt's paint machinery; catch it so we don't crash the whole process.
        try:
            self._paint_inner(event)
        except Exception:
            pass

    def _paint_inner(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        r = self.rect()

        # macOS-style scale — apply FIRST so clip and everything scales together
        if self._press_progress > 0.001:
            scale = 1.0 - self._press_progress * 0.08
            cx, cy = r.width() / 2.0, r.height() / 2.0
            painter.translate(cx, cy)
            painter.scale(scale, scale)
            painter.translate(-cx, -cy)

        bounds = r.adjusted(2, 2, -2, -2)
        w, h = bounds.width(), bounds.height()

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(bounds), 10, 10)
        painter.setClipPath(clip)

        # Fill: transparent at rest → transparent blue on hover
        base_fill  = QColor(59, 130, 246, 0)    # fully transparent at rest
        hover_fill = QColor(59, 130, 246, 38)    # soft blue tint on hover
        fill = _mix_colors(base_fill, hover_fill, self._hover_progress)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(bounds), 10, 10)

        # Border: faint always, brighter blue on hover
        base_border_a = 18
        hover_border_a = 110
        border_alpha = int(base_border_a + (hover_border_a - base_border_a) * self._hover_progress)
        border_c = QColor(self._accent.red(), self._accent.green(), self._accent.blue(), border_alpha)
        painter.setPen(QPen(border_c, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(bounds), 10, 10)

        # Diagonal shimmer sweep (only during hover-enter, ~480ms one-shot)
        if self._hover_progress > 0.01 and -0.3 <= self._shimmer_x <= 1.3:
            sx = bounds.left() + self._shimmer_x * w
            shimmer_w = w * 0.30
            grad = QLinearGradient(sx - shimmer_w, 0.0, sx + shimmer_w, 0.0)
            alpha = int(62 * self._hover_progress)
            grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            grad.setColorAt(0.5, QColor(255, 255, 255, alpha))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(bounds), 10, 10)

        # Ripple on click
        if self._ripple_progress > 0.0:
            max_r = math.sqrt(w * w + h * h)
            rr = max_r * self._ripple_progress
            alpha = int(70 * (1.0 - self._ripple_progress ** 0.6))
            rip = QColor(self._accent)
            rip.setAlpha(max(0, alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(rip)
            painter.drawEllipse(QPointF(self._ripple_ox, self._ripple_oy), rr, rr)

        # Text
        painter.setClipping(False)
        text_color = _mix_colors(QColor(226, 232, 240, 220), QColor(255, 255, 255, 255), self._hover_progress)
        painter.setPen(text_color)
        font = QFont("Segoe UI Variable", 11, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(bounds), Qt.AlignmentFlag.AlignCenter, self.text())

class JarvisOrbWidget(QWidget):
    """
    Circular JARVIS orb with HUD rings, breathing animation, and
    state-specific overlays. Renders only circular content — no rectangle.
    """

    def __init__(self, compact: bool = False):
        super().__init__()
        self.compact = compact
        # Prevent Qt from painting any background rectangle before paintEvent
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        min_size = 340 if compact else 480
        self.setMinimumSize(min_size, min_size)

        # Animation state
        self.phase = 0.0
        self._target_phase_speed = 0.003
        self._current_phase_speed = 0.003
        self.audio_level = 0.0
        self._smooth_audio = 0.0
        self.speech_detected = False
        self.mode = "wake_phrase"
        self.status = "idle"
        self.response_style = "calm"

        # Smooth status transition
        self._status_blend = 0.0  # 0=previous, 1=current
        self._prev_color = STATUS_COLORS["idle"]
        self._cur_color  = STATUS_COLORS["idle"]

        # Particles for thinking state
        self._particles: list[dict] = []

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 fps

        # Apply circular mask immediately; updated again on every resize.
        # This tells Qt/Windows that the widget's hit-testable and visible
        # area is a circle — corners are fully transparent regardless of what
        # any parent widget paints.
        QTimer.singleShot(0, self._apply_circular_mask)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_circular_mask()

    def _apply_circular_mask(self) -> None:
        w, h = self.width(), self.height()
        if w > 0 and h > 0:
            self.setMask(QRegion(0, 0, w, h, QRegion.RegionType.Ellipse))

    def set_status(self, status: str) -> None:
        if status == self.status:
            return
        self._prev_color = self._get_blended_color()
        self._cur_color  = STATUS_COLORS.get(status, STATUS_COLORS["idle"])
        self._status_blend = 0.0
        self.status = status
        # Adjust animation speed target
        self._target_phase_speed = {
            "idle":         0.003,
            "listening":    0.022,
            "transcribing": 0.035,
            "thinking":     0.045,
            "speaking":     0.028,
            "error":        0.012,
        }.get(status, 0.003)
        self.update()

    def set_response_style(self, style: str) -> None:
        self.response_style = style
        self.update()

    def set_audio_level(self, level: float, speech_detected: bool, mode: str) -> None:
        # Scale ×40 so even very quiet mics produce visible animation (clamped to 1.0)
        self.audio_level = max(0.0, min(level * 40.0, 1.0))
        self.speech_detected = speech_detected
        self.mode = mode
        self.update()

    def _get_blended_color(self) -> QColor:
        return _mix_colors(self._prev_color, self._cur_color, self._status_blend)

    def _tick(self) -> None:
        # Smooth phase speed transition
        self._current_phase_speed += (self._target_phase_speed - self._current_phase_speed) * 0.035
        self.phase += self._current_phase_speed

        # Smooth audio level (slower = less jittery)
        self._smooth_audio += (self.audio_level - self._smooth_audio) * 0.10

        # Smooth status color blend (slower = more elegant transition)
        if self._status_blend < 1.0:
            self._status_blend = min(1.0, self._status_blend + 0.025)

        # Spawn/update particles when thinking
        if self.status == "thinking":
            self._update_particles()
        else:
            self._particles.clear()

        self.update()

    def _update_particles(self) -> None:
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        orb_size = min(w, h)
        core_r = orb_size * 0.165

        # Spawn new particles
        while len(self._particles) < 18:
            angle = math.tau * math.sin(self.phase * 7 + len(self._particles) * 0.7)
            speed = 0.6 + 0.4 * abs(math.sin(self.phase * 3 + len(self._particles)))
            self._particles.append({
                "x": cx, "y": cy,
                "vx": math.cos(angle) * speed * 2.5,
                "vy": math.sin(angle) * speed * 2.5,
                "life": 1.0,
                "decay": 0.014 + 0.008 * abs(math.sin(self.phase + len(self._particles))),
                "r": core_r * (0.8 + 0.4 * abs(math.sin(self.phase * 2 + len(self._particles)))),
            })

        # Update existing
        alive = []
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vx"] *= 0.97
            p["vy"] *= 0.97
            p["life"] -= p["decay"]
            if p["life"] > 0:
                alive.append(p)
        self._particles = alive

    # Paint entry point
    def paintEvent(self, event) -> None:
        try:
            self._paint_inner(event)
        except Exception:
            pass

    def _paint_inner(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()

        # Step 1 — force-clear the entire widget rect to fully transparent.
        # CompositionMode_Source REPLACES whatever Qt/Windows pre-filled here
        # (system background, parent fill, etc.) with alpha=0.  Without this,
        # Windows can paint a black rectangle before calling paintEvent even
        # when WA_NoSystemBackground + WA_TranslucentBackground are set.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Step 2 — restrict all subsequent drawing to the circle so no radial
        # halo ever reaches a rectangular edge and creates a visible corner.
        _clip = QPainterPath()
        _clip.addEllipse(QRectF(0, 0, w, h))
        painter.setClipPath(_clip)

        center = QPointF(w / 2.0, h / 2.0)
        orb_size = min(w, h)
        color = self._get_blended_color()
        cr, cg, cb = color.red(), color.green(), color.blue()

        base_r    = orb_size * (0.155 if self.compact else 0.165)
        breathing = math.sin(self.phase * 0.8) * (5 if self.compact else 8)
        audio_boost = self._smooth_audio * (30 if self.speech_detected else 14)
        core_r = max(40.0, base_r + breathing + audio_boost)

        # Draw back-to-front — all circular, no rectangles
        self._draw_deep_halos(painter, center, cr, cg, cb, core_r)
        self._draw_arc_rings(painter, center, cr, cg, cb, core_r)
        self._draw_tick_ring(painter, center, cr, cg, cb, core_r * 2.55, 72)
        self._draw_tick_ring(painter, center, cr, cg, cb, core_r * 1.75, 36)
        self._draw_status_layer(painter, center, color, cr, cg, cb, core_r)
        self._draw_core(painter, center, cr, cg, cb, core_r)
        self._draw_labels(painter, center, cr, cg, cb, core_r)

    # Deep outer halos
    def _draw_deep_halos(self, painter, center, cr, cg, cb, core_r):
        painter.setPen(Qt.PenStyle.NoPen)
        for alpha, scale in ((12, 5.2), (8, 4.2), (5, 3.2)):
            grad = QRadialGradient(center, core_r * scale)
            grad.setColorAt(0.0, QColor(cr, cg, cb, alpha))
            grad.setColorAt(1.0, QColor(cr, cg, cb, 0))
            painter.setBrush(grad)
            painter.drawEllipse(center, core_r * scale, core_r * scale)

    # Rotating HUD arc rings
    def _draw_arc_rings(self, painter, center, cr, cg, cb, core_r):
        # (radius_mult, rot_speed, arc_degrees, num_arcs, alpha, pen_w)
        rings = [
            (4.2,   0.06, 150, 3,  35, 0.9),
            (3.5,  -0.12, 110, 4,  55, 1.1),
            (2.85,  0.20,  85, 5,  80, 1.4),
            (2.30, -0.32,  65, 6, 105, 1.7),
            (1.85,  0.48,  48, 8, 130, 1.9),
            (1.48, -0.72,  32, 10, 155, 1.5),
        ]
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for r_mult, spd, arc_deg, n, alpha, pw in rings:
            r = core_r * r_mult
            rect = QRectF(center.x() - r, center.y() - r, 2*r, 2*r)
            rot_deg = (self.phase * spd * 57.2958) % 360
            step = 360.0 / n
            pen = QPen(QColor(cr, cg, cb, alpha), pw)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            for i in range(n):
                start = int((rot_deg + i * step) * 16)
                span  = int(arc_deg * 16)
                painter.drawArc(rect, start, span)

    # Tick mark rings
    def _draw_tick_ring(self, painter, center, cr, cg, cb, r, n_ticks):
        slow_rot = self.phase * 0.03
        for i in range(n_ticks):
            angle = (math.pi * 2 / n_ticks) * i + slow_rot
            major = i % 12 == 0
            minor = i % 4 == 0
            tick_len = 10 if major else (5 if minor else 2.5)
            alpha    = 140 if major else (80 if minor else 38)
            pw       = 1.6 if major else (1.1 if minor else 0.7)
            x1 = center.x() + math.cos(angle) * (r - tick_len)
            y1 = center.y() + math.sin(angle) * (r - tick_len)
            x2 = center.x() + math.cos(angle) * r
            y2 = center.y() + math.sin(angle) * r
            painter.setPen(QPen(QColor(cr, cg, cb, alpha), pw))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # State-specific overlays
    def _draw_status_layer(self, painter, center, color, cr, cg, cb, core_r):
        if self.status == "thinking":
            # Fast spinning broken arcs + particle shower
            for i, (r_m, spd, arc, n, alp, pw) in enumerate([
                (2.15,  2.5, 55, 5, 200, 2.8),
                (1.65, -3.8, 38, 7, 180, 2.2),
                (1.25,  5.2, 25, 9, 160, 1.8),
            ]):
                r = core_r * r_m
                rect = QRectF(center.x()-r, center.y()-r, 2*r, 2*r)
                rot  = (self.phase * spd * 57.2958) % 360
                step = 360.0 / n
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for j in range(n):
                    start = int((rot + j*step) * 16)
                    span  = int(arc * 16)
                    painter.setPen(QPen(QColor(cr, cg, cb, alp - i*20), pw - i*0.3))
                    painter.drawArc(rect, start, span)
            # Particles
            for p in self._particles:
                alpha = max(0, int(p["life"] * 180))
                rad   = max(1.0, p["r"] * 0.08 * p["life"])
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(cr, cg, cb, alpha))
                painter.drawEllipse(QPointF(p["x"], p["y"]), rad, rad)
            return

        if self.status == "speaking":
            # Concentric expanding rings
            for i in range(4):
                delay = i * 0.3
                ring_phase = (self.phase - delay * 0.5) % 1.0
                r = core_r * (1.3 + i * 0.6 + ring_phase * 1.2)
                alpha = int(180 * (1.0 - ring_phase) * (1.0 - i * 0.15))
                pw = 2.4 - i * 0.3
                painter.setPen(QPen(QColor(cr, cg, cb, max(0, alpha)), max(0.4, pw)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, r, r)
            # Smooth pulsing outward waves underneath
            for i in range(5):
                phase_off = i * math.pi * 0.4
                wave_t = (math.sin(self.phase * 2.2 + phase_off) + 1) * 0.5
                r = core_r * (1.4 + 0.7 * i) + wave_t * (18 + i * 5)
                alpha = int(80 * wave_t * (1.0 - i * 0.16))
                pw    = 1.8 - i * 0.3
                painter.setPen(QPen(QColor(cr, cg, cb, max(0, alpha)), max(0.4, pw)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, r, r)
            return

        if self.status == "error":
            # Red error glow and pulsing danger indication
            error_color = STATUS_COLORS["error"]
            ecr, ecg, ecb = error_color.red(), error_color.green(), error_color.blue()
            # Breathing red glow
            glow_phase = (math.sin(self.phase * 3.5) + 1) * 0.5
            for i in range(3):
                glow_r = core_r * (2.0 + i) + glow_phase * 20
                glow_alpha = int(120 * (1.0 - i * 0.3) * glow_phase)
                grad = QRadialGradient(center, glow_r)
                grad.setColorAt(0.3, QColor(ecr, ecg, ecb, glow_alpha))
                grad.setColorAt(1.0, QColor(ecr, ecg, ecb, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(grad)
                painter.drawEllipse(center, glow_r, glow_r)
            # Fast flashing warning rings
            flash_phase = (math.sin(self.phase * 6.0) + 1) * 0.5
            for i in range(3):
                r = core_r * (1.2 + i * 0.4)
                alpha = int(200 * flash_phase) if flash_phase > 0.4 else 0
                painter.setPen(QPen(QColor(ecr, ecg, ecb, alpha), 2.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, r, r)
            return

        if self.status in ("listening", ) or self.speech_detected:
            # Equalizer bars radiating outward
            n_bars = 40
            for i in range(n_bars):
                angle  = (math.tau / n_bars) * i + self.phase * 0.4
                energy = 0.35 + 0.65 * abs(math.sin(self.phase * 3 + i * 0.57))
                bar    = 5 + self._smooth_audio * 32 * energy
                inner  = core_r * 1.10
                x1 = center.x() + math.cos(angle) * inner
                y1 = center.y() + math.sin(angle) * inner
                x2 = center.x() + math.cos(angle) * (inner + bar)
                y2 = center.y() + math.sin(angle) * (inner + bar)
                alpha = int(70 + 130 * energy)
                painter.setPen(QPen(QColor(cr, cg, cb, alpha), 1.8))
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # Core sphere
    def _draw_core(self, painter, center, cr, cg, cb, core_r):
        painter.setPen(Qt.PenStyle.NoPen)

        # Outer glow halos using radial gradient
        for alpha, scale in ((45, 1.90), (80, 1.50), (130, 1.15)):
            grad = QRadialGradient(center, core_r * scale)
            grad.setColorAt(0.0, QColor(cr, cg, cb, alpha))
            grad.setColorAt(1.0, QColor(cr, cg, cb, 0))
            painter.setBrush(grad)
            painter.drawEllipse(center, core_r * scale, core_r * scale)

        # Iris ring
        iris = QColor(min(cr+60, 255), min(cg+60, 255), min(cb+60, 255), 230)
        painter.setPen(QPen(iris, 3.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, core_r, core_r)

        # Inner detail ring
        painter.setPen(QPen(QColor(cr, cg, cb, 100), 1.2))
        painter.drawEllipse(center, core_r * 0.78, core_r * 0.78)

        # Dark sphere fill
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(3, 10, 22, 245))
        painter.drawEllipse(center, core_r * 0.94, core_r * 0.94)

        # Radial inner colour wash
        grad2 = QRadialGradient(
            QPointF(center.x() - core_r * 0.2, center.y() - core_r * 0.25),
            core_r * 0.9,
        )
        grad2.setColorAt(0.0, QColor(cr, cg, cb, 38))
        grad2.setColorAt(1.0, QColor(cr, cg, cb, 0))
        painter.setBrush(grad2)
        painter.drawEllipse(center, core_r * 0.90, core_r * 0.90)

        # Audio-reactive inner accent ring
        pulse_r = core_r * 0.52 + self._smooth_audio * 14
        painter.setPen(QPen(QColor(cr, cg, cb, 150), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, pulse_r, pulse_r)

    # Text labels
    def _draw_labels(self, painter, center, cr, cg, cb, core_r):
        painter.setPen(QColor(230, 250, 255, 235))
        font_sz = max(int(core_r * (0.34 if not self.compact else 0.28)), 9)
        painter.setFont(QFont("Segoe UI Variable", font_sz, QFont.Weight.Bold))
        title_rect = QRectF(
            center.x() - core_r * 0.85, center.y() - core_r * 0.38,
            core_r * 1.70, core_r * 0.76,
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "JARVIS")

        status_text = {
            "idle":         "ONLINE",
            "thinking":     "PROCESSING",
            "listening":    "LISTENING",
            "transcribing": "TRANSCRIBING",
            "speaking":     "RESPONDING",
            "error":        "ERROR",
        }.get(self.status, self.status.upper())
        painter.setPen(QColor(cr, cg, cb, 165))
        sub_sz = max(int(core_r * (0.14 if not self.compact else 0.11)), 6)
        painter.setFont(QFont("Segoe UI Variable", sub_sz, QFont.Weight.Medium))
        sub_rect = QRectF(
            center.x() - core_r * 0.85, center.y() + core_r * 0.18,
            core_r * 1.70, core_r * 0.30,
        )
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, status_text)

class HUDRootWidget(QWidget):
    """Animated HUD-style background that fills the root window area."""

    _MAX_PARTICLES = 18
    _LINK_DIST = 90  # pixels — particles within this range draw connecting lines

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self.setAutoFillBackground(False)
        self._phase = 0.0
        self._scan_phase = 0.0

        # Constellation particle system
        import random
        self._particles_bg: list[dict] = []
        for _ in range(self._MAX_PARTICLES):
            self._particles_bg.append({
                "x": random.random(),  # normalised 0-1
                "y": random.random(),
                "vx": (random.random() - 0.5) * 0.0006,
                "vy": (random.random() - 0.5) * 0.0006,
                "r": 1.2 + random.random() * 1.5,
                "alpha": 40 + int(random.random() * 60),
            })

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)  # 20 fps for background — smooth enough, much cheaper

    def _tick(self) -> None:
        self._phase += 0.002
        self._scan_phase += 0.005
        # Move particles
        for p in self._particles_bg:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["x"] < -0.02 or p["x"] > 1.02:
                p["vx"] *= -1
            if p["y"] < -0.02 or p["y"] > 1.02:
                p["vy"] *= -1
        self.update()

    def paintEvent(self, event) -> None:
        try:
            self._paint_inner(event)
        except Exception:
            pass

    def _paint_inner(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Semi-transparent base — lets desktop wallpaper show through.
        # CompositionMode_Source writes the alpha channel directly so Qt's
        # WA_TranslucentBackground compositing actually punches through.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(8, 12, 22, 160))  # 63% opaque #080c16
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Very faint grid
        painter.setPen(QPen(QColor(0, 200, 232, 3), 1))
        grid = 72
        for x in range(0, w + grid, grid):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h + grid, grid):
            painter.drawLine(0, y, w, y)

        cx, cy = w / 2.0, h / 2.0
        max_r = math.sqrt(w * w + h * h) / 2.0 + 60

        # Constellation particle layer
        pts = [(p["x"] * w, p["y"] * h, p["alpha"]) for p in self._particles_bg]
        link_d2 = self._LINK_DIST ** 2
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i, (ax, ay, _) in enumerate(pts):
            for j in range(i + 1, len(pts)):
                bx, by, _ = pts[j]
                d2 = (ax - bx) ** 2 + (ay - by) ** 2
                if d2 < link_d2:
                    alpha = int(28 * (1.0 - d2 / link_d2))
                    painter.setPen(QPen(QColor(0, 229, 255, alpha), 0.6))
                    painter.drawLine(QPointF(ax, ay), QPointF(bx, by))
        painter.setPen(Qt.PenStyle.NoPen)
        for (px, py, pa), p in zip(pts, self._particles_bg):
            painter.setBrush(QColor(0, 200, 232, pa + 20))
            painter.drawEllipse(QPointF(px, py), p["r"], p["r"])

        # (concentric rings removed — cleaner look)

        # Vignette — darken edges
        for edge_alpha, inset in ((50, 0), (30, 30), (15, 70)):
            vig_grad = QLinearGradient(0, 0, 0, h)
            vig_grad.setColorAt(0.0, QColor(0, 0, 0, edge_alpha))
            vig_grad.setColorAt(0.12, QColor(0, 0, 0, 0))
            vig_grad.setColorAt(0.88, QColor(0, 0, 0, 0))
            vig_grad.setColorAt(1.0, QColor(0, 0, 0, edge_alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(vig_grad)
            painter.drawRect(inset, 0, w - inset * 2, h)

        # Corner brackets and diagonal accents removed — cleaner, less "HUD slop"

    def _draw_corner_brackets(self, painter: QPainter, w: int, h: int) -> None:
        # Pulsing bracket opacity for a living HUD feel
        pulse_a = int(45 + 25 * math.sin(self._phase * 1.5))
        painter.setPen(QPen(QColor(0, 229, 255, pulse_a), 2.2))
        arm, gap = 56, 16
        painter.drawLine(gap, gap, gap + arm, gap)
        painter.drawLine(gap, gap, gap, gap + arm)
        painter.drawLine(w - gap - arm, gap, w - gap, gap)
        painter.drawLine(w - gap, gap, w - gap, gap + arm)
        painter.drawLine(gap, h - gap, gap + arm, h - gap)
        painter.drawLine(gap, h - gap, gap, h - gap - arm)
        painter.drawLine(w - gap - arm, h - gap, w - gap, h - gap)
        painter.drawLine(w - gap, h - gap, w - gap, h - gap - arm)
