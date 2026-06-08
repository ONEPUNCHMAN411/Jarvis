"""
Ollama Model Manager Dialog
Lets users list installed models, pull popular ones, and delete models.
"""

import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from jarvis.ui.orb_widgets import AnimatedButton

_BG      = "rgba(10,14,39,0.97)"
_SURFACE = "rgba(17,24,39,1)"
_ACCENT  = "#00E5FF"
_MUTED   = "rgba(148,163,184,0.65)"
_BORDER  = "rgba(0,229,255,0.14)"

_POPULAR_MODELS = [
    ("llama3.2",          "3B",  "Meta — fast, great for chat"),
    ("llama3.2:1b",       "1B",  "Meta — ultra-fast, minimal RAM"),
    ("llama3.1",          "8B",  "Meta — strong reasoning"),
    ("qwen2.5",           "7B",  "Alibaba — excellent coding"),
    ("qwen2.5-coder",     "7B",  "Alibaba — code-specialised"),
    ("mistral",           "7B",  "Mistral — balanced, fast"),
    ("phi4",              "14B", "Microsoft — compact powerhouse"),
    ("phi3.5",            "4B",  "Microsoft — lightweight"),
    ("gemma2",            "9B",  "Google — instruction-tuned"),
    ("deepseek-r1",       "7B",  "DeepSeek — strong reasoning"),
    ("llava",             "7B",  "LLaVA — multimodal, vision"),
    ("moondream",         "2B",  "Moondream — tiny vision model"),
]

_SHEET = f"""
QDialog {{
    background: {_BG};
    border: 1px solid {_BORDER};
    border-radius: 16px;
}}
QWidget {{ background: transparent; color: #E2E8F0; font-size: 13px; font-family: 'Segoe UI', Arial; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: rgba(15,23,42,0.40); width: 6px; border-radius: 3px; }}
QScrollBar::handle:vertical {{ background: rgba(0,229,255,0.28); border-radius: 3px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLineEdit {{
    background: rgba(15,23,42,0.60);
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    color: #E2E8F0;
}}
QLineEdit:focus {{ border-color: {_ACCENT}; }}
QProgressBar {{
    background: rgba(0,229,255,0.07);
    border: none;
    border-radius: 3px;
    height: 5px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00B4D8,stop:1 {_ACCENT});
    border-radius: 3px;
}}
"""

class OllamaManagerDialog(QDialog):
    """Non-modal dialog for managing Ollama models."""

    model_pulled = pyqtSignal(str)  # emits model name when pull succeeds

    def __init__(self, base_url: str = "http://localhost:11434", parent=None):
        super().__init__(parent)
        self._base_url = base_url.rstrip("/")
        self._pull_threads: dict[str, threading.Thread] = {}
        self._pull_bars: dict[str, QProgressBar] = {}
        self._pull_labels: dict[str, QLabel] = {}
        self._pull_btns: dict[str, QPushButton] = {}
        self._installed: list[str] = []
        self.setWindowTitle("Ollama Model Manager")
        self.setMinimumSize(640, 720)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(_SHEET)
        self._build()
        QTimer.singleShot(200, self._refresh_installed)

    # UI

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(16)

        # Header
        title = QLabel("OLLAMA MODEL MANAGER")
        title.setStyleSheet(f"font-size:12px;font-weight:700;color:{_ACCENT};letter-spacing:2.5px;")
        root.addWidget(title)

        desc = QLabel(
            "Pull free open-source models to run locally with Ollama. "
            "Models are downloaded once and cached on disk."
        )
        desc.setStyleSheet(f"color:{_MUTED};font-size:12px;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        # Custom pull row
        custom_frame = QFrame()
        custom_frame.setStyleSheet(f"QFrame{{background:rgba(0,229,255,0.04);border:1px solid {_BORDER};border-radius:8px;}}")
        custom_layout = QVBoxLayout(custom_frame)
        custom_layout.setContentsMargins(14, 10, 14, 10)
        custom_layout.setSpacing(6)
        custom_lbl = QLabel("Pull any model by name:")
        custom_lbl.setStyleSheet(f"font-size:11px;font-weight:600;color:{_ACCENT};letter-spacing:1px;")
        custom_layout.addWidget(custom_lbl)
        custom_row = QHBoxLayout()
        self._custom_input = QLineEdit()
        self._custom_input.setPlaceholderText("e.g.  llama3.2:latest   or   qwen2.5:7b")
        self._custom_input.returnPressed.connect(self._pull_custom)
        custom_row.addWidget(self._custom_input, 1)
        pull_custom_btn = AnimatedButton("Pull")
        pull_custom_btn.setFixedWidth(68)
        pull_custom_btn.clicked.connect(self._pull_custom)
        custom_row.addWidget(pull_custom_btn)
        custom_layout.addLayout(custom_row)
        self._custom_bar = QProgressBar()
        self._custom_bar.setRange(0, 0)
        self._custom_bar.setVisible(False)
        self._custom_bar.setFixedHeight(4)
        custom_layout.addWidget(self._custom_bar)
        self._custom_status = QLabel("")
        self._custom_status.setStyleSheet(f"font-size:11px;color:{_MUTED};")
        self._custom_status.setVisible(False)
        custom_layout.addWidget(self._custom_status)
        root.addWidget(custom_frame)

        # Installed models section
        installed_header = QHBoxLayout()
        installed_title = QLabel("INSTALLED MODELS")
        installed_title.setStyleSheet(f"font-size:11px;font-weight:600;color:{_ACCENT};letter-spacing:1.5px;")
        installed_header.addWidget(installed_title)
        installed_header.addStretch()
        refresh_btn = AnimatedButton("Refresh")
        refresh_btn.setFixedWidth(70)
        refresh_btn.clicked.connect(self._refresh_installed)
        installed_header.addWidget(refresh_btn)
        root.addLayout(installed_header)

        self._installed_label = QLabel("Checking Ollama…")
        self._installed_label.setStyleSheet(f"color:{_MUTED};font-size:12px;padding:4px 0;")
        self._installed_label.setWordWrap(True)
        root.addWidget(self._installed_label)

        # Popular models
        popular_title = QLabel("POPULAR MODELS")
        popular_title.setStyleSheet(f"font-size:11px;font-weight:600;color:{_ACCENT};letter-spacing:1.5px;")
        root.addWidget(popular_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._popular_layout = QVBoxLayout(content)
        self._popular_layout.setContentsMargins(0, 0, 4, 0)
        self._popular_layout.setSpacing(6)

        for model_name, size, description in _POPULAR_MODELS:
            card = self._build_model_card(model_name, size, description)
            self._popular_layout.addWidget(card)
        self._popular_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # Bottom close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = AnimatedButton("Close")
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _build_model_card(self, model_name: str, size: str, description: str) -> QWidget:
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:rgba(15,23,42,0.50);border:1px solid rgba(0,229,255,0.09);border-radius:8px;}"
        )
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self._pull_labels[model_name] = QLabel("●")
        self._pull_labels[model_name].setStyleSheet("color:rgba(100,116,139,0.40);font-size:10px;")
        self._pull_labels[model_name].setFixedWidth(14)
        layout.addWidget(self._pull_labels[model_name])

        info = QVBoxLayout()
        info.setSpacing(1)
        name_lbl = QLabel(f"{model_name}  <span style='color:{_MUTED};font-size:11px;'>{size}</span>")
        name_lbl.setStyleSheet("font-weight:600;color:#E2E8F0;font-size:13px;")
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        info.addWidget(name_lbl)
        info.addWidget(desc_lbl)
        layout.addLayout(info, 1)

        bar_wrap = QVBoxLayout()
        bar_wrap.setSpacing(0)
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setFixedHeight(3)
        bar.setVisible(False)
        self._pull_bars[model_name] = bar
        bar_wrap.addWidget(bar)
        layout.addLayout(bar_wrap)

        btn = AnimatedButton("Pull")
        btn.setFixedWidth(60)
        btn.setFixedHeight(28)
        btn.setStyleSheet("font-size:12px;padding:2px 8px;")
        btn.clicked.connect(lambda _, m=model_name: self._pull_model(m, btn))
        self._pull_btns[model_name] = btn
        layout.addWidget(btn)

        return card

    # Logic

    def _refresh_installed(self) -> None:
        def _fetch():
            try:
                import httpx
                resp = httpx.get(f"{self._base_url}/api/tags", timeout=5)
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                QTimer.singleShot(0, lambda: self._update_installed(models))
            except Exception as exc:
                QTimer.singleShot(0, lambda: self._installed_label.setText(
                    f"Ollama not running — start it first.  ({exc})"
                ))
        threading.Thread(target=_fetch, daemon=True).start()

    def _update_installed(self, models: list[str]) -> None:
        self._installed = models
        if not models:
            self._installed_label.setText("No models installed yet — pull one below.")
        else:
            self._installed_label.setText("Installed: " + "   •   ".join(models))

        # Update status dots on popular cards
        for model_name, lbl in self._pull_labels.items():
            base = model_name.split(":")[0]
            installed = any(m.startswith(base) for m in models)
            lbl.setStyleSheet(
                f"color:{'#34D399' if installed else 'rgba(100,116,139,0.40)'};font-size:10px;"
            )
            if model_name in self._pull_btns:
                self._pull_btns[model_name].setText("Installed" if installed else "Pull")
                self._pull_btns[model_name].setEnabled(not installed)

    def _pull_custom(self) -> None:
        name = self._custom_input.text().strip()
        if not name:
            return
        self._custom_bar.setVisible(True)
        self._custom_status.setText(f"Pulling {name}…")
        self._custom_status.setVisible(True)

        def _do():
            ok, msg = _pull_model_blocking(self._base_url, name)
            def _done():
                self._custom_bar.setVisible(False)
                self._custom_status.setText(msg)
                self._custom_status.setStyleSheet(
                    f"font-size:11px;color:{'#34D399' if ok else '#FB7185'};"
                )
                if ok:
                    self.model_pulled.emit(name)
                    self._refresh_installed()
            QTimer.singleShot(0, _done)

        threading.Thread(target=_do, daemon=True).start()

    def _pull_model(self, model_name: str, btn: QPushButton) -> None:
        if model_name in self._pull_threads and self._pull_threads[model_name].is_alive():
            return
        btn.setEnabled(False)
        btn.setText("Pulling…")
        bar = self._pull_bars.get(model_name)
        if bar:
            bar.setVisible(True)

        def _do():
            ok, msg = _pull_model_blocking(self._base_url, model_name)
            def _done():
                if bar:
                    bar.setVisible(False)
                if ok:
                    btn.setText("Installed")
                    self.model_pulled.emit(model_name)
                    if model_name in self._pull_labels:
                        self._pull_labels[model_name].setStyleSheet(
                            "color:#34D399;font-size:10px;"
                        )
                    self._refresh_installed()
                else:
                    btn.setText("Retry")
                    btn.setEnabled(True)
            QTimer.singleShot(0, _done)

        t = threading.Thread(target=_do, daemon=True)
        self._pull_threads[model_name] = t
        t.start()

def _pull_model_blocking(base_url: str, model_name: str) -> tuple[bool, str]:
    """Stream a POST to /api/pull and wait for completion. Returns (success, message)."""
    try:
        import httpx
        with httpx.Client(timeout=httpx.Timeout(connect=10, read=1800, write=30, pool=10)) as client:
            with client.stream("POST", f"{base_url}/api/pull", json={"name": model_name}) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    import json
                    try:
                        data = json.loads(line)
                        if data.get("status") == "success":
                            return True, f"✓ {model_name} ready"
                        if "error" in data:
                            return False, f"✗ {data['error']}"
                    except json.JSONDecodeError:
                        pass
        return True, f"✓ {model_name} ready"
    except Exception as exc:
        return False, f"✗ Pull failed: {exc}"
