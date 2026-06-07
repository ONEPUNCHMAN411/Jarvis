"""JARVIS 3D Orb — raymarched GLSL plasma sphere with orbital rings.

Renders a true 3D scene on the GPU via QOpenGLWidget:
  • plasma-core sphere with fresnel rim lighting and fbm noise interior
  • three tilted orbital rings raymarched as glowing tori
  • volumetric halo, audio-reactive breathing, per-status color/motion

Public API matches the legacy 2D JarvisOrbWidget exactly:
  set_status(str), set_audio_level(level, speech_detected, mode),
  set_response_style(str), compact constructor flag.

Use create_orb_widget() — it falls back to the 2D orb if OpenGL is
unavailable (missing PyOpenGL, software-only host, driver failure).
"""

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QSurfaceFormat
from PyQt6.QtWidgets import QSizePolicy

from jarvis.ui.orb_widgets import STATUS_COLORS, _mix_colors

_VERT = """
#version 120
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
    v_uv = a_pos * 0.5 + 0.5;
    gl_Position = vec4(a_pos, 0.0, 1.0);
}
"""

_FRAG = """
#version 120
uniform vec2  u_res;
uniform float u_time;
uniform vec3  u_color;   // status color, 0-1
uniform float u_audio;   // smoothed mic level 0-1
uniform float u_speed;   // status animation speed
uniform float u_flash;   // error strobe amount
uniform float u_pulse;   // speaking pulse amount
uniform float u_spin;    // thinking spin boost
varying vec2  v_uv;

float hash(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(mix(hash(i + vec3(0,0,0)), hash(i + vec3(1,0,0)), f.x),
            mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
        mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
            mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y),
        f.z);
}

float fbm(vec3 p) {
    float a = 0.5;
    float s = 0.0;
    for (int i = 0; i < 3; i++) {
        s += a * noise(p);
        p = p * 2.03 + vec3(1.7);
        a *= 0.5;
    }
    return s;
}

mat3 rotX(float a) { float c = cos(a), s = sin(a); return mat3(1,0,0, 0,c,-s, 0,s,c); }
mat3 rotY(float a) { float c = cos(a), s = sin(a); return mat3(c,0,s, 0,1,0, -s,0,c); }
mat3 rotZ(float a) { float c = cos(a), s = sin(a); return mat3(c,-s,0, s,c,0, 0,0,1); }

// Exact glow of a flat circular ring (radius R, in the y=0 plane of frame m).
// Intersects the ray with the ring's plane — continuous and alias-free.
// occl: 1.0 when in front of the sphere surface at tS, dimmed when behind.
float ringGlow(vec3 ro, vec3 rd, mat3 m, float R, float tS, float k) {
    vec3 o = m * ro;
    vec3 d = m * rd;
    if (abs(d.y) < 0.02) return 0.0;        // grazing — avoid streaks
    float t = -o.y / d.y;
    if (t < 0.0) return 0.0;
    vec3 p = o + d * t;
    float dist = abs(length(p.xz) - R);
    float g = exp(-dist * k) + exp(-dist * k * 0.18) * 0.10;
    if (t > tS) g *= 0.13;                  // occluded by the core sphere
    return g;
}

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= u_res.x / u_res.y;

    float t  = u_time * u_speed;
    float tw = u_time;                       // wall-clock, for camera drift

    vec3 ro = vec3(0.0, 0.0, 3.1);
    vec3 rd = normalize(vec3(uv, -2.1));

    // Slow scene tumble so the 3D structure reads clearly
    mat3 cam = rotY(tw * 0.04) * rotX(0.42 + 0.05 * sin(tw * 0.07));

    float R = 0.60 + 0.025 * sin(t * 0.9) + 0.07 * u_audio;

    vec3 col = vec3(0.0);

    // ── Core sphere (analytic intersection) ───────────────────────
    float tS = 1e9;
    float b = dot(ro, rd);
    float c = dot(ro, ro) - R * R;
    float h = b * b - c;
    if (h > 0.0) {
        tS = -b - sqrt(h);
        vec3 pos = ro + rd * tS;
        vec3 n   = pos / R;
        vec3 pn  = cam * n;

        float fres   = pow(1.0 - max(dot(n, -rd), 0.0), 2.8);
        float plasma = fbm(pn * 2.6 + vec3(0.0, 0.0, t * 0.32));
        plasma += 0.35 * fbm(pn * 6.5 - vec3(t * 0.18));
        plasma = plasma * plasma * 1.35;                               // contrast

        vec3 deep  = u_color * 0.03;
        vec3 inner = mix(deep, u_color * 0.85, smoothstep(0.30, 0.95, plasma));
        inner += vec3(1.0) * smoothstep(0.88, 1.15, plasma) * 0.30;   // hot flecks
        float lam = 0.30 + 0.70 * max(dot(n, normalize(vec3(0.4, 0.7, 0.6))), 0.0);
        col += inner * lam;
        col += u_color * fres * 2.10;                                  // fresnel rim
        col += u_color * u_audio * 0.32;                               // voice energy
    }

    // ── Orbital rings (raymarched glowing tori) ────────────────────
    mat3 m1 = rotX(1.05 + 0.25 * sin(t * 0.5)) * rotY(t * (0.55 + u_spin * 1.6));
    mat3 m2 = rotZ(0.85) * rotX(0.55) * rotY(-t * (0.80 + u_spin * 2.2));
    mat3 m3 = rotX(-0.95 + 0.2 * cos(t * 0.4)) * rotY(t * (1.15 + u_spin * 2.8) + 2.1);

    float r1 = R * 1.55;
    float r2 = R * 1.95;
    float r3 = R * 2.35;

    float pulseT = fract(t * 0.55);
    float rp     = R * mix(1.25, 3.0, pulseT);
    float pulseW = u_pulse * (1.0 - pulseT);

    col += u_color * ringGlow(ro, rd, m1, r1, tS, 150.0) * 0.62;
    col += u_color * ringGlow(ro, rd, m2, r2, tS, 175.0) * 0.46;
    col += mix(u_color, vec3(1.0), 0.35) * ringGlow(ro, rd, m3, r3, tS, 200.0) * 0.34;
    if (pulseW > 0.001) {
        col += u_color * ringGlow(ro, rd, rotX(1.35), rp, tS, 80.0) * 0.80 * pulseW;
    }

    // ── Ambient halo around the silhouette ─────────────────────────
    float ds = length(uv) - R * 0.92;
    col += u_color * exp(-max(ds, 0.0) * 8.0) * 0.30;
    col += u_color * exp(-max(ds, 0.0) * 2.2) * 0.05;

    // ── Error strobe ───────────────────────────────────────────────
    col *= 1.0 + u_flash * 0.55 * (0.5 + 0.5 * sin(u_time * 11.0));

    col = clamp(col, 0.0, 1.0);

    // Radial vignette — multiplies alpha to zero at the widget corners so
    // the GL rectangle boundary is never visible against the background.
    float edge = length(uv / (u_res / min(u_res.x, u_res.y)));
    float vignette = 1.0 - smoothstep(0.78, 1.02, edge);
    float alpha = clamp(max(col.r, max(col.g, col.b)) * 1.10, 0.0, 1.0) * vignette;
    gl_FragColor = vec4(col * alpha, alpha);   // premultiplied
}
"""

# (speed, flash, pulse, spin) per status — kept slow for a calm, professional feel
_STATUS_MOTION = {
    "idle":         (0.12, 0.0, 0.0, 0.0),
    "listening":    (0.26, 0.0, 0.0, 0.0),
    "transcribing": (0.38, 0.0, 0.0, 0.15),
    "thinking":     (0.20, 0.0, 0.0, 0.20),
    "speaking":     (0.32, 0.0, 0.5, 0.0),
    "error":        (0.24, 0.8, 0.0, 0.0),
}


def _make_orb_class():
    """Build the QOpenGLWidget subclass lazily so missing GL deps only
    fail inside create_orb_widget(), never at import time."""
    from OpenGL import GL
    from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from PyQt6.QtGui import QVector2D, QVector3D
    import ctypes

    class JarvisOrb3DWidget(QOpenGLWidget):
        def __init__(self, compact: bool = False):
            super().__init__()
            self.compact = compact
            fmt = QSurfaceFormat()
            fmt.setAlphaBufferSize(8)
            fmt.setSamples(2)
            self.setFormat(fmt)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            min_size = 420 if compact else 560
            self.setMinimumSize(min_size, min_size)

            # State — mirrors the 2D orb API
            self.status = "idle"
            self.mode = "wake_phrase"
            self.response_style = "calm"
            self.audio_level = 0.0
            self.speech_detected = False
            self._smooth_audio = 0.0

            self._status_blend = 1.0
            self._prev_color = STATUS_COLORS["idle"]
            self._cur_color = STATUS_COLORS["idle"]

            # Motion params ease toward targets so transitions are smooth
            self._motion = list(_STATUS_MOTION["idle"])
            self._motion_target = list(_STATUS_MOTION["idle"])

            self._t0 = time.perf_counter()
            self._program = None
            self._gl_ok = False

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(40)  # ~25 fps — halves GPU load vs 60 fps

        # ── Public API (same as 2D orb) ────────────────────────────
        def set_status(self, status: str) -> None:
            if status == self.status:
                return
            self._prev_color = self._blended_color()
            self._cur_color = STATUS_COLORS.get(status, STATUS_COLORS["idle"])
            self._status_blend = 0.0
            self.status = status
            self._motion_target = list(_STATUS_MOTION.get(status, _STATUS_MOTION["idle"]))

        def set_response_style(self, style: str) -> None:
            self.response_style = style

        def set_audio_level(self, level: float, speech_detected: bool, mode: str) -> None:
            self.audio_level = max(0.0, min(level * 12.0, 1.0))
            self.speech_detected = speech_detected
            self.mode = mode

        # ── Internals ──────────────────────────────────────────────
        def _blended_color(self) -> QColor:
            return _mix_colors(self._prev_color, self._cur_color, self._status_blend)

        def _tick(self) -> None:
            self._smooth_audio += (self.audio_level - self._smooth_audio) * 0.05
            if self._status_blend < 1.0:
                self._status_blend = min(1.0, self._status_blend + 0.025)
            for i in range(4):
                self._motion[i] += (self._motion_target[i] - self._motion[i]) * 0.045
            self.update()

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)

        # ── OpenGL ─────────────────────────────────────────────────
        def initializeGL(self) -> None:
            try:
                program = QOpenGLShaderProgram(self)
                if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VERT):
                    raise RuntimeError(program.log())
                if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, _FRAG):
                    raise RuntimeError(program.log())
                program.bindAttributeLocation("a_pos", 0)
                if not program.link():
                    raise RuntimeError(program.log())
                self._program = program
                quad = (ctypes.c_float * 8)(-1, -1, 1, -1, -1, 1, 1, 1)
                self._quad = quad
                self._gl_ok = True
            except Exception:
                self._program = None
                self._gl_ok = False

        def paintGL(self) -> None:
            painter = QPainter(self)
            painter.beginNativePainting()
            try:
                GL.glClearColor(0.0, 0.0, 0.0, 0.0)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT)
                if self._gl_ok and self._program is not None:
                    try:
                        self._draw_scene()
                    except Exception:
                        self._gl_ok = False
                GL.glDisable(GL.GL_BLEND)
            finally:
                painter.endNativePainting()

            self._draw_labels(painter)
            painter.end()

        def _draw_scene(self) -> None:
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)

            prog = self._program
            prog.bind()
            color = self._blended_color()
            dpr = self.devicePixelRatioF()
            prog.setUniformValue("u_res", QVector2D(self.width() * dpr, self.height() * dpr))
            prog.setUniformValue("u_time", float(time.perf_counter() - self._t0))
            prog.setUniformValue(
                "u_color",
                QVector3D(color.redF(), color.greenF(), color.blueF()),
            )
            prog.setUniformValue("u_audio", float(self._smooth_audio))
            prog.setUniformValue("u_speed", float(self._motion[0]))
            prog.setUniformValue("u_flash", float(self._motion[1]))
            prog.setUniformValue("u_pulse", float(self._motion[2]))
            prog.setUniformValue("u_spin", float(self._motion[3]))

            GL.glEnableVertexAttribArray(0)
            GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, self._quad)
            GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
            GL.glDisableVertexAttribArray(0)
            prog.release()

        def _draw_labels(self, painter: QPainter) -> None:
            pass

    return JarvisOrb3DWidget


def create_orb_widget(compact: bool = False):
    """Return the 3D GPU orb, or the legacy 2D orb if OpenGL is unavailable."""
    try:
        cls = _make_orb_class()
        return cls(compact=compact)
    except Exception:
        from jarvis.ui.orb_widgets import JarvisOrbWidget
        return JarvisOrbWidget(compact=compact)
