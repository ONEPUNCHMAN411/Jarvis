import html as _html
import json
import math
import time as _time
from datetime import datetime
from pathlib import Path

from jarvis.brain.groq_provider import _model_caps as _groq_model_caps
from jarvis.ui.notification_toast import NotificationToast

from loguru import logger
from PyQt6.QtCore import Qt, QUrl, QTimer, QPropertyAnimation, QEasingCurve, QEvent, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPainterPath, QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QDialog,
    QDoubleSpinBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Optional psutil for system resource monitoring
try:
    import psutil as _psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _psutil = None
    _PSUTIL_AVAILABLE = False

from jarvis.ui.orb_overlay_window import OrbOverlayWindow
from jarvis.ui.orb_state import classify_response_style
from jarvis.ui.orb_3d import create_orb_widget
from jarvis.ui.orb_widgets import AnimatedButton, HUDRootWidget, STATUS_COLORS
from jarvis.ui.computer_use_overlay import ComputerUseOverlay
from jarvis.ui.plugin_panels import (
    SpotifyDialog, TodoDialog, NotesDialog, ClipboardDialog,
    WebRemoteDialog, TranslatorDialog, QRDialog, VoiceMemoDialog,
    HabitDialog, AlertDialog, UIBridge,
)
from jarvis.voice.voice_profiles import builtin_voice_profiles, normalize_custom_profile

def _glow_effect(color: str = "#00E5FF", radius: int = 18) -> QGraphicsDropShadowEffect:
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(radius)
    fx.setColor(QColor(color))
    fx.setOffset(0, 0)
    return fx

class ProviderCard(QFrame):
    def __init__(self, provider_name: str, title: str, has_key: bool = True, has_base_url: bool = False):
        super().__init__()
        self.provider_name = provider_name
        self.has_key = has_key
        self.has_base_url = has_base_url
        self._build(title)

    def _build(self, title: str) -> None:
        self.setObjectName("providerCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Card header strip
        header_strip = QFrame()
        header_strip.setFixedHeight(36)
        header_strip.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 rgba(0,200,232,0.09), stop:1 rgba(0,200,232,0.02));"
            "border-bottom: 1px solid rgba(0,200,232,0.10);"
            "border-top-left-radius: 14px; border-top-right-radius: 14px;"
            "border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;"
        )
        h_strip = QHBoxLayout(header_strip)
        h_strip.setContentsMargins(14, 0, 14, 0)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: rgba(148,163,184,0.35); font-size: 10px;")
        h_strip.addWidget(self.status_dot)
        h_strip.addSpacing(6)

        name_label = QLabel(title)
        name_label.setObjectName("panelTitle")
        h_strip.addWidget(name_label)
        h_strip.addStretch()

        self.enabled_checkbox = QCheckBox("Enabled")
        h_strip.addWidget(self.enabled_checkbox)
        layout.addWidget(header_strip)

        # Card body
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 14)
        body_layout.setSpacing(10)

        form = QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(9)

        if self.has_key:
            self.api_key_input = QLineEdit()
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key_input.setPlaceholderText("Paste API key")
            form.addRow("API key", self.api_key_input)
        else:
            self.api_key_input = None

        if self.has_base_url:
            self.base_url_input = QLineEdit()
            self.base_url_input.setPlaceholderText("http://localhost:11434")
            form.addRow("Endpoint", self.base_url_input)
        else:
            self.base_url_input = None

        self.model_input = QComboBox()
        self.model_input.setEditable(True)
        self.model_input.setToolTip("Select or type a model name")

        _GROQ_MODELS = [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.3-70b-specdec",
            "llama-3.1-8b-instant",
            "llama-3.2-3b-preview",
            "llama-3.2-1b-preview",
            "llama-3.2-90b-vision-preview",
            "llama-3.2-11b-vision-preview",
            "llama3-70b-8192",
            "llama3-8b-8192",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "gemma-7b-it",
        ]
        _GEMINI_MODELS = [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]
        _OPENROUTER_MODELS = [
            "meta-llama/llama-3.1-8b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-3-27b-it:free",
            "mistralai/mistral-7b-instruct:free",
        ]
        _CLAUDE_MODELS = [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ]
        _OPENAI_MODELS = [
            "gpt-4o",
            "gpt-4o-mini",
            "o1-preview",
            "o1-mini",
        ]
        _MISTRAL_MODELS = [
            "mistral-small-latest",
            "mistral-medium-latest",
            "mistral-large-latest",
            "pixtral-large-latest",
            "pixtral-12b-2409",
            "codestral-latest",
            "open-mistral-nemo",
            "open-codestral-mamba",
        ]
        preset_models = {
            "groq": _GROQ_MODELS,
            "gemini": _GEMINI_MODELS,
            "openrouter": _OPENROUTER_MODELS,
            "claude": _CLAUDE_MODELS,
            "openai": _OPENAI_MODELS,
            "mistral": _MISTRAL_MODELS,
        }
        if self.provider_name in preset_models:
            self.model_input.addItems(preset_models[self.provider_name])

        if self.provider_name == "ollama":
            model_layout = QHBoxLayout()
            model_layout.addWidget(self.model_input, 1)
            self.refresh_btn = AnimatedButton("Refresh")
            self.refresh_btn.setMinimumWidth(80)
            self.refresh_btn.clicked.connect(self._refresh_ollama_models)
            model_layout.addWidget(self.refresh_btn)
            form.addRow("Model", model_layout)
        else:
            form.addRow("Model", self.model_input)

        body_layout.addLayout(form)

        actions = QHBoxLayout()
        self.test_button = AnimatedButton("Test")
        self.help_button = AnimatedButton("How to get it")
        actions.addWidget(self.test_button)
        actions.addWidget(self.help_button)
        body_layout.addLayout(actions)

        self.status_label = QLabel("Not tested")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        body_layout.addWidget(self.status_label)

        layout.addWidget(body)

    def apply_settings(self, settings: dict) -> None:
        self.enabled_checkbox.setChecked(bool(settings.get("enabled", False)))
        if self.api_key_input is not None:
            self.api_key_input.setText(settings.get("api_key", ""))
        if self.base_url_input is not None:
            self.base_url_input.setText(settings.get("base_url", ""))
        saved_model = settings.get("model", "")
        if saved_model:
            # Ensure the saved model appears in the list, then select it
            if self.model_input.findText(saved_model) == -1:
                self.model_input.insertItem(0, saved_model)
            self.model_input.setCurrentText(saved_model)
        elif self.model_input.count() > 0:
            # No saved model — keep the first preset as the default
            pass

    def to_settings(self) -> dict:
        settings = {
            "enabled": self.enabled_checkbox.isChecked(),
            "model": self.model_input.currentText().strip(),
        }
        if self.api_key_input is not None:
            settings["api_key"] = self.api_key_input.text().strip()
        if self.base_url_input is not None:
            settings["base_url"] = self.base_url_input.text().strip()
        return settings

    def set_test_result(self, success: bool, message: str) -> None:
        color = "#10B981" if success else "#F43F5E"
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.status_label.setText(message)
        dot_color = "#10B981" if success else "#F43F5E"
        self.status_dot.setStyleSheet(f"color: {dot_color}; font-size: 10px;")

    def _refresh_ollama_models(self) -> None:
        import threading
        import urllib.request
        import json

        base_url = self.base_url_input.text().strip() if self.base_url_input else "http://localhost:11434"
        if not base_url:
            base_url = "http://localhost:11434"

        self.set_test_result(True, "Fetching models…")

        def _fetch():
            try:
                req = urllib.request.Request(f"{base_url}/api/tags")
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    models = [m.get("name") for m in data.get("models", []) if "name" in m]
                # Marshal back to Qt main thread via a zero-delay timer
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._on_ollama_models_fetched(models, None))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._on_ollama_models_fetched([], str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_ollama_models_fetched(self, models: list, error: str | None) -> None:
        if error:
            self.set_test_result(False, f"Could not fetch models: {error}")
        else:
            self.model_input.clear()
            self.model_input.addItems(models)
            self.set_test_result(True, f"Found {len(models)} local models.")

class LocalAICard(QFrame):
    """Settings card for llama.cpp local AI provider."""
    def __init__(self):
        super().__init__()
        self.provider_name = "llamacpp"
        self._build()

    def _build(self) -> None:
        self.setObjectName("providerCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Card header strip
        header_strip = QFrame()
        header_strip.setFixedHeight(36)
        header_strip.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 rgba(0,200,232,0.09), stop:1 rgba(0,200,232,0.02));"
            "border-bottom: 1px solid rgba(0,200,232,0.10);"
            "border-top-left-radius: 14px; border-top-right-radius: 14px;"
            "border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;"
        )
        h_strip = QHBoxLayout(header_strip)
        h_strip.setContentsMargins(14, 0, 14, 0)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: rgba(148,163,184,0.35); font-size: 10px;")
        h_strip.addWidget(self.status_dot)
        h_strip.addSpacing(6)

        name_label = QLabel("Local (llama.cpp)")
        name_label.setObjectName("panelTitle")
        h_strip.addWidget(name_label)
        h_strip.addStretch()

        self.enabled_checkbox = QCheckBox("Enabled")
        h_strip.addWidget(self.enabled_checkbox)
        layout.addWidget(header_strip)

        # Card body
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 14)
        body_layout.setSpacing(10)

        form = QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(9)

        # Model path row — input + Browse + Auto-detect
        model_layout = QHBoxLayout()
        self.model_path_input = QLineEdit()
        self.model_path_input.setPlaceholderText("e.g., C:\\models\\Qwen3-8B-Q4_K_M.gguf")
        self.model_browse_btn = AnimatedButton("Browse")
        self.model_browse_btn.setMinimumWidth(70)
        self.model_browse_btn.clicked.connect(self._browse_model_path)
        self.model_autodetect_btn = AnimatedButton("🔍 Scan")
        self.model_autodetect_btn.setMinimumWidth(70)
        self.model_autodetect_btn.setToolTip("Scan common model folders for .gguf files")
        self.model_autodetect_btn.clicked.connect(self._auto_detect_model)
        model_layout.addWidget(self.model_path_input, 1)
        model_layout.addWidget(self.model_browse_btn)
        model_layout.addWidget(self.model_autodetect_btn)
        form.addRow("Model (.gguf)", model_layout)

        # Draft model path
        draft_layout = QHBoxLayout()
        self.draft_path_input = QLineEdit()
        self.draft_path_input.setPlaceholderText("Optional: DFlash drafter for 3x coding speed")
        self.draft_browse_btn = AnimatedButton("Browse")
        self.draft_browse_btn.setMinimumWidth(80)
        self.draft_browse_btn.clicked.connect(self._browse_draft_path)
        draft_layout.addWidget(self.draft_path_input, 1)
        draft_layout.addWidget(self.draft_browse_btn)
        form.addRow("DFlash Drafter", draft_layout)

        # GPU Layers slider
        gpu_layout = QHBoxLayout()
        self.gpu_layers_slider = QSlider(Qt.Orientation.Horizontal)
        self.gpu_layers_slider.setMinimum(0)
        self.gpu_layers_slider.setMaximum(99)
        self.gpu_layers_slider.setValue(99)
        self.gpu_layers_label = QLabel("99 (all on GPU)")
        self.gpu_layers_label.setMinimumWidth(120)
        self.gpu_layers_slider.valueChanged.connect(self._update_gpu_layers_label)
        gpu_layout.addWidget(self.gpu_layers_slider, 1)
        gpu_layout.addWidget(self.gpu_layers_label)
        form.addRow("GPU Layers", gpu_layout)

        # Context Size
        self.context_size_combo = QComboBox()
        self.context_size_combo.addItems(["8192", "16384", "32768", "65536"])
        self.context_size_combo.setCurrentText("32768")
        form.addRow("Context Size", self.context_size_combo)

        # KV Cache K — standard: f16/q8_0/q4_0 | beellama.cpp: turbo4/turbo3/turbo2_tcq
        self.kv_k_combo = QComboBox()
        self.kv_k_combo.addItems(["f16", "q8_0", "q4_0", "turbo4", "turbo3", "turbo2_tcq", "turbo3_tcq"])
        self.kv_k_combo.setCurrentText("q4_0")
        self.kv_k_combo.setToolTip("turbo* types require beellama.cpp — up to 7.5x compression")
        form.addRow("KV Cache K", self.kv_k_combo)

        # KV Cache V
        self.kv_v_combo = QComboBox()
        self.kv_v_combo.addItems(["f16", "q8_0", "q4_0", "q3_0", "turbo4", "turbo3", "turbo2_tcq", "turbo3_tcq"])
        self.kv_v_combo.setCurrentText("q4_0")
        self.kv_v_combo.setToolTip("turbo* types require beellama.cpp — up to 7.5x compression")
        form.addRow("KV Cache V", self.kv_v_combo)

        # MoE CPU Experts
        moe_layout = QHBoxLayout()
        self.moe_spinbox = QSpinBox()
        self.moe_spinbox.setMinimum(0)
        self.moe_spinbox.setMaximum(128)
        self.moe_spinbox.setValue(0)
        self.moe_info = QLabel("(0 = off; use >0 for MoE models only e.g. Qwen3-30B)")
        self.moe_info.setObjectName("muted")
        moe_layout.addWidget(self.moe_spinbox)
        moe_layout.addWidget(self.moe_info)
        moe_layout.addStretch()
        form.addRow("MoE CPU Experts", moe_layout)

        # DFlash speculative decoding section
        spec_label = QLabel("── Speculative Decoding (DFlash) ──────────────")
        spec_label.setObjectName("muted")
        body_layout.addLayout(form)
        body_layout.addWidget(spec_label)

        form2 = QFormLayout()
        form2.setHorizontalSpacing(10)
        form2.setVerticalSpacing(8)

        self.spec_type_combo = QComboBox()
        self.spec_type_combo.addItems(["", "dflash", "ngram-simple"])
        self.spec_type_combo.setCurrentText("")
        self.spec_type_combo.setToolTip(
            "disabled (empty) = safest; dflash requires beellama.cpp; "
            "ngram-simple: only with --parallel 2 (halves slot context with parallel 4)"
        )
        form2.addRow("Spec Type", self.spec_type_combo)

        draft_n_layout = QHBoxLayout()
        self.spec_draft_n_max = QSpinBox()
        self.spec_draft_n_max.setRange(1, 16)
        self.spec_draft_n_max.setValue(3)
        self.spec_draft_n_max.setToolTip("3 = sweet spot (83% acceptance on coding); 4-5 wastes compute")
        draft_n_layout.addWidget(self.spec_draft_n_max)
        draft_n_layout.addWidget(QLabel("tokens (3 = sweet spot, 83% acc)"))
        draft_n_layout.addStretch()
        form2.addRow("Max Draft Tokens", draft_n_layout)

        self.spec_draft_p_min = QDoubleSpinBox()
        self.spec_draft_p_min.setRange(0.0, 1.0)
        self.spec_draft_p_min.setSingleStep(0.05)
        self.spec_draft_p_min.setValue(0.75)
        self.spec_draft_p_min.setToolTip("Early-stop draft if confidence below this threshold")
        form2.addRow("Min Draft P", self.spec_draft_p_min)

        cross_ctx_layout = QHBoxLayout()
        self.spec_cross_ctx = QSpinBox()
        self.spec_cross_ctx.setRange(64, 4096)
        self.spec_cross_ctx.setSingleStep(64)
        self.spec_cross_ctx.setValue(512)
        self.spec_cross_ctx.setToolTip("DFlash cross-attention window (use 1024 for long contexts)")
        cross_ctx_layout.addWidget(self.spec_cross_ctx)
        cross_ctx_layout.addWidget(QLabel("(1024 for long ctx)"))
        cross_ctx_layout.addStretch()
        form2.addRow("DFlash Cross-Ctx", cross_ctx_layout)

        body_layout.addLayout(form2)

        form3 = QFormLayout()
        form3.setHorizontalSpacing(10)
        form3.setVerticalSpacing(8)

        # Process priority
        self.prio_combo = QComboBox()
        self.prio_combo.addItems(["0 - Normal", "1 - Medium", "2 - High", "3 - Realtime"])
        self.prio_combo.setCurrentIndex(2)  # High by default
        self.prio_combo.setToolTip("High priority reduces scheduling interruptions")
        form3.addRow("Process Priority", self.prio_combo)

        # Defrag threshold
        self.defrag_spin = QDoubleSpinBox()
        self.defrag_spin.setRange(0.0, 1.0)
        self.defrag_spin.setSingleStep(0.05)
        self.defrag_spin.setValue(0.1)
        self.defrag_spin.setToolTip("Defrag KV cache when this fraction is fragmented (keeps speed stable)")
        form3.addRow("Defrag Threshold", self.defrag_spin)

        # Port
        port_layout = QHBoxLayout()
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setMinimum(1024)
        self.port_spinbox.setMaximum(65535)
        self.port_spinbox.setValue(8080)
        port_layout.addWidget(self.port_spinbox)
        port_layout.addStretch()
        form3.addRow("Port", port_layout)

        body_layout.addLayout(form3)

        # Checkboxes row
        checks_layout = QHBoxLayout()
        self.flash_attn_check = QCheckBox("Flash Attention")
        self.flash_attn_check.setChecked(True)
        self.flash_attn_check.setToolTip("Ampere+ / RDNA3 required; 1.3-2x faster")
        checks_layout.addWidget(self.flash_attn_check)

        self.no_mmap_check = QCheckBox("No-mmap")
        self.no_mmap_check.setChecked(True)
        self.no_mmap_check.setToolTip("Load model into RAM upfront — eliminates page-fault stutters")
        checks_layout.addWidget(self.no_mmap_check)

        self.mlock_check = QCheckBox("Lock RAM")
        self.mlock_check.setChecked(True)
        self.mlock_check.setToolTip("Pin RAM — prevents OS from paging model out after hours of uptime")
        checks_layout.addWidget(self.mlock_check)
        checks_layout.addStretch()
        body_layout.addLayout(checks_layout)

        # Test button
        self.test_button = AnimatedButton("Test Connection")
        body_layout.addWidget(self.test_button)

        # Info and download links
        info_text = QLabel(
            "Qwen3-8B fits on 8GB VRAM. DFlash gives 3x speed on coding tasks."
        )
        info_text.setObjectName("muted")
        info_text.setWordWrap(True)
        body_layout.addWidget(info_text)

        links_layout = QHBoxLayout()
        model_link = QLabel(
            '<a href="https://huggingface.co/unsloth/Qwen3-8B-GGUF" style="color: #00C8E8;">HuggingFace model page</a>'
        )
        model_link.setOpenExternalLinks(True)
        model_link.setObjectName("muted")

        draft_link = QLabel(
            '<a href="https://huggingface.co/z-lab/Qwen3-8B-DFlash" style="color: #00C8E8;">DFlash drafter</a>'
        )
        draft_link.setOpenExternalLinks(True)
        draft_link.setObjectName("muted")

        links_layout.addWidget(model_link)
        links_layout.addWidget(draft_link)
        links_layout.addStretch()
        body_layout.addLayout(links_layout)

        # One-click install
        install_frame = QFrame()
        install_frame.setStyleSheet(
            "background: rgba(0,200,232,0.05); border: 1px solid rgba(0,200,232,0.12);"
            "border-radius: 10px; padding: 4px;"
        )
        install_layout = QVBoxLayout(install_frame)
        install_layout.setContentsMargins(10, 8, 10, 8)
        install_layout.setSpacing(6)

        install_top = QHBoxLayout()
        install_label = QLabel("No model installed")
        install_label.setObjectName("muted")
        install_label.setStyleSheet("font-size: 12px; color: rgba(148,163,184,0.8);")
        self._install_status_label = install_label

        self._install_btn = AnimatedButton("⬇  Install Qwen3-8B (4-bit, ~5 GB)")
        self._install_btn.setToolTip(
            "Downloads Qwen3-8B-Q4_K_M.gguf from HuggingFace into ~/models/\n"
            "Requires: pip install huggingface_hub  (or hf_transfer for fast download)"
        )
        self._install_btn.setStyleSheet(
            "QPushButton { background: rgba(0,200,232,0.10); color: #00C8E8; "
            "border: 1px solid rgba(0,200,232,0.30); border-radius: 8px; "
            "padding: 5px 14px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(0,200,232,0.20); border-color: rgba(0,200,232,0.55); }"
            "QPushButton:disabled { opacity: 0.5; }"
        )
        self._install_btn.clicked.connect(self._install_model)

        install_top.addWidget(self._install_status_label, 1)
        install_top.addWidget(self._install_btn)
        install_layout.addLayout(install_top)

        self._install_progress = QProgressBar()
        self._install_progress.setRange(0, 100)
        self._install_progress.setValue(0)
        self._install_progress.setVisible(False)
        self._install_progress.setFixedHeight(6)
        self._install_progress.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,0.07); border-radius: 3px; border: none; }"
            "QProgressBar::chunk { background: #00C8E8; border-radius: 3px; }"
        )
        install_layout.addWidget(self._install_progress)
        body_layout.addWidget(install_frame)
        self._install_frame = install_frame

        self.status_label = QLabel("Not tested")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        body_layout.addWidget(self.status_label)

        layout.addWidget(body)

        # Auto-scan on creation so the user immediately sees if a model is present
        QTimer.singleShot(200, self._auto_detect_model)

    def _update_gpu_layers_label(self) -> None:
        val = self.gpu_layers_slider.value()
        self.gpu_layers_label.setText(f"{val} {'(all on GPU)' if val == 99 else ''}")

    def _browse_model_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select llama.cpp model (.gguf)",
            "",
            "GGUF Files (*.gguf);;All Files (*)"
        )
        if path:
            self.model_path_input.setText(path)

    def _browse_draft_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select draft model (.gguf)",
            "",
            "GGUF Files (*.gguf);;All Files (*)"
        )
        if path:
            self.draft_path_input.setText(path)

    def apply_settings(self, settings: dict) -> None:
        """Load settings from dict."""
        self.enabled_checkbox.setChecked(bool(settings.get("enabled", False)))
        mp = settings.get("model_path", "")
        self.model_path_input.setText(mp)
        # Update install panel immediately from saved path
        self._set_install_status(Path(mp) if mp else None)
        self.draft_path_input.setText(settings.get("draft_model_path", ""))
        self.gpu_layers_slider.setValue(int(settings.get("n_gpu_layers", 99)))
        self.context_size_combo.setCurrentText(str(settings.get("context_size", 32768)))
        self.kv_k_combo.setCurrentText(settings.get("kv_cache_type_k", "q4_0"))
        self.kv_v_combo.setCurrentText(settings.get("kv_cache_type_v", "q4_0"))
        self.moe_spinbox.setValue(int(settings.get("n_cpu_moe", 0)))
        self.flash_attn_check.setChecked(bool(settings.get("flash_attn", True)))
        self.no_mmap_check.setChecked(bool(settings.get("no_mmap", True)))
        self.mlock_check.setChecked(bool(settings.get("mlock", True)))
        self.port_spinbox.setValue(int(settings.get("port", 8080)))
        # Speculative decoding
        spec_type = settings.get("spec_type", "dflash")
        idx = self.spec_type_combo.findText(spec_type)
        if idx >= 0:
            self.spec_type_combo.setCurrentIndex(idx)
        self.spec_draft_n_max.setValue(int(settings.get("spec_draft_n_max", 3)))
        self.spec_draft_p_min.setValue(float(settings.get("spec_draft_p_min", 0.75)))
        self.spec_cross_ctx.setValue(int(settings.get("spec_dflash_cross_ctx", 512)))
        # Priority
        prio = int(settings.get("prio", 2))
        self.prio_combo.setCurrentIndex(min(prio, 3))
        self.defrag_spin.setValue(float(settings.get("defrag_thold", 0.1)))

    def to_settings(self) -> dict:
        """Collect settings into dict matching LlamaCppLauncher DEFAULT_CONFIG keys exactly."""
        prio = self.prio_combo.currentIndex()
        port = self.port_spinbox.value()
        return {
            "enabled": self.enabled_checkbox.isChecked(),
            "model_path": self.model_path_input.text().strip(),
            "draft_model_path": self.draft_path_input.text().strip(),
            "n_gpu_layers": self.gpu_layers_slider.value(),
            "n_gpu_layers_draft": 99,
            "context_size": int(self.context_size_combo.currentText()),
            "batch_size": 2048,
            "ubatch_size": 2048,
            "kv_cache_type_k": self.kv_k_combo.currentText(),
            "kv_cache_type_v": self.kv_v_combo.currentText(),
            "n_cpu_moe": self.moe_spinbox.value(),
            "flash_attn": self.flash_attn_check.isChecked(),
            "no_mmap": self.no_mmap_check.isChecked(),
            "mlock": self.mlock_check.isChecked(),
            "cont_batching": True,
            "prio": prio,
            "defrag_thold": self.defrag_spin.value(),
            "spec_type": self.spec_type_combo.currentText(),
            "spec_draft_n_max": self.spec_draft_n_max.value(),
            "spec_draft_p_min": self.spec_draft_p_min.value(),
            "spec_dflash_cross_ctx": self.spec_cross_ctx.value(),
            "port": port,
            "host": "127.0.0.1",
            "base_url": f"http://127.0.0.1:{port}/v1",
        }

    def set_test_result(self, success: bool, message: str) -> None:
        """Update status display after test."""
        color = "#10B981" if success else "#F43F5E"
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.status_label.setText(message)
        dot_color = "#10B981" if success else "#F43F5E"
        self.status_dot.setStyleSheet(f"color: {dot_color}; font-size: 10px;")

    # Model auto-detect

    # Canonical recommended model filename (used for one-click install)
    _RECOMMENDED_MODEL = "Qwen3-8B-Q4_K_M.gguf"
    _HF_REPO = "unsloth/Qwen3-8B-GGUF"

    def _scan_dirs(self) -> list[Path]:
        """Return candidate directories to search for .gguf files."""
        home = Path.home()
        candidates = [
            home / "models",
            home / "Models",
            home / "Downloads",
            home / ".cache" / "huggingface" / "hub",
            home / ".lm_studio" / "models",
            home / "AppData" / "Local" / "LM-Studio" / "models",
            home / "AppData" / "Local" / "lmstudio" / "models",
            home / "AppData" / "Roaming" / "LM-Studio" / "models",
            Path("C:/models"),
            Path("C:/Models"),
            Path("C:/AI/models"),
        ]
        # Also add parent folder of current model_path (if set)
        current = self.model_path_input.text().strip()
        if current:
            candidates.insert(0, Path(current).parent)
        return [d for d in candidates if d.exists()]

    def _auto_detect_model(self) -> None:
        """Scan common directories for .gguf files and populate the model path."""
        self.model_autodetect_btn.setEnabled(False)
        self.model_autodetect_btn.setText("Scanning…")

        found: list[Path] = []
        preferred: Path | None = None

        for d in self._scan_dirs():
            try:
                # Recurse up to 4 levels deep to handle HuggingFace cache layout
                for gguf in d.rglob("*.gguf"):
                    if gguf.is_file():
                        found.append(gguf)
                        # Prefer exact recommended model name
                        if self._RECOMMENDED_MODEL.lower() in gguf.name.lower():
                            preferred = gguf
            except PermissionError:
                pass

        self.model_autodetect_btn.setEnabled(True)
        self.model_autodetect_btn.setText("🔍 Scan")

        if not found:
            self._set_install_status(None)
            NotificationToast.show_toast(
                "No .gguf models found. Click '⬇ Install Qwen3-8B' to download one.",
                "warning", self, "llm_scan", 8000,
            )
            return

        # Pick best match
        pick = preferred or found[0]

        # Only auto-fill if field is currently empty
        if not self.model_path_input.text().strip():
            self.model_path_input.setText(str(pick))
            self.enabled_checkbox.setChecked(True)

        self._set_install_status(pick)

        if len(found) == 1:
            msg = f"Found: {pick.name}"
        else:
            msg = f"Found {len(found)} models — using {pick.name}"

        NotificationToast.show_toast(msg, "success", self, "llm_scan", 7000)

    def _set_install_status(self, model_path: Path | None) -> None:
        """Update the install-frame label and button based on whether a model exists."""
        if model_path and model_path.exists():
            size_gb = model_path.stat().st_size / 1e9
            self._install_status_label.setText(
                f"✓ Model ready: {model_path.name}  ({size_gb:.1f} GB)"
            )
            self._install_status_label.setStyleSheet("font-size: 12px; color: #10B981;")
            self._install_btn.setText("⬇  Re-install / Update")
            self._install_btn.setEnabled(True)
        else:
            self._install_status_label.setText("No model installed")
            self._install_status_label.setStyleSheet(
                "font-size: 12px; color: rgba(148,163,184,0.8);"
            )
            self._install_btn.setText("⬇  Install Qwen3-8B (4-bit, ~5 GB)")
            self._install_btn.setEnabled(True)

    def _install_model(self) -> None:
        """Download Qwen3-8B-Q4_K_M.gguf via huggingface_hub into ~/models/."""
        import threading

        dest_dir = Path.home() / "models"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / self._RECOMMENDED_MODEL

        self._install_btn.setEnabled(False)
        self._install_btn.setText("Downloading…")
        self._install_progress.setValue(0)
        self._install_progress.setVisible(True)
        self._install_status_label.setText("Downloading Qwen3-8B-Q4_K_M.gguf…")
        self._install_status_label.setStyleSheet("font-size: 12px; color: #F59E0B;")

        def _do_download():
            try:
                from huggingface_hub import hf_hub_download
                # hf_hub_download streams to a cache; copy to dest_dir after
                local = hf_hub_download(
                    repo_id=self._HF_REPO,
                    filename=self._RECOMMENDED_MODEL,
                    local_dir=str(dest_dir),
                    local_dir_use_symlinks=False,
                )
                QTimer.singleShot(0, lambda p=Path(local): self._on_install_done(p, None))
            except ImportError:
                QTimer.singleShot(0, lambda: self._on_install_done(None,
                    "huggingface_hub not installed.\n"
                    "Run:  pip install huggingface_hub\n"
                    "Then try again, or manually place the .gguf file and click Browse."
                ))
            except Exception as exc:
                QTimer.singleShot(0, lambda e=str(exc): self._on_install_done(None, e))

        threading.Thread(target=_do_download, daemon=True).start()

        # Pulse the progress bar while downloading (indeterminate)
        self._install_progress.setRange(0, 0)

    def _on_install_done(self, model_path: Path | None, error: str | None) -> None:
        self._install_progress.setRange(0, 100)
        self._install_progress.setValue(100 if not error else 0)
        self._install_progress.setVisible(False)

        if error:
            self._install_btn.setEnabled(True)
            self._install_btn.setText("⬇  Install Qwen3-8B (4-bit, ~5 GB)")
            self._install_status_label.setText(f"Install failed: {error[:80]}")
            self._install_status_label.setStyleSheet("font-size: 12px; color: #F43F5E;")
            NotificationToast.show_toast(
                f"Model install failed: {error[:120]}", "error", self, "llm_install", 12000
            )
            return

        # Success
        self.model_path_input.setText(str(model_path))
        self.enabled_checkbox.setChecked(True)
        self._set_install_status(model_path)
        NotificationToast.show_toast(
            f"Model installed: {model_path.name} — Local engine ready.",
            "success", self, "llm_install", 8000,
        )

_CONNECTOR_DEFS = [
    {
        "id": "gmail", "name": "Gmail", "icon": "✉", "desc": "Send & read email",
        "setup_url": "https://console.cloud.google.com/apis/credentials",
        "has_oauth": True,
        "oauth_scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        "setup_steps": [
            "1. Go to Google Cloud Console → APIs & Services → Credentials",
            "2. Create a project (or select an existing one)",
            "3. Enable the Gmail API under 'Library'",
            "4. Create an OAuth 2.0 Client ID (choose 'Desktop app')",
            "5. Download the credentials.json file",
            "6. Set the path below, then click 'Authorize' to sign in",
        ],
        "fields": [
            {"key": "credentials_path", "label": "credentials.json", "type": "filepath", "ph": "Path to Google OAuth credentials.json"},
            {"key": "token_path",        "label": "Token cache (.json)", "type": "filepath", "ph": "Path to store OAuth token"},
        ],
    },
    {
        "id": "google_calendar", "name": "Google Calendar", "icon": "📅", "desc": "Events & reminders",
        "setup_url": "https://console.cloud.google.com/apis/credentials",
        "has_oauth": True,
        "oauth_scopes": ["https://www.googleapis.com/auth/calendar"],
        "setup_steps": [
            "1. Go to Google Cloud Console → APIs & Services",
            "2. Enable the Google Calendar API",
            "3. Create OAuth 2.0 Client ID (Desktop app) if not done already",
            "4. Download credentials.json and set the path below",
            "5. Click 'Authorize' to sign in via browser",
        ],
        "fields": [
            {"key": "credentials_path", "label": "credentials.json", "type": "filepath", "ph": "Path to Google OAuth credentials.json"},
        ],
    },
    {
        "id": "telegram", "name": "Telegram", "icon": "✈", "desc": "Bot messaging",
        "setup_url": "https://t.me/BotFather",
        "setup_steps": [
            "1. Open Telegram and message @BotFather",
            "2. Send /newbot and follow the prompts",
            "3. Copy the bot token provided",
            "4. Get your Chat ID from @userinfobot",
        ],
        "fields": [
            {"key": "bot_token", "label": "Bot token", "type": "password", "ph": "123456:ABCdef..."},
            {"key": "chat_id",   "label": "Chat ID",   "type": "text",     "ph": "Your numeric chat ID"},
        ],
    },
    {
        "id": "spotify", "name": "Spotify", "icon": "♪", "desc": "Music playback control",
        "setup_url": "https://developer.spotify.com/dashboard",
        "setup_steps": [
            "1. Go to Spotify Developer Dashboard",
            "2. Create a new app",
            "3. Copy Client ID and Client Secret",
            "4. Set redirect URI to http://localhost:8888/callback in app settings",
        ],
        "fields": [
            {"key": "client_id",     "label": "Client ID",     "type": "text",     "ph": "Spotify app client ID"},
            {"key": "client_secret", "label": "Client secret", "type": "password", "ph": "Spotify app client secret"},
            {"key": "redirect_uri",  "label": "Redirect URI",  "type": "text",     "ph": "http://localhost:8888/callback"},
        ],
    },
    {
        "id": "notion", "name": "Notion", "icon": "N", "desc": "Pages & databases",
        "setup_url": "https://www.notion.so/my-integrations",
        "setup_steps": [
            "1. Go to notion.so/my-integrations",
            "2. Create a new integration",
            "3. Copy the Internal Integration Secret",
            "4. Share the target database with your integration",
        ],
        "fields": [
            {"key": "api_key",     "label": "API key",     "type": "password", "ph": "secret_..."},
            {"key": "database_id", "label": "Database ID", "type": "text",     "ph": "32-char Notion page/database ID"},
        ],
    },
    {
        "id": "github", "name": "GitHub", "icon": "⑂", "desc": "Repos, issues & PRs",
        "setup_url": "https://github.com/settings/tokens?type=beta",
        "setup_steps": [
            "1. Go to GitHub → Settings → Developer settings → Personal access tokens",
            "2. Generate a new fine-grained token",
            "3. Select the repos and permissions you need",
            "4. Copy the token (starts with ghp_)",
        ],
        "fields": [
            {"key": "token",        "label": "Personal access token", "type": "password", "ph": "ghp_..."},
            {"key": "default_repo", "label": "Default repo",          "type": "text",     "ph": "owner/repo"},
        ],
    },
    {
        "id": "discord", "name": "Discord", "icon": "D", "desc": "Channel notifications",
        "setup_url": "https://discord.com/developers/applications",
        "setup_steps": [
            "1. Go to Discord server settings → Integrations → Webhooks",
            "2. Create a new webhook",
            "3. Copy the webhook URL",
        ],
        "fields": [
            {"key": "webhook_url", "label": "Webhook URL", "type": "password", "ph": "https://discord.com/api/webhooks/..."},
        ],
    },
    {
        "id": "slack", "name": "Slack", "icon": "S", "desc": "Workspace messaging",
        "setup_url": "https://api.slack.com/apps",
        "setup_steps": [
            "1. Go to api.slack.com/apps and create a new app",
            "2. Under OAuth & Permissions, add chat:write scope",
            "3. Install the app to your workspace",
            "4. Copy the Bot User OAuth Token (starts with xoxb-)",
        ],
        "fields": [
            {"key": "bot_token",       "label": "Bot token",       "type": "password", "ph": "xoxb-..."},
            {"key": "default_channel", "label": "Default channel", "type": "text",     "ph": "#general"},
        ],
    },
    {
        "id": "openweathermap", "name": "OpenWeatherMap", "icon": "☁", "desc": "Live weather data",
        "setup_url": "https://home.openweathermap.org/api_keys",
        "setup_steps": [
            "1. Sign up at openweathermap.org (free tier available)",
            "2. Go to API Keys tab",
            "3. Copy your API key (takes ~10 min to activate)",
        ],
        "fields": [
            {"key": "api_key",      "label": "API key",      "type": "password", "ph": "32-char OWM key"},
            {"key": "default_city", "label": "Default city", "type": "text",     "ph": "London"},
        ],
    },
    {
        "id": "newsapi", "name": "NewsAPI", "icon": "◉", "desc": "News headlines",
        "setup_url": "https://newsapi.org/register",
        "setup_steps": [
            "1. Register at newsapi.org (free for dev use)",
            "2. Copy your API key from the dashboard",
        ],
        "fields": [
            {"key": "api_key", "label": "API key",      "type": "password", "ph": "32-char NewsAPI key"},
            {"key": "country", "label": "Country code", "type": "text",     "ph": "us"},
        ],
    },
    {
        "id": "home_assistant", "name": "Home Assistant", "icon": "⌂", "desc": "Smart home control",
        "setup_url": "https://www.home-assistant.io/docs/authentication/",
        "setup_steps": [
            "1. Open Home Assistant → Profile → Long-Lived Access Tokens",
            "2. Create a new token and copy it",
            "3. Enter your HA base URL below",
        ],
        "fields": [
            {"key": "base_url", "label": "Base URL",                 "type": "text",     "ph": "http://homeassistant.local:8123"},
            {"key": "token",    "label": "Long-lived access token",  "type": "password", "ph": "eyJ..."},
        ],
    },
    {
        "id": "google_tasks", "name": "Google Tasks", "icon": "✓", "desc": "Task lists & todos",
        "setup_url": "https://console.cloud.google.com/apis/credentials",
        "has_oauth": True,
        "oauth_scopes": ["https://www.googleapis.com/auth/tasks"],
        "setup_steps": [
            "1. Enable the Google Tasks API in Cloud Console",
            "2. Reuse the same OAuth Client ID as Gmail/Calendar",
            "3. Set credentials path and click 'Authorize'",
        ],
        "fields": [
            {"key": "credentials_path", "label": "credentials.json", "type": "filepath", "ph": "Path to Google OAuth credentials.json"},
        ],
    },
    {
        "id": "wolframalpha", "name": "Wolfram Alpha", "icon": "Ω", "desc": "Computational knowledge",
        "setup_url": "https://developer.wolframalpha.com/portal/myapps/",
        "setup_steps": [
            "1. Sign up at developer.wolframalpha.com",
            "2. Create a new app (Short Answers API is free)",
            "3. Copy the App ID",
        ],
        "fields": [
            {"key": "app_id", "label": "App ID", "type": "password", "ph": "XXXX-XXXXXXXXXX"},
        ],
    },
    {
        "id": "todoist", "name": "Todoist", "icon": "✔", "desc": "Task management",
        "setup_url": "https://todoist.com/app/settings/integrations/developer",
        "setup_steps": [
            "1. Go to Todoist settings → Integrations → Developer",
            "2. Copy your API token",
        ],
        "fields": [
            {"key": "api_token", "label": "API token", "type": "password", "ph": "Your Todoist API token"},
        ],
    },
    {
        "id": "trello", "name": "Trello", "icon": "T", "desc": "Kanban boards",
        "setup_url": "https://trello.com/power-ups/admin",
        "setup_steps": [
            "1. Go to trello.com/power-ups/admin",
            "2. Create a new Power-Up (or use existing)",
            "3. Copy the API key and generate a token",
        ],
        "fields": [
            {"key": "api_key",   "label": "API key",   "type": "password", "ph": "32-char Trello key"},
            {"key": "api_token", "label": "API token", "type": "password", "ph": "64-char Trello token"},
        ],
    },
]

class ConnectorsDialog(QDialog):
    """Popout dialog for configuring third-party service connectors."""

    _FIELD_STYLE = (
        "background: rgba(15,23,42,0.60);"
        "border: 1px solid rgba(0,200,232,0.18);"
        "border-radius: 6px;"
        "padding: 5px 8px;"
        "color: #E2E8F0;"
    )

    def __init__(self, parent, saved_settings: dict):
        super().__init__(parent)
        self._saved = saved_settings or {}
        self._field_widgets: dict[str, dict[str, QLineEdit]] = {}
        self._enabled_checks: dict[str, QCheckBox] = {}
        self._build()

    def _build(self) -> None:
        self.setWindowTitle("Connectors")
        self.setMinimumSize(580, 700)
        self.setStyleSheet("""
            QDialog {
                background: rgba(10,14,39,0.97);
                border: 1px solid rgba(0,200,232,0.20);
                border-radius: 16px;
            }
            QWidget { background: transparent; color: #E2E8F0; font-size: 13px; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: rgba(15,23,42,0.40); width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0,200,232,0.28); border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("CONNECTORS")
        title.setStyleSheet(
            "font-size:12px; font-weight:700; color:rgba(0,200,232,0.85); letter-spacing:2.5px;"
        )
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        desc = QLabel(
            "Connect JARVIS to external services. "
            "Credentials are stored locally and passed to plugins at runtime."
        )
        desc.setStyleSheet("color: rgba(148,163,184,0.65); font-size: 12px;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 4, 6, 4)
        content_layout.setSpacing(8)

        for conn in _CONNECTOR_DEFS:
            card = self._build_card(conn, self._saved.get(conn["id"], {}))
            content_layout.addWidget(card)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = AnimatedButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = AnimatedButton("Save connectors")
        save_btn.setStyleSheet("font-weight: 700;")
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    def _build_card(self, conn: dict, saved: dict) -> QWidget:
        conn_id = conn["id"]
        fields_def = conn["fields"]
        any_filled = any(saved.get(f["key"], "").strip() for f in fields_def)

        outer = QFrame()
        outer.setStyleSheet("""
            QFrame {
                background: rgba(15,23,42,0.50);
                border: 1px solid rgba(0,200,232,0.09);
                border-radius: 10px;
            }
        """)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(14, 10, 14, 10)
        outer_layout.setSpacing(0)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        dot = QLabel("●")
        dot.setFixedWidth(14)
        dot.setStyleSheet(
            f"color: {'#34D399' if any_filled else 'rgba(100,116,139,0.35)'}; font-size: 10px;"
        )
        header_row.addWidget(dot)

        icon_lbl = QLabel(conn["icon"])
        icon_lbl.setStyleSheet("font-size: 14px; color: #94A3B8;")
        icon_lbl.setFixedWidth(20)
        header_row.addWidget(icon_lbl)

        name_lbl = QLabel(conn["name"])
        name_lbl.setStyleSheet("font-weight: 600; color: #E2E8F0; font-size: 13px;")
        header_row.addWidget(name_lbl)

        desc_lbl = QLabel(f"— {conn['desc']}")
        desc_lbl.setStyleSheet("color: rgba(148,163,184,0.50); font-size: 12px;")
        header_row.addWidget(desc_lbl, 1)

        enabled_cb = QCheckBox("Enable")
        enabled_cb.setChecked(bool(saved.get("enabled", False)))
        enabled_cb.setStyleSheet("font-size: 12px; color: rgba(148,163,184,0.70);")
        header_row.addWidget(enabled_cb)
        self._enabled_checks[conn_id] = enabled_cb

        expand_btn = AnimatedButton("▼ Setup")
        expand_btn.setFixedWidth(76)
        expand_btn.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        header_row.addWidget(expand_btn)
        outer_layout.addLayout(header_row)

        body = QWidget()
        body.setVisible(any_filled)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(34, 8, 0, 2)
        body_layout.setSpacing(6)

        # Setup guide section
        setup_steps = conn.get("setup_steps", [])
        setup_url = conn.get("setup_url", "")
        has_oauth = conn.get("has_oauth", False)

        if setup_steps:
            guide_frame = QFrame()
            guide_frame.setStyleSheet(
                "QFrame { background: rgba(0,200,232,0.04); "
                "border: 1px solid rgba(0,200,232,0.10); border-radius: 8px; }"
            )
            guide_inner = QVBoxLayout(guide_frame)
            guide_inner.setContentsMargins(12, 8, 12, 8)
            guide_inner.setSpacing(3)

            guide_title = QLabel("Setup Guide")
            guide_title.setStyleSheet(
                "font-size: 11px; font-weight: 600; color: rgba(0,200,232,0.70); "
                "letter-spacing: 1.5px; border: none;"
            )
            guide_inner.addWidget(guide_title)

            for step_text in setup_steps:
                step_lbl = QLabel(step_text)
                step_lbl.setStyleSheet("color: rgba(148,163,184,0.80); font-size: 12px; border: none;")
                step_lbl.setWordWrap(True)
                guide_inner.addWidget(step_lbl)

            # Action buttons row
            guide_btns = QHBoxLayout()
            guide_btns.setSpacing(6)
            if setup_url:
                link_btn = AnimatedButton("Get credentials ↗")
                link_btn.setFixedHeight(28)
                link_btn.setStyleSheet("font-size: 11px; padding: 2px 10px;")
                link_btn.clicked.connect(
                    lambda _, url=setup_url: QDesktopServices.openUrl(QUrl(url))
                )
                guide_btns.addWidget(link_btn)
            if has_oauth:
                auth_btn = AnimatedButton("🔐 Authorize")
                auth_btn.setFixedHeight(28)
                auth_btn.setStyleSheet(
                    "font-size: 11px; padding: 2px 10px; font-weight: 600;"
                )
                _conn_ref = conn  # capture for lambda
                auth_btn.clicked.connect(
                    lambda _, c=_conn_ref, fw=None: self._run_oauth(c)
                )
                guide_btns.addWidget(auth_btn)
            guide_btns.addStretch()
            guide_inner.addLayout(guide_btns)
            body_layout.addWidget(guide_frame)

        # Credential fields
        fields_form = QFormLayout()
        fields_form.setVerticalSpacing(7)
        fields_form.setHorizontalSpacing(10)

        field_widgets: dict[str, QLineEdit] = {}
        for fdef in fields_def:
            fkey   = fdef["key"]
            ftype  = fdef["type"]
            flabel = fdef["label"]
            fph    = fdef["ph"]

            inp = QLineEdit()
            inp.setPlaceholderText(fph)
            inp.setText(saved.get(fkey, ""))
            inp.setStyleSheet(self._FIELD_STYLE)

            if ftype == "password":
                inp.setEchoMode(QLineEdit.EchoMode.Password)

            if ftype == "filepath":
                row_w = QWidget()
                row_h = QHBoxLayout(row_w)
                row_h.setContentsMargins(0, 0, 0, 0)
                row_h.setSpacing(5)
                browse = AnimatedButton("Browse…")
                browse.setFixedWidth(70)
                browse.setStyleSheet("font-size: 11px; padding: 2px 6px;")
                browse.clicked.connect(lambda _, i=inp: self._browse_file(i))
                row_h.addWidget(inp, 1)
                row_h.addWidget(browse)
                fields_form.addRow(flabel, row_w)
            else:
                fields_form.addRow(flabel, inp)

            field_widgets[fkey] = inp

        body_layout.addLayout(fields_form)
        self._field_widgets[conn_id] = field_widgets
        outer_layout.addWidget(body)

        expand_btn.setText("▲ Collapse" if any_filled else "▼ Setup")

        def _toggle() -> None:
            visible = not body.isVisible()
            body.setVisible(visible)
            expand_btn.setText("▲ Collapse" if visible else "▼ Setup")
            any_f = any(w.text().strip() for w in field_widgets.values())
            dot.setStyleSheet(
                f"color: {'#34D399' if any_f else 'rgba(100,116,139,0.35)'}; font-size: 10px;"
            )

        expand_btn.clicked.connect(_toggle)
        return outer

    @staticmethod
    def _browse_file(inp: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            None, "Select file", "", "JSON files (*.json);;All files (*.*)"
        )
        if path:
            inp.setText(path)

    def _run_oauth(self, conn: dict) -> None:
        """Launch Google OAuth browser flow for this connector."""
        conn_id = conn["id"]
        scopes = conn.get("oauth_scopes", [])
        fields = self._field_widgets.get(conn_id, {})
        creds_inp = fields.get("credentials_path")
        if not creds_inp or not creds_inp.text().strip():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Missing credentials",
                "Set the credentials.json path first, then click Authorize.",
            )
            return

        creds_path = creds_inp.text().strip()
        token_inp = fields.get("token_path")

        import asyncio
        import threading
        from jarvis.connectors.oauth_server import run_google_oauth

        status_lbl = QLabel("Authorizing — check your browser…")
        status_lbl.setStyleSheet("color: #FBBF24; font-size: 12px; padding: 4px 0;")
        # Find the parent body layout to insert status
        body = creds_inp.parentWidget()
        while body and not isinstance(body.layout(), QVBoxLayout):
            body = body.parentWidget()
        if body and body.layout():
            body.layout().addWidget(status_lbl)

        def _run():
            loop = asyncio.new_event_loop()
            try:
                token_out = token_inp.text().strip() if token_inp else None
                result = loop.run_until_complete(
                    run_google_oauth(creds_path, scopes, token_out or None)
                )
                if result:
                    if token_inp:
                        token_inp.setText(result)
                    status_lbl.setText("✓ Authorized successfully")
                    status_lbl.setStyleSheet("color: #34D399; font-size: 12px; padding: 4px 0;")
                else:
                    status_lbl.setText("✗ Authorization failed — check activity log")
                    status_lbl.setStyleSheet("color: #FB7185; font-size: 12px; padding: 4px 0;")
            except Exception as exc:
                status_lbl.setText(f"✗ Error: {exc}")
                status_lbl.setStyleSheet("color: #FB7185; font-size: 12px; padding: 4px 0;")
            finally:
                loop.close()

        threading.Thread(target=_run, daemon=True).start()

    def get_settings(self) -> dict:
        result: dict = {}
        for conn_id, fields in self._field_widgets.items():
            entry: dict = {k: w.text().strip() for k, w in fields.items()}
            entry["enabled"] = self._enabled_checks.get(conn_id, QCheckBox()).isChecked()
            result[conn_id] = entry
        return result

class _ApiKeySetupDialog(QDialog):
    """Guided API-key setup dialog for Claude, OpenAI, Groq, Mistral, OpenRouter."""

    key_accepted = pyqtSignal(str)

    _CONFIGS: dict = {
        "claude": {
            "title": "Configure Provider Key",
            "btn": "Open Console →",
            "url": "https://console.anthropic.com/settings/keys",
            "instructions": (
                "1. Click 'Open Console' above\n"
                "2. Sign in or create an account\n"
                "3. In the left sidebar click 'API Keys'\n"
                "4. Click 'Create Key', give it a name and copy it\n"
                "5. Paste the key below (starts with sk-ant-…)"
            ),
        },
        "openai": {
            "title": "Get your OpenAI API Key",
            "btn": "Open Platform →",
            "url": "https://platform.openai.com/api-keys",
            "instructions": (
                "1. Click 'Open Platform' above — goes to platform.openai.com\n"
                "2. Sign in or create an OpenAI account\n"
                "3. In the left sidebar click 'API keys'\n"
                "4. Click '+ Create new secret key' and copy it\n"
                "   ⚠  You won't be able to see it again!\n"
                "5. Paste the key below (starts with sk-…)"
            ),
        },
        "groq": {
            "title": "Get your Groq API Key",
            "btn": "Open Console →",
            "url": "https://console.groq.com/keys",
            "instructions": (
                "1. Click 'Open Console' above — goes to console.groq.com\n"
                "2. Sign in or create a free Groq account\n"
                "3. Click 'Create API Key'\n"
                "4. Copy the key\n"
                "5. Paste it below"
            ),
        },
        "mistral": {
            "title": "Get your Mistral API Key",
            "btn": "Open Console →",
            "url": "https://console.mistral.ai/api-keys/",
            "instructions": (
                "1. Click 'Open Console' above — goes to console.mistral.ai\n"
                "2. Sign in or create an account\n"
                "3. Click 'Create new key'\n"
                "4. Copy the key\n"
                "5. Paste it below"
            ),
        },
        "openrouter": {
            "title": "Get your OpenRouter API Key",
            "btn": "Open OpenRouter →",
            "url": "https://openrouter.ai/settings/keys",
            "instructions": (
                "1. Click 'Open OpenRouter' above — goes to openrouter.ai\n"
                "2. Sign in or create an account\n"
                "3. Click 'Create Key'\n"
                "4. Copy the key\n"
                "5. Paste it below"
            ),
        },
    }

    def __init__(self, provider_name: str, parent=None):
        super().__init__(parent)
        cfg = self._CONFIGS.get(provider_name, {})
        self.setWindowTitle(cfg.get("title", "Get API Key"))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setMinimumSize(460, 380)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        open_btn = AnimatedButton(cfg.get("btn", "Open website →"))
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(cfg.get("url", ""))))
        layout.addWidget(open_btn)

        instr = QTextEdit()
        instr.setReadOnly(True)
        instr.setPlainText(cfg.get("instructions", ""))
        instr.setFixedHeight(130)
        instr.setObjectName("chatDisplay")
        layout.addWidget(instr)

        paste_lbl = QLabel("Paste API key here:")
        paste_lbl.setObjectName("muted")
        layout.addWidget(paste_lbl)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("Paste your key…")
        self._key_input.setMinimumHeight(36)
        layout.addWidget(self._key_input)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = AnimatedButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = AnimatedButton("Save Key")
        save_btn.setStyleSheet("font-weight:700;")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self) -> None:
        key = self._key_input.text().strip()
        if key:
            self.key_accepted.emit(key)
            self.accept()

class _HistoryDialog(QDialog):
    """Browse and load past chat sessions."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Chat History")
        self.resize(680, 520)
        self.setStyleSheet(parent.styleSheet())
        self._parent_window = parent
        self._sessions: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Search bar
        from PyQt6.QtWidgets import QLineEdit
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search conversations…")
        self._search.setStyleSheet(
            "background: rgba(15,23,42,0.8); border: 1px solid rgba(0,200,232,0.25);"
            "border-radius: 8px; padding: 6px 12px; color: #F8FAFC; font-size: 13px;"
        )
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        # Sessions list
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: rgba(10,16,32,0.9); border: 1px solid rgba(0,200,232,0.15);"
            "border-radius: 10px; padding: 4px; }"
            "QListWidget::item { padding: 10px 14px; border-radius: 6px; color: #E2E8F0; }"
            "QListWidget::item:selected { background: rgba(0,200,232,0.18); color: #FFFFFF; }"
            "QListWidget::item:hover { background: rgba(0,200,232,0.08); }"
        )
        self._list.setAlternatingRowColors(False)
        layout.addWidget(self._list, 1)

        # Buttons
        from PyQt6.QtWidgets import QHBoxLayout
        btn_row = QHBoxLayout()
        load_btn = AnimatedButton("Load session")
        load_btn.clicked.connect(self._load_selected)
        btn_row.addWidget(load_btn)
        btn_row.addStretch()
        close_btn = AnimatedButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._list.itemDoubleClicked.connect(self._load_selected)

    def _populate(self, sessions: list[dict]) -> None:
        from PyQt6.QtWidgets import QListWidgetItem
        self._sessions = sessions
        self._render(sessions)

    def _render(self, sessions: list[dict]) -> None:
        self._list.clear()
        for s in sessions:
            updated = (s.get("updated_at") or "")[:16].replace("T", " ")
            count = s.get("message_count", 0)
            title = s.get("title") or "(untitled)"
            label = f"{updated}  ·  {title[:60]}  [{count} msgs]"
            item = __import__("PyQt6.QtWidgets", fromlist=["QListWidgetItem"]).QListWidgetItem(label)
            item.setData(256, s["session_id"])  # Qt.UserRole = 256
            self._list.addItem(item)

    def _filter(self, text: str) -> None:
        if not text:
            self._render(self._sessions)
            return
        filtered = [
            s for s in self._sessions
            if text.lower() in (s.get("title") or "").lower()
        ]
        self._render(filtered)

    def _load_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        session_id = item.data(256)
        self._parent_window.runtime.load_session(session_id)
        self._parent_window.chat_display.clear()
        self.close()


class _GeminiAuthDialog(QDialog):
    """Auth dialog for Gemini: API key tab + Google OAuth tab."""

    key_accepted = pyqtSignal(str)
    oauth_token_saved = pyqtSignal(str)

    _GEMINI_SCOPES = ["https://www.googleapis.com/auth/generative-language"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gemini Authentication")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setMinimumSize(500, 440)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        from PyQt6.QtWidgets import QTabWidget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        tabs = QTabWidget()

        # Tab 1: API Key
        key_tab = QWidget()
        kl = QVBoxLayout(key_tab)
        kl.setContentsMargins(20, 16, 20, 16)
        kl.setSpacing(12)

        open_btn = AnimatedButton("Open Google AI Studio →")
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://aistudio.google.com/apikey"))
        )
        kl.addWidget(open_btn)

        instr = QTextEdit()
        instr.setReadOnly(True)
        instr.setPlainText(
            "1. Click 'Open Google AI Studio' above\n"
            "2. Sign in with your Google account\n"
            "3. Click 'Create API key'\n"
            "4. Copy the generated key (starts with AIza…)\n"
            "5. Paste it below and click Save"
        )
        instr.setFixedHeight(110)
        instr.setObjectName("chatDisplay")
        kl.addWidget(instr)

        kl.addWidget(self._muted("Paste API key:"))
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setMinimumHeight(36)
        kl.addWidget(self._key_input)

        key_row = QHBoxLayout()
        key_row.addStretch()
        save_key_btn = AnimatedButton("Save API Key")
        save_key_btn.setStyleSheet("font-weight:700;")
        save_key_btn.clicked.connect(self._save_key)
        key_row.addWidget(save_key_btn)
        kl.addLayout(key_row)
        kl.addStretch()

        tabs.addTab(key_tab, "API Key")

        # Tab 2: Google OAuth
        oauth_tab = QWidget()
        ol = QVBoxLayout(oauth_tab)
        ol.setContentsMargins(20, 16, 20, 16)
        ol.setSpacing(12)

        info = QLabel(
            "Uses Google OAuth 2.0 — no API key needed.\n\n"
            "Requires a credentials.json from Google Cloud Console:\n"
            "  APIs & Services → Credentials → Create OAuth 2.0 Client ID\n"
            "  Application type: Desktop application"
        )
        info.setObjectName("muted")
        info.setWordWrap(True)
        ol.addWidget(info)

        ol.addWidget(self._muted("credentials.json path:"))
        creds_row = QHBoxLayout()
        self._creds_input = QLineEdit()
        self._creds_input.setPlaceholderText("C:/Users/…/credentials.json")
        browse_btn = AnimatedButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_creds)
        creds_row.addWidget(self._creds_input, 1)
        creds_row.addWidget(browse_btn)
        ol.addLayout(creds_row)

        ol.addWidget(self._muted("Save token to (leave blank for default):"))
        self._token_input = QLineEdit()
        from pathlib import Path as _Path
        self._token_input.setText(str(_Path.home() / ".jarvis" / "gemini_token.json"))
        ol.addWidget(self._token_input)

        self._oauth_status = QLabel("")
        self._oauth_status.setWordWrap(True)
        ol.addWidget(self._oauth_status)

        auth_row = QHBoxLayout()
        auth_row.addStretch()
        auth_btn = AnimatedButton("Authorize with Google →")
        auth_btn.setStyleSheet("font-weight:700;")
        auth_btn.clicked.connect(self._run_oauth)
        auth_row.addWidget(auth_btn)
        ol.addLayout(auth_row)
        ol.addStretch()

        tabs.addTab(oauth_tab, "Google OAuth")
        layout.addWidget(tabs, 1)

        close_row = QHBoxLayout()
        close_row.setContentsMargins(16, 4, 16, 0)
        close_row.addStretch()
        close_btn = AnimatedButton("Close")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    @staticmethod
    def _muted(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("muted")
        return lbl

    def _save_key(self) -> None:
        key = self._key_input.text().strip()
        if key:
            self.key_accepted.emit(key)
            self.accept()

    def _browse_creds(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select credentials.json", "", "JSON files (*.json);;All files (*.*)"
        )
        if path:
            self._creds_input.setText(path)

    def _run_oauth(self) -> None:
        creds_path = self._creds_input.text().strip()
        if not creds_path:
            self._oauth_status.setText("Set the credentials.json path first.")
            self._oauth_status.setStyleSheet("color: #FB7185;")
            return

        token_out = self._token_input.text().strip() or None
        if token_out:
            from pathlib import Path as _Path
            _Path(token_out).parent.mkdir(parents=True, exist_ok=True)

        import asyncio
        import threading
        from jarvis.connectors.oauth_server import run_google_oauth

        self._oauth_status.setText("Opening browser for Google authorization…")
        self._oauth_status.setStyleSheet("color: #FBBF24;")

        def _run():
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    run_google_oauth(creds_path, self._GEMINI_SCOPES, token_out)
                )
                if result:
                    QTimer.singleShot(0, lambda: self._on_oauth_success(result))
                else:
                    QTimer.singleShot(0, self._on_oauth_failure)
            except Exception as exc:
                err = str(exc)
                QTimer.singleShot(0, lambda: self._on_oauth_error(err))
            finally:
                loop.close()

        threading.Thread(target=_run, daemon=True).start()

    def _on_oauth_success(self, token_path: str) -> None:
        self._oauth_status.setText(f"✓ Authorized!  Token saved to:\n{token_path}")
        self._oauth_status.setStyleSheet("color: #34D399;")
        self.oauth_token_saved.emit(token_path)

    def _on_oauth_failure(self) -> None:
        self._oauth_status.setText("✗ Authorization failed — check the activity log.")
        self._oauth_status.setStyleSheet("color: #FB7185;")

    def _on_oauth_error(self, msg: str) -> None:
        self._oauth_status.setText(f"✗ Error: {msg}")
        self._oauth_status.setStyleSheet("color: #FB7185;")

class _DonutGauge(QWidget):
    """Small circular arc gauge with label and percentage."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = QColor(color)
        self._value = 0
        self.setFixedSize(60, 70)

    def set_value(self, v: int) -> None:
        self._value = max(0, min(100, v))
        self.update()

    def paintEvent(self, event) -> None:
        from PyQt6.QtGui import QPainter, QPen, QFont
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 30, 28, 22
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        bg = QColor(self._color)
        bg.setAlpha(30)
        pen = QPen(bg, 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 225 * 16, -270 * 16)

        pen2 = QPen(self._color, 5)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen2)
        span = int(-270 * 16 * self._value / 100)
        p.drawArc(rect, 225 * 16, span)

        p.setPen(QColor(self._color))
        f = QFont()
        f.setPixelSize(10)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 18, 60, 20), Qt.AlignmentFlag.AlignCenter, f"{self._value}%")

        p.setPen(QColor(148, 163, 184, 180))
        f2 = QFont()
        f2.setPixelSize(9)
        p.setFont(f2)
        p.drawText(QRectF(0, 54, 60, 14), Qt.AlignmentFlag.AlignCenter, self._label)


class _MiniGraph(QWidget):
    """Tiny scrolling line graph for network activity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples: list[float] = [0.0] * 40
        self._color = QColor("#00C8E8")

    def push(self, value: float) -> None:
        self._samples.append(max(0.0, value))
        if len(self._samples) > 40:
            self._samples.pop(0)
        self.update()

    def paintEvent(self, event) -> None:
        from PyQt6.QtGui import QPainter, QPen, QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mx = max(self._samples) or 1.0
        step = w / max(len(self._samples) - 1, 1)
        path = QPainterPath()
        for i, v in enumerate(self._samples):
            x = i * step
            y = h - (v / mx) * (h - 4) - 2
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        pen = QPen(self._color, 1.5)
        p.setPen(pen)
        p.drawPath(path)


class _PomodoroDialog(QDialog):
    """Standalone Pomodoro timer with work/break controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pomodoro Timer")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowCloseButtonHint)
        self.setFixedSize(280, 280)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._remaining = 25 * 60
        self._running = False
        self._work_mins = 25
        self._break_mins = 5
        self._is_break = False
        self._qtimer = QTimer(self)
        self._qtimer.setInterval(1000)
        self._qtimer.timeout.connect(self._tick)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self._phase_label = QLabel("Work")
        self._phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._phase_label.setStyleSheet("font-size: 12px; color: rgba(0,200,232,0.80); font-weight: 600; letter-spacing: 2px;")
        layout.addWidget(self._phase_label)

        self._time_label = QLabel("25:00")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_label.setStyleSheet("font-size: 48px; font-weight: 200; color: #E2E8F0; letter-spacing: 4px;")
        layout.addWidget(self._time_label)

        # Work / Break spin controls
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(8)
        for label, attr, default in [("Work", "_work_mins", 25), ("Break", "_break_mins", 5)]:
            lbl = QLabel(label)
            lbl.setStyleSheet("color: rgba(148,163,184,0.70); font-size: 11px;")
            cfg_row.addWidget(lbl)
            spin = QSpinBox()
            spin.setRange(1, 60)
            spin.setValue(default)
            spin.setSuffix(" min")
            spin.setFixedWidth(72)
            spin.valueChanged.connect(lambda v, a=attr: setattr(self, a, v))
            cfg_row.addWidget(spin)
        layout.addLayout(cfg_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._start_btn = AnimatedButton("Start")
        self._start_btn.clicked.connect(self._toggle)
        self._reset_btn = AnimatedButton("Reset")
        self._reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._reset_btn)
        layout.addLayout(btn_row)

    def _toggle(self):
        self._running = not self._running
        if self._running:
            self._qtimer.start()
            self._start_btn.setText("Pause")
        else:
            self._qtimer.stop()
            self._start_btn.setText("Resume")

    def _reset(self):
        self._qtimer.stop()
        self._running = False
        self._is_break = False
        self._remaining = self._work_mins * 60
        self._start_btn.setText("Start")
        self._phase_label.setText("Work")
        self._time_label.setText(f"{self._work_mins:02d}:00")

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._qtimer.stop()
            self._running = False
            self._is_break = not self._is_break
            if self._is_break:
                self._remaining = self._break_mins * 60
                self._phase_label.setText("Break")
            else:
                self._remaining = self._work_mins * 60
                self._phase_label.setText("Work")
            try:
                from plyer import notification
                notification.notify(title="JARVIS Pomodoro",
                                    message="Break time!" if self._is_break else "Back to work!",
                                    timeout=5)
            except Exception:
                pass
            self._start_btn.setText("Start")
        m, s = divmod(self._remaining, 60)
        self._time_label.setText(f"{m:02d}:{s:02d}")


class _ImageGenDialog(QDialog):
    """Image generation prompt panel with style presets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Generator")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowCloseButtonHint)
        self.setFixedSize(360, 220)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._on_generate = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        lbl = QLabel("Image prompt")
        lbl.setObjectName("panelTitle")
        layout.addWidget(lbl)

        self._prompt = QLineEdit()
        self._prompt.setPlaceholderText("Describe what to generate…")
        self._prompt.setFixedHeight(36)
        layout.addWidget(self._prompt)

        style_row = QHBoxLayout()
        style_lbl = QLabel("Style")
        style_lbl.setStyleSheet("color: rgba(148,163,184,0.70); font-size: 11px;")
        style_row.addWidget(style_lbl)
        self._style_combo = QComboBox()
        self._style_combo.setFixedWidth(180)
        for s in ["Photorealistic", "Digital art", "Oil painting", "Anime",
                  "Watercolor", "3D render", "Sketch", "Cinematic"]:
            self._style_combo.addItem(s)
        style_row.addWidget(self._style_combo)
        style_row.addStretch()
        layout.addLayout(style_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        gen_btn = AnimatedButton("Generate")
        gen_btn.setFixedWidth(100)
        gen_btn.clicked.connect(self._do_generate)
        btn_row.addWidget(gen_btn)
        layout.addLayout(btn_row)

    def _do_generate(self):
        prompt = self._prompt.text().strip()
        style  = self._style_combo.currentText()
        if prompt and callable(self._on_generate):
            self._on_generate(prompt, style)
            self.hide()


class _PanelDialog(QDialog):
    """Thin wrapper that turns a settings frame into a popout dialog."""

    def __init__(self, title: str, content: QWidget, save_cb, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.resize(460, 720)
        self.setMinimumSize(420, 500)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area so content never hides the footer buttons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 5px; }"
            "QScrollBar::handle:vertical { background: rgba(139,124,255,0.25); border-radius: 2px; }"
        )
        layout.addWidget(scroll, 1)

        # Always-visible footer
        footer = QFrame()
        footer.setStyleSheet("QFrame { border-top: 1px solid rgba(139,124,255,0.15); background: rgba(10,14,24,0.72); }")
        btn_row = QHBoxLayout(footer)
        btn_row.setContentsMargins(16, 8, 16, 10)
        btn_row.addStretch()
        close_btn = AnimatedButton("Close")
        close_btn.clicked.connect(self.hide)
        save_btn = AnimatedButton("Save & Apply")
        save_btn.setStyleSheet("font-weight:700;")
        save_btn.clicked.connect(lambda: (save_cb(), self.hide()))
        btn_row.addWidget(close_btn)
        btn_row.addWidget(save_btn)
        layout.addWidget(footer)

class _PluginsDialog(QDialog):
    """Floating plugins manager — list, enable / disable all JARVIS plugins."""

    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self._runtime = runtime
        self._rows: dict[str, tuple] = {}  # name -> (dot, toggle)
        self.setWindowTitle("Plugins")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.resize(480, 640)
        self.setMinimumSize(380, 400)
        if parent:
            self.setStyleSheet(parent.styleSheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setStyleSheet(
            "QFrame { background: rgba(10,14,39,0.92); border-bottom: 1px solid rgba(139,124,255,0.18); }"
        )
        tb_row = QHBoxLayout(toolbar)
        tb_row.setContentsMargins(16, 10, 16, 10)
        title_lbl = QLabel("Plugins")
        title_lbl.setStyleSheet("font-size:15px; font-weight:600; color:#C8D8F4; letter-spacing:1px;")
        tb_row.addWidget(title_lbl)
        tb_row.addStretch()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter…")
        self._search.setFixedWidth(160)
        self._search.setStyleSheet(
            "QLineEdit { background: rgba(15,23,42,0.70); border: 1px solid rgba(139,124,255,0.20);"
            "  border-radius: 6px; padding: 4px 8px; color: #E2E8F0; font-size: 12px; }"
        )
        self._search.textChanged.connect(self._filter)
        tb_row.addWidget(self._search)
        refresh_btn = AnimatedButton("↻ Refresh")
        refresh_btn.setFixedHeight(28)
        refresh_btn.clicked.connect(self._do_refresh)
        tb_row.addWidget(refresh_btn)
        root.addWidget(toolbar)

        # ── Scrollable plugin list ────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 5px; }"
            "QScrollBar::handle:vertical { background: rgba(139,124,255,0.25); border-radius: 2px; }"
        )
        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(12, 8, 12, 8)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, 1)

        # ── Footer ────────────────────────────────────────────────────
        footer = QFrame()
        footer.setStyleSheet("QFrame { border-top: 1px solid rgba(139,124,255,0.15); background: rgba(10,14,24,0.72); }")
        ft_row = QHBoxLayout(footer)
        ft_row.setContentsMargins(16, 8, 16, 10)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: rgba(148,163,184,0.60); font-size: 11px;")
        ft_row.addWidget(self._status_lbl, 1)
        close_btn = AnimatedButton("Close")
        close_btn.clicked.connect(self.hide)
        ft_row.addWidget(close_btn)
        root.addWidget(footer)

    def showEvent(self, event):
        super().showEvent(event)
        self._do_refresh()

    def _do_refresh(self):
        self._status_lbl.setText("Loading…")
        self._runtime.list_plugins()

    def update_plugins(self, plugins: list[dict]):
        # Clear list (keep stretch at end)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()

        enabled_count = sum(1 for p in plugins if p.get("enabled", True))
        self._status_lbl.setText(f"{enabled_count} of {len(plugins)} enabled")

        filter_text = self._search.text().lower()
        for p in sorted(plugins, key=lambda x: x["name"]):
            name = p["name"]
            enabled = p.get("enabled", True)
            if filter_text and filter_text not in name.lower():
                continue

            row_widget = QFrame()
            row_widget.setStyleSheet(
                "QFrame { background: rgba(15,22,45,0.55); border: 1px solid rgba(139,124,255,0.10);"
                "  border-radius: 8px; }"
                "QFrame:hover { border-color: rgba(139,124,255,0.28); }"
            )
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(12, 8, 12, 8)
            row.setSpacing(10)

            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setStyleSheet(f"color: {'#34D399' if enabled else 'rgba(148,163,184,0.35)'}; font-size: 10px;")
            row.addWidget(dot)

            name_lbl = QLabel(name.replace("_", " ").title())
            name_lbl.setStyleSheet("color: #C8D8F4; font-size: 12px; font-weight: 500;")
            row.addWidget(name_lbl, 1)

            toggle = AnimatedButton("Disable" if enabled else "Enable")
            toggle.setFixedHeight(26)
            toggle.setFixedWidth(72)
            toggle.setStyleSheet(
                f"font-size:11px; font-weight:600; "
                f"color:{'#FF5C7A' if enabled else '#2DE8B0'};"
            )
            toggle.clicked.connect(
                lambda _, n=name, e=enabled: (
                    self._runtime.disable_plugin(n) if e else self._runtime.enable_plugin(n),
                    QTimer.singleShot(300, self._do_refresh),
                )
            )
            row.addWidget(toggle)

            self._rows[name] = (dot, toggle)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row_widget)

    def _filter(self, text: str):
        text = text.lower()
        for i in range(self._list_layout.count() - 1):
            item = self._list_layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                name_lbl = w.findChild(QLabel)
                visible = not text or (name_lbl and text in name_lbl.text().lower())
                w.setVisible(visible)


class AdvancedChatWindow(QMainWindow):
    def __init__(self, runtime, demo_mode: bool = False):
        super().__init__()
        self.runtime = runtime
        self.demo_mode = demo_mode
        self.settings = {}
        self._quitting = False
        self.provider_cards = {}
        self.current_status = "idle"
        self.current_response_style = "calm"
        self._command_history: list[str] = []
        self._history_index: int = -1
        self._plugin_rows: dict[str, QWidget] = {}
        self._streaming_active: bool = False
        self._stream_anchor: int | None = None
        self._last_jarvis_response: str = ""
        self._last_user_message: str = ""
        self._search_visible: bool = False
        self._chat_font_size: int = 14
        self._elapsed_start: float = 0.0
        self._elapsed_timer = QTimer()
        self._elapsed_timer.setInterval(200)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        # Feature: thinking animation
        self._thinking_bubble_active: bool = False
        self._thinking_dot_phase: int = 0
        self._thinking_timer = QTimer()
        self._thinking_timer.setInterval(400)
        self._thinking_timer.timeout.connect(self._tick_thinking_dots)

        # Feature: message ratings
        self._message_ratings: list[dict] = []

        # Feature: tool call tracking in chat
        self._active_tool_block_id: str | None = None

        # Feature: system resource timer
        self._sys_timer = QTimer()
        self._sys_timer.setInterval(2000)
        self._sys_timer.timeout.connect(self._update_sys_resources)

        # Feature 1: Quick-reply chips
        self._quick_reply_suggestions: list[str] = []

        # Feature 2: Status bar
        self._status_bar: QLabel | None = None
        self._message_count: int = 0
        self._total_token_estimate: int = 0

        # Raw conversation log — used by _export_chat to preserve code blocks
        self._raw_conversation_log: list[dict] = []

        # Feature 3: Help tips
        self._help_tip_index: int = 0
        self._help_tip_shown_this_session: bool = False
        self._help_tips = [
            "Try: 'Open Chrome and search for Python tutorials'",
            "Try: 'Take a screenshot and describe what you see'",
            "Tip: Use Ctrl+K to open the command palette",
            "Try: 'Write a Python script that lists all files in Downloads'",
            "Tip: Say 'Hey JARVIS' to activate voice control",
            "Try: 'Create a workflow to check the news then send me a summary'",
        ]

        self.runtime.bridge.event_received.connect(self._handle_runtime_event)
        self.overlay_window = OrbOverlayWindow()
        self.overlay_window.restore_requested.connect(self._restore_from_overlay)
        self.overlay_window.quit_requested.connect(self._quit_from_tray)
        self.computer_use_overlay = ComputerUseOverlay()
        from jarvis.ui.subtitle_overlay import SubtitleOverlay
        self._subtitle_overlay = SubtitleOverlay()
        from jarvis.ui.notification_toast import NotificationToast
        self.notification_toast = NotificationToast()
        self.notification_toast.help_requested.connect(self._on_proactive_help)
        self.notification_toast.dismissed.connect(self._on_proactive_dismiss)
        self._build_ui()
        self._setup_tray()
        # Start system resource polling if psutil is available
        if _PSUTIL_AVAILABLE:
            self._sys_timer.start()
            self._update_sys_resources()

        # Initialise UIBridge on the Qt main thread so async tool calls can
        # open/update panel dialogs safely from any thread.
        UIBridge.init()
        UIBridge.set_parent_window(self)

        if self.demo_mode:
            self._schedule_demo_messages()

    def _schedule_demo_messages(self) -> None:
        """Auto-send demo messages on a timed schedule."""
        # Message 1: after 2 seconds
        QTimer.singleShot(2000, lambda: self._auto_send_demo_message("What time is it?"))
        # Message 2: after 5 seconds (2s + 3s)
        QTimer.singleShot(5000, lambda: self._auto_send_demo_message("Show me my system info"))
        # Message 3: after 9 seconds (5s + 4s)
        QTimer.singleShot(9000, lambda: self._auto_send_demo_message("List files in my Downloads folder"))

    def _auto_send_demo_message(self, message: str) -> None:
        """Auto-populate and send a demo message."""
        if self.input_field and not self._quitting:
            self.input_field.setText(message)
            self._send_message()

    def _build_ui(self) -> None:
        self.setWindowTitle("JARVIS")
        self.resize(1280, 860)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(self._stylesheet())

        root = HUDRootWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())

        # Three-panel splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("splitter")
        splitter.setHandleWidth(8)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_column())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([240, 780, 260])
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(2, True)
        layout.addWidget(splitter, 1)

        # Build settings panels as hidden popout dialogs
        ctrl_frame = self._build_control_column()
        prov_frame = self._build_provider_column()
        self._settings_dlg = _PanelDialog("Assistant Controls", ctrl_frame, self._save_settings, parent=self)
        self._ai_dlg = _PanelDialog("Providers & Diagnostics", prov_frame, self._save_settings, parent=self)
        self._plugins_dlg = _PluginsDialog(self.runtime, parent=self)

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("headerPanel")
        frame.setMinimumHeight(64)
        frame.setMaximumHeight(78)
        root_layout = QVBoxLayout(frame)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top_row = QWidget()
        header = QHBoxLayout(top_row)
        header.setContentsMargins(20, 8, 20, 8)
        header.setSpacing(10)

        # Left — model info block with inline quick-select combo
        model_block = QWidget()
        model_block.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        model_block_layout = QVBoxLayout(model_block)
        model_block_layout.setContentsMargins(0, 0, 0, 0)
        model_block_layout.setSpacing(2)
        _model_label = QLabel("MODEL")
        _model_label.setObjectName("panelTitle")
        model_block_layout.addWidget(_model_label)

        # Quick model/provider combo inline in header
        self._header_model_combo = QComboBox()
        self._header_model_combo.setFixedHeight(22)
        self._header_model_combo.setMinimumWidth(160)
        self._header_model_combo.setMaximumWidth(240)
        self._header_model_combo.setStyleSheet(
            "QComboBox { background: rgba(0,200,232,0.06); border: none; border-radius: 5px;"
            "  padding: 1px 8px; color: #E2E8F0; font-size: 12px; font-weight: 500; }"
            "QComboBox::drop-down { border: none; width: 14px; }"
            "QComboBox::down-arrow { width: 8px; height: 8px; }"
            "QComboBox QAbstractItemView { background: #08101e; border: none;"
            "  color: #E2E8F0; selection-background-color: rgba(0,200,232,0.15); }"
        )
        for label, data in [
            ("Auto", "auto"), ("Local", "llamacpp"), ("Ollama", "ollama"),
            ("Groq", "groq"), ("Gemini", "gemini"), ("Claude", "claude"),
            ("OpenAI", "openai"), ("Mistral", "mistral"), ("OpenRouter", "openrouter"),
        ]:
            self._header_model_combo.addItem(label, data)
        self._header_model_combo.currentIndexChanged.connect(self._on_quick_provider_changed)
        self._header_model_combo.setToolTip("Switch provider")
        model_block_layout.addWidget(self._header_model_combo)

        # Hidden compat label kept for update code that sets _provider_badge
        self._provider_badge = QLabel("—")
        self._provider_badge.hide()

        header.addWidget(model_block)

        # Hidden chips kept for compatibility with _apply_status / _apply_settings_to_ui
        self.status_chip = QLabel()
        self.status_chip.hide()
        self.mode_chip = QLabel()
        self.mode_chip.hide()

        header.addStretch()

        # Clock group — date and time side by side, centered in header
        now = datetime.now()
        clock_group = QWidget()
        clock_group.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        clock_row = QHBoxLayout(clock_group)
        clock_row.setContentsMargins(0, 0, 0, 0)
        clock_row.setSpacing(14)

        self._date_label = QLabel(now.strftime("%a, %b %d %Y"))
        self._date_label.setObjectName("clockLabel")
        self._date_label.setStyleSheet(
            "font-size:12px; font-weight:400; color:#7A8DAE; letter-spacing:0.5px;"
        )
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        clock_row.addWidget(self._date_label)

        self._clock_label = QLabel(now.strftime("%H:%M:%S"))
        self._clock_label.setObjectName("clockLabel")
        self._clock_label.setStyleSheet(
            "font-size:20px; font-weight:300; color:#C8D8F4; letter-spacing:2px;"
        )
        self._clock_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        clock_row.addWidget(self._clock_label)

        self._clock_update_timer = QTimer()
        self._clock_update_timer.timeout.connect(self._tick_clock)
        self._clock_update_timer.start(1000)

        header.addWidget(clock_group)
        header.addStretch()

        # Right — action buttons
        self._elapsed_label = QLabel("")
        self._elapsed_label.setObjectName("muted")
        self._elapsed_label.setFixedWidth(72)
        self._elapsed_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._elapsed_label)

        self.orb_only_button = AnimatedButton("Orb only")
        self.orb_only_button.clicked.connect(self._show_overlay_only)
        header.addWidget(self.orb_only_button)

        shortcuts_btn = AnimatedButton("?")
        shortcuts_btn.setFixedWidth(34)
        shortcuts_btn.setToolTip("Keyboard shortcuts")
        shortcuts_btn.clicked.connect(self._show_shortcuts_panel)
        header.addWidget(shortcuts_btn)

        bug_btn = AnimatedButton("Report bug")
        bug_btn.setToolTip("Fill out and send a bug report to the developer")
        bug_btn.clicked.connect(self._open_bug_report)
        header.addWidget(bug_btn)

        settings_btn = AnimatedButton("Settings")
        settings_btn.setToolTip("Assistant controls & settings")
        settings_btn.clicked.connect(lambda: self._settings_dlg.show())
        header.addWidget(settings_btn)

        ai_btn = AnimatedButton("Providers")
        ai_btn.setToolTip("Providers & diagnostics")
        ai_btn.clicked.connect(lambda: self._ai_dlg.show())
        header.addWidget(ai_btn)

        ollama_btn = AnimatedButton("Models")
        ollama_btn.setToolTip("Manage Ollama models")
        ollama_btn.clicked.connect(self._open_ollama_manager)
        header.addWidget(ollama_btn)

        plugins_btn = AnimatedButton("Plugins")
        plugins_btn.setToolTip("Enable / disable JARVIS plugins")
        plugins_btn.clicked.connect(lambda: self._plugins_dlg.show())
        header.addWidget(plugins_btn)

        for btn_label, btn_tip, btn_slot in [
            ("Transcript", "Browse conversation transcript", self._open_transcript),
            ("MCPs",       "Manage MCP tool servers",        self._open_mcp_manager),
            ("SSH",        "Manage SSH connections",          self._open_ssh_manager),
        ]:
            _b = AnimatedButton(btn_label)
            _b.setToolTip(btn_tip)
            _b.clicked.connect(btn_slot)
            header.addWidget(_b)

        # Chip pulse timer removed — chips hidden, no CPU cost needed
        self._chip_phase = 0.0

        root_layout.addWidget(top_row)

        return frame

    def _pulse_chip(self) -> None:
        self._chip_phase += 0.04
        alpha = int(140 + 115 * math.sin(self._chip_phase))
        color = STATUS_COLORS.get(self.current_status, STATUS_COLORS["idle"])
        r, g, b = color.red(), color.green(), color.blue()
        self.status_chip.setStyleSheet(
            f"background: rgba({r},{g},{b},0.07);"
            f"border: 1px solid rgba({r},{g},{b},{alpha});"
            f"color: rgb({r},{g},{b});"
            f"padding: 4px 10px; border-radius: 4px;"
            f"letter-spacing: 2px; font-size: 10px; font-weight: 600;"
        )

    def _build_control_column(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        # Scrollable settings area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        inner = QVBoxLayout(scroll_content)
        inner.setContentsMargins(0, 0, 8, 0)
        inner.setSpacing(10)
        scroll.setWidget(scroll_content)

        section_title = QLabel("ASSISTANT CONTROLS")
        section_title.setObjectName("panelTitle")
        inner.addWidget(section_title)

        self.voice_toggle = QCheckBox("Voice enabled")
        self.screen_toggle = QCheckBox("Screen awareness")
        self.voice_toggle.setChecked(True)
        self.screen_toggle.setChecked(True)
        self.voice_toggle.toggled.connect(self._on_voice_toggle_changed)
        inner.addWidget(self.voice_toggle)
        inner.addWidget(self.screen_toggle)

        self.watcher_toggle = QCheckBox("Proactive screen watcher")
        self.watcher_toggle.setChecked(False)
        self.watcher_toggle.setToolTip(
            "Periodically capture the screen and suggest help when JARVIS detects "
            "something it can assist with"
        )
        inner.addWidget(self.watcher_toggle)

        mute_row = QHBoxLayout()
        self._mute_button = AnimatedButton("Mute mic")
        self._mute_button.setToolTip("Temporarily mute/unmute the microphone without saving settings")
        self._mute_button.setCheckable(True)
        self._mute_button.clicked.connect(self._toggle_mic_mute)
        mute_row.addWidget(self._mute_button)
        mute_row.addStretch()
        inner.addLayout(mute_row)

        from jarvis.utils.startup_manager import is_startup_enabled
        self.startup_toggle = QCheckBox("Start with Windows")
        self.startup_toggle.setChecked(is_startup_enabled())
        self.startup_toggle.setToolTip("Launch JARVIS automatically when Windows starts")
        self.startup_toggle.toggled.connect(self._on_startup_toggled)
        inner.addWidget(self.startup_toggle)

        self.start_minimized_toggle = QCheckBox("Start minimized (orb only)")
        self.start_minimized_toggle.setChecked(False)
        self.start_minimized_toggle.setToolTip("Start as floating orb instead of showing the full window")
        inner.addWidget(self.start_minimized_toggle)

        wdir_row = QHBoxLayout()
        wdir_lbl = QLabel("Working dir")
        wdir_lbl.setObjectName("muted")
        wdir_lbl.setFixedWidth(76)
        self._wdir_input = QLineEdit()
        self._wdir_input.setPlaceholderText("Default: user home")
        self._wdir_input.setToolTip("Directory JARVIS uses for file operations and relative paths")
        self._wdir_browse = AnimatedButton("Browse")
        self._wdir_browse.setFixedWidth(62)
        self._wdir_browse.clicked.connect(self._browse_working_dir)
        wdir_row.addWidget(wdir_lbl)
        wdir_row.addWidget(self._wdir_input, 1)
        wdir_row.addWidget(self._wdir_browse)
        inner.addLayout(wdir_row)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.primary_provider_combo = QComboBox()
        self.primary_provider_combo.addItem("Auto  (fallback chain)", "auto")
        self.primary_provider_combo.addItem("Local  (llama.cpp)", "llamacpp")
        self.primary_provider_combo.addItem("Ollama  (local only)", "ollama")
        self.primary_provider_combo.addItem("Groq  (cloud only)", "groq")
        self.primary_provider_combo.addItem("Gemini  (cloud only)", "gemini")
        self.primary_provider_combo.addItem("Claude  (cloud only)", "claude")
        self.primary_provider_combo.addItem("OpenAI  (cloud only)", "openai")
        self.primary_provider_combo.addItem("Mistral  (cloud only)", "mistral")
        self.primary_provider_combo.addItem("OpenRouter  (cloud only)", "openrouter")
        form.addRow("Provider", self.primary_provider_combo)

        self.policy_combo = QComboBox()
        self.policy_combo.addItem("Ask before actions", "ask")
        self.policy_combo.addItem("Auto-run safe actions", "safe_auto")
        self.policy_combo.addItem("Fully autonomous", "full_auto")
        form.addRow("Automation", self.policy_combo)

        self.background_mode_combo = QComboBox()
        self.background_mode_combo.addItem("Wake phrase only", "wake_phrase")
        self.background_mode_combo.addItem("Always listening", "always_listening")
        form.addRow("Background voice", self.background_mode_combo)

        self.overlay_mode_combo = QComboBox()
        self.overlay_mode_combo.addItem("Floating", "floating")
        self.overlay_mode_combo.addItem("Smart overlay", "smart_overlay")
        self.overlay_mode_combo.addItem("Docked", "docked")
        form.addRow("Overlay mode", self.overlay_mode_combo)
        inner.addLayout(form)

        # Response voice
        voice_header = QLabel("RESPONSE VOICE")
        voice_header.setObjectName("panelTitle")
        inner.addWidget(voice_header)

        voice_row = QHBoxLayout()
        self.voice_profile_combo = QComboBox()
        self._populate_voice_profiles()
        self.voice_preview_button = AnimatedButton("Preview")
        self.voice_preview_button.clicked.connect(self._preview_voice)
        voice_row.addWidget(self.voice_profile_combo, 1)
        voice_row.addWidget(self.voice_preview_button)
        inner.addLayout(voice_row)

        custom_form = QFormLayout()
        custom_form.setVerticalSpacing(8)
        self.custom_voice_label = QLineEdit()
        self.custom_voice_label.setPlaceholderText("Imported label")
        self.custom_voice_name = QLineEdit()
        self.custom_voice_name.setPlaceholderText("Edge voice name, e.g. en-US-AndrewNeural")
        self.custom_voice_rate = QLineEdit()
        self.custom_voice_rate.setPlaceholderText("-2%")
        self.custom_voice_pitch = QLineEdit()
        self.custom_voice_pitch.setPlaceholderText("-1Hz")
        custom_form.addRow("Custom label", self.custom_voice_label)
        custom_form.addRow("Voice name", self.custom_voice_name)
        custom_form.addRow("Rate", self.custom_voice_rate)
        custom_form.addRow("Pitch", self.custom_voice_pitch)
        inner.addLayout(custom_form)

        custom_actions = QHBoxLayout()
        self.import_voice_button = AnimatedButton("Import voice profile")
        self.import_voice_button.clicked.connect(self._import_voice_profile)
        self.voice_guide_button = AnimatedButton("Voice guide")
        self.voice_guide_button.clicked.connect(self._open_voice_guide)
        custom_actions.addWidget(self.import_voice_button)
        custom_actions.addWidget(self.voice_guide_button)
        inner.addLayout(custom_actions)

        self.last_heard_label = QLabel("Last heard: --")
        self.last_heard_label.setWordWrap(True)
        self.last_heard_label.setObjectName("muted")
        inner.addWidget(self.last_heard_label)

        # STT settings
        stt_header = QLabel("STT SETTINGS")
        stt_header.setObjectName("panelTitle")
        inner.addWidget(stt_header)

        stt_form = QFormLayout()
        stt_form.setVerticalSpacing(8)

        self.mic_device_combo = QComboBox()
        self.mic_device_combo.addItem("Default", None)
        self._populate_mic_devices()
        stt_form.addRow("Microphone", self.mic_device_combo)

        self.stt_model_combo = QComboBox()
        for m in ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]:
            self.stt_model_combo.addItem(m, m)
        self.stt_model_combo.setCurrentText("medium.en")
        stt_form.addRow("Whisper model", self.stt_model_combo)

        self.stt_language_combo = QComboBox()
        for code, label in [
            ("en", "English"), ("es", "Spanish"), ("fr", "French"),
            ("de", "German"), ("pt", "Portuguese"), ("ja", "Japanese"),
            ("zh", "Chinese"), ("ko", "Korean"), ("ru", "Russian"),
            ("ar", "Arabic"), ("hi", "Hindi"), ("it", "Italian"),
        ]:
            self.stt_language_combo.addItem(label, code)
        stt_form.addRow("Language", self.stt_language_combo)
        inner.addLayout(stt_form)

        sensitivity_row = QHBoxLayout()
        sensitivity_lbl = QLabel("Wake sensitivity")
        sensitivity_lbl.setObjectName("muted")
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setRange(10, 90)
        self.sensitivity_slider.setValue(50)
        self.sensitivity_slider.setTickInterval(10)
        self.sensitivity_value_lbl = QLabel("0.50")
        self.sensitivity_value_lbl.setObjectName("muted")
        self.sensitivity_value_lbl.setFixedWidth(36)
        self.sensitivity_slider.valueChanged.connect(
            lambda v: self.sensitivity_value_lbl.setText(f"{v / 100:.2f}")
        )
        sensitivity_row.addWidget(sensitivity_lbl)
        sensitivity_row.addWidget(self.sensitivity_slider, 1)
        sensitivity_row.addWidget(self.sensitivity_value_lbl)
        inner.addLayout(sensitivity_row)

        self._wake_word_status_lbl = QLabel("")
        self._wake_word_status_lbl.setWordWrap(True)
        self._wake_word_status_lbl.setStyleSheet("color:#FFB454;font-size:11px;")
        self._wake_word_status_lbl.hide()
        inner.addWidget(self._wake_word_status_lbl)
        QTimer.singleShot(0, self._check_wake_word_status)

        # Plugins
        plugins_header = QHBoxLayout()
        plugins_title = QLabel("PLUGINS")
        plugins_title.setObjectName("panelTitle")
        plugins_header.addWidget(plugins_title)
        plugins_header.addStretch()
        self._refresh_plugins_btn = AnimatedButton("Refresh")
        self._refresh_plugins_btn.setFixedWidth(70)
        self._refresh_plugins_btn.clicked.connect(self._refresh_plugins)
        plugins_header.addWidget(self._refresh_plugins_btn)
        inner.addLayout(plugins_header)

        self._plugins_container = QWidget()
        self._plugins_layout = QVBoxLayout(self._plugins_container)
        self._plugins_layout.setContentsMargins(0, 0, 0, 0)
        self._plugins_layout.setSpacing(6)
        no_plugins = QLabel("Loading plugins…")
        no_plugins.setObjectName("muted")
        self._plugins_layout.addWidget(no_plugins)
        inner.addWidget(self._plugins_container)
        # Pinned context
        pinned_header = QLabel("PINNED CONTEXT")
        pinned_header.setObjectName("panelTitle")
        inner.addWidget(pinned_header)

        pinned_desc = QLabel("Always prepended to every prompt (name, project, preferences…)")
        pinned_desc.setObjectName("muted")
        pinned_desc.setWordWrap(True)
        pinned_desc.setStyleSheet("font-size: 11px; color: rgba(148,163,184,0.60);")
        inner.addWidget(pinned_desc)

        self.pinned_context_field = QTextEdit()
        self.pinned_context_field.setPlaceholderText(
            "e.g. My name is Sivao. I'm a Python developer working on Windows 11.\n"
            "Always respond concisely and prefer code examples."
        )
        self.pinned_context_field.setFixedHeight(80)
        self.pinned_context_field.setStyleSheet(
            "background: rgba(15,23,42,0.60); border: 1px solid rgba(0,200,232,0.15); "
            "border-radius: 8px; padding: 6px; color: #E2E8F0; font-size: 12px;"
        )
        inner.addWidget(self.pinned_context_field)

        # System resource mini-widgets
        sys_header = QLabel("SYSTEM")
        sys_header.setObjectName("panelTitle")
        inner.addWidget(sys_header)

        sys_frame = QFrame()
        sys_frame.setStyleSheet(
            "QFrame { background: rgba(15,23,42,0.60); border: 1px solid rgba(0,200,232,0.10); "
            "border-radius: 10px; }"
        )
        sys_layout = QVBoxLayout(sys_frame)
        sys_layout.setContentsMargins(10, 8, 10, 8)
        sys_layout.setSpacing(6)

        _bar_style = (
            "QProgressBar { background: rgba(0,200,232,0.06); border: none; border-radius: 3px; height: 5px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #00B4D8, stop:1 #00C8E8); border-radius: 3px; }"
        )

        cpu_row = QHBoxLayout()
        cpu_lbl = QLabel("CPU")
        cpu_lbl.setStyleSheet("color: rgba(148,163,184,0.70); font-size: 11px;")
        cpu_lbl.setFixedWidth(32)
        self._cpu_val_lbl = QLabel("--")
        self._cpu_val_lbl.setStyleSheet("color: rgba(0,200,232,0.85); font-size: 11px;")
        self._cpu_val_lbl.setFixedWidth(36)
        self._cpu_val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        cpu_row.addWidget(cpu_lbl)
        cpu_row.addWidget(self._cpu_val_lbl)
        sys_layout.addLayout(cpu_row)

        self._cpu_bar = QProgressBar()
        self._cpu_bar.setRange(0, 100)
        self._cpu_bar.setValue(0)
        self._cpu_bar.setTextVisible(False)
        self._cpu_bar.setFixedHeight(5)
        self._cpu_bar.setStyleSheet(_bar_style)
        sys_layout.addWidget(self._cpu_bar)

        ram_row = QHBoxLayout()
        ram_lbl = QLabel("RAM")
        ram_lbl.setStyleSheet("color: rgba(148,163,184,0.70); font-size: 11px;")
        ram_lbl.setFixedWidth(32)
        self._ram_val_lbl = QLabel("--")
        self._ram_val_lbl.setStyleSheet("color: rgba(0,200,232,0.85); font-size: 11px;")
        self._ram_val_lbl.setFixedWidth(36)
        self._ram_val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        ram_row.addWidget(ram_lbl)
        ram_row.addWidget(self._ram_val_lbl)
        sys_layout.addLayout(ram_row)

        self._ram_bar = QProgressBar()
        self._ram_bar.setRange(0, 100)
        self._ram_bar.setValue(0)
        self._ram_bar.setTextVisible(False)
        self._ram_bar.setFixedHeight(5)
        self._ram_bar.setStyleSheet(_bar_style)
        sys_layout.addWidget(self._ram_bar)

        inner.addWidget(sys_frame)

        inner.addStretch(1)

        layout.addWidget(scroll, 1)

        # Activity log (pinned below scroll)
        log_header = QHBoxLayout()
        log_title = QLabel("ACTIVITY LOG")
        log_title.setObjectName("panelTitle")
        log_header.addWidget(log_title)
        log_header.addStretch()
        clear_log_btn = AnimatedButton("Clear")
        clear_log_btn.setFixedWidth(56)
        clear_log_btn.clicked.connect(lambda: self.activity_log.clear())
        log_header.addWidget(clear_log_btn)
        layout.addLayout(log_header)

        self.activity_log = QListWidget()
        self.activity_log.setFixedHeight(148)
        layout.addWidget(self.activity_log)

        # Bottom action buttons
        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.save_button = AnimatedButton("Save")
        self.save_button.clicked.connect(self._save_settings)
        self.test_all_button = AnimatedButton("Test providers")
        self.test_all_button.clicked.connect(self._test_all_providers)
        self.connectors_button = AnimatedButton("Connectors…")
        self.connectors_button.clicked.connect(self._open_connectors)
        admin_btn = AnimatedButton("Run as Admin")
        admin_btn.setToolTip("Relaunch JARVIS with administrator privileges (needed for some automations)")
        admin_btn.clicked.connect(self._relaunch_as_admin)
        controls.addWidget(self.save_button)
        controls.addWidget(self.test_all_button)
        controls.addWidget(self.connectors_button)
        controls.addWidget(admin_btn)
        layout.addLayout(controls)
        return frame

    def _build_left_panel(self) -> QWidget:
        from PyQt6.QtGui import QPen
        frame = QFrame()
        frame.setObjectName("panel")
        frame.setMinimumWidth(220)
        frame.setMaximumWidth(280)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Hidden compat labels — referenced by _update_model_badge but not shown here
        self._left_provider_label = QLabel("Model")
        self._left_provider_label.hide()
        self._left_model_label = QLabel("—")
        self._left_model_label.hide()

        sys_title = QLabel("System")
        sys_title.setObjectName("panelTitle")
        layout.addWidget(sys_title)

        # Donut gauges — row 1: CPU / RAM / DISK
        gauges_row = QHBoxLayout()
        gauges_row.setSpacing(4)
        self._cpu_gauge  = _DonutGauge("CPU",  "#00C8E8")
        self._ram_gauge  = _DonutGauge("RAM",  "#F59E0B")
        self._disk_gauge = _DonutGauge("DISK", "#EF4444")
        for g in (self._cpu_gauge, self._ram_gauge, self._disk_gauge):
            gauges_row.addWidget(g)
        layout.addLayout(gauges_row)

        # Donut gauges — row 2: GPU load / VRAM
        gauges_row2 = QHBoxLayout()
        gauges_row2.setSpacing(4)
        self._gpu_gauge  = _DonutGauge("GPU",  "#8B7CFF")
        self._vram_gauge = _DonutGauge("VRAM", "#2DE8B0")
        self._gpu_gauge.set_value(0)
        self._vram_gauge.set_value(0)
        gauges_row2.addWidget(self._gpu_gauge)
        gauges_row2.addWidget(self._vram_gauge)
        gauges_row2.addStretch()
        layout.addLayout(gauges_row2)

        # Network mini-graph
        self._net_graph = _MiniGraph()
        self._net_graph.setFixedHeight(48)
        layout.addWidget(self._net_graph)

        # Activity log
        log_hdr = QHBoxLayout()
        log_title = QLabel("Log")
        log_title.setObjectName("panelTitle")
        log_hdr.addWidget(log_title)
        log_hdr.addStretch()
        clear_log_btn = AnimatedButton("Clear")
        clear_log_btn.setFixedWidth(52)
        clear_log_btn.setFixedHeight(28)
        clear_log_btn.clicked.connect(lambda: self.activity_log.clear())
        log_hdr.addWidget(clear_log_btn)
        layout.addLayout(log_hdr)

        self.activity_log = QListWidget()
        self.activity_log.setObjectName("activityLog")
        self.activity_log.setStyleSheet(
            "QListWidget { background: transparent; border: none; font-size: 12px; }"
            "QListWidget::item { padding: 3px 4px; border-radius: 3px; color: rgba(226,232,240,0.80); }"
        )
        layout.addWidget(self.activity_log, 1)

        return frame

    def _build_right_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        frame.setMinimumWidth(220)
        frame.setMaximumWidth(270)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Quick tools — each opens its own mini panel
        qt_title = QLabel("Quick tools")
        qt_title.setObjectName("panelTitle")
        layout.addWidget(qt_title)

        translate_btn = AnimatedButton("Translate")
        translate_btn.setFixedHeight(32)
        translate_btn.clicked.connect(self._open_translator_panel)
        layout.addWidget(translate_btn)

        img_btn = AnimatedButton("Image generator")
        img_btn.setFixedHeight(32)
        img_btn.clicked.connect(self._open_image_gen_panel)
        layout.addWidget(img_btn)

        ocr_btn = AnimatedButton("OCR")
        ocr_btn.setFixedHeight(32)
        ocr_btn.clicked.connect(self._open_ocr_panel)
        layout.addWidget(ocr_btn)

        pomodoro_btn = AnimatedButton("Pomodoro")
        pomodoro_btn.setFixedHeight(32)
        pomodoro_btn.clicked.connect(self._open_pomodoro_panel)
        layout.addWidget(pomodoro_btn)

        spotify_btn = AnimatedButton("Spotify")
        spotify_btn.setFixedHeight(32)
        spotify_btn.clicked.connect(self._open_spotify_panel)
        layout.addWidget(spotify_btn)

        todo_btn = AnimatedButton("Todo")
        todo_btn.setFixedHeight(32)
        todo_btn.clicked.connect(self._open_todo_panel)
        layout.addWidget(todo_btn)

        notes_btn = AnimatedButton("Notes")
        notes_btn.setFixedHeight(32)
        notes_btn.clicked.connect(self._open_notes_panel)
        layout.addWidget(notes_btn)

        clipboard_btn = AnimatedButton("Clipboard")
        clipboard_btn.setFixedHeight(32)
        clipboard_btn.clicked.connect(self._open_clipboard_panel)
        layout.addWidget(clipboard_btn)

        qr_btn = AnimatedButton("QR Code")
        qr_btn.setFixedHeight(32)
        qr_btn.clicked.connect(self._open_qr_panel)
        layout.addWidget(qr_btn)

        voice_btn = AnimatedButton("Voice Memos")
        voice_btn.setFixedHeight(32)
        voice_btn.clicked.connect(self._open_voice_memo_panel)
        layout.addWidget(voice_btn)

        habit_btn = AnimatedButton("Habits")
        habit_btn.setFixedHeight(32)
        habit_btn.clicked.connect(self._open_habit_panel)
        layout.addWidget(habit_btn)

        alert_btn = AnimatedButton("Alerts")
        alert_btn.setFixedHeight(32)
        alert_btn.clicked.connect(self._open_alert_panel)
        layout.addWidget(alert_btn)

        web_remote_btn = AnimatedButton("Web Remote")
        web_remote_btn.setFixedHeight(32)
        web_remote_btn.clicked.connect(self._open_web_remote_panel)
        layout.addWidget(web_remote_btn)

        # Calendar
        cal_title = QLabel("Calendar")
        cal_title.setObjectName("panelTitle")
        layout.addWidget(cal_title)

        from PyQt6.QtWidgets import QCalendarWidget, QHeaderView, QAbstractItemView
        self._calendar_widget = QCalendarWidget()
        self._calendar_widget.setGridVisible(False)
        self._calendar_widget.setNavigationBarVisible(True)
        # Hide week numbers so all 7 day columns get equal space
        self._calendar_widget.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self._calendar_widget.setStyleSheet(
            "QCalendarWidget { background: transparent; color: #E2E8F0; font-size: 12px; }"
            "QCalendarWidget QToolButton { color: #E2E8F0; background: transparent; border: none;"
            "  font-size: 12px; padding: 3px 6px; font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif; }"
            "QCalendarWidget QToolButton::menu-indicator { image: none; width: 0; }"
            "QCalendarWidget QToolButton:hover { color: #00C8E8; }"
            "QCalendarWidget QMenu { background: #080d18; color: #E2E8F0; border: none; }"
            "QCalendarWidget QWidget#qt_calendar_navigationbar { background: rgba(0,200,232,0.05);"
            "  border-radius: 8px; padding: 3px; margin-bottom: 2px; }"
            "QCalendarWidget QAbstractItemView { background: transparent; color: #E2E8F0; font-size: 12px;"
            "  selection-background-color: rgba(0,200,232,0.18); selection-color: #00C8E8; }"
            "QCalendarWidget QAbstractItemView:disabled { color: rgba(148,163,184,0.25); }"
            "QCalendarWidget QHeaderView::section { color: rgba(0,200,232,0.70); background: transparent;"
            "  border: none; min-width: 28px; font-size: 10px; font-weight: 600; letter-spacing: 1px; }"
        )
        self._calendar_widget.setMinimumHeight(185)
        self._calendar_widget.setMaximumHeight(210)
        self._calendar_widget.setMinimumWidth(220)

        # Apply column stretch after Qt finishes building calendar internals
        def _fix_cal_cols():
            for _v in self._calendar_widget.findChildren(QAbstractItemView):
                if hasattr(_v, "horizontalHeader"):
                    _h = _v.horizontalHeader()
                    _h.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                    break
        QTimer.singleShot(0, _fix_cal_cols)

        layout.addWidget(self._calendar_widget)

        # Date event preview (shows on date click)
        self._cal_event_label = QLabel("Click a date to see notes")
        self._cal_event_label.setObjectName("muted")
        self._cal_event_label.setWordWrap(True)
        self._cal_event_label.setStyleSheet(
            "color: rgba(148,163,184,0.60); font-size: 11px; padding: 4px 2px;"
        )
        layout.addWidget(self._cal_event_label)

        self._calendar_widget.selectionChanged.connect(self._on_calendar_date_clicked)

        # Intel feed
        intel_title = QLabel("Intel feed")
        intel_title.setObjectName("panelTitle")
        layout.addWidget(intel_title)

        self._intel_feed = QTextEdit()
        self._intel_feed.setReadOnly(True)
        self._intel_feed.setObjectName("chatDisplay")
        self._intel_feed.setStyleSheet(
            "QTextEdit { background: transparent; border: none; font-size: 12px; color: rgba(226,232,240,0.75); }"
        )
        self._intel_feed.setPlaceholderText("Tool activity will appear here")
        layout.addWidget(self._intel_feed, 1)

        return frame

    def _build_center_column(self) -> QWidget:
        container = QWidget()
        container.setAutoFillBackground(False)
        container.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        hero = QWidget()
        hero.setObjectName("heroPanel")
        hero.setAutoFillBackground(False)
        hero.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(20, 20, 20, 20)
        hero_layout.setSpacing(10)

        self.orb = create_orb_widget(compact=False)
        hero_layout.addWidget(self.orb, 1)

        self.orb_status_label = QLabel("Ready")
        self.orb_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orb_status_label.setStyleSheet(
            "color: #D4E4F7; font-size: 30px; font-weight: 300; letter-spacing: 3px;"
            "font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif;"
        )
        hero_layout.addWidget(self.orb_status_label)

        self.orb_subtitle_label = QLabel("")
        self.orb_subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orb_subtitle_label.setStyleSheet(
            "color: rgba(148, 163, 184, 0.60); font-size: 13px; letter-spacing: 1px;"
        )
        hero_layout.addWidget(self.orb_subtitle_label)

        hero_btn_row = QHBoxLayout()
        hero_btn_row.setSpacing(16)
        hero_btn_row.addStretch()
        self._talk_button = AnimatedButton("Talk")
        self._talk_button.setFixedWidth(116)
        self._talk_button.setFixedHeight(48)
        self._talk_button.setToolTip("Toggle always-listening mode")
        self._talk_button.clicked.connect(self._on_talk_clicked)
        hero_btn_row.addWidget(self._talk_button)
        self._hero_mute_btn = AnimatedButton("Mute")
        self._hero_mute_btn.setFixedWidth(104)
        self._hero_mute_btn.setFixedHeight(48)
        self._hero_mute_btn.setCheckable(True)
        self._hero_mute_btn.setToolTip("Mute/unmute microphone")
        self._hero_mute_btn.clicked.connect(self._on_hero_mute_clicked)
        hero_btn_row.addWidget(self._hero_mute_btn)
        hero_btn_row.addStretch()
        hero_layout.addLayout(hero_btn_row)

        layout.addWidget(hero, 1)

        chat_panel = QFrame()
        chat_panel.setObjectName("panel")
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.setContentsMargins(18, 18, 18, 18)
        chat_layout.setSpacing(12)

        chat_header_row = QHBoxLayout()
        chat_title = QLabel("CONVERSATION")
        chat_title.setObjectName("panelTitle")
        chat_header_row.addWidget(chat_title)

        # Quick model switcher — mirrors primary_provider_combo without opening settings
        self._quick_provider_combo = QComboBox()
        self._quick_provider_combo.setFixedWidth(130)
        self._quick_provider_combo.setToolTip("Switch engine for this session")
        for label, data in [
            ("Auto", "auto"), ("Local", "llamacpp"), ("Ollama", "ollama"), ("Groq", "groq"),
            ("Gemini", "gemini"), ("Claude", "claude"),
            ("OpenAI", "openai"), ("Mistral", "mistral"), ("OpenRouter", "openrouter"),
        ]:
            self._quick_provider_combo.addItem(label, data)
        self._quick_provider_combo.currentIndexChanged.connect(self._on_quick_provider_changed)
        chat_header_row.addWidget(self._quick_provider_combo)

        self._token_budget_label = QLabel("")
        self._token_budget_label.setObjectName("muted")
        self._token_budget_label.setToolTip("Estimated token usage vs context window")
        self._token_budget_label.setFixedWidth(90)
        self._token_budget_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        chat_header_row.addWidget(self._token_budget_label)

        chat_header_row.addStretch()

        font_dec = AnimatedButton("A−")
        font_dec.setFixedWidth(36)
        font_dec.setToolTip("Decrease font size")
        font_dec.clicked.connect(lambda: self._change_font_size(-1))
        chat_header_row.addWidget(font_dec)

        font_inc = AnimatedButton("A+")
        font_inc.setFixedWidth(36)
        font_inc.setToolTip("Increase font size")
        font_inc.clicked.connect(lambda: self._change_font_size(1))
        chat_header_row.addWidget(font_inc)

        export_btn = AnimatedButton("Export")
        export_btn.setFixedWidth(64)
        export_btn.setToolTip("Export chat as Markdown")
        export_btn.clicked.connect(self._export_chat)
        chat_header_row.addWidget(export_btn)

        history_btn = AnimatedButton("History")
        history_btn.setFixedWidth(66)
        history_btn.setToolTip("Browse and load past conversations")
        history_btn.clicked.connect(self._show_history_panel)
        chat_header_row.addWidget(history_btn)

        bookmarks_btn = AnimatedButton("Bookmarks")
        bookmarks_btn.setFixedWidth(86)
        bookmarks_btn.setToolTip("Browser bookmarks")
        bookmarks_btn.clicked.connect(self._open_bookmarks)
        chat_header_row.addWidget(bookmarks_btn)

        macros_btn = AnimatedButton("Macros")
        macros_btn.setFixedWidth(60)
        macros_btn.setToolTip("Create and run action macros")
        macros_btn.clicked.connect(self._open_macros)
        chat_header_row.addWidget(macros_btn)

        schedules_btn = AnimatedButton("Schedules")
        schedules_btn.setFixedWidth(72)
        schedules_btn.setToolTip("Scheduled / recurring prompts")
        schedules_btn.clicked.connect(self._open_schedules)
        chat_header_row.addWidget(schedules_btn)

        toggle_panels_btn = AnimatedButton("<>")
        toggle_panels_btn.setFixedWidth(36)
        toggle_panels_btn.setToolTip("Toggle side panels")
        toggle_panels_btn.clicked.connect(self._toggle_side_panels)
        chat_header_row.addWidget(toggle_panels_btn)

        clear_mem_btn = AnimatedButton("New chat")
        clear_mem_btn.setFixedWidth(76)
        clear_mem_btn.setToolTip("Save current conversation and start a new one")
        clear_mem_btn.clicked.connect(self._new_chat_session)
        chat_header_row.addWidget(clear_mem_btn)

        self.clear_chat_button = AnimatedButton("Clear")
        self.clear_chat_button.setFixedWidth(56)
        self.clear_chat_button.setToolTip("Clear chat display only")
        self.clear_chat_button.clicked.connect(self._clear_chat)
        chat_header_row.addWidget(self.clear_chat_button)
        chat_layout.addLayout(chat_header_row)

        # Search bar (Ctrl+F to toggle)
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search conversation…  (Esc to close)")
        self.search_bar.setFixedHeight(34)
        self.search_bar.textChanged.connect(self._on_search_changed)
        self.search_bar.installEventFilter(self)
        self.search_bar.hide()
        chat_layout.addWidget(self.search_bar)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setMinimumHeight(260)
        self.chat_display.setObjectName("chatDisplay")
        self.chat_display.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_display.customContextMenuRequested.connect(self._chat_context_menu)
        chat_layout.addWidget(self.chat_display, 1)

        # Quick actions
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        quick_label = QLabel("Quick:")
        quick_label.setObjectName("muted")
        quick_row.addWidget(quick_label)
        for label, cmd in [
            ("Time", "What time is it?"),
            ("Weather", "What's the weather?"),
            ("Screenshot", "Take a screenshot"),
            ("Sysinfo", "Show system info"),
            ("Search", "Search the web for "),
        ]:
            btn = AnimatedButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, c=cmd: self._quick_action(c))
            quick_row.addWidget(btn)

        paste_btn = AnimatedButton("Clipboard")
        paste_btn.setFixedHeight(26)
        paste_btn.setToolTip("Paste clipboard content into input field")
        paste_btn.clicked.connect(self._paste_clipboard)
        quick_row.addWidget(paste_btn)

        notes_btn = AnimatedButton("Notes")
        notes_btn.setFixedHeight(26)
        notes_btn.setToolTip("View saved notes (/notes)")
        notes_btn.clicked.connect(lambda: self._handle_console_command("/notes"))
        quick_row.addWidget(notes_btn)

        templates_btn = AnimatedButton("Templates")
        templates_btn.setFixedHeight(26)
        templates_btn.setToolTip("Open prompt templates")
        templates_btn.clicked.connect(self._open_templates)
        quick_row.addWidget(templates_btn)

        bookmark_btn = AnimatedButton("Bookmark")
        bookmark_btn.setFixedHeight(26)
        bookmark_btn.setToolTip("Open browser bookmarks")
        bookmark_btn.clicked.connect(self._open_bookmarks)
        quick_row.addWidget(bookmark_btn)

        demo_btn = AnimatedButton("★ Demo")
        demo_btn.setFixedHeight(26)
        demo_btn.setToolTip("Run a demo sequence")
        demo_btn.clicked.connect(lambda: self._handle_console_command("/demo"))
        quick_row.addWidget(demo_btn)

        quick_row.addStretch()
        chat_layout.addLayout(quick_row)

        # Approval bar — shown when a tool call needs user permission
        self._approval_bar = QFrame()
        self._approval_bar.setObjectName("approvalBar")
        self._approval_bar.setStyleSheet(
            "QFrame#approvalBar {"
            "  background: rgba(15, 22, 45, 0.92);"
            "  border: 1px solid rgba(139,124,255,0.35);"
            "  border-radius: 10px;"
            "  padding: 2px 0px;"
            "}"
        )
        self._approval_bar.hide()
        _ab_row = QHBoxLayout(self._approval_bar)
        _ab_row.setContentsMargins(10, 6, 10, 6)
        _ab_row.setSpacing(8)
        self._approval_icon = QLabel("🔐")
        self._approval_icon.setStyleSheet("font-size:14px;")
        _ab_row.addWidget(self._approval_icon)
        self._approval_label = QLabel("JARVIS wants to run: <b>action</b>")
        self._approval_label.setStyleSheet("color:#C8D8F4; font-size:12px;")
        _ab_row.addWidget(self._approval_label, 1)
        self._approval_id = None
        _approve_btn = AnimatedButton("✓ Approve")
        _approve_btn.setFixedHeight(28)
        _approve_btn.setStyleSheet("font-size:11px; font-weight:600; color:#2DE8B0;")
        _approve_btn.clicked.connect(self._on_approve_action)
        _ab_row.addWidget(_approve_btn)
        _always_btn = AnimatedButton("★ Always")
        _always_btn.setFixedHeight(28)
        _always_btn.setStyleSheet("font-size:11px; font-weight:600; color:#8B7CFF;")
        _always_btn.clicked.connect(self._on_always_approve_action)
        _ab_row.addWidget(_always_btn)
        _decline_btn = AnimatedButton("✗ Decline")
        _decline_btn.setFixedHeight(28)
        _decline_btn.setStyleSheet("font-size:11px; font-weight:600; color:#FF5C7A;")
        _decline_btn.clicked.connect(self._on_decline_action)
        _ab_row.addWidget(_decline_btn)
        chat_layout.addWidget(self._approval_bar)

        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setObjectName("msgInput")
        self.input_field.setPlaceholderText("Tell JARVIS what to do  (↑↓ history  /help for commands)")
        self.input_field.returnPressed.connect(self._send_message)
        self.input_field.installEventFilter(self)
        self.input_field.textChanged.connect(self._on_input_changed)
        self._char_counter = QLabel("0")
        self._char_counter.setObjectName("muted")
        self._char_counter.setFixedWidth(42)
        self._char_counter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._char_counter.setToolTip("Characters / estimated tokens")
        self.send_button = AnimatedButton("Send")
        self.send_button.clicked.connect(self._send_message)
        input_row.addWidget(self.input_field, 1)
        input_row.addWidget(self._char_counter)
        input_row.addWidget(self.send_button)
        chat_layout.addLayout(input_row)

        # Working directory + permissions row
        bottom_meta_row = QHBoxLayout()
        bottom_meta_row.setSpacing(8)

        from pathlib import Path as _Path
        _default_cwd = str(_Path.home())
        _saved_cwd = self.settings.get("working_directory", _default_cwd) if hasattr(self, "settings") else _default_cwd

        _dir_icon = QLabel("📁")
        _dir_icon.setStyleSheet("font-size: 11px; color: rgba(148,163,184,0.55);")
        bottom_meta_row.addWidget(_dir_icon)

        self._cwd_label = QLabel(_saved_cwd)
        self._cwd_label.setObjectName("muted")
        self._cwd_label.setStyleSheet("font-size: 10px; color: rgba(148,163,184,0.55);")
        self._cwd_label.setToolTip("Current working directory for file operations")
        bottom_meta_row.addWidget(self._cwd_label, 1)

        _browse_btn = AnimatedButton("📁 Dir")
        _browse_btn.setFixedHeight(26)
        _browse_btn.setMinimumWidth(68)
        _browse_btn.setToolTip("Change working directory")
        _browse_btn.clicked.connect(self._choose_working_directory)
        bottom_meta_row.addWidget(_browse_btn)

        bottom_meta_row.addSpacing(12)

        self._quick_policy_combo = QComboBox()
        self._quick_policy_combo.setFixedWidth(180)
        self._quick_policy_combo.addItem("Ask first", "ask")
        self._quick_policy_combo.addItem("Auto (safe)", "safe_auto")
        self._quick_policy_combo.addItem("Full auto", "full_auto")
        self._quick_policy_combo.setToolTip("Automation permissions — how JARVIS handles computer actions")
        self._quick_policy_combo.currentIndexChanged.connect(self._on_quick_policy_changed)
        bottom_meta_row.addWidget(self._quick_policy_combo)

        chat_layout.addLayout(bottom_meta_row)

        # Status bar
        self._status_bar = QLabel()
        self._status_bar.setObjectName("statusBar")
        self._status_bar.setTextFormat(Qt.TextFormat.RichText)
        self._status_bar.setStyleSheet(
            "background: rgba(8,12,24,0.60); "
            "border-top: 1px solid rgba(0,200,232,0.08); "
            "color: rgba(148,163,184,0.70); "
            "font-size: 10px; "
            "padding: 3px 6px;"
        )
        self._status_bar.setText(
            '<span style="background:rgba(0,200,232,0.07);border:1px solid rgba(0,200,232,0.15);'
            'border-radius:4px;padding:1px 8px;color:rgba(148,163,184,0.75);font-size:10px;margin-right:4px;">'
            'ready</span>'
            '<span style="background:rgba(0,200,232,0.07);border:1px solid rgba(0,200,232,0.15);'
            'border-radius:4px;padding:1px 8px;color:rgba(148,163,184,0.75);font-size:10px;margin-right:4px;">'
            '0 msgs</span>'
            '<span style="background:rgba(0,200,232,0.07);border:1px solid rgba(0,200,232,0.15);'
            'border-radius:4px;padding:1px 8px;color:rgba(148,163,184,0.75);font-size:10px;margin-right:4px;">'
            '~0 tok</span>'
        )
        chat_layout.addWidget(self._status_bar)

        layout.addWidget(chat_panel, 0)
        return container

    def _build_provider_column(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("PROVIDERS  &  DIAGNOSTICS")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        definitions = [
            ("ollama", "Ollama", False, True),
            ("groq", "Groq", True, False),
            ("gemini", "Gemini", True, False),
            ("claude", "Claude", True, False),
            ("openai", "OpenAI", True, True),
            ("mistral", "Mistral", True, False),
            ("openrouter", "OpenRouter", True, False),
        ]
        for provider_name, label, has_key, has_base_url in definitions:
            card = ProviderCard(provider_name, label, has_key=has_key, has_base_url=has_base_url)
            card.test_button.clicked.connect(
                lambda _checked=False, name=provider_name: self._test_single_provider(name)
            )
            card.help_button.clicked.connect(
                lambda _checked=False, name=provider_name: self._open_help(name)
            )
            self.provider_cards[provider_name] = card
            content_layout.addWidget(card)

        # Local AI (llama.cpp) card
        local_ai_card = LocalAICard()
        local_ai_card.test_button.clicked.connect(
            lambda _checked=False: self._test_single_provider("llamacpp")
        )
        self.provider_cards["llamacpp"] = local_ai_card
        content_layout.addWidget(local_ai_card)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return frame

    def _setup_tray(self) -> None:
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray_icon = QSystemTrayIcon(icon, self)
        menu = QMenu(self)
        restore_action = menu.addAction("Open console")
        restore_action.triggered.connect(self._restore_from_overlay)
        overlay_action = menu.addAction("Show orb overlay")
        overlay_action.triggered.connect(self._show_overlay_only)
        menu.addSeparator()

        # Quick actions submenu
        quick_menu = menu.addMenu("Quick Actions")
        time_action = quick_menu.addAction("What time is it?")
        time_action.triggered.connect(lambda: self._quick_action("What time is it? "))
        sysinfo_action = quick_menu.addAction("System info")
        sysinfo_action.triggered.connect(lambda: self._quick_action("Show me system information "))
        screenshot_action = quick_menu.addAction("Take screenshot")
        screenshot_action.triggered.connect(lambda: self._quick_action("Take a screenshot of my screen "))

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit_from_tray)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(
            lambda reason: self._restore_from_overlay()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        self.tray_icon.show()

    def _populate_voice_profiles(self, custom_profile: dict | None = None) -> None:
        self.voice_profile_combo.clear()
        for profile in builtin_voice_profiles(custom_profile):
            self.voice_profile_combo.addItem(profile["label"], profile["id"])

    def _handle_runtime_event(self, payload: dict) -> None:
        try:
            self._process_runtime_event(payload)
        except Exception as exc:
            import traceback
            logger.error(f"UI Event Error: {exc}\n{traceback.format_exc()}")

    def _process_runtime_event(self, payload: dict) -> None:
        event_type = payload.get("type")
        if event_type == "partial_response":
            accumulated = payload.get("accumulated", "")
            if not self._streaming_active:
                self._streaming_active = True
                # Record where this streaming block starts so we can replace in-place
                self._stream_anchor = self.chat_display.document().characterCount()
                self._add_chat_message("JARVIS", accumulated, "assistant")
            else:
                self._update_streaming_message(accumulated)
            return
        if event_type == "message":
            sender = payload.get("sender", "SYSTEM")
            text = payload.get("text", "")
            origin = payload.get("origin", "assistant")
            if sender == "JARVIS" and self._streaming_active:
                self._streaming_active = False
                self._update_streaming_message(text, final=True, raw=payload.get("raw"))
            else:
                self._add_chat_message(sender, text, origin, payload.get("raw"))
            if sender == "JARVIS":
                raw = payload.get("raw") or {}
                actual_provider = raw.get("provider", "")
                if actual_provider and hasattr(self, "_provider_badge"):
                    label = self._get_active_model_label(actual_provider)
                    badge_text = f"{actual_provider} · {label}" if label else actual_provider
                    self._provider_badge.setText(badge_text.upper())
                    if hasattr(self, "_left_model_label"):
                        self._left_model_label.setText(badge_text)
                    # Update header combo tooltip to show active model
                    if hasattr(self, "_header_model_combo"):
                        self._header_model_combo.setToolTip(f"Active: {badge_text}\nClick to switch provider")
            if origin == "voice":
                self.last_heard_label.setText(f"Last heard: {text}")
            if sender == "JARVIS":
                self._last_jarvis_response = text
                self.current_response_style = classify_response_style(text)
                self.orb.set_response_style(self.current_response_style)
                self.overlay_window.set_response_style(self.current_response_style)
        elif event_type == "status":
            self._apply_status(payload.get("status", "idle"))
        elif event_type == "mic":
            level = payload.get("level", 0.0)
            speech_detected = payload.get("speech_detected", False)
            mode = payload.get("mode", "idle")
            self.orb.set_audio_level(level, speech_detected, mode)
            self.overlay_window.set_audio_level(level, speech_detected, mode)
            if speech_detected and self.current_status in ("idle", "listening"):
                self.orb_subtitle_label.setText("Speech energy detected — recording")
        elif event_type == "log":
            level = payload.get("level", "info")
            message = payload.get("message", "")
            if level != "debug":
                self._add_activity(level, message)
            if message.startswith("Heard: "):
                self.last_heard_label.setText(f"Last heard: {message[7:]}")
        elif event_type == "tool_call":
            name = payload.get("name", "unknown tool")
            args = payload.get("args", {})
            self._add_activity("tool", f"{name} {args}")
            self.computer_use_overlay.on_tool_start(name)
            self._hide_thinking_bubble()
            self._show_tool_call_bubble(name, args if isinstance(args, dict) else {})
            if hasattr(self, "_intel_feed"):
                from PyQt6.QtCore import QDateTime
                ts = QDateTime.currentDateTime().toString("HH:mm:ss")
                self._intel_feed.append(f'<span style="color:#8A94B8;">{ts}</span> → <b>{name}</b>')
        elif event_type == "tool_result":
            name = payload.get("name", "unknown tool")
            result_text = str(payload.get("result", ""))
            success = payload.get("success", True)
            self._add_activity(
                "tool",
                f"{name}: {'ok' if success else 'failed'} {result_text[:180]}",
            )
            self.computer_use_overlay.on_tool_end(name)
            self._update_tool_result_bubble(name, result_text, success)
            if hasattr(self, "_intel_feed"):
                color = "#2DE8B0" if success else "#FF5C7A"
                self._intel_feed.append(
                    f'<span style="color:{color};">{"✓" if success else "✗"} {name}: {result_text[:120]}</span>'
                )
        elif event_type == "settings_loaded":
            self._apply_settings_to_ui(payload["settings"])
        elif event_type == "provider_test":
            card = self.provider_cards.get(payload["provider"])
            if card:
                help_text = payload.get("help", {}).get("instructions", "")
                message = payload.get("message", "")
                if help_text and not payload.get("success"):
                    message = f"{message}\n{help_text}"
                card.set_test_result(payload.get("success", False), message)
        elif event_type == "proactive_help":
            suggestion = payload.get("suggestion", "")
            category = payload.get("category", "general")
            if suggestion:
                self.notification_toast.show_suggestion(suggestion, category)
        elif event_type == "chat_history":
            messages = payload.get("messages", [])
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    self._add_chat_message("YOU", content, "typed")
                elif role == "assistant":
                    self._add_chat_message("JARVIS", content, "assistant")
                    self._last_jarvis_response = content
        elif event_type == "transcription_chunk":
            text = payload.get("text", "")
            if text and hasattr(self, "_subtitle_overlay"):
                self._subtitle_overlay.push_text(text)
        elif event_type == "new_session":
            self.chat_display.clear()
            self._last_jarvis_response = ""
            self._streaming_active = False
            self._add_activity("info", "New conversation started")
        elif event_type == "session_list":
            sessions = payload.get("sessions", [])
            if hasattr(self, "_history_dialog") and self._history_dialog:
                self._history_dialog._populate(sessions)
        elif event_type == "runtime_ready":
            self._add_activity("info", "Runtime ready")
            self._apply_status("idle")
            # Request plugin list and restore chat history once runtime is ready
            QTimer.singleShot(500, self.runtime.list_plugins)
            QTimer.singleShot(800, self.runtime.load_chat_history)
        elif event_type == "approval_request":
            self._show_approval_bar(payload["id"], payload["action"])
        elif event_type == "settings_saved":
            self._add_activity("info", "Settings saved")
        elif event_type == "plugins_list":
            plugins = payload.get("plugins", [])
            self._update_plugins_ui(plugins)
            if hasattr(self, "_plugins_dlg") and self._plugins_dlg.isVisible():
                self._plugins_dlg.update_plugins(plugins)
        elif event_type == "status_report":
            lines = [
                f"CPU: {payload.get('cpu', 0):.1f}%",
                f"Memory: {payload.get('mem_pct', 0):.1f}%",
                f"Providers: {', '.join(payload.get('providers', [])) or 'none'}",
                f"Plugins: {', '.join(payload.get('plugins', [])) or 'none'}",
                f"Voice: {'on' if payload.get('voice_enabled') else 'off'}",
            ]
            self._add_chat_message("SYSTEM", "\n".join(lines), "system")

    def _apply_status(self, status: str) -> None:
        import time as _time
        self.current_status = status
        self.orb.set_status(status)
        self.overlay_window.set_status(status)
        if status == "thinking":
            self._elapsed_start = _time.monotonic()
            self._elapsed_timer.start()
            # Show thinking animation bubble if not currently streaming
            if not self._streaming_active:
                self._show_thinking_bubble()
        elif status in ("idle", "error", "speaking"):
            self._elapsed_timer.stop()
            self._elapsed_label.setText("")
            if self._thinking_bubble_active:
                self._hide_thinking_bubble()
        pretty = {
            "idle": "Ready",
            "listening": "Listening",
            "transcribing": "Transcribing",
            "thinking": "Working",
            "speaking": "Responding",
            "error": "Error",
        }.get(status, status.title())
        self.orb_status_label.setText(pretty)
        self.status_chip.setText(pretty)
        subtitle = {
            "idle": "",
            "listening": "Listening...",
            "transcribing": "Transcribing...",
            "thinking": "Working...",
            "speaking": "Speaking...",
            "error": "Error",
        }.get(status, "")
        self.orb_subtitle_label.setText(subtitle)

    def _apply_settings_to_ui(self, settings: dict) -> None:
        self.settings = settings
        self.voice_toggle.setChecked(bool(settings.get("voice_enabled", True)))
        self.screen_toggle.setChecked(bool(settings.get("screen_awareness", True)))
        self.start_minimized_toggle.setChecked(bool(settings.get("start_minimized", True)))
        self.watcher_toggle.setChecked(bool(settings.get("watcher_enabled", False)))
        self._set_combo_value(self.primary_provider_combo, settings.get("primary_provider", "mistral"))
        self._set_combo_value(self.policy_combo, settings.get("automation_policy", "safe_auto"))
        self._set_combo_value(self.background_mode_combo, settings.get("background_mode", "wake_phrase"))
        self._set_combo_value(self.overlay_mode_combo, settings.get("overlay_mode", "floating"))
        custom_profile = normalize_custom_profile(settings.get("custom_voice_profile"))
        self._populate_voice_profiles(custom_profile)
        self._set_combo_value(self.voice_profile_combo, settings.get("voice_profile", "jarvis"))
        self.custom_voice_label.setText(custom_profile["label"])
        self.custom_voice_name.setText(custom_profile["voice"])
        self.custom_voice_rate.setText(custom_profile["rate"])
        self.custom_voice_pitch.setText(custom_profile["pitch"])
        # Wire STT settings
        stt_model = settings.get("stt_model", "medium.en")
        idx = self.stt_model_combo.findText(stt_model)
        if idx >= 0:
            self.stt_model_combo.setCurrentIndex(idx)
        stt_lang = settings.get("stt_language", "en")
        for i in range(self.stt_language_combo.count()):
            if self.stt_language_combo.itemData(i) == stt_lang:
                self.stt_language_combo.setCurrentIndex(i)
                break
        sensitivity = settings.get("wake_word_sensitivity", 0.5)
        self.sensitivity_slider.setValue(int(float(sensitivity) * 100))
        saved_device = settings.get("input_device")
        if saved_device is not None:
            for i in range(self.mic_device_combo.count()):
                if self.mic_device_combo.itemData(i) == saved_device:
                    self.mic_device_combo.setCurrentIndex(i)
                    break

        self.overlay_window.apply_mode(settings.get("overlay_mode", "floating"))
        self.mode_chip.setText(
            "Always listening"
            if settings.get("background_mode") == "always_listening"
            else "Wake phrase"
        )
        # Merge saved settings with runtime config so that fields set in the
        # YAML (e.g. llamacpp model_path) are visible in the UI even if the
        # user never explicitly saved them from the Settings panel.
        runtime_providers = {}
        try:
            runtime_providers = self.runtime.config.ai.providers
        except Exception:
            pass
        for provider_name, card in self.provider_cards.items():
            yaml_defaults = dict(runtime_providers.get(provider_name, {}))
            saved = settings.get("providers", {}).get(provider_name, {})
            # Saved values win — but don't let an empty saved value hide a real YAML value
            merged = dict(yaml_defaults)
            for k, v in saved.items():
                if isinstance(v, str) and not v.strip() and merged.get(k):
                    continue  # keep YAML value when UI sent empty
                merged[k] = v
            card.apply_settings(merged)
        pinned = settings.get("pinned_context", "")
        if hasattr(self, "pinned_context_field"):
            self.pinned_context_field.setPlainText(pinned)
        font_sz = settings.get("chat_font_size", 14)
        if isinstance(font_sz, int) and 8 <= font_sz <= 28:
            self._chat_font_size = font_sz
        # Sync provider combos with the saved primary provider
        _prov = settings.get("primary_provider", "auto")
        if hasattr(self, "_quick_provider_combo"):
            self._set_combo_value(self._quick_provider_combo, _prov)
        if hasattr(self, "_header_model_combo"):
            self._set_combo_value(self._header_model_combo, _prov)
        if hasattr(self, "_quick_policy_combo"):
            self._set_combo_value(self._quick_policy_combo, settings.get("automation_policy", "safe_auto"))
        if hasattr(self, "_wdir_input"):
            self._wdir_input.setText(settings.get("working_dir", ""))
        if hasattr(self, "_cwd_label"):
            from pathlib import Path as _P
            self._cwd_label.setText(settings.get("working_directory", str(_P.home())))
        QTimer.singleShot(200, self._update_token_budget)

    def _collect_settings(self) -> dict:
        settings = dict(self.settings) if self.settings else {}
        settings["voice_enabled"] = self.voice_toggle.isChecked()
        settings["screen_awareness"] = self.screen_toggle.isChecked()
        settings["start_minimized"] = self.start_minimized_toggle.isChecked()
        settings["watcher_enabled"] = self.watcher_toggle.isChecked()
        settings["primary_provider"] = self.primary_provider_combo.currentData()
        settings["automation_policy"] = self.policy_combo.currentData()
        settings["background_mode"] = self.background_mode_combo.currentData()
        settings["overlay_mode"] = self.overlay_mode_combo.currentData()
        settings["voice_profile"] = self.voice_profile_combo.currentData()
        settings["stt_model"] = self.stt_model_combo.currentData()
        settings["stt_language"] = self.stt_language_combo.currentData()
        settings["wake_word_sensitivity"] = self.sensitivity_slider.value() / 100.0
        settings["input_device"] = self.mic_device_combo.currentData()
        settings["custom_voice_profile"] = {
            "label": self.custom_voice_label.text().strip() or "Custom imported profile",
            "voice": self.custom_voice_name.text().strip() or "en-US-EricNeural",
            "rate": self.custom_voice_rate.text().strip() or "-2%",
            "pitch": self.custom_voice_pitch.text().strip() or "-1Hz",
        }
        settings.setdefault("providers", {})
        for provider_name, card in self.provider_cards.items():
            settings["providers"][provider_name] = card.to_settings()
        settings["connectors"] = self.settings.get("connectors", {})
        if hasattr(self, "pinned_context_field"):
            settings["pinned_context"] = self.pinned_context_field.toPlainText().strip()
        if hasattr(self, "_cwd_label"):
            settings["working_directory"] = self._cwd_label.text()
        settings["chat_font_size"] = self._chat_font_size
        if hasattr(self, "_wdir_input"):
            settings["working_dir"] = self._wdir_input.text().strip()
        return settings

    def _save_settings(self) -> None:
        settings = self._collect_settings()
        self.runtime.apply_settings(settings)
        self.overlay_window.apply_mode(settings.get("overlay_mode", "floating"))

    def _test_all_providers(self) -> None:
        self._save_settings()
        for provider_name in self.provider_cards:
            self.runtime.test_provider(provider_name)

    def _open_connectors(self) -> None:
        saved = self.settings.get("connectors", {})
        dlg = ConnectorsDialog(self, saved)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            conn_settings = dlg.get_settings()
            self.settings.setdefault("connectors", {}).update(conn_settings)
            self._add_activity("info", "Connector settings updated — click Save to persist")

    def _open_ollama_manager(self) -> None:
        from jarvis.ui.ollama_manager import OllamaManagerDialog
        if not hasattr(self, "_ollama_dlg") or self._ollama_dlg is None:
            base_url = self.settings.get("providers", {}).get("ollama", {}).get("base_url", "http://localhost:11434")
            self._ollama_dlg = OllamaManagerDialog(base_url=base_url, parent=self)
            self._ollama_dlg.model_pulled.connect(
                lambda m: self._add_activity("success", f"Ollama model pulled: {m}")
            )
        self._ollama_dlg.show()
        self._ollama_dlg.raise_()

    def _open_transcript(self) -> None:
        from jarvis.ui.transcript_sidebar import TranscriptSidebar
        if not hasattr(self, "_transcript_dlg") or self._transcript_dlg is None:
            self._transcript_dlg = TranscriptSidebar(parent=None)  # top-level
            self._transcript_dlg.setWindowFlags(
                Qt.WindowType.Tool | Qt.WindowType.WindowCloseButtonHint
            )
        # Position it below the main window, left-aligned
        mw = self.geometry()
        self._transcript_dlg.move(mw.x(), mw.y() + mw.height() + 8)
        self._transcript_dlg.resize(400, 360)
        self._transcript_dlg.show()
        self._transcript_dlg.raise_()

    def _open_mcp_manager(self) -> None:
        from jarvis.ui.mcp_manager_dialog import MCPManagerDialog
        servers = self.settings.get("mcp_servers", [])
        dlg = MCPManagerDialog(servers=servers, parent=self)
        if dlg.exec():
            self.settings["mcp_servers"] = dlg._servers
            self._save_settings()

    def _open_ssh_manager(self) -> None:
        from jarvis.ui.ssh_manager_dialog import SSHManagerDialog
        servers = self.settings.get("ssh_servers", [])
        dlg = SSHManagerDialog(servers=servers, parent=self)
        if dlg.exec():
            self.settings["ssh_servers"] = dlg._servers
            self._save_settings()

    def _open_macros(self) -> None:
        from jarvis.ui.macros_dialog import MacrosDialog
        if not hasattr(self, "_macros_dlg") or self._macros_dlg is None:
            self._macros_dlg = MacrosDialog(parent=self)
        self._macros_dlg.show()
        self._macros_dlg.raise_()

    def _open_schedules(self) -> None:
        from jarvis.ui.schedules_dialog import SchedulesDialog
        if not hasattr(self, "_schedules_dlg") or self._schedules_dlg is None:
            self._schedules_dlg = SchedulesDialog(parent=self)
        self._schedules_dlg.show()
        self._schedules_dlg.raise_()

    def _open_templates(self) -> None:
        from jarvis.ui.templates_dialog import TemplatesDialog
        if not hasattr(self, "_templates_dlg") or self._templates_dlg is None:
            self._templates_dlg = TemplatesDialog(parent=self)
        self._templates_dlg.show()
        self._templates_dlg.raise_()

    def _open_bookmarks(self) -> None:
        from jarvis.ui.bookmarks_dialog import BookmarksDialog
        if not hasattr(self, "_bookmarks_dlg") or self._bookmarks_dlg is None:
            self._bookmarks_dlg = BookmarksDialog(parent=self)
        self._bookmarks_dlg.show()
        self._bookmarks_dlg.raise_()

    def _test_single_provider(self, provider_name: str) -> None:
        self._save_settings()
        self.runtime.test_provider(provider_name)

    def _preview_voice(self) -> None:
        settings = self._collect_settings()
        self.runtime.preview_voice(
            settings.get("voice_profile", "jarvis"),
            settings.get("custom_voice_profile"),
        )

    def _import_voice_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import voice profile",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            profile = normalize_custom_profile(payload)
            self.custom_voice_label.setText(profile["label"])
            self.custom_voice_name.setText(profile["voice"])
            self.custom_voice_rate.setText(profile["rate"])
            self.custom_voice_pitch.setText(profile["pitch"])
            self._set_combo_value(self.voice_profile_combo, "custom")
            self._add_activity("info", f"Imported voice profile from {path}")
        except Exception as exc:
            self._add_activity("error", f"Voice profile import failed: {exc}")

    def _open_voice_guide(self) -> None:
        QDesktopServices.openUrl(
            QUrl("https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts")
        )

    def _open_help(self, provider_name: str) -> None:
        card = self.provider_cards.get(provider_name)

        if provider_name == "gemini":
            dlg = _GeminiAuthDialog(parent=self)
            if card and card.api_key_input is not None:
                dlg.key_accepted.connect(card.api_key_input.setText)
            def _store_token(path: str) -> None:
                self.settings.setdefault("providers", {}).setdefault("gemini", {})["oauth_token_path"] = path
                self._add_activity("success", f"Gemini OAuth token saved — restart JARVIS to apply")
            dlg.oauth_token_saved.connect(_store_token)
            dlg.show()
            return

        if provider_name in _ApiKeySetupDialog._CONFIGS:
            dlg = _ApiKeySetupDialog(provider_name, parent=self)
            if card and card.api_key_input is not None:
                dlg.key_accepted.connect(card.api_key_input.setText)
            dlg.show()
            return

        # Fallback: just open the URL for providers without a guided dialog (ollama)
        help_urls = {
            "ollama": "https://ollama.com/download",
        }
        url = help_urls.get(provider_name)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    _ACTIVITY_LOG_MAX = 300

    def _add_activity(self, level: str, message: str) -> None:
        # Cap log at _ACTIVITY_LOG_MAX to prevent unbounded memory growth.
        while self.activity_log.count() >= self._ACTIVITY_LOG_MAX:
            self.activity_log.takeItem(0)

        ts = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{ts}] [{level.upper()}] {message}")
        colors = {
            "error":   QColor("#FB7185"),  # rose-400
            "warning": QColor("#FBBF24"),  # amber-400
            "tool":    QColor("#38BDF8"),  # sky-400
            "info":    QColor("#94A3B8"),  # slate-400
        }
        item.setForeground(colors.get(level, QColor("#94A3B8")))
        self.activity_log.addItem(item)
        self.activity_log.scrollToBottom()

    @staticmethod
    def _md_to_html(text: str) -> str:
        """Markdown→HTML converter with Pygments syntax highlighting for JARVIS chat bubbles."""
        import html as _html
        import re as _re

        # Pygments syntax highlighting — loaded once per call (module-level cache handles cost)
        try:
            from pygments import highlight as _pyg_hl  # type: ignore[import]
            from pygments.lexers import get_lexer_by_name as _get_lexer  # type: ignore[import]
            from pygments.lexers import TextLexer as _TextLexer  # type: ignore[import]
            from pygments.formatters import HtmlFormatter as _HtmlFormatter  # type: ignore[import]
            from pygments.util import ClassNotFound as _ClassNotFound  # type: ignore[import]
            _PYGMENTS_OK = True
        except ImportError:
            _PYGMENTS_OK = False

        def _highlight_code(lang: str, code_raw: str) -> str:
            """Return Pygments-highlighted HTML snippet for code_raw, or HTML-escaped fallback."""
            if not _PYGMENTS_OK:
                return _html.escape(code_raw)
            try:
                try:
                    lexer = _get_lexer(lang, stripall=True) if lang else _TextLexer()
                except _ClassNotFound:
                    lexer = _TextLexer()
                # noclasses=True → inline color styles (no external CSS needed)
                # nowrap=True   → bare highlighted tokens, no wrapping <div>/<pre>
                formatter = _HtmlFormatter(style="monokai", noclasses=True, nowrap=True)
                return _pyg_hl(code_raw, lexer, formatter)
            except Exception:
                return _html.escape(code_raw)

        # Language → display label mapping for code block headers
        _LANG_LABELS = {
            "python": "Python", "py": "Python",
            "javascript": "JavaScript", "js": "JavaScript", "ts": "TypeScript", "typescript": "TypeScript",
            "bash": "Bash", "sh": "Shell", "shell": "Shell",
            "json": "JSON", "yaml": "YAML", "yml": "YAML",
            "html": "HTML", "css": "CSS", "sql": "SQL",
            "rust": "Rust", "go": "Go", "c": "C", "cpp": "C++",
            "java": "Java", "kotlin": "Kotlin", "swift": "Swift",
            "powershell": "PowerShell", "ps1": "PowerShell",
            "xml": "XML", "toml": "TOML",
        }

        # Fenced code blocks first (before escaping)
        blocks: dict[str, str] = {}
        def _store_block(m):
            key = f"\x00BLOCK{len(blocks)}\x00"
            lang = m.group(1).strip().lower()
            code_raw = m.group(2)
            highlighted = _highlight_code(lang, code_raw)
            lang_label = _LANG_LABELS.get(lang, lang.upper() if lang else "CODE")
            header = (
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:6px 12px;background:rgba(0,0,0,0.45);border-radius:8px 8px 0 0;'
                f'border-bottom:1px solid rgba(0,200,232,0.10);">'
                f'<span style="color:rgba(0,200,232,0.75);font-size:10px;font-weight:700;'
                f'letter-spacing:1.8px;font-family:Consolas,monospace;">{lang_label}</span>'
                f'<span style="color:rgba(148,163,184,0.50);font-size:10px;'
                f'font-family:Consolas,monospace;" title="Copy code">copy</span>'
                f'</div>'
            )
            body = (
                f'<pre style="margin:0;padding:12px 14px;overflow-x:auto;font-size:12px;'
                f'font-family:Consolas,Menlo,monospace;line-height:1.6;background:#1E1E2E;">'
                f'<code>{highlighted}</code></pre>'
            )
            blocks[key] = (
                f'<div style="background:#1E1E2E;border-radius:10px;margin:8px 0;'
                f'border:1px solid rgba(0,200,232,0.14);'
                f'border-left:3px solid #00C8E8;overflow:hidden;">'
                f'{header}{body}</div>'
            )
            return key
        text = _re.sub(r"```(\w*)\n?([\s\S]*?)```", _store_block, text)

        safe = _html.escape(text)

        # Inline code
        safe = _re.sub(r"`([^`]+)`",
            r'<code style="background:rgba(0,200,232,0.10);border:1px solid rgba(0,200,232,0.18);'
            r'border-radius:5px;padding:1px 6px;font-family:Consolas,monospace;font-size:12px;'
            r'color:#00C8E8;">\1</code>',
            safe)

        # Bold / italic
        safe = _re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", safe)
        safe = _re.sub(r"\*\*(.+?)\*\*",     r"<strong>\1</strong>", safe)
        safe = _re.sub(r"\*(.+?)\*",          r"<em>\1</em>", safe)

        # Headers (h1-h3 → styled spans)
        safe = _re.sub(r"^### (.+)$",
            r'<span style="font-weight:700;font-size:14px;color:#93C5FD;">\1</span>',
            safe, flags=_re.MULTILINE)
        safe = _re.sub(r"^## (.+)$",
            r'<span style="font-weight:700;font-size:15px;color:#A5F3FC;">\1</span>',
            safe, flags=_re.MULTILINE)
        safe = _re.sub(r"^# (.+)$",
            r'<span style="font-weight:700;font-size:16px;color:#E2E8F0;">\1</span>',
            safe, flags=_re.MULTILINE)
        # h4-h6 fallback
        safe = _re.sub(r"^#{4,6}\s+(.+)$",
            r'<span style="font-weight:700;font-size:13px;color:#CBD5E1;">\1</span>',
            safe, flags=_re.MULTILINE)

        # Blockquotes (> text)
        safe = _re.sub(r"^&gt;\s?(.+)$",
            r'<span style="border-left:3px solid rgba(0,200,232,0.45);'
            r'padding-left:10px;color:rgba(203,213,225,0.80);'
            r'font-style:italic;display:block;">\1</span>',
            safe, flags=_re.MULTILINE)

        # Horizontal rule
        safe = _re.sub(r"^---+$",
            '<hr style="border:none;border-top:1px solid rgba(0,200,232,0.15);margin:10px 0;">',
            safe, flags=_re.MULTILINE)

        # Ordered lists (preserve numbering)
        _ol_counter = [0]
        def _ol_item(m):
            _ol_counter[0] += 1
            num = m.group(1)  # original number from the text
            return (
                f'&nbsp;&nbsp;<span style="color:rgba(0,229,255,0.70);'
                f'font-weight:600;min-width:20px;display:inline-block;">{num}.</span>'
                f'&nbsp;{m.group(2)}'
            )
        safe = _re.sub(r"^(\d+)\.\s+(.+)$", _ol_item, safe, flags=_re.MULTILINE)

        # Unordered lists
        safe = _re.sub(r"^[*\-]\s+(.+)$",
            r'&nbsp;&nbsp;<span style="color:rgba(0,229,255,0.70);">&#x25CF;</span>&nbsp;\1',
            safe, flags=_re.MULTILINE)

        # Newlines
        safe = safe.replace("\n", "<br>")

        # Restore fenced blocks
        for key, html in blocks.items():
            safe = safe.replace(_html.escape(key), html)

        return safe

    def _build_metadata_badge(self, raw: dict | None) -> str:
        if not raw:
            return ""
        provider = raw.get("provider", "")
        usage = raw.get("usage") or {}
        latency = usage.get("total_time_ms")
        prompt_tok = usage.get("prompt_tokens", 0)
        comp_tok = usage.get("completion_tokens", 0)
        parts = []
        if provider:
            active_model = self._get_active_model_label(provider)
            parts.append(f"{provider} · {active_model}" if active_model else provider)
        if latency:
            parts.append(f"{int(latency)}ms")
        elif self._elapsed_start:
            elapsed_ms = int((_time.monotonic() - self._elapsed_start) * 1000)
            if elapsed_ms > 100:
                parts.append(f"{elapsed_ms}ms")
        if prompt_tok:
            parts.append(f"{prompt_tok}+{comp_tok}tok")
        if not parts:
            return ""
        return (
            f'<br><span style="color:rgba(0,200,232,0.45); font-size:10px; '
            f'background:rgba(0,200,232,0.05); border-radius:5px; padding:1px 6px;">'
            f'{"  ·  ".join(parts)}</span>'
        )

    def _get_quick_reply_chips(self, response_text: str) -> list[str]:
        """Generate context-aware quick-reply suggestions based on response."""
        suggestions = ["Tell me more"]
        lower = response_text.lower()

        # Check for code
        if any(x in lower for x in ["```", ".py", ".js", ".tsx", ".jsx", "code snippet", "def ", "function "]):
            suggestions.append("Run it")

        # Check for URLs
        if "http" in lower or "www." in lower:
            suggestions.append("Open link")

        # Check for notes/reminders
        if any(x in lower for x in ["note:", "remember", "save", "note to"]):
            suggestions.append("Save note")

        return suggestions[:3]

    def _get_quick_reply_html(self, response_text: str) -> str:
        """Generate HTML for quick-reply chips."""
        suggestions = self._get_quick_reply_chips(response_text)
        if not suggestions:
            return ""

        chips_html = '<div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">'
        for chip_text in suggestions:
            chips_html += (
                f'<span style="'
                f'background:rgba(0,200,232,0.08); '
                f'border:1px solid rgba(0,200,232,0.20); '
                f'border-radius:4px; '
                f'padding:4px 12px; '
                f'font-size:11px; '
                f'color:rgba(0,200,232,0.85); '
                f'user-select:none; '
                f'" '
                f'title="Send: {chip_text}" '
                f'data-chip="{chip_text}">'
                f'{chip_text}</span>'
            )
        chips_html += '</div>'
        return chips_html

    def _add_chat_message(self, sender: str, text: str, origin: str, raw: dict | None = None) -> None:
        # Hide thinking bubble if it's showing
        if self._thinking_bubble_active and sender == "JARVIS":
            self._hide_thinking_bubble()

        ts = datetime.now().strftime("%H:%M")

        if sender == "YOU":
            sender_color = "#00C8E8"
            bubble_bg = "rgba(0,200,232,0.07)"
            border_left = "border-left:3px solid rgba(0,200,232,0.45);"
            border_clr = "rgba(0,200,232,0.18)"
            align = "right"
            safe_text = _html.escape(text).replace("\n", "<br>")
        elif origin == "system":
            sender_color = "#F59E0B"
            bubble_bg = "rgba(245,158,11,0.08)"
            border_left = "border-left:3px solid #F59E0B;"
            border_clr = "rgba(245,158,11,0.20)"
            align = "left"
            safe_text = _html.escape(text).replace("\n", "<br>")
        else:
            sender_color = "#10B981"
            bubble_bg = "rgba(8,18,36,0.50)"
            border_left = "border-left:2px solid rgba(0,200,232,0.50);"
            border_clr = "rgba(0,200,232,0.12)"
            align = "left"
            safe_text = self._md_to_html(text)

        meta = self._build_metadata_badge(raw) if raw and origin == "assistant" else ""

        block = (
            f'<div style="margin:12px 0; text-align:{align};">'
            f'<span style="color:rgba(148,163,184,0.45); font-size:10px;">{ts}</span><br>'
            f'<span style="color:{sender_color}; font-weight:700; font-size:11px; letter-spacing:0.8px;">{sender}</span>'
            f'<div style="display:inline-block; background:{bubble_bg}; '
            f'border:1px solid {border_clr}; {border_left} '
            f'border-radius:14px; padding:11px 16px; margin-top:5px; '
            f'color:#F8FAFC; max-width:86%; word-wrap:break-word; '
            f'font-size:{self._chat_font_size}px; line-height:1.65;">'
            f'{safe_text}{meta}</div>'
        )

        # Quick-reply chips only (no emoji reaction buttons)
        if sender == "JARVIS" and origin == "assistant":
            block += self._get_quick_reply_html(text)

        block += '</div>'

        # Feature 2: Update status bar
        self._message_count += 1
        if sender == "JARVIS":
            self._total_token_estimate += max(len(text) // 4, 1)
        self._update_status_bar()

        # Log raw entry for export
        role_map = {"YOU": "user", "JARVIS": "assistant", "SYSTEM": "system"}
        self._raw_conversation_log.append({
            "role": role_map.get(sender, "system"),
            "content": text,
            "ts": ts,
        })

        self.chat_display.append(block)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_streaming_message(self, text: str, final: bool = False, raw: dict | None = None) -> None:
        if self._thinking_bubble_active:
            self._hide_thinking_bubble()

        if final:
            self._last_jarvis_response = text
            safe_text = self._md_to_html(text)
        else:
            safe_text = _html.escape(text).replace("\n", "<br>")

        cursor_hint = "" if final else (
            '<span style="color:rgba(148,163,184,0.5); font-size:14px; margin-left:4px;">▌</span>'
        )

        meta = self._build_metadata_badge(raw) if final else ""

        ts = datetime.now().strftime("%H:%M")

        extra_html = ""
        if final:
            extra_html += self._get_quick_reply_html(text)
            self._message_count += 1
            self._total_token_estimate += max(len(text) // 4, 1)
            self._update_status_bar()
            self._raw_conversation_log.append({
                "role": "assistant",
                "content": text,
                "ts": ts,
            })

        new_block = (
            f'<div style="margin:12px 0; text-align:left;">'
            f'<span style="color:rgba(148,163,184,0.45); font-size:10px;">{ts}</span><br>'
            f'<span style="color:#10B981; font-weight:700; font-size:11px; letter-spacing:0.8px;">JARVIS</span>'
            f'<div style="background:rgba(8,18,36,0.55); '
            f'border:1px solid rgba(0,200,232,0.14); '
            f'border-left:2px solid rgba(0,200,232,0.55); '
            f'border-radius:12px; padding:11px 16px; margin-top:5px; '
            f'color:#E8EDF5; max-width:90%; word-wrap:break-word; '
            f'font-size:{self._chat_font_size}px; line-height:1.7;">'
            f'{safe_text}{cursor_hint}{meta}</div>'
            f'{extra_html}</div>'
        )

        # Replace from the recorded stream anchor position to end of document
        anchor = getattr(self, "_stream_anchor", None)
        if anchor is not None:
            doc = self.chat_display.document()
            cursor = self.chat_display.textCursor()
            cursor.setPosition(anchor)
            cursor.movePosition(cursor.MoveOperation.End, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertHtml(new_block)
        else:
            self.chat_display.append(new_block)

        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_proactive_help(self, suggestion: str) -> None:
        self.runtime.send_text(suggestion)
        self.show()
        self.raise_()
        self.activateWindow()
        if self.runtime.screen_watcher:
            self.runtime.screen_watcher.record_acceptance()

    def _on_proactive_dismiss(self, category: str) -> None:
        if self.runtime.screen_watcher:
            self.runtime.screen_watcher.record_dismissal(category)

    def _update_status_bar(self) -> None:
        """Update status bar with message count, token estimate, and active provider."""
        if self._status_bar:
            provider_info = "ready"
            if hasattr(self, 'provider_cards') and self.provider_cards:
                for name, card in self.provider_cards.items():
                    if not card.enabled_checkbox.isChecked():
                        continue
                    # LocalAICard uses model_path_input (QLineEdit); ProviderCard uses model_input (QComboBox)
                    if hasattr(card, 'model_input'):
                        model = card.model_input.currentText().strip()
                    elif hasattr(card, 'model_path_input'):
                        import os as _os
                        model = _os.path.basename(card.model_path_input.text().strip()) or "local"
                    else:
                        model = ""
                    provider_info = f"{name} · {model}" if model else name
                    break

            current_time = datetime.now().strftime("%H:%M")
            _pill = (
                'background:rgba(0,200,232,0.07);border:1px solid rgba(0,200,232,0.15);'
                'border-radius:4px;padding:1px 8px;color:rgba(148,163,184,0.75);font-size:10px;'
                'margin-right:4px;'
            )
            self._status_bar.setText(
                f'<span style="{_pill}">{provider_info}</span>'
                f'<span style="{_pill}">{self._message_count} msgs</span>'
                f'<span style="{_pill}">~{self._total_token_estimate} tok</span>'
                f'<span style="{_pill}">{current_time}</span>'
            )
            # Sync provider badge in header and left panel
            if hasattr(self, '_provider_badge'):
                self._provider_badge.setText(provider_info.upper())
            if hasattr(self, '_left_model_label'):
                self._left_model_label.setText(provider_info)

    def _show_help_tip(self) -> None:
        """Feature 3: Display a contextual help tip above the input."""
        tip = self._help_tips[self._help_tip_index % len(self._help_tips)]
        self._help_tip_index += 1

        # Create help tip widget
        help_tip = QFrame()
        help_tip.setObjectName("helpTip")
        help_tip.setStyleSheet(
            "background: rgba(217,119,6,0.08); "
            "border: 1px solid rgba(217,119,6,0.18); "
            "border-radius: 10px; "
            "padding: 8px 12px;"
        )
        tip_layout = QHBoxLayout(help_tip)
        tip_layout.setContentsMargins(12, 8, 12, 8)
        tip_layout.setSpacing(10)

        tip_label = QLabel(f"💡 Tip: {tip}")
        tip_label.setStyleSheet("color: rgba(217,119,6,0.9); font-size: 11px;")
        tip_label.setWordWrap(True)
        tip_layout.addWidget(tip_label, 1)

        dismiss_btn = AnimatedButton("Got it")
        dismiss_btn.setFixedWidth(60)
        dismiss_btn.setFixedHeight(24)
        dismiss_btn.clicked.connect(lambda: help_tip.deleteLater())
        tip_layout.addWidget(dismiss_btn)

        # Insert help tip above input field (find input row and insert before it)
        # We'll store it as a temporary widget that gets removed after dismissal
        self._current_help_tip = help_tip

    def _open_bug_report(self) -> None:
        from jarvis.ui.bug_report_dialog import BugReportDialog
        dlg = BugReportDialog(parent=self, runtime=self.runtime)
        dlg.exec()

    def _new_chat_session(self) -> None:
        self.runtime.new_chat_session()

    def _show_history_panel(self) -> None:
        if not hasattr(self, "_history_dialog") or not self._history_dialog:
            self._history_dialog = _HistoryDialog(self)
        self._history_dialog.show()
        self._history_dialog.raise_()
        self.runtime.list_chat_sessions()

    def _clear_chat(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Clear Chat",
            "Clear the conversation display? (Memory is kept — use 'New chat' to also clear memory.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.chat_display.clear()
            self._last_jarvis_response = ""

    def _send_message(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self._char_counter.setText("0")
        self._history_index = -1

        if text.startswith("/"):
            self._handle_console_command(text)
            return

        if not self._command_history or self._command_history[-1] != text:
            self._command_history.append(text)
            if len(self._command_history) > 100:
                self._command_history.pop(0)

        self._last_user_message = text
        self.runtime.send_text(text)
        self._update_token_budget()

    def _quick_action(self, cmd: str) -> None:
        self.input_field.setText(cmd)
        if not cmd.endswith(" "):
            self._send_message()
        else:
            self.input_field.setFocus()

    def _handle_console_command(self, raw: str) -> None:
        parts = raw.strip().lstrip("/").split()
        if not parts:
            return
        cmd, args = parts[0].lower(), parts[1:]

        if cmd == "help":
            self._add_chat_message("SYSTEM", (
                "Console commands:\n"
                "  /help                          — show this help\n"
                "  /clear                         — clear chat window (with confirmation)\n"
                "  /status                        — show system status\n"
                "  /export                        — export chat as Markdown to ~/Downloads\n"
                "  /note <text>                   — save a quick note to ~/.jarvis/notes.txt\n"
                "  /notes                         — view recent saved notes\n"
                "  /version                       — show JARVIS version\n"
                "  /providers                     — list available providers\n"
                "  /tools                         — list available tools\n"
                "  /memory                        — show memory & context info\n"
                "  /workflow list                 — show execution flows\n"
                "  /provider <name>               — switch provider (groq, mistral, nexus…)\n"
                "  /groq [model]                  — switch to Groq, optionally set model\n"
                "  /fontsize <8-28>               — set chat font size\n"
                "  /plugins list                  — list all plugins\n"
                "  /plugins enable <name>         — enable a plugin\n"
                "  /plugins disable <name>        — disable a plugin\n"
                "  /demo                          — show demo status\n"
                "\nKeyboard shortcuts:\n"
                "  ↑ / ↓           — navigate command history\n"
                "  Ctrl+F          — search conversation\n"
                "  Ctrl+K          — command palette\n"
                "  Ctrl+Shift+J    — global hotkey (any app)\n"
                "  A+  /  A−       — increase / decrease font size\n"
                "  ?               — keyboard shortcuts panel\n"
                "  Right-click     — copy, retry, export options\n"
                "\nQuick bar: Time · Weather · Screenshot · Sysinfo · Search · Clipboard · Notes"
            ), "system")
        elif cmd == "clear":
            self._clear_chat()
        elif cmd == "status":
            self.runtime.get_status()
        elif cmd == "export":
            self._export_chat()
        elif cmd == "note":
            if not args:
                self._add_chat_message("SYSTEM", "Usage: /note <text to save>", "system")
            else:
                self._save_note(" ".join(args))
        elif cmd == "notes":
            self._view_notes()
        elif cmd == "fontsize":
            try:
                sz = int(args[0]) if args else 0
                if 8 <= sz <= 28:
                    self._change_font_size(sz - self._chat_font_size)
                    self._add_chat_message("SYSTEM", f"Font size set to {sz}px", "system")
                    NotificationToast.show_toast(f"Font size: {sz}px", "success", self, "fontsize", 5000)
                else:
                    self._add_chat_message("SYSTEM", "Usage: /fontsize 8–28", "system")
                    NotificationToast.show_toast("Font size must be 8–28", "warning", self, "fontsize", 6000)
            except ValueError:
                self._add_chat_message("SYSTEM", "Usage: /fontsize <size>  (8–28)", "system")
                NotificationToast.show_toast("Invalid font size", "error", self, "fontsize", 6000)
        elif cmd in ("provider", "model"):
            _valid = ["auto", "ollama", "groq", "gemini", "claude", "openai", "mistral", "openrouter"]
            if args and args[0].lower() in _valid:
                prov = args[0].lower()
                self._set_combo_value(self._quick_provider_combo, prov)
                settings = self._collect_settings()
                settings["primary_provider"] = prov
                self.runtime.apply_settings(settings)
                self._add_chat_message("SYSTEM", f"Switched to {prov}", "system")
                NotificationToast.show_toast(f"Using {prov}", "success", self, "provider", 6000)
            else:
                current = self._quick_provider_combo.currentData()
                self._add_chat_message("SYSTEM",
                    f"Current provider: {current}\n"
                    f"Usage: /provider <{' | '.join(_valid)}>", "system")
        elif cmd == "groq":
            # Convenience shortcut: switch to Groq + optionally set model
            self._set_combo_value(self._quick_provider_combo, "groq")
            if args:
                card = self.provider_cards.get("groq")
                if card:
                    if card.model_input.findText(args[0]) == -1:
                        card.model_input.insertItem(0, args[0])
                    card.model_input.setCurrentText(args[0])
            settings = self._collect_settings()
            settings["primary_provider"] = "groq"
            self.runtime.apply_settings(settings)
            model_now = self.provider_cards["groq"].model_input.currentText() if "groq" in self.provider_cards else ""
            self._add_chat_message("SYSTEM", f"Switched to Groq · {model_now}", "system")
            NotificationToast.show_toast(f"Groq: {model_now}", "success", self, "groq", 6000)
        elif cmd == "plugins":
            sub = args[0].lower() if args else "list"
            if sub == "list":
                self.runtime.list_plugins()
            elif sub == "enable" and len(args) > 1:
                self.runtime.enable_plugin(args[1])
            elif sub == "disable" and len(args) > 1:
                self.runtime.disable_plugin(args[1])
            else:
                self._add_chat_message("SYSTEM", "Usage: /plugins [list | enable <name> | disable <name>]", "system")
        elif cmd == "version":
            version = getattr(self.runtime, "version", "unknown")
            self._add_chat_message("SYSTEM", f"JARVIS version: {version}", "system")
        elif cmd == "providers":
            providers_info = (
                "Available providers:\n"
                "  • auto          — auto-detect (default)\n"
                "  • groq          — Groq (fast inference)\n"
                "  • gpt           — GPT models\n"
                "  • mistral       — Mistral\n"
                "  • gemini        — Gemini\n"
                "  • ollama        — Ollama (local)\n"
                "  • openrouter    — OpenRouter\n\n"
                "Current: " + (self._quick_provider_combo.currentData() or "auto")
            )
            self._add_chat_message("SYSTEM", providers_info, "system")
        elif cmd == "tools":
            tools_info = (
                "Available tools:\n"
                "  • Web Search       — search the internet\n"
                "  • File System      — read/write files\n"
                "  • System Info      — get hardware/OS info\n"
                "  • Screenshot       — capture desktop\n"
                "  • Code Exec        — execute Python code\n"
                "  • Browser Control  — control web browser\n"
                "  • Memory Recall    — access chat history\n"
                "  • Notes            — save/retrieve notes\n"
                "  • Plugins          — extend capabilities\n\n"
                "Use /workflow list to see execution flows"
            )
            self._add_chat_message("SYSTEM", tools_info, "system")
        elif cmd == "memory":
            memory_info = (
                "Memory & Context:\n"
                f"  • Total messages:  {len(self._message_ratings)} tracked\n"
                f"  • Command history: {len(self._command_history)} items\n"
                f"  • Last user:       {self._last_user_message[:60]}...\n"
                f"  • Last jarvis:     {self._last_jarvis_response[:60]}...\n"
                f"  • Current session: active\n"
                f"  • Context tokens:  estimated ~2000\n\n"
                "Use /notes to view saved notes and memory"
            )
            self._add_chat_message("SYSTEM", memory_info, "system")
        elif cmd == "workflow":
            sub = args[0].lower() if args else "list"
            if sub == "list":
                workflow_info = (
                    "Workflow execution flows:\n"
                    "  • Input Handling   → Text processing → Inference\n"
                    "  • Tool Invocation  → Tool selection → Tool execution → Result parsing\n"
                    "  • Response Stream  → Token accumulation → Display update → Audio synthesis\n"
                    "  • Memory Update    → Message logging → Context refresh\n"
                    "  • Plugin Chain     → Plugin discovery → Hook execution → Result merge\n\n"
                    "Each flow handles errors gracefully with fallback paths"
                )
                self._add_chat_message("SYSTEM", workflow_info, "system")
            else:
                self._add_chat_message("SYSTEM", "Usage: /workflow list", "system")
        elif cmd == "demo":
            if not self.demo_mode:
                self._add_chat_message("SYSTEM", "Demo mode not active. Launch with --demo flag to enable.", "system")
            else:
                self._add_chat_message("SYSTEM", "Demo messages already scheduled. Watch the chat for automated responses.", "system")
        else:
            self._add_chat_message("SYSTEM", f"Unknown command: /{cmd}  -- type /help for commands", "system")

    def _export_chat(self) -> None:
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path.home() / "Downloads" / f"jarvis_chat_{ts_str}.md"
        try:
            # Use raw conversation log if available (preserves code blocks)
            if hasattr(self, "_raw_conversation_log") and self._raw_conversation_log:
                md_lines = [
                    f"# JARVIS Conversation — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    f"*Exported from J.A.R.V.I.S. — https://github.com/ONEPUNCHMAN411/Jarvis*\n",
                ]
                for entry in self._raw_conversation_log:
                    role = entry.get("role", "")
                    content = entry.get("content", "")
                    entry_ts = entry.get("ts", "")
                    if role == "user":
                        md_lines.append(f"\n---\n**You** _{entry_ts}_\n\n{content}")
                    elif role == "assistant":
                        md_lines.append(f"\n---\n**JARVIS** _{entry_ts}_\n\n{content}")
                    elif role == "system":
                        md_lines.append(f"\n> {content}")
            else:
                # Fallback: extract from plain text, preserving structure
                plain = self.chat_display.toPlainText()
                lines = plain.splitlines()
                md_lines = [
                    f"# JARVIS Conversation — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
                ]
                in_code = False
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("```"):
                        in_code = not in_code
                    if in_code:
                        md_lines.append(line)
                        continue
                    if not stripped:
                        md_lines.append("")
                        continue
                    if stripped.startswith("YOU") and (stripped.startswith("YOU:") or " " in stripped[:4]):
                        md_lines.append(f"\n**You:** {stripped.split(':', 1)[-1].strip() if ':' in stripped else stripped}")
                    elif stripped.startswith("JARVIS"):
                        md_lines.append(f"\n**JARVIS:** {stripped.split(':', 1)[-1].strip() if ':' in stripped else stripped}")
                    elif stripped.startswith("SYSTEM"):
                        md_lines.append(f"> {stripped.split(':', 1)[-1].strip()}")
                    else:
                        md_lines.append(stripped)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(md_lines))
            self._add_chat_message("SYSTEM", f"Chat exported to: {path}", "system")
            NotificationToast.show_toast("Chat exported to Downloads", "success", self, "export", 8000)
        except Exception as exc:
            self._add_chat_message("SYSTEM", f"Export failed: {exc}", "system")
            NotificationToast.show_toast(f"Export failed: {str(exc)}", "error", self, "export", 10000)

    def _save_note(self, text: str) -> None:
        notes_path = Path.home() / ".jarvis" / "notes.txt"
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(notes_path, "a", encoding="utf-8") as fh:
                fh.write(f"[{ts}] {text}\n")
            self._add_chat_message("SYSTEM", f"Note saved: {text}", "system")
            NotificationToast.show_toast("Note saved", "success", self, "note", 6000)
        except Exception as exc:
            self._add_chat_message("SYSTEM", f"Note save failed: {exc}", "system")
            NotificationToast.show_toast(f"Note save failed: {str(exc)}", "error", self, "note", 10000)

    def _view_notes(self) -> None:
        notes_path = Path.home() / ".jarvis" / "notes.txt"
        if not notes_path.exists():
            self._add_chat_message("SYSTEM", "No notes saved yet. Use /note <text> to save one.", "system")
            NotificationToast.show_toast("No notes saved yet", "info", self, "notes", 6000)
            return
        try:
            with open(notes_path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            recent = "".join(lines[-20:]).strip()
            self._add_chat_message("SYSTEM", f"Recent notes (last 20):\n{recent}", "system")
            NotificationToast.show_toast(f"Showing {min(len(lines), 20)} notes", "info", self, "notes", 6000)
        except Exception as exc:
            self._add_chat_message("SYSTEM", f"Could not read notes: {exc}", "system")
            NotificationToast.show_toast(f"Could not read notes: {str(exc)}", "error", self, "notes", 10000)

    def _paste_clipboard(self) -> None:
        try:
            import pyperclip
            text = pyperclip.paste().strip()
            if text:
                self.input_field.setText(text)
                self.input_field.setFocus()
        except Exception:
            pass

    def _refresh_plugins(self) -> None:
        self.runtime.list_plugins()

    def _update_plugins_ui(self, plugins: list[dict]) -> None:
        # Clear existing rows
        while self._plugins_layout.count():
            item = self._plugins_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._plugin_rows.clear()

        if not plugins:
            lbl = QLabel("No plugins registered")
            lbl.setObjectName("muted")
            self._plugins_layout.addWidget(lbl)
            return

        for p in plugins:
            name = p["name"]
            enabled = p.get("enabled", True)
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {'#34D399' if enabled else '#FB7185'}; font-size: 10px;")
            lbl = QLabel(name)
            lbl.setObjectName("muted")
            toggle = AnimatedButton("Disable" if enabled else "Enable")
            toggle.setFixedWidth(68)
            toggle.clicked.connect(
                lambda _, n=name, e=enabled: (
                    self.runtime.disable_plugin(n) if e else self.runtime.enable_plugin(n)
                )
            )
            row.addWidget(dot)
            row.addWidget(lbl, 1)
            row.addWidget(toggle)
            row_widget = QWidget()
            row_widget.setLayout(row)
            self._plugins_layout.addWidget(row_widget)
            self._plugin_rows[name] = row_widget

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()
        if mods == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_F:
                self._toggle_search()
                return
            if key == Qt.Key.Key_K:
                self._show_command_palette()
                return
            if key == Qt.Key.Key_N:
                self._new_chat_session()
                return
            if key == Qt.Key.Key_E:
                self._export_chat()
                return
            if key == Qt.Key.Key_L:
                self._clear_chat()
                return
            if key == Qt.Key.Key_Comma:
                self._show_settings_panel()
                return
        elif mods == Qt.KeyboardModifier.AltModifier:
            # Alt+1 through Alt+8 for provider selection
            if Qt.Key.Key_1 <= key <= Qt.Key.Key_8:
                provider_index = key - Qt.Key.Key_1
                self._select_provider_by_index(provider_index)
                return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if getattr(self, 'search_bar', None) is obj and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._toggle_search()
                return True
        # Feature 3: Show help tip on first input focus
        if getattr(self, 'input_field', None) is obj and event.type() == QEvent.Type.FocusIn:
            if not self._help_tip_shown_this_session:
                self._show_help_tip()
                self._help_tip_shown_this_session = True
        if getattr(self, 'input_field', None) is obj and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Up:
                if self._command_history:
                    if self._history_index == -1:
                        self._history_index = len(self._command_history) - 1
                    elif self._history_index > 0:
                        self._history_index -= 1
                    self.input_field.setText(self._command_history[self._history_index])
                    self.input_field.end(False)
                return True
            if key == Qt.Key.Key_Down:
                if self._history_index >= 0:
                    self._history_index += 1
                    if self._history_index >= len(self._command_history):
                        self._history_index = -1
                        self.input_field.clear()
                    else:
                        self.input_field.setText(self._command_history[self._history_index])
                        self.input_field.end(False)
                return True
        return super().eventFilter(obj, event)

    def _show_settings_panel(self) -> None:
        """Show settings panel (Ctrl+,)."""
        self._show_shortcuts_panel()

    def _select_provider_by_index(self, index: int) -> None:
        """Select provider by numeric index Alt+1-8."""
        providers_list = ["auto", "ollama", "groq", "gemini", "claude", "openai", "mistral", "openrouter"]
        if index < len(providers_list):
            provider = providers_list[index]
            self._set_combo_value(self._quick_provider_combo, provider)
            settings = self._collect_settings()
            settings["primary_provider"] = provider
            self.runtime.apply_settings(settings)
            self._add_chat_message("SYSTEM", f"Switched to {provider} (Alt+{index+1})", "system")
            NotificationToast.show_toast(f"Using {provider}", "success", self, "alt_provider", 5000)

    def _clear_chat_silent(self) -> None:
        """Clear chat without confirmation."""
        if hasattr(self, 'chat_display'):
            self.chat_display.clear()
            self._message_ratings.clear()

    def _show_overlay_only(self) -> None:
        self.runtime.set_background_state(True)
        self.overlay_window.apply_mode(self.overlay_mode_combo.currentData())
        self.overlay_window.show_overlay()
        self.hide()

    def _go_background(self) -> None:
        self._show_overlay_only()
        self.tray_icon.showMessage(
            "JARVIS",
            "Orb overlay is active. Double-click it to reopen the console.",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )

    def _on_startup_toggled(self, checked: bool) -> None:
        from jarvis.utils.startup_manager import set_startup
        minimized = self.start_minimized_toggle.isChecked()
        ok = set_startup(checked, minimized)
        if ok:
            state = "added to" if checked else "removed from"
            self._add_activity("info", f"JARVIS {state} Windows startup.")
        else:
            self._add_activity("error", "Failed to update Windows startup registry (run as user).")

    def _on_voice_toggle_changed(self, checked: bool) -> None:
        if checked and self._mute_button.isChecked():
            self._mute_button.setChecked(False)
            self._mute_button.setText("Mute mic")

    def _toggle_mic_mute(self) -> None:
        muted = self._mute_button.isChecked()
        self._mute_button.setText("Unmute mic" if muted else "Mute mic")
        # Don't uncheck voice_toggle — mute is temporary, toggle is the persistent setting.
        settings = self._collect_settings()
        settings["voice_enabled"] = not muted
        self.runtime.apply_settings(settings)
        self._add_activity("info", "Mic muted" if muted else "Mic unmuted")

    def _on_talk_clicked(self) -> None:
        settings = self._collect_settings()
        current_mode = settings.get("background_mode", "wake_phrase")
        new_mode = "always_listening" if current_mode == "wake_phrase" else "wake_phrase"
        settings["background_mode"] = new_mode
        self.runtime.apply_settings(settings)
        self.mode_chip.setText("Always listening" if new_mode == "always_listening" else "Wake phrase")
        self._add_activity("info", "Now always listening" if new_mode == "always_listening" else "Wake phrase mode")

    def _toggle_side_panels(self) -> None:
        splitter = self.centralWidget().findChild(QSplitter)
        if splitter and splitter.count() >= 3:
            left = splitter.widget(0)
            right = splitter.widget(2)
            visible = left.isVisible()
            left.setVisible(not visible)
            right.setVisible(not visible)

    def _on_hero_mute_clicked(self) -> None:
        muted = self._hero_mute_btn.isChecked()
        self._hero_mute_btn.setText("Unmute" if muted else "Mute")
        if hasattr(self, "_mute_button"):
            self._mute_button.setChecked(muted)
            self._mute_button.setText("Unmute mic" if muted else "Mute mic")
        settings = self._collect_settings()
        settings["voice_enabled"] = not muted
        self.runtime.apply_settings(settings)
        self._add_activity("info", "Mic muted" if muted else "Mic unmuted")

    def _on_quick_policy_changed(self, _index: int) -> None:
        policy = self._quick_policy_combo.currentData()
        if hasattr(self, "policy_combo"):
            self._set_combo_value(self.policy_combo, policy)
        settings = self._collect_settings()
        settings["automation_policy"] = policy
        self.runtime.apply_settings(settings)

    def _browse_working_dir(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Select working directory",
                                                self._wdir_input.text() or "")
        if path:
            self._wdir_input.setText(path)

    def _relaunch_as_admin(self) -> None:
        import ctypes, sys
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                                " ".join(["-m", "jarvis"]), None, 1)
            QApplication.instance().quit()
        except Exception as e:
            self._add_activity("error", f"Could not relaunch as admin: {e}")

    def _check_wake_word_status(self) -> None:
        try:
            import openwakeword  # noqa: F401
        except ImportError:
            if hasattr(self, "_wake_word_status_lbl"):
                self._wake_word_status_lbl.setText(
                    "Wake word unavailable — openwakeword not installed. "
                    "Run: pip install openwakeword"
                )
                self._wake_word_status_lbl.show()

    def _show_approval_bar(self, approval_id: str, action_name: str) -> None:
        self._approval_id = approval_id
        self._approval_label.setText(
            f"JARVIS wants to run: <b style='color:#8B7CFF;'>{action_name}</b>"
        )
        self._approval_bar.show()

    def _hide_approval_bar(self) -> None:
        self._approval_bar.hide()
        self._approval_id = None

    def _on_approve_action(self) -> None:
        if self._approval_id:
            self.runtime.approve_action(self._approval_id, always=False)
        self._hide_approval_bar()

    def _on_always_approve_action(self) -> None:
        if self._approval_id:
            self.runtime.approve_action(self._approval_id, always=True)
        self._hide_approval_bar()

    def _on_decline_action(self) -> None:
        if self._approval_id:
            self.runtime.decline_action(self._approval_id)
        self._hide_approval_bar()

    def _restore_from_overlay(self) -> None:
        self.runtime.set_background_state(False)
        self.overlay_window.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._quitting = True
        self.overlay_window.hide()
        self.tray_icon.hide()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        # Stop all timers to prevent Qt warnings on exit
        self._thinking_timer.stop()
        self._sys_timer.stop()
        if self._quitting:
            event.accept()
            return
        # Ask user: quit or minimize to orb?
        from PyQt6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("JARVIS")
        box.setText("Minimize JARVIS to the orb overlay, or quit completely?")
        minimize_btn = box.addButton("Minimize to orb", QMessageBox.ButtonRole.AcceptRole)
        quit_btn = box.addButton("Quit", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(minimize_btn)
        box.exec()
        if box.clickedButton() == quit_btn:
            self._quitting = True
            self.overlay_window.hide()
            self.tray_icon.hide()
            QApplication.instance().quit()
            event.accept()
        else:
            event.ignore()
            self._go_background()

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _populate_mic_devices(self) -> None:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    self.mic_device_combo.addItem(dev["name"], i)
        except Exception:
            pass

    def _toggle_search(self) -> None:
        self._search_visible = not self._search_visible
        if self._search_visible:
            self.search_bar.show()
            self.search_bar.setFocus()
            self.search_bar.selectAll()
        else:
            self.search_bar.hide()
            self.search_bar.clear()
            self.chat_display.setFocus()

    def _on_search_changed(self, text: str) -> None:
        if not text:
            self.chat_display.setExtraSelections([])
            return
        cursor = self.chat_display.document().find(text)
        if not cursor.isNull():
            self.chat_display.setTextCursor(cursor)

    def _chat_context_menu(self, pos) -> None:
        menu = QMenu(self)
        copy_sel = menu.addAction("Copy selection")
        copy_sel.triggered.connect(self.chat_display.copy)
        if self._last_jarvis_response:
            copy_last = menu.addAction("Copy last JARVIS response")
            copy_last.triggered.connect(self._copy_last_response)
        copy_all = menu.addAction("Copy full transcript")
        copy_all.triggered.connect(
            lambda: QApplication.clipboard().setText(self.chat_display.toPlainText())
        )
        menu.addSeparator()
        if self._last_user_message:
            retry_action = menu.addAction("Retry last message")
            retry_action.triggered.connect(self._retry_last_message)
        menu.addSeparator()
        export_action = menu.addAction("Export as Markdown…")
        export_action.triggered.connect(self._export_chat)
        clear_action = menu.addAction("Clear chat")
        clear_action.triggered.connect(self._clear_chat)
        menu.exec(self.chat_display.mapToGlobal(pos))

    def _copy_last_response(self) -> None:
        if self._last_jarvis_response:
            QApplication.clipboard().setText(self._last_jarvis_response)

    def _change_font_size(self, delta: int) -> None:
        self._chat_font_size = max(8, min(28, self._chat_font_size + delta))
        # Re-render the chat display with new font size by tweaking QTextEdit font
        font = self.chat_display.font()
        font.setPointSize(self._chat_font_size)
        self.chat_display.setFont(font)

    def _get_active_model_label(self, provider: str) -> str:
        """Return short model name for a given provider (from current UI state)."""
        card = self.provider_cards.get(provider.lower()) if hasattr(self, "provider_cards") else None
        if not card:
            return ""
        if hasattr(card, 'model_input'):
            model = card.model_input.currentText().strip()
        elif hasattr(card, 'model_path_input'):
            import os as _os2
            model = _os2.path.basename(card.model_path_input.text().strip()) or "local"
        else:
            model = ""
        # Shorten long model names for the badge
        if len(model) > 24:
            model = model[:22] + "…"
        return model

    def _choose_working_directory(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        from pathlib import Path as _Path
        current = self.settings.get("working_directory", str(_Path.home()))
        chosen = QFileDialog.getExistingDirectory(self, "Choose working directory", current)
        if chosen:
            self.settings["working_directory"] = chosen
            if hasattr(self, "_cwd_label"):
                self._cwd_label.setText(chosen)
            import os
            os.chdir(chosen)
            self.runtime.apply_settings(self.settings)

    def _on_quick_provider_changed(self, _idx: int) -> None:
        # Sync from whichever combo fired (header or conversation bar)
        sender = self.sender()
        if sender is self._header_model_combo:
            prov = self._header_model_combo.currentData()
            # Mirror to conversation combo without triggering loop
            idx = self._quick_provider_combo.findData(prov)
            if idx >= 0:
                self._quick_provider_combo.blockSignals(True)
                self._quick_provider_combo.setCurrentIndex(idx)
                self._quick_provider_combo.blockSignals(False)
        else:
            prov = self._quick_provider_combo.currentData()
            idx = self._header_model_combo.findData(prov)
            if idx >= 0:
                self._header_model_combo.blockSignals(True)
                self._header_model_combo.setCurrentIndex(idx)
                self._header_model_combo.blockSignals(False)
        if not prov:
            return
        self._set_combo_value(self.primary_provider_combo, prov)
        settings = self._collect_settings()
        settings["primary_provider"] = prov
        self.runtime.apply_settings(settings)
        self._update_token_budget()

    def _on_calendar_date_clicked(self) -> None:
        """Show date info and prompt to ask JARVIS for events on that day."""
        if not hasattr(self, "_cal_event_label"):
            return
        from datetime import date as _date
        sel = self._calendar_widget.selectedDate()
        today = _date.today()
        chosen = _date(sel.year(), sel.month(), sel.day())
        diff = (chosen - today).days
        if diff == 0:
            rel = "Today"
        elif diff == 1:
            rel = "Tomorrow"
        elif diff == -1:
            rel = "Yesterday"
        elif diff > 1:
            rel = f"In {diff} days"
        else:
            rel = f"{-diff} days ago"
        self._cal_event_label.setText(
            f"{rel} — {sel.toString('dddd, MMMM d')}\n"
            "Ask JARVIS about events on this day →"
        )
        self._cal_event_label.mousePressEvent = lambda _e: self._quick_action(
            f"What events or tasks do I have on {sel.toString('MMMM d, yyyy')}?"
        )

    def _open_pomodoro_panel(self) -> None:
        """Open the Pomodoro timer mini panel."""
        if not hasattr(self, "_pomodoro_dlg") or self._pomodoro_dlg is None:
            self._pomodoro_dlg = _PomodoroDialog(self)
        self._pomodoro_dlg.show()
        self._pomodoro_dlg.raise_()

    def _open_image_gen_panel(self) -> None:
        """Open the image generation mini panel."""
        if not hasattr(self, "_image_gen_dlg") or self._image_gen_dlg is None:
            self._image_gen_dlg = _ImageGenDialog(self)
        self._image_gen_dlg._on_generate = lambda prompt, style: self._quick_action(
            f"Generate an image: {prompt}. Style: {style}."
        )
        self._image_gen_dlg.show()
        self._image_gen_dlg.raise_()

    def _open_ocr_panel(self) -> None:
        """Run OCR via JARVIS directly."""
        self._quick_action("Take a screenshot and extract all readable text from it using OCR")

    # ── Plugin panel openers (singleton pattern) ──────────────────────────────

    def _open_spotify_panel(self) -> None:
        if not hasattr(self, "_spotify_dlg") or self._spotify_dlg is None:
            self._spotify_dlg = SpotifyDialog(self)
        self._spotify_dlg.show()
        self._spotify_dlg.raise_()

    def _open_todo_panel(self) -> None:
        if not hasattr(self, "_todo_dlg") or self._todo_dlg is None:
            self._todo_dlg = TodoDialog(self)
        self._todo_dlg.show()
        self._todo_dlg.raise_()
        QTimer.singleShot(0, self._todo_dlg._refresh)

    def _open_notes_panel(self) -> None:
        if not hasattr(self, "_notes_dlg") or self._notes_dlg is None:
            self._notes_dlg = NotesDialog(self)
        self._notes_dlg.show()
        self._notes_dlg.raise_()

    def _open_clipboard_panel(self) -> None:
        if not hasattr(self, "_clipboard_dlg") or self._clipboard_dlg is None:
            self._clipboard_dlg = ClipboardDialog(self)
        self._clipboard_dlg.show()
        self._clipboard_dlg.raise_()
        QTimer.singleShot(0, self._clipboard_dlg._refresh)

    def _open_translator_panel(self) -> None:
        if not hasattr(self, "_translator_dlg") or self._translator_dlg is None:
            self._translator_dlg = TranslatorDialog(self)
        self._translator_dlg.show()
        self._translator_dlg.raise_()

    def _open_qr_panel(self) -> None:
        if not hasattr(self, "_qr_dlg") or self._qr_dlg is None:
            self._qr_dlg = QRDialog(self)
        self._qr_dlg.show()
        self._qr_dlg.raise_()

    def _open_voice_memo_panel(self) -> None:
        if not hasattr(self, "_voice_memo_dlg") or self._voice_memo_dlg is None:
            self._voice_memo_dlg = VoiceMemoDialog(self)
        self._voice_memo_dlg.show()
        self._voice_memo_dlg.raise_()

    def _open_habit_panel(self) -> None:
        if not hasattr(self, "_habit_dlg") or self._habit_dlg is None:
            self._habit_dlg = HabitDialog(self)
        self._habit_dlg.show()
        self._habit_dlg.raise_()

    def _open_alert_panel(self) -> None:
        if not hasattr(self, "_alert_dlg") or self._alert_dlg is None:
            self._alert_dlg = AlertDialog(self)
        self._alert_dlg.show()
        self._alert_dlg.raise_()

    def _open_web_remote_panel(self) -> None:
        if not hasattr(self, "_web_remote_dlg") or self._web_remote_dlg is None:
            self._web_remote_dlg = WebRemoteDialog(self)
        self._web_remote_dlg.show()
        self._web_remote_dlg.raise_()

    def _open_panel_by_name(self, name: str) -> None:
        """Called by UIBridge when a tool asks to open a panel that doesn't exist yet."""
        if name == "todo":
            self._open_todo_panel()
        elif name == "notes":
            self._open_notes_panel()
        elif name == "clipboard":
            self._open_clipboard_panel()
        elif name == "spotify":
            self._open_spotify_panel()
        elif name == "web_remote":
            self._open_web_remote_panel()
        elif name == "translator":
            self._open_translator_panel()
        elif name == "qr":
            self._open_qr_panel()
        elif name == "voice_memos":
            self._open_voice_memos_panel()
        elif name == "habits":
            self._open_habits_panel()
        elif name == "alerts":
            self._open_alerts_panel()
        else:
            logger.warning(f"_open_panel_by_name: unknown panel {name!r}")

    def _update_token_budget(self) -> None:
        prov = self._quick_provider_combo.currentData() or "auto"
        model = ""
        if hasattr(self, "provider_cards"):
            card = self.provider_cards.get(prov)
            if card:
                model = card.model_input.currentText().strip().lower()

        ctx_window = 8_192
        if prov == "groq":
            caps = _groq_model_caps(model)
            ctx_window = caps["ctx"]
        elif prov in ("claude", "openai", "gemini"):
            ctx_window = 128_000
        elif prov == "mistral":
            ctx_window = 32_000

        # Rough estimate: memory messages * avg 200 tokens each
        if self.runtime.memory:
            n_msgs = len(self.runtime.memory.get_all_messages())
            est_used = n_msgs * 200
        else:
            est_used = 0

        pct = min(100, int(est_used * 100 / ctx_window)) if ctx_window else 0
        color = "#34D399" if pct < 60 else ("#FBBF24" if pct < 85 else "#FB7185")
        self._token_budget_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._token_budget_label.setText(f"~{pct}% ctx")

    def _on_input_changed(self, text: str) -> None:
        chars = len(text)
        tokens = max(1, chars // 4)
        self._char_counter.setText(f"{chars}" if chars < 1000 else f"~{tokens}t")

    def _tick_elapsed(self) -> None:
        import time as _time
        elapsed = _time.monotonic() - self._elapsed_start
        self._elapsed_label.setText(f"{elapsed:.1f}s")

    def _tick_clock(self) -> None:
        now = datetime.now()
        self._clock_label.setText(now.strftime("%H:%M:%S"))
        if hasattr(self, "_date_label"):
            self._date_label.setText(now.strftime("%a, %b %d %Y"))

    # Thinking animation
    def _show_thinking_bubble(self) -> None:
        """Insert an animated thinking placeholder bubble into the chat."""
        if self._thinking_bubble_active:
            return
        self._thinking_bubble_active = True
        self._thinking_dot_phase = 0
        self._append_thinking_html()
        self._thinking_timer.start()

    def _hide_thinking_bubble(self) -> None:
        """Remove the thinking placeholder bubble."""
        if not self._thinking_bubble_active:
            return
        self._thinking_bubble_active = False
        self._thinking_timer.stop()
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
        while cursor.position() > 0:
            if "thinking-bubble" in cursor.selectedText() or "2DE8B0" in cursor.selectedText():
                break
            cursor.movePosition(cursor.MoveOperation.PreviousBlock, cursor.MoveMode.KeepAnchor)
        cursor.movePosition(cursor.MoveOperation.End, cursor.MoveMode.KeepAnchor)
        try:
            cursor.removeSelectedText()
            cursor.deletePreviousChar()
        except Exception:
            pass

    def _append_thinking_html(self) -> None:
        """Append a minimal working-indicator bar into the chat display."""
        bars = self._thinking_bars_html()
        ts = datetime.now().strftime("%H:%M")
        block = (
            f'<div style="margin:12px 0; text-align:left;" class="thinking-bubble">'
            f'<span style="color:rgba(148,163,184,0.45); font-size:10px;">{ts}</span>'
            f'<span style="color:rgba(45,232,176,0.30); font-size:9px;"> ⟳</span>'
            f'<div style="display:inline-block; background:rgba(6,9,20,0.80); '
            f'border-left:2px solid rgba(45,232,176,0.70); '
            f'border-radius:0 6px 6px 0; padding:9px 18px; margin-top:4px; margin-left:4px;">'
            f'{bars}</div></div>'
        )
        self.chat_display.append(block)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _thinking_bars_html(self) -> str:
        """Generate pulsing bar segments based on current phase."""
        phase = self._thinking_dot_phase % 4
        widths = [28, 16, 22, 10]
        bars = []
        for i, w in enumerate(widths):
            active = (i == phase)
            opacity = "0.90" if active else "0.25"
            bars.append(
                f'<span style="display:inline-block; width:{w}px; height:3px; '
                f'background:#2DE8B0; opacity:{opacity}; border-radius:2px; margin:0 2px; '
                f'vertical-align:middle;"></span>'
            )
        return "".join(bars)

    def _tick_thinking_dots(self) -> None:
        """Update the thinking dots animation by replacing the bubble."""
        if not self._thinking_bubble_active:
            return
        self._thinking_dot_phase += 1
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
        while cursor.position() > 0:
            sel = cursor.selectedText()
            if "⟳" in sel:
                break
            cursor.movePosition(cursor.MoveOperation.PreviousBlock, cursor.MoveMode.KeepAnchor)
        cursor.movePosition(cursor.MoveOperation.End, cursor.MoveMode.KeepAnchor)
        try:
            cursor.removeSelectedText()
            cursor.deletePreviousChar()
        except Exception:
            pass
        self._append_thinking_html()

    # Tool call visualization
    def _show_tool_call_bubble(self, tool_name: str, args: dict) -> None:
        """Show a compact inline tool call block in the chat."""
        # Build argument summary (first 60 chars)
        try:
            arg_str = ", ".join(f"{k}={repr(v)[:20]}" for k, v in list(args.items())[:3])
        except Exception:
            arg_str = str(args)[:60]
        if len(arg_str) > 60:
            arg_str = arg_str[:57] + "…"
        self._active_tool_block_id = tool_name
        ts = datetime.now().strftime("%H:%M")
        block = (
            f'<div style="margin:6px 0; text-align:left;" id="tool-{tool_name}">'
            f'<div style="display:inline-block; background:rgba(245,158,11,0.08); '
            f'border:1px solid rgba(245,158,11,0.22); border-radius:10px; '
            f'padding:8px 14px; max-width:80%;">'
            f'<span style="color:rgba(251,191,36,0.90); font-size:11px; font-weight:600;">'
            f'⚙ {_html.escape(tool_name)}'
            f'</span>'
            f'<span style="color:rgba(148,163,184,0.60); font-size:11px;">'
            f'({_html.escape(arg_str)})</span><br>'
            f'<span style="color:rgba(251,191,36,0.60); font-size:11px;">'
            f'Running…</span>'
            f'</div></div>'
        )
        self.chat_display.append(block)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_tool_result_bubble(self, tool_name: str, result: str, success: bool) -> None:
        """Update the tool call bubble to show the result."""
        self._active_tool_block_id = None
        preview = result[:120] + ("…" if len(result) > 120 else "")
        status_color = "#34D399" if success else "#FB7185"
        status_icon = "✓" if success else "✗"
        # Append a result line (can't easily update in-place with QTextEdit HTML)
        block = (
            f'<div style="margin:2px 0 6px 14px; text-align:left;">'
            f'<div style="display:inline-block; background:rgba(245,158,11,0.05); '
            f'border-left:3px solid {status_color}; border-radius:0 6px 6px 0; '
            f'padding:4px 12px; max-width:76%;">'
            f'<span style="color:{status_color}; font-size:11px;">{status_icon} </span>'
            f'<span style="color:rgba(148,163,184,0.70); font-size:11px;">'
            f'{_html.escape(preview)}</span>'
            f'</div></div>'
        )
        self.chat_display.append(block)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    # System resource monitoring
    def _update_sys_resources(self) -> None:
        """Poll CPU/RAM/disk/GPU usage and update sidebar gauges."""
        if not _PSUTIL_AVAILABLE:
            return
        try:
            cpu  = _psutil.cpu_percent(interval=None)
            ram  = _psutil.virtual_memory().percent
            disk = _psutil.disk_usage("/").percent
            if hasattr(self, "_cpu_gauge"):
                self._cpu_gauge.set_value(int(cpu))
            if hasattr(self, "_ram_gauge"):
                self._ram_gauge.set_value(int(ram))
            if hasattr(self, "_disk_gauge"):
                self._disk_gauge.set_value(int(disk))
            # GPU + VRAM via pynvml or gputil
            if hasattr(self, "_gpu_gauge"):
                try:
                    import pynvml as _nv
                    _nv.nvmlInit()
                    h = _nv.nvmlDeviceGetHandleByIndex(0)
                    util = _nv.nvmlDeviceGetUtilizationRates(h)
                    mem  = _nv.nvmlDeviceGetMemoryInfo(h)
                    self._gpu_gauge.set_value(int(util.gpu))
                    self._vram_gauge.set_value(int(mem.used * 100 / mem.total))
                except Exception:
                    pass  # GPU stats unavailable — leave gauge at last value
            if hasattr(self, "_net_graph"):
                try:
                    net  = _psutil.net_io_counters()
                    sent = getattr(net, "bytes_sent", 0)
                    prev = getattr(self, "_prev_net_sent", sent)
                    self._net_graph.push((sent - prev) / 1024)
                    self._prev_net_sent = sent
                except Exception:
                    pass
            if hasattr(self, "_cpu_bar"):
                self._cpu_bar.setValue(int(cpu))
            if hasattr(self, "_cpu_val_lbl"):
                color = "#34D399" if cpu < 60 else ("#FBBF24" if cpu < 80 else "#FB7185")
                self._cpu_val_lbl.setText(f"{cpu:.0f}%")
                self._cpu_val_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
            if hasattr(self, "_ram_bar"):
                self._ram_bar.setValue(int(ram))
            if hasattr(self, "_ram_val_lbl"):
                color = "#34D399" if ram < 60 else ("#FBBF24" if ram < 80 else "#FB7185")
                self._ram_val_lbl.setText(f"{ram:.0f}%")
                self._ram_val_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
        except Exception:
            pass

    # Animated panel slide-in on startup
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Animate panels sliding in on first show
        if not getattr(self, "_panels_animated", False):
            self._panels_animated = True
            QTimer.singleShot(80, self._animate_panels_in)

    def _animate_panels_in(self) -> None:
        """Slide the left and right panels in from off-screen."""
        try:
            splitter = self.centralWidget().findChild(QSplitter)
            if splitter and splitter.count() >= 3:
                left_panel = splitter.widget(0)
                right_panel = splitter.widget(2)
                self._slide_panel_in(left_panel, from_left=True)
                self._slide_panel_in(right_panel, from_left=False)
        except Exception:
            pass  # non-critical animation

    def _slide_panel_in(self, widget: QWidget, from_left: bool) -> None:
        """Animate a panel widget sliding in from off-screen."""
        try:
            original_geo = widget.geometry()
            start_geo = QRect(original_geo)
            offset = -original_geo.width() if from_left else original_geo.width()
            start_geo.moveLeft(original_geo.left() + offset)
            # Use opacity fade-in instead of geometry (geometry animation
            # conflicts with the splitter layout manager)
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", widget)
            anim.setDuration(450)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: widget.setGraphicsEffect(None))
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        except Exception:
            pass

    def _clear_chat_and_memory(self) -> None:
        from PyQt6.QtWidgets import QMessageBox  # type: ignore
        reply = QMessageBox.question(
            self, "New Chat",
            "Clear the conversation display AND reset memory?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.chat_display.clear()
            self._last_jarvis_response = ""
            self._last_user_message = ""
            if self.runtime.memory:
                try:
                    self.runtime.memory.clear()
                except Exception:
                    pass
            self._add_activity("info", "Conversation and memory cleared — new session started")

    def _retry_last_message(self) -> None:
        if self._last_user_message:
            self.runtime.send_text(self._last_user_message)
            self._add_activity("info", f"Retrying: {self._last_user_message[:80]}")

    def _show_shortcuts_panel(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumWidth(440)
        dlg.setStyleSheet("""
            QDialog { background: rgba(10,14,39,0.97); border: 1px solid rgba(0,200,232,0.22); border-radius: 14px; }
            QLabel { color: #E2E8F0; font-size: 13px; background: transparent; }
            QLabel#key { color: #00C8E8; font-family: Consolas, monospace; font-size: 12px;
                         background: rgba(0,200,232,0.08); border: 1px solid rgba(0,200,232,0.20);
                         border-radius: 5px; padding: 2px 8px; }
        """)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(8)

        title = QLabel("KEYBOARD SHORTCUTS")
        title.setStyleSheet("font-size:11px; font-weight:700; color:rgba(0,200,232,0.85); letter-spacing:2.5px;")
        layout.addWidget(title)
        layout.addSpacing(6)

        shortcuts = [
            ("Enter",              "Send message"),
            ("↑ / ↓",              "Navigate command history"),
            ("Ctrl+F",             "Search conversation"),
            ("Ctrl+K",             "Command palette"),
            ("Ctrl+N",             "New chat session"),
            ("Ctrl+E",             "Export chat to Markdown"),
            ("Ctrl+L",             "Clear chat display"),
            ("Ctrl+,",             "Settings & shortcuts"),
            ("Alt+1-8",            "Switch engine (auto, ollama, groq, gemini, nexus, gpt, mistral, openrouter)"),
            ("Ctrl+Shift+J",       "Global hotkey — open JARVIS"),
            ("Esc",                "Close search / dialogs"),
            ("A+  /  A−",         "Increase / decrease font size"),
            ("Right-click chat",   "Copy, export, retry options"),
            ("/help",              "List all console commands"),
            ("/clear",             "Clear conversation display"),
            ("/note <text>",       "Save a quick note"),
            ("/notes",             "View saved notes"),
            ("/export",            "Export chat as Markdown"),
            ("/status",            "System status report"),
            ("/plugins list",      "List loaded plugins"),
        ]
        for key, desc in shortcuts:
            row = QHBoxLayout()
            row.setSpacing(12)
            key_lbl = QLabel(key)
            key_lbl.setObjectName("key")
            key_lbl.setFixedWidth(160)
            desc_lbl = QLabel(desc)
            row.addWidget(key_lbl)
            row.addWidget(desc_lbl, 1)
            w = QWidget()
            w.setLayout(row)
            layout.addWidget(w)

        layout.addSpacing(8)
        close_btn = AnimatedButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _show_command_palette(self) -> None:
        _PALETTE_COMMANDS = [
            ("/clear",   "Clear the conversation"),
            ("/status",  "Show system status report"),
            ("/export",  "Export chat to Downloads"),
            ("/notes",   "View saved notes"),
            ("/help",    "Show all console commands"),
            ("Time",     "What time is it?"),
            ("Weather",  "What's the weather?"),
            ("Screenshot", "Take a screenshot"),
            ("Sysinfo",  "Show system info"),
        ]
        dlg = QDialog(self)
        dlg.setWindowTitle("Command Palette")
        dlg.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dlg.setMinimumWidth(480)
        dlg.setStyleSheet("""
            QDialog { background: rgba(10,14,39,0.97); border: 1px solid rgba(0,229,255,0.25);
                      border-radius: 14px; }
            QLineEdit { background: rgba(15,23,42,0.80); border: 1px solid rgba(0,229,255,0.35);
                        border-radius: 8px; padding: 10px 14px; color: #E2E8F0; font-size: 14px; }
            QListWidget { background: transparent; border: none; color: #E2E8F0; font-size: 13px; }
            QListWidget::item { padding: 8px 12px; border-radius: 6px; }
            QListWidget::item:selected { background: rgba(0,229,255,0.14); color: #00E5FF; }
        """)
        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(14, 14, 14, 14)
        vbox.setSpacing(10)
        search = QLineEdit()
        search.setPlaceholderText("Type a command or action…")
        vbox.addWidget(search)
        lst = QListWidget()
        vbox.addWidget(lst)

        def _populate(query: str = "") -> None:
            lst.clear()
            q = query.lower()
            for cmd, desc in _PALETTE_COMMANDS:
                if not q or q in cmd.lower() or q in desc.lower():
                    item = QListWidgetItem(f"{cmd}  —  {desc}")
                    item.setData(Qt.ItemDataRole.UserRole, cmd)
                    lst.addItem(item)
            if lst.count():
                lst.setCurrentRow(0)

        _populate()
        search.textChanged.connect(_populate)

        def _run_selected() -> None:
            item = lst.currentItem()
            if item:
                cmd = item.data(Qt.ItemDataRole.UserRole)
                dlg.accept()
                if cmd.startswith("/"):
                    self._handle_console_command(cmd)
                else:
                    self._quick_action(cmd)

        lst.itemDoubleClicked.connect(lambda _: _run_selected())
        search.returnPressed.connect(_run_selected)
        dlg.exec()

    @staticmethod
    def _stylesheet() -> str:
        return """
        /* ══════════════════════════════════════════════════════════════
           JARVIS — Dark professional HUD
           Base: #04060e  Panels: rgba(7,11,20,0.92)
           Accent: #00C8E8  Secondary: #8B7CFF
           ══════════════════════════════════════════════════════════════ */

        QMainWindow, QWidget {
            color: #E2E8F0;
            font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
            font-size: 13px;
            background: transparent;
        }
        QSplitter, QSplitter::handle {
            background: transparent;
        }

        /* ── Scrollbars ─────────────────────────────────────────────── */
        QScrollBar:vertical {
            background: transparent;
            width: 5px;
            margin: 4px 0;
        }
        QScrollBar::handle:vertical {
            background: rgba(0, 200, 232, 0.18);
            border-radius: 3px;
            min-height: 24px;
        }
        QScrollBar::handle:vertical:hover { background: rgba(0, 200, 232, 0.35); }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal {
            background: transparent;
            height: 5px;
            margin: 0 4px;
        }
        QScrollBar::handle:horizontal {
            background: rgba(0, 200, 232, 0.18);
            border-radius: 3px;
            min-width: 24px;
        }
        QScrollBar::handle:horizontal:hover { background: rgba(0, 200, 232, 0.35); }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

        /* ── Panels ─────────────────────────────────────────────────── */
        QFrame#headerPanel {
            background: rgba(8, 14, 28, 0.35);
            border: 1px solid rgba(148, 163, 184, 0.06);
            border-radius: 14px;
        }
        QFrame#panel {
            background: rgba(10, 16, 30, 0.28);
            border: 1px solid rgba(148, 163, 184, 0.05);
            border-radius: 16px;
        }
        QWidget#heroPanel {
            background: transparent;
        }
        QFrame#providerCard {
            background: rgba(8, 14, 26, 0.25);
            border: none;
            border-radius: 12px;
        }

        /* ── Typography ─────────────────────────────────────────────── */
        QLabel#panelTitle {
            font-size: 9px;
            font-weight: 700;
            color: rgba(0, 200, 232, 0.55);
            letter-spacing: 2px;
            text-transform: uppercase;
        }
        QLabel#muted {
            color: rgba(148, 163, 184, 0.60);
            font-size: 12px;
        }
        QLabel#modeChip { background: transparent; border: none; }
        QLabel#statusChip { background: transparent; border: none; }
        QLabel#providerBadge {
            background: rgba(0, 200, 232, 0.08);
            border-radius: 8px;
            padding: 4px 12px;
            color: rgba(0, 200, 232, 0.90);
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.8px;
        }
        QLabel#clockLabel {
            color: #B0BFDA;
            font-size: 17px;
            line-height: 1.4;
            font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
            font-weight: 300;
        }

        /* ── Inputs ─────────────────────────────────────────────────── */
        QLineEdit {
            background: rgba(6, 10, 18, 0.35);
            border: none;
            border-radius: 8px;
            padding: 9px 13px;
            color: #E2E8F0;
            selection-background-color: rgba(0, 200, 232, 0.20);
            font-size: 13px;
        }
        QLineEdit:focus {
            background: rgba(6, 10, 18, 0.50);
            border-bottom: 1px solid rgba(0, 200, 232, 0.40);
        }
        QLineEdit::placeholder {
            color: rgba(100, 116, 139, 0.35);
        }
        QComboBox {
            background: rgba(6, 10, 18, 0.55);
            border: none;
            border-radius: 8px;
            padding: 7px 12px;
            color: #E2E8F0;
            font-size: 13px;
        }
        QComboBox:focus { background: rgba(6, 10, 18, 0.75); }
        QComboBox:hover { background: rgba(6, 10, 18, 0.70); }
        QComboBox::drop-down { border: none; width: 22px; }
        QComboBox::down-arrow { width: 9px; height: 9px; }
        QComboBox QAbstractItemView {
            background: #080d18;
            border: none;
            border-radius: 8px;
            color: #E2E8F0;
            padding: 4px;
            selection-background-color: rgba(0, 200, 232, 0.12);
        }
        QSpinBox, QDoubleSpinBox {
            background: rgba(6, 10, 18, 0.55);
            border: none;
            border-radius: 8px;
            padding: 6px 10px;
            color: #E2E8F0;
            font-size: 13px;
        }
        QSpinBox:focus, QDoubleSpinBox:focus {
            background: rgba(6, 10, 18, 0.75);
        }
        QSpinBox::up-button, QSpinBox::down-button,
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
            border: none;
            background: rgba(0, 200, 232, 0.08);
            width: 18px;
            border-radius: 4px;
        }
        QSpinBox::up-button:hover, QSpinBox::down-button:hover,
        QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
            background: rgba(0, 200, 232, 0.16);
        }

        /* ── Chat display ───────────────────────────────────────────── */
        QTextEdit#chatDisplay {
            background: rgba(6, 10, 22, 0.22);
            border: none;
            border-radius: 12px;
            padding: 14px;
            color: #E2E8F0;
            font-size: 14px;
            line-height: 1.65;
        }

        /* ── Checkboxes ─────────────────────────────────────────────── */
        QCheckBox {
            spacing: 10px;
            color: #CBD5E1;
            font-size: 13px;
        }
        QCheckBox::indicator {
            width: 17px;
            height: 17px;
            border-radius: 5px;
            border: none;
            background: rgba(10, 15, 28, 0.80);
        }
        QCheckBox::indicator:checked {
            background: rgba(0, 200, 232, 0.80);
        }
        QCheckBox::indicator:hover {
            background: rgba(10, 15, 28, 0.95);
        }

        /* ── Form labels ────────────────────────────────────────────── */
        QFormLayout QLabel {
            color: rgba(148, 163, 184, 0.75);
            font-size: 12px;
            font-weight: 500;
        }

        /* ── List widget ────────────────────────────────────────────── */
        QListWidget {
            background: rgba(3, 5, 12, 0.30);
            border: none;
            border-radius: 12px;
            padding: 5px;
        }
        QListWidget::item {
            padding: 7px 9px;
            border-radius: 6px;
            font-size: 12px;
            color: #94A3B8;
        }
        QListWidget::item:selected {
            background: rgba(0, 200, 232, 0.10);
            color: #F8FAFC;
        }
        QListWidget::item:hover {
            background: rgba(0, 200, 232, 0.05);
        }

        /* ── Scroll areas ───────────────────────────────────────────── */
        QScrollArea {
            border: none;
            background: transparent;
        }

        /* ── Splitter ───────────────────────────────────────────────── */
        QSplitter#splitter::handle {
            background: transparent;
            width: 2px;
            margin: 0;
        }

        /* ── Tooltips ───────────────────────────────────────────────── */
        QToolTip {
            background: #080d18;
            color: #E2E8F0;
            border: none;
            border-radius: 8px;
            padding: 7px 11px;
            font-size: 12px;
        }

        /* ── Context menus ──────────────────────────────────────────── */
        QMenu {
            background: rgba(8, 13, 24, 0.97);
            border: none;
            border-radius: 12px;
            padding: 6px;
            font-size: 13px;
        }
        QMenu::item {
            color: #E2E8F0;
            padding: 8px 20px 8px 12px;
            border-radius: 7px;
        }
        QMenu::item:selected {
            background: rgba(0, 200, 232, 0.10);
            color: #00C8E8;
        }
        QMenu::separator {
            height: 1px;
            background: rgba(0, 200, 232, 0.06);
            margin: 4px 8px;
        }

        /* ── Sliders ────────────────────────────────────────────────── */
        QSlider::groove:horizontal {
            background: rgba(0, 200, 232, 0.10);
            height: 5px;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: qradialgradient(cx:0.5,cy:0.5,radius:0.5,
                fx:0.5,fy:0.5,
                stop:0 #00C8E8,
                stop:0.6 rgba(0,200,232,0.60),
                stop:1 transparent);
            width: 17px;
            height: 17px;
            margin: -6px 0;
            border-radius: 9px;
            border: 1px solid rgba(0,200,232,0.50);
        }
        QSlider::handle:horizontal:hover {
            border: 1px solid rgba(0,200,232,0.80);
        }
        QSlider::sub-page:horizontal {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 rgba(0,180,216,0.60),
                stop:1 rgba(0,200,232,0.45));
            border-radius: 3px;
        }

        /* ── Message input (clean underline style) ──────────────────── */
        QLineEdit#msgInput {
            background: rgba(4, 7, 14, 0.50);
            border: none;
            border-bottom: 1px solid rgba(0, 200, 232, 0.18);
            border-radius: 4px;
            padding: 12px 18px;
            color: #E2E8F0;
            font-size: 14px;
            selection-background-color: rgba(0, 200, 232, 0.20);
        }
        QLineEdit#msgInput:focus {
            border-bottom: 1px solid rgba(0, 200, 232, 0.55);
            background: rgba(4, 7, 14, 0.70);
        }
        QLineEdit#msgInput::placeholder {
            color: rgba(100, 116, 139, 0.35);
        }

        /* ── Progress bars ──────────────────────────────────────────── */
        QProgressBar {
            background: rgba(0, 200, 232, 0.06);
            border: none;
            border-radius: 3px;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #00B4D8,
                stop:1 #00C8E8);
            border-radius: 3px;
        }

        /* ── Status bar / footer ────────────────────────────────────── */
        QLabel#statusBar {
            background: rgba(3, 5, 12, 0.40);
            border-top: none;
            color: rgba(148, 163, 184, 0.55);
            font-size: 10px;
            padding: 3px 8px;
        }
        """
