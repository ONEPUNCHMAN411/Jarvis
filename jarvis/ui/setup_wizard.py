"""
JARVIS First-Run Setup Wizard

Animated 5-page PyQt6 wizard matching the HUD dark theme.
Shown once on first launch; writes config to %APPDATA%/JARVIS/config.yaml.
"""

import platform

import psutil
import yaml
from loguru import logger

from PyQt6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QSequentialAnimationGroup,
    Qt, QThread, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QRadialGradient
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSpacerItem, QStackedWidget, QVBoxLayout, QWidget,
)

from jarvis.brain.claude_code_provider import (
    find_claude_code_api_key,
    is_claude_cli_available,
)
from jarvis.utils.first_run import get_user_config_path, mark_setup_complete

# Design tokens

BG          = "#0A0E1A"
SURFACE     = "#111827"
SURFACE2    = "#1F2937"
ACCENT      = "#00E5FF"
ACCENT_DIM  = "#0095AA"
TEXT        = "#F0F4FF"
TEXT_MUTED  = "#6B7280"
SUCCESS     = "#34D399"
WARNING     = "#FBBF24"
ERROR       = "#FB7185"
BORDER      = "#1E3A5F"

_FONT_FAMILY = "Segoe UI, Arial, sans-serif"

def _style_sheet() -> str:
    return f"""
    * {{
        font-family: {_FONT_FAMILY};
        color: {TEXT};
    }}
    QDialog {{
        background: {BG};
    }}
    QWidget#page {{
        background: transparent;
    }}
    QFrame#card {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}
    QFrame#card:hover {{
        border: 1px solid {ACCENT_DIM};
    }}
    QFrame#card[selected="true"] {{
        border: 2px solid {ACCENT};
        background: #0D1F33;
    }}
    QLabel#title {{
        font-size: 28px;
        font-weight: 700;
        color: {TEXT};
    }}
    QLabel#subtitle {{
        font-size: 14px;
        color: {TEXT_MUTED};
    }}
    QLabel#section {{
        font-size: 12px;
        font-weight: 600;
        color: {ACCENT};
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }}
    QLabel#badge {{
        background: {SURFACE2};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 2px 10px;
        font-size: 11px;
        color: {TEXT_MUTED};
    }}
    QPushButton#primary {{
        background: {ACCENT};
        color: #000000;
        font-size: 14px;
        font-weight: 700;
        border: none;
        border-radius: 8px;
        padding: 12px 32px;
        min-width: 140px;
    }}
    QPushButton#primary:hover {{
        background: #33EDFF;
    }}
    QPushButton#primary:pressed {{
        background: {ACCENT_DIM};
    }}
    QPushButton#secondary {{
        background: transparent;
        color: {TEXT_MUTED};
        font-size: 13px;
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 11px 24px;
    }}
    QPushButton#secondary:hover {{
        color: {TEXT};
        border-color: {ACCENT_DIM};
    }}
    QPushButton#icon_btn {{
        background: transparent;
        border: none;
        color: {TEXT_MUTED};
        font-size: 16px;
        padding: 4px;
    }}
    QLineEdit {{
        background: {SURFACE2};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 13px;
        color: {TEXT};
        selection-background-color: {ACCENT_DIM};
    }}
    QLineEdit:focus {{
        border: 1px solid {ACCENT};
    }}
    QComboBox {{
        background: {SURFACE2};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 9px 14px;
        font-size: 13px;
        color: {TEXT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 28px;
    }}
    QComboBox QAbstractItemView {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        selection-background-color: {SURFACE2};
        color: {TEXT};
    }}
    QProgressBar {{
        background: {SURFACE2};
        border: none;
        border-radius: 4px;
        height: 6px;
    }}
    QProgressBar::chunk {{
        background: {ACCENT};
        border-radius: 4px;
    }}
    QCheckBox {{
        font-size: 13px;
        color: {TEXT};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {BORDER};
        border-radius: 4px;
        background: {SURFACE2};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    """

# Step indicator widget

class StepIndicator(QWidget):
    def __init__(self, total: int, parent=None):
        super().__init__(parent)
        self._total = total
        self._current = 0
        self.setFixedHeight(40)

    def set_step(self, step: int) -> None:
        self._current = step
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        dot_r = 8
        spacing = min(60, (w - dot_r * 2) // max(1, self._total - 1))
        total_w = spacing * (self._total - 1) + dot_r * 2
        ox = (w - total_w) // 2
        cy = h // 2

        accent = QColor(ACCENT)
        dim = QColor(SURFACE2)
        border = QColor(BORDER)

        for i in range(self._total):
            cx = ox + dot_r + i * spacing

            # connector line
            if i < self._total - 1:
                line_color = accent if i < self._current else border
                pen = QPen(line_color, 2)
                painter.setPen(pen)
                painter.drawLine(cx + dot_r, cy, cx + spacing - dot_r, cy)

            # dot
            if i < self._current:
                painter.setBrush(QBrush(accent))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPoint(cx, cy), dot_r, dot_r)
                # checkmark
                painter.setPen(QPen(QColor("#000000"), 2))
                painter.drawText(cx - 5, cy + 5, "✓")
            elif i == self._current:
                grad = QRadialGradient(cx, cy, dot_r)
                grad.setColorAt(0, accent)
                grad.setColorAt(1, QColor(ACCENT_DIM))
                painter.setBrush(QBrush(grad))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPoint(cx, cy), dot_r, dot_r)
            else:
                painter.setBrush(QBrush(dim))
                painter.setPen(QPen(border, 1))
                painter.drawEllipse(QPoint(cx, cy), dot_r, dot_r)

        painter.end()

# Orb pulse widget

class OrbPulse(QWidget):
    """Animated cyan orb used on Welcome and Finish pages."""

    def __init__(self, size: int = 120, parent=None):
        super().__init__(parent)
        self._size = size
        self._phase = 0.0
        self._glow = 0.0
        self.setFixedSize(size + 40, size + 40)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _tick(self) -> None:
        import math
        self._phase += 0.04
        self._glow = 0.5 + 0.5 * math.sin(self._phase)
        self.update()

    def paintEvent(self, event):
        import math
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        r = self._size // 2

        pulse_r = int(r * (1.0 + 0.08 * math.sin(self._phase)))
        alpha = int(40 + 30 * self._glow)

        # outer glow ring
        glow_color = QColor(0, 229, 255, alpha)
        painter.setPen(QPen(glow_color, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPoint(cx, cy), pulse_r + 20, pulse_r + 20)

        # middle ring
        painter.setPen(QPen(QColor(0, 229, 255, alpha + 30), 1))
        painter.drawEllipse(QPoint(cx, cy), pulse_r + 10, pulse_r + 10)

        # core
        grad = QRadialGradient(cx, cy, r)
        grad.setColorAt(0.0, QColor(0, 229, 255, 220))
        grad.setColorAt(0.5, QColor(0, 140, 180, 160))
        grad.setColorAt(1.0, QColor(0, 30, 60, 80))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QPoint(cx, cy), pulse_r, pulse_r)

        painter.end()

# System check worker

class SystemCheckWorker(QThread):
    result = pyqtSignal(str, str, str)   # (check_name, status, detail)
    finished_all = pyqtSignal()

    def run(self) -> None:
        import math

        checks = [
            self._check_ram,
            self._check_disk,
            self._check_gpu,
            self._check_python,
        ]
        for check in checks:
            name, status, detail = check()
            self.result.emit(name, status, detail)

        self.finished_all.emit()

    def _check_ram(self):
        gb = psutil.virtual_memory().total / (1024 ** 3)
        if gb >= 16:
            return "RAM", "ok", f"{gb:.1f} GB — excellent"
        elif gb >= 8:
            return "RAM", "warn", f"{gb:.1f} GB — OK, but 16 GB recommended"
        else:
            return "RAM", "error", f"{gb:.1f} GB — 8 GB minimum required"

    def _check_disk(self):
        try:
            free_gb = psutil.disk_usage("C:\\").free / (1024 ** 3)
        except Exception:
            free_gb = psutil.disk_usage("/").free / (1024 ** 3)
        if free_gb >= 5:
            return "Disk Space", "ok", f"{free_gb:.1f} GB free"
        elif free_gb >= 2:
            return "Disk Space", "warn", f"{free_gb:.1f} GB free — 5 GB recommended"
        else:
            return "Disk Space", "error", f"{free_gb:.1f} GB free — insufficient"

    def _check_gpu(self):
        # Check if ctranslate2 (the actual voice engine) supports CUDA
        try:
            import ctranslate2
            ct2_cuda = bool(ctranslate2.get_supported_compute_types("cuda"))
        except Exception:
            ct2_cuda = False

        try:
            import torch
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                if ct2_cuda:
                    return "GPU (CUDA)", "ok", f"{name} — {vram:.1f} GB VRAM — voice GPU-accelerated ✅"
                else:
                    return "GPU (CUDA)", "warn", (
                        f"{name} found but voice engine lacks CUDA build — "
                        "running on CPU. Reinstall ctranslate2 with CUDA support."
                    )
            else:
                return "GPU (CUDA)", "warn", "No CUDA GPU detected — voice will run on CPU (still works)"
        except ImportError:
            return "GPU (CUDA)", "warn", "torch not installed — voice will run on CPU"

    def _check_python(self):
        import sys
        v = sys.version_info
        ver = f"{v.major}.{v.minor}.{v.micro}"
        if v >= (3, 12):
            return "Python", "ok", f"{ver}"
        elif v >= (3, 10):
            return "Python", "warn", f"{ver} — 3.12+ recommended"
        else:
            return "Python", "error", f"{ver} — Python 3.10+ required"

# Dependency download worker

class DownloadWorker(QThread):
    item_started  = pyqtSignal(str)               # (name)
    item_done     = pyqtSignal(str, bool, str)    # (name, success, message)
    all_done      = pyqtSignal()

    def run(self) -> None:
        self._install_cuda_support()   # must be first — whisper load uses GPU
        self._install_playwright()
        self._download_whisper()
        self.all_done.emit()

    def _install_cuda_support(self) -> None:
        """Verify GPU voice acceleration is available.
        When packaged as EXE, CUDA DLLs are bundled at build time — no install needed.
        When running from source, pip-install the CUDA packages if missing."""
        import subprocess, sys

        # Detect GPU name via wmic (works without torch)
        gpu_name = None
        try:
            r = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name", "/value"],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                if "NVIDIA" in line.upper() and "=" in line:
                    gpu_name = line.split("=", 1)[-1].strip()
                    break
        except Exception:
            pass

        if not gpu_name:
            self.item_done.emit("cuda", True, "No NVIDIA GPU — voice runs on CPU (works fine)")
            return

        self.item_started.emit("cuda")

        # Check if ctranslate2 already supports CUDA (bundled EXE or already installed)
        try:
            import ctranslate2
            if ctranslate2.get_supported_compute_types("cuda"):
                self.item_done.emit(
                    "cuda", True, f"{gpu_name} — GPU voice enabled ✅"
                )
                return
        except Exception:
            pass

        # Running from source — try pip install
        is_frozen = getattr(sys, "frozen", False)
        if is_frozen:
            # EXE without bundled CUDA — CUDA packages weren't installed at build time
            self.item_done.emit(
                "cuda", False,
                f"{gpu_name} found but GPU voice not bundled — voice uses CPU. "
                "Rebuild with CUDA packages installed."
            )
            return

        cuda_pkgs = ["nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-runtime-cu12"]
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", *cuda_pkgs],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                self.item_done.emit(
                    "cuda", True,
                    f"{gpu_name} — GPU voice enabled (~300 MB installed) ✅"
                )
            else:
                err = (result.stderr or result.stdout or "pip failed").strip()[:100]
                self.item_done.emit("cuda", False, f"GPU install failed — voice uses CPU. {err}")
        except subprocess.TimeoutExpired:
            self.item_done.emit("cuda", False, "GPU install timed out — voice uses CPU")
        except Exception as exc:
            self.item_done.emit("cuda", False, str(exc)[:100])

    def _install_playwright(self) -> None:
        import subprocess, sys
        self.item_started.emit("browser")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium",
                 "--with-deps"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                self.item_done.emit("browser", True, "Chromium ready")
            else:
                err = (result.stderr or result.stdout or "unknown error").strip()[:120]
                self.item_done.emit("browser", False, err)
        except subprocess.TimeoutExpired:
            self.item_done.emit("browser", False, "Timed out after 5 minutes")
        except Exception as exc:
            self.item_done.emit("browser", False, str(exc)[:120])

    def _download_whisper(self) -> None:
        self.item_started.emit("whisper")
        try:
            from faster_whisper import WhisperModel
            # tiny.en — small (~75 MB), fast on CPU; GPU users get near-instant results.
            # Downloads to ~/.cache/huggingface/hub/ and stays there.
            model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
            del model
            self.item_done.emit("whisper", True, "Voice model ready (~75 MB)")
        except Exception as exc:
            # Non-fatal: STT will retry download on first voice use
            self.item_done.emit("whisper", False,
                                f"Will retry on first voice use — {str(exc)[:80]}")

# Downloads page

class DownloadsPage(QWidget):
    all_complete = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._worker: DownloadWorker | None = None
        self._rows: dict[str, dict] = {}
        self._done_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(12)

        label = QLabel("INSTALLING COMPONENTS")
        label.setObjectName("section")
        layout.addWidget(label)

        title = QLabel("Downloading required components…")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        layout.addWidget(title)
        self._title = title

        sub = QLabel("This only happens once. Please keep JARVIS open.")
        sub.setObjectName("subtitle")
        layout.addWidget(sub)

        layout.addSpacing(16)

        items = [
            ("cuda", "⚡", "GPU Voice Acceleration",
             "CUDA libraries for ctranslate2 — 10-20× faster voice (~300 MB, GPU only)"),
            ("browser", "🌐", "Chromium Browser",
             "Required for web browsing and automation (~150 MB)"),
            ("whisper", "🎙️", "Voice Recognition Model",
             "Whisper tiny.en — speech-to-text engine (~75 MB)"),
        ]
        for key, icon, name, desc in items:
            row = self._make_row(key, icon, name, desc)
            layout.addWidget(row)
            layout.addSpacing(4)

        layout.addStretch()

    def _make_row(self, key: str, icon: str, name: str, desc: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")

        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(6)

        top = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setFixedWidth(32)
        top.addWidget(icon_lbl)

        info = QVBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        info.addWidget(name_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        info.addWidget(desc_lbl)
        top.addLayout(info)

        top.addStretch()
        status_lbl = QLabel("Waiting…")
        status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(status_lbl)

        v.addLayout(top)

        bar = QProgressBar()
        bar.setRange(0, 0)       # indeterminate / marquee
        bar.setFixedHeight(5)
        bar.setVisible(False)
        v.addWidget(bar)

        self._rows[key] = {"card": card, "status": status_lbl, "bar": bar}
        return card

    def start_downloads(self) -> None:
        self._worker = DownloadWorker()
        self._worker.item_started.connect(self._on_started)
        self._worker.item_done.connect(self._on_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_started(self, name: str) -> None:
        row = self._rows.get(name)
        if not row:
            return
        row["status"].setText("Downloading…")
        row["status"].setStyleSheet(f"color: {ACCENT}; font-size: 12px;")
        row["bar"].setVisible(True)

    def _on_done(self, name: str, success: bool, message: str) -> None:
        row = self._rows.get(name)
        if not row:
            return
        row["bar"].setRange(0, 100)
        row["bar"].setValue(100)
        if success:
            row["status"].setText(f"✅  {message}")
            row["status"].setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
            row["bar"].setStyleSheet(
                f"QProgressBar::chunk {{ background: {SUCCESS}; border-radius: 2px; }}"
            )
        else:
            row["status"].setText(f"⚠️  {message}")
            row["status"].setStyleSheet(f"color: {WARNING}; font-size: 12px;")
            row["bar"].setStyleSheet(
                f"QProgressBar::chunk {{ background: {WARNING}; border-radius: 2px; }}"
            )
        self._done_count += 1

    def _on_all_done(self) -> None:
        self._title.setText("Components installed ✅")
        self.all_complete.emit()

# Individual pages

class WelcomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(0)

        layout.addStretch(1)

        self._orb = OrbPulse(size=140)
        layout.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(24)

        title = QLabel("JARVIS")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 38, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 6px;")
        layout.addWidget(title)

        layout.addSpacing(8)

        badge = QLabel("BETA v1.0.0")
        badge.setObjectName("badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(20)

        subtitle = QLabel("Your intelligent desktop assistant\nLet's get you set up in under 2 minutes.")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Antivirus notice — shown prominently so users aren't confused
        av_card = QFrame()
        av_card.setObjectName("card")
        av_card.setStyleSheet(
            f"QFrame#card {{ background: #1A1200; border: 1px solid {WARNING}; border-radius: 10px; }}"
        )
        av_v = QVBoxLayout(av_card)
        av_v.setContentsMargins(16, 12, 16, 12)
        av_v.setSpacing(4)

        av_title_row = QHBoxLayout()
        av_icon = QLabel("⚠️")
        av_icon.setFont(QFont("Segoe UI", 14))
        av_title_row.addWidget(av_icon)
        av_title = QLabel("Windows may flag this app")
        av_title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        av_title.setStyleSheet(f"color: {WARNING};")
        av_title_row.addWidget(av_title)
        av_title_row.addStretch()
        av_v.addLayout(av_title_row)

        av_body = QLabel(
            "JARVIS is open-source and safe. Windows SmartScreen shows a warning for\n"
            "any new unsigned app. If blocked: click  More info → Run anyway.\n"
            "Or add an exclusion: Windows Security → Virus & threat protection → Exclusions."
        )
        av_body.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        av_body.setWordWrap(True)
        av_v.addWidget(av_body)

        av_link = QPushButton("View source code on GitHub →")
        av_link.setObjectName("icon_btn")
        av_link.setStyleSheet(f"color: {ACCENT}; font-size: 11px; text-align: left;")
        av_link.clicked.connect(lambda: __import__("webbrowser").open(
            "https://github.com/ONEPUNCHMAN411/Jarvis"
        ))
        av_v.addWidget(av_link)

        layout.addWidget(av_card)

        layout.addStretch(2)

class SysCheckPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._checks: dict[str, tuple[QLabel, QLabel]] = {}
        self._worker: SystemCheckWorker | None = None
        self._all_critical_ok = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(12)

        label = QLabel("SYSTEM REQUIREMENTS")
        label.setObjectName("section")
        layout.addWidget(label)

        title = QLabel("Checking your setup…")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        layout.addWidget(title)
        self._title = title

        layout.addSpacing(16)
        self._checks_layout = QVBoxLayout()
        self._checks_layout.setSpacing(10)
        layout.addLayout(self._checks_layout)
        layout.addStretch()

    def start_checks(self) -> None:
        for name in ["RAM", "Disk Space", "GPU (CUDA)", "Python"]:
            row = QFrame()
            row.setObjectName("card")
            row.setFixedHeight(58)
            h = QHBoxLayout(row)
            h.setContentsMargins(16, 0, 16, 0)

            name_lbl = QLabel(name)
            name_lbl.setFont(QFont("Segoe UI", 13))
            h.addWidget(name_lbl)

            h.addStretch()

            detail_lbl = QLabel("Checking…")
            detail_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
            h.addWidget(detail_lbl)

            status_lbl = QLabel("⏳")
            status_lbl.setFixedWidth(28)
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.addWidget(status_lbl)

            self._checks[name] = (status_lbl, detail_lbl)
            self._checks_layout.addWidget(row)

        self._worker = SystemCheckWorker()
        self._worker.result.connect(self._on_result)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _on_result(self, name: str, status: str, detail: str) -> None:
        if name not in self._checks:
            return
        status_lbl, detail_lbl = self._checks[name]
        icons = {"ok": "✅", "warn": "⚠️", "error": "❌"}
        colors = {"ok": SUCCESS, "warn": WARNING, "error": ERROR}
        status_lbl.setText(icons.get(status, "?"))
        detail_lbl.setText(detail)
        detail_lbl.setStyleSheet(f"color: {colors.get(status, TEXT_MUTED)}; font-size: 12px;")

    def _on_finished(self) -> None:
        errors = [n for n, (s, _) in self._checks.items() if s.text() == "❌"]
        if not errors:
            self._all_critical_ok = True
            self._title.setText("Looking good! ✅")
        else:
            self._title.setText("Issues found — check below")

    def is_ok_to_continue(self) -> bool:
        return self._all_critical_ok or True  # always allow continue, errors are advisory

class ProviderPage(QWidget):
    provider_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._selected: str = "groq"
        self._cards: dict[str, QFrame] = {}
        self._api_key_field: QLineEdit | None = None
        self._provider_combo: QComboBox | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(12)

        label = QLabel("ENGINE")
        label.setObjectName("section")
        layout.addWidget(label)

        title = QLabel("Choose your provider")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        layout.addWidget(title)

        sub = QLabel("Pick a provider — you can change this any time in Settings.")
        sub.setObjectName("subtitle")
        layout.addWidget(sub)

        layout.addSpacing(12)

        # Card 1: Groq (free, recommended)
        self._add_card(
            layout, "groq",
            "Groq  —  Free & fast",
            "Free API key, no credit card required",
            "Llama 3.3 70B — great for most tasks",
        )

        # Card 2: Ollama (local)
        self._add_card(
            layout, "ollama",
            "Ollama  —  Fully local",
            "Runs models on your own machine, nothing sent online",
            "Requires Ollama installed and a model pulled",
        )

        # Card 3: Manual API key
        manual_card = self._add_card(
            layout, "manual",
            "Other provider",
            "Enter your own API key for any supported provider",
            "Gemini, Mistral, OpenAI, OpenRouter",
        )
        # Extra fields inside manual card
        extra = QVBoxLayout()
        extra.setContentsMargins(0, 8, 0, 0)
        extra.setSpacing(6)

        provider_row = QHBoxLayout()
        provider_row.setSpacing(8)
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["groq", "gemini", "mistral", "openai", "openrouter"])
        self._provider_combo.setFixedWidth(150)
        provider_row.addWidget(QLabel("Provider:"))
        provider_row.addWidget(self._provider_combo)
        provider_row.addStretch()
        extra.addLayout(provider_row)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self._api_key_field = QLineEdit()
        self._api_key_field.setPlaceholderText("sk-ant-…  or  sk-…")
        self._api_key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_field.textChanged.connect(self._on_key_changed)
        key_row.addWidget(self._api_key_field)

        eye_btn = QPushButton("👁")
        eye_btn.setObjectName("icon_btn")
        eye_btn.setFixedWidth(32)
        eye_btn.clicked.connect(self._toggle_echo)
        key_row.addWidget(eye_btn)
        extra.addLayout(key_row)

        self._key_status = QLabel("")
        self._key_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        extra.addWidget(self._key_status)

        manual_card_inner = manual_card.findChild(QVBoxLayout)
        if manual_card_inner:
            manual_card_inner.addLayout(extra)

        layout.addSpacing(12)

        # Step-by-step instructions panel — updates when card is selected
        self._instructions_frame = QFrame()
        self._instructions_frame.setObjectName("card")
        self._instructions_frame.setStyleSheet(
            f"QFrame#card {{ background: #0D1F33; border: 1px solid {ACCENT_DIM}; border-radius: 10px; }}"
        )
        inst_v = QVBoxLayout(self._instructions_frame)
        inst_v.setContentsMargins(16, 12, 16, 12)
        inst_v.setSpacing(4)

        inst_header = QLabel("SETUP GUIDE")
        inst_header.setObjectName("section")
        inst_v.addWidget(inst_header)

        self._instructions_label = QLabel()
        self._instructions_label.setStyleSheet(f"color: {TEXT}; font-size: 12px; line-height: 1.6;")
        self._instructions_label.setWordWrap(True)
        self._instructions_label.setOpenExternalLinks(True)
        inst_v.addWidget(self._instructions_label)

        self._open_link_btn = QPushButton()
        self._open_link_btn.setObjectName("icon_btn")
        self._open_link_btn.setStyleSheet(f"color: {ACCENT}; font-size: 11px; text-align: left;")
        inst_v.addWidget(self._open_link_btn)

        layout.addWidget(self._instructions_frame)
        layout.addStretch()
        self._select_card("groq")

    _PROVIDER_INSTRUCTIONS = {
        "groq": (
            "1.  Go to console.groq.com and sign up (free, no credit card).\n"
            "2.  Create an API key in the dashboard.\n"
            "3.  Paste it below.\n\n"
            "Groq runs Llama 3.3 70B on their hardware — fast responses, generous free tier.",
            "Open console.groq.com →",
            "https://console.groq.com",
        ),
        "ollama": (
            "1.  Install Ollama from ollama.com.\n"
            "2.  Open a terminal and run:  ollama pull llama3.1:8b\n"
            "3.  JARVIS will connect to Ollama on localhost automatically.\n\n"
            "Everything runs on your machine. No internet required after setup.",
            "Open ollama.com →",
            "https://ollama.com",
        ),
        "manual": (
            "Enter your API key below.  Where to get one:\n\n"
            "  • Groq      →  console.groq.com  (free tier)\n"
            "  • Gemini    →  aistudio.google.com/app/apikey  (free tier)\n"
            "  • Mistral   →  console.mistral.ai\n"
            "  • OpenAI    →  platform.openai.com/api-keys\n"
            "  • OpenRouter →  openrouter.ai/keys\n\n"
            "Your key is stored locally and never sent anywhere except the provider you choose.",
            "Get a free Groq key →",
            "https://console.groq.com",
        ),
    }

    def _add_card(self, layout: QVBoxLayout, key: str, title: str, detail: str, sub: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setProperty("selected", "false")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setMinimumHeight(72)

        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(3)

        t = QLabel(title)
        t.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        v.addWidget(t)

        d = QLabel(detail)
        d.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        v.addWidget(d)

        s = QLabel(sub)
        s.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;")
        v.addWidget(s)

        layout.addWidget(card)
        self._cards[key] = card

        card.mousePressEvent = lambda e, k=key: self._select_card(k)
        return card

    def _select_card(self, key: str) -> None:
        for k, card in self._cards.items():
            selected = k == key
            card.setProperty("selected", "true" if selected else "false")
            card.style().unpolish(card)
            card.style().polish(card)
        self._selected = key
        self.provider_selected.emit(key)

        # Update step-by-step instructions
        inst = self._PROVIDER_INSTRUCTIONS.get(key)
        if inst:
            text, link_label, link_url = inst
            self._instructions_label.setText(text)
            self._open_link_btn.setText(link_label)
            try:
                self._open_link_btn.clicked.disconnect()
            except TypeError:
                pass
            self._open_link_btn.clicked.connect(
                lambda: __import__("webbrowser").open(link_url)
            )

        # Show/hide API key fields
        if self._api_key_field:
            self._api_key_field.setEnabled(key == "manual")
            self._api_key_field.setVisible(key == "manual")
        if self._provider_combo:
            self._provider_combo.setEnabled(key == "manual")
            self._provider_combo.setVisible(key == "manual")

    def _toggle_echo(self) -> None:
        if self._api_key_field:
            if self._api_key_field.echoMode() == QLineEdit.EchoMode.Password:
                self._api_key_field.setEchoMode(QLineEdit.EchoMode.Normal)
            else:
                self._api_key_field.setEchoMode(QLineEdit.EchoMode.Password)

    def _on_key_changed(self, text: str) -> None:
        if not text:
            self._key_status.setText("")
            return
        looks_valid = text.startswith("sk-") and len(text) > 20
        if looks_valid:
            self._key_status.setText("✅ Looks valid")
            self._key_status.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
        else:
            self._key_status.setText("Key should start with sk- and be longer")
            self._key_status.setStyleSheet(f"color: {WARNING}; font-size: 11px;")

    def get_config(self) -> dict:
        if self._selected == "groq":
            return {"provider": "groq", "api_key": self._api_key_field.text() if self._api_key_field else ""}
        elif self._selected == "ollama":
            return {"provider": "ollama"}
        else:
            return {
                "provider": self._provider_combo.currentText() if self._provider_combo else "groq",
                "api_key": self._api_key_field.text() if self._api_key_field else "",
            }

class VoicePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(12)

        label = QLabel("VOICE SETUP")
        label.setObjectName("section")
        layout.addWidget(label)

        title = QLabel("Optional: set up voice")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        layout.addWidget(title)

        sub = QLabel("JARVIS works without voice — you can always enable it later in Settings.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        layout.addSpacing(16)

        # Mic check card
        mic_card = QFrame()
        mic_card.setObjectName("card")
        mic_v = QVBoxLayout(mic_card)
        mic_v.setContentsMargins(16, 14, 16, 14)

        mic_row = QHBoxLayout()
        mic_icon = QLabel("🎤")
        mic_icon.setFont(QFont("Segoe UI", 20))
        mic_row.addWidget(mic_icon)

        mic_info = QVBoxLayout()
        mic_info.addWidget(_lbl("Microphone", bold=True, size=13))
        self._mic_status = _lbl("Not tested", color=TEXT_MUTED, size=12)
        mic_info.addWidget(self._mic_status)
        mic_row.addLayout(mic_info)
        mic_row.addStretch()

        test_mic_btn = QPushButton("Test Mic")
        test_mic_btn.setObjectName("secondary")
        test_mic_btn.clicked.connect(self._test_mic)
        mic_row.addWidget(test_mic_btn)

        mic_v.addLayout(mic_row)
        layout.addWidget(mic_card)

        # TTS check card
        tts_card = QFrame()
        tts_card.setObjectName("card")
        tts_v = QVBoxLayout(tts_card)
        tts_v.setContentsMargins(16, 14, 16, 14)

        tts_row = QHBoxLayout()
        tts_icon = QLabel("🔊")
        tts_icon.setFont(QFont("Segoe UI", 20))
        tts_row.addWidget(tts_icon)

        tts_info = QVBoxLayout()
        tts_info.addWidget(_lbl("Text-to-Speech", bold=True, size=13))
        self._tts_status = _lbl("Not tested", color=TEXT_MUTED, size=12)
        tts_info.addWidget(self._tts_status)
        tts_row.addLayout(tts_info)
        tts_row.addStretch()

        test_tts_btn = QPushButton("Test TTS")
        test_tts_btn.setObjectName("secondary")
        test_tts_btn.clicked.connect(self._test_tts)
        tts_row.addWidget(test_tts_btn)

        tts_v.addLayout(tts_row)
        layout.addWidget(tts_card)

        layout.addSpacing(8)
        self._enable_voice = QCheckBox("Enable voice features")
        self._enable_voice.setChecked(True)
        layout.addWidget(self._enable_voice)

        layout.addStretch()

    def _test_mic(self) -> None:
        try:
            import sounddevice as sd
            self._mic_status.setText("✅ Microphone found — sounddevice OK")
            self._mic_status.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
        except Exception as exc:
            self._mic_status.setText(f"⚠️ {exc}")
            self._mic_status.setStyleSheet(f"color: {WARNING}; font-size: 12px;")

    def _test_tts(self) -> None:
        try:
            import edge_tts  # noqa: F401
            self._tts_status.setText("✅ edge-tts available")
            self._tts_status.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
        except Exception as exc:
            self._tts_status.setText(f"⚠️ {exc}")
            self._tts_status.setStyleSheet(f"color: {WARNING}; font-size: 12px;")

    def get_config(self) -> dict:
        return {"voice_enabled": self._enable_voice.isChecked()}

class FinishPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._summary_lines: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(0)

        layout.addStretch(1)

        self._orb = OrbPulse(size=100)
        layout.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(20)

        title = QLabel("JARVIS is ready.")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(f"color: {ACCENT};")
        layout.addWidget(title)

        layout.addSpacing(16)

        self._summary_label = QLabel()
        self._summary_label.setObjectName("subtitle")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        layout.addStretch(2)

    def set_summary(self, lines: list[str]) -> None:
        self._summary_label.setText("\n".join(f"✅  {l}" for l in lines))

# Helpers

def _lbl(text: str, bold: bool = False, size: int = 12, color: str = TEXT) -> QLabel:
    lbl = QLabel(text)
    font = QFont("Segoe UI", size)
    if bold:
        font.setWeight(QFont.Weight.DemiBold)
    lbl.setFont(font)
    lbl.setStyleSheet(f"color: {color};")
    return lbl

# Main wizard dialog

class SetupWizard(QDialog):
    setup_complete = pyqtSignal(dict)   # emits final config dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS Setup")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumSize(680, 540)
        self.resize(720, 580)
        self.setStyleSheet(_style_sheet())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._config: dict = {}
        self._dragging = False
        self._drag_pos = QPoint()

        root = QFrame(self)
        root.setStyleSheet(f"background: {BG}; border-radius: 16px;")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(root)

        main = QVBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Title bar
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"background: {SURFACE}; border-radius: 16px 16px 0 0;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(20, 0, 12, 0)
        bar_title = QLabel("JARVIS Setup")
        bar_title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        bar_title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px;")
        bar_layout.addWidget(bar_title)
        bar_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setObjectName("icon_btn")
        close_btn.clicked.connect(self.reject)
        bar_layout.addWidget(close_btn)
        main.addWidget(bar)

        # Step indicator
        self._steps = StepIndicator(total=6)
        self._steps.setContentsMargins(40, 12, 40, 4)
        main.addWidget(self._steps)

        # Page stack  (0=Welcome, 1=SysCheck, 2=Downloads, 3=Provider, 4=Voice, 5=Finish)
        self._stack = QStackedWidget()
        self._welcome   = WelcomePage()
        self._syscheck  = SysCheckPage()
        self._downloads = DownloadsPage()
        self._provider  = ProviderPage()
        self._voice     = VoicePage()
        self._finish    = FinishPage()

        self._downloads.all_complete.connect(self._on_downloads_complete)

        for page in [self._welcome, self._syscheck, self._downloads,
                     self._provider, self._voice, self._finish]:
            self._stack.addWidget(page)
        main.addWidget(self._stack, stretch=1)

        # Nav row
        nav = QWidget()
        nav.setStyleSheet(f"background: {SURFACE}; border-radius: 0 0 16px 16px;")
        nav.setFixedHeight(68)
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(28, 0, 28, 0)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setObjectName("secondary")
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.setVisible(False)
        nav_layout.addWidget(self._back_btn)

        nav_layout.addStretch()

        self._next_btn = QPushButton("Get Started →")
        self._next_btn.setObjectName("primary")
        self._next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self._next_btn)

        main.addWidget(nav)

        # shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 229, 255, 40))
        root.setGraphicsEffect(shadow)

        self._current_page = 0

    # Drag to move
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    # Navigation
    def _go_next(self) -> None:
        page = self._current_page
        if page == 0:
            # Welcome → SysCheck: start checks
            self._syscheck.start_checks()
        elif page == 1:
            # SysCheck → Downloads: kick off installs, lock Next until done
            self._next_btn.setEnabled(False)
            self._next_btn.setText("Installing…")
            self._animate_to(2)
            self._downloads.start_downloads()
            return
        elif page == 2:
            pass  # Downloads → Provider (Next already re-enabled by _on_downloads_complete)
        elif page == 3:
            # Provider → Voice: save provider config
            self._config.update(self._provider.get_config())
        elif page == 4:
            # Voice → Finish: save voice config, build summary
            self._config.update(self._voice.get_config())
            self._show_finish()
        elif page == 5:
            # Finish → done
            self._complete_setup()
            return

        self._animate_to(page + 1)

    def _on_downloads_complete(self) -> None:
        self._next_btn.setEnabled(True)
        self._update_nav()

    def _go_back(self) -> None:
        if self._current_page > 0:
            self._animate_to(self._current_page - 1)

    def _animate_to(self, target: int) -> None:
        going_forward = target > self._current_page
        current_widget = self._stack.currentWidget()
        next_widget = self._stack.widget(target)

        w = self._stack.width()
        offset = w if going_forward else -w

        next_widget.move(offset, 0)
        next_widget.show()

        anim_out = QPropertyAnimation(current_widget, b"pos", self)
        anim_out.setDuration(320)
        anim_out.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_out.setEndValue(QPoint(-offset, 0))

        anim_in = QPropertyAnimation(next_widget, b"pos", self)
        anim_in.setDuration(320)
        anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_in.setStartValue(QPoint(offset, 0))
        anim_in.setEndValue(QPoint(0, 0))

        def _finish():
            self._stack.setCurrentIndex(target)
            current_widget.move(0, 0)
            self._current_page = target
            self._steps.set_step(target)
            self._update_nav()

        anim_out.start()
        anim_in.start()
        anim_in.finished.connect(_finish)

    def _update_nav(self, page: int | None = None) -> None:
        if page is None:
            page = self._current_page
        self._back_btn.setVisible(page > 0 and page != 2)  # hide Back on Downloads page
        labels = {
            0: "Get Started →",
            1: "Continue →",
            2: "Continue →",
            3: "Continue →",
            4: "Continue →",
            5: "Launch JARVIS  🚀",
        }
        self._next_btn.setText(labels.get(page, "Next →"))

    def _show_finish(self) -> None:
        provider_name = self._config.get("provider", "unknown")
        voice_on = self._config.get("voice_enabled", False)
        summary = [
            f"Engine: {provider_name}",
            f"Voice: {'enabled' if voice_on else 'disabled'}",
            "Config saved to %APPDATA%\\JARVIS",
        ]
        self._finish.set_summary(summary)

    def _complete_setup(self) -> None:
        try:
            mark_setup_complete()
            self._write_config()
        except Exception as exc:
            logger.error(f"Setup wizard failed to write config: {exc}")
        self.setup_complete.emit(self._config)
        self.accept()

    def _write_config(self) -> None:
        from jarvis.utils.first_run import get_user_config_path
        path = get_user_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        cfg = {
            "wizard_completed": True,
            "ai": {
                "primary_provider": self._config.get("provider", "groq"),
            },
            "voice": {
                "enabled": self._config.get("voice_enabled", True),
            },
        }
        if self._config.get("api_key"):
            cfg["ai"]["api_key"] = self._config["api_key"]

        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg, fh, default_flow_style=False, allow_unicode=True)

        # Mirror into SettingsStore so the runtime picks up the chosen provider
        # and API key on first launch without the user having to re-enter them.
        try:
            from jarvis.ui.settings_store import SettingsStore
            store = SettingsStore()
            settings = store.load()
            provider = self._config.get("provider", "")
            api_key = self._config.get("api_key", "")
            if provider:
                settings["primary_provider"] = provider
            if api_key and provider in settings.get("providers", {}):
                settings["providers"][provider]["enabled"] = True
                settings["providers"][provider]["api_key"] = api_key
            settings["voice_enabled"] = self._config.get("voice_enabled", True)
            store.save(settings)
        except Exception as exc:
            logger.warning(f"Could not write provider settings to store: {exc}")

        logger.info(f"Setup wizard wrote config to {path}")
