from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
)


class TranscriptSidebar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chunks = []
        self._session_start = None
        self._live = False
        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumSize(280, 420)
        self.setMaximumWidth(420)
        self.setWindowTitle("JARVIS Transcript")
        self.setStyleSheet("background: rgba(8, 12, 22, 0.98);")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(40)
        hdr.setStyleSheet(
            "background: rgba(59, 158, 255,0.06);"
            "border-bottom: 1px solid rgba(59, 158, 255,0.16);"
        )
        hrow = QHBoxLayout(hdr)
        hrow.setContentsMargins(12, 0, 8, 0)
        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #3d4355; font-size: 9px;")
        hrow.addWidget(self._dot)
        lbl = QLabel("LIVE TRANSCRIPT")
        lbl.setStyleSheet("color: rgba(59, 158, 255,0.75); font-size: 10px; font-weight: 700; letter-spacing: 1.5px;")
        hrow.addWidget(lbl)
        hrow.addStretch()
        for text, slot in (("Save", self._save), ("Clear", self._clear)):
            btn = QPushButton(text)
            btn.setFixedSize(50, 24)
            btn.setStyleSheet(
                "QPushButton{background:rgba(59, 158, 255,0.08);color:rgba(59, 158, 255,0.82);"
                "border:1px solid rgba(59, 158, 255,0.2);border-radius:5px;font-size:10px;}"
                "QPushButton:hover{background:rgba(59, 158, 255,0.18);}"
            )
            btn.clicked.connect(slot)
            hrow.addWidget(btn)
        root.addWidget(hdr)

        self._caption = QLabel("Waiting for speech...")
        self._caption.setWordWrap(True)
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption.setFixedHeight(72)
        self._caption.setFont(QFont("Segoe UI", 13))
        self._caption.setStyleSheet(
            "background: rgba(0,0,0,0.6); color: #eef2ff; padding: 10px 14px;"
            "border-bottom: 1px solid rgba(59, 158, 255,0.10);"
        )
        root.addWidget(self._caption)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Segoe UI", 11))
        self._log.setStyleSheet(
            "QTextEdit{background:transparent;color:rgba(176,196,216,0.9);border:none;padding:6px 10px;}"
            "QScrollBar:vertical{background:transparent;width:5px;}"
            "QScrollBar::handle:vertical{background:rgba(59, 158, 255,0.22);border-radius:2px;}"
        )
        root.addWidget(self._log, 1)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle)

    def set_live(self, live: bool) -> None:
        self._live = live
        if live:
            self._session_start = datetime.now()
            self._dot.setStyleSheet("color: #3B9EFF; font-size: 9px;")
            self._caption.setText("Listening...")
            self._meta("── Session started ──")
        else:
            self._dot.setStyleSheet("color: #3d4355; font-size: 9px;")
            self._caption.setText("")
            self._meta("── Session ended ──")

    def push_chunk(self, text: str) -> None:
        now = datetime.now()
        self._chunks.append({"ts": now, "text": text})
        self._caption.setText(text)
        self._idle_timer.stop()
        self._idle_timer.start(5500)
        ts = now.strftime("%H:%M:%S")
        self._log.append(
            f'<span style="color:rgba(59, 158, 255,0.45);font-size:10px;">[{ts}]</span> {text}'
        )
        c = self._log.textCursor()
        c.movePosition(QTextCursor.MoveOperation.End)
        self._log.setTextCursor(c)

    def _on_idle(self):
        self._caption.setText("Listening..." if self._live else "")

    def _meta(self, text: str) -> None:
        style = "color:rgba(59, 158, 255,0.38);font-size:10px;margin:2px 0;"
        self._log.append(f'<p style="{style}">{text}</p>')

    def _clear(self) -> None:
        self._chunks.clear()
        self._log.clear()
        self._caption.setText("Listening..." if self._live else "Waiting for speech...")

    def _save(self) -> None:
        if not self._chunks:
            return
        fmt = "%Y-%m-%d_%H-%M"
        default = f"transcript_{datetime.now().strftime(fmt)}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Transcript", str(Path.home() / default),
            "Text (*.txt);;Markdown (*.md);;All (*.*)",
        )
        if not path:
            return
        start_str = self._session_start.strftime("%Y-%m-%d %H:%M") if self._session_start else "unknown"
        lines = [f"# JARVIS Transcript -- {start_str}", ""]
        for c in self._chunks:
            lines.append(f"[{c['ts'].strftime('%H:%M:%S')}]  {c['text']}")
        Path(path).write_text("\n".join(lines), encoding="utf-8")


# ── Transparent bottom-of-screen overlay ──────────────────────────────────────

class TranscriptOverlay(QWidget):
    """Frameless translucent bar at the bottom of the JARVIS screen.

    Shows rolling live transcription + controls for Language / Model / Speed.
    Emits setting_changed(key, value) when the user picks a new option so
    AdvancedChatWindow can persist and apply changes.
    """

    setting_changed = pyqtSignal(str, object)   # (key, value)

    _LANGUAGES = [
        ("en", "English"), ("es", "Español"), ("fr", "Français"),
        ("de", "Deutsch"), ("pt", "Português"), ("ja", "Japanese"),
        ("zh", "中文"), ("ko", "Korean"), ("ru", "Russian"),
        ("ar", "Arabic"), ("hi", "Hindi"), ("it", "Italiano"),
    ]
    _MODELS  = ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]
    _SPEEDS  = ["0.5×", "0.75×", "1.0×", "1.25×", "1.5×", "2.0×"]

    def __init__(self):
        super().__init__(None)   # no parent — independent window
        self._chunks: list[str] = []
        self._ref_widget = None  # set to the JARVIS window for screen detection
        self._setup_window()
        self._setup_ui()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._container = QFrame()
        self._container.setObjectName("txOverlay")
        self._container.setStyleSheet("""
            QFrame#txOverlay {
                background: rgba(4, 10, 20, 0.86);
                border: 1px solid rgba(59, 158, 255,0.22);
                border-radius: 12px;
            }
        """)
        outer.addWidget(self._container)

        inner = QVBoxLayout(self._container)
        inner.setContentsMargins(20, 10, 20, 8)
        inner.setSpacing(6)

        # ── Live transcription text ───────────────────────────────────────────
        self._text = QLabel("Listening…")
        self._text.setWordWrap(True)
        self._text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text.setFont(QFont("Segoe UI", 14))
        self._text.setStyleSheet(
            "color: #E8F4FF; background: transparent; padding: 2px 0;"
        )
        inner.addWidget(self._text)

        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(12)

        # Language
        ctrl.addWidget(self._muted("Language"))
        self._lang_combo = self._combo(
            [lbl for _, lbl in self._LANGUAGES],
            [code for code, _ in self._LANGUAGES],
        )
        self._lang_combo.currentIndexChanged.connect(
            lambda: self.setting_changed.emit(
                "stt_language", self._lang_combo.currentData()
            )
        )
        ctrl.addWidget(self._lang_combo)

        ctrl.addWidget(self._sep())

        # Model
        ctrl.addWidget(self._muted("Model"))
        self._model_combo = self._combo(self._MODELS, self._MODELS)
        self._model_combo.setCurrentText("medium.en")
        self._model_combo.currentIndexChanged.connect(
            lambda: self.setting_changed.emit(
                "stt_model", self._model_combo.currentText()
            )
        )
        ctrl.addWidget(self._model_combo)

        ctrl.addWidget(self._sep())

        # Speed  (display only — JARVIS doesn't have a live speed setting yet)
        ctrl.addWidget(self._muted("Speed"))
        self._speed_combo = self._combo(self._SPEEDS, self._SPEEDS)
        self._speed_combo.setCurrentText("1.0×")
        ctrl.addWidget(self._speed_combo)

        ctrl.addStretch()

        # Clear button
        clr = QPushButton("Clear")
        clr.setFixedSize(52, 24)
        clr.setStyleSheet(self._btn_style())
        clr.clicked.connect(self._clear)
        ctrl.addWidget(clr)

        # Close button
        close = QPushButton("✕")
        close.setFixedSize(28, 24)
        close.setStyleSheet(self._btn_style())
        close.clicked.connect(self.hide)
        ctrl.addWidget(close)

        inner.addLayout(ctrl)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _muted(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(
            "color: rgba(59, 158, 255,0.55); font-size: 11px; background: transparent;"
        )
        return l

    @staticmethod
    def _sep() -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.VLine)
        s.setStyleSheet("color: rgba(59, 158, 255,0.12);")
        s.setFixedHeight(20)
        return s

    @staticmethod
    def _combo(labels: list[str], data: list) -> QComboBox:
        c = QComboBox()
        for lbl, d in zip(labels, data):
            c.addItem(lbl, d)
        c.setFixedHeight(26)
        c.setStyleSheet("""
            QComboBox {
                background: rgba(59, 158, 255,0.08);
                color: #C8E8F0;
                border: 1px solid rgba(59, 158, 255,0.22);
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: #0a1420;
                color: #C8E8F0;
                selection-background-color: rgba(59, 158, 255,0.15);
                border: 1px solid rgba(59, 158, 255,0.20);
            }
        """)
        return c

    @staticmethod
    def _btn_style() -> str:
        return (
            "QPushButton{"
            "  background: rgba(59, 158, 255,0.07);"
            "  color: rgba(59, 158, 255,0.7);"
            "  border: 1px solid rgba(59, 158, 255,0.18);"
            "  border-radius: 5px;"
            "  font-size: 11px;"
            "}"
            "QPushButton:hover{"
            "  background: rgba(59, 158, 255,0.18);"
            "  color: #3B9EFF;"
            "}"
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def set_ref_widget(self, widget: QWidget) -> None:
        """Call once with the JARVIS main window so we know which screen it's on."""
        self._ref_widget = widget

    def push_chunk(self, text: str) -> None:
        """Append a transcription chunk and update the display."""
        self._chunks.append(text)
        combined = " ".join(self._chunks)
        if len(combined) > 160:
            combined = "…" + combined[-160:]
        self._text.setText(combined)

    def set_language(self, code: str) -> None:
        """Sync language combo to current settings (called on startup)."""
        for i in range(self._lang_combo.count()):
            if self._lang_combo.itemData(i) == code:
                self._lang_combo.setCurrentIndex(i)
                break

    def set_model(self, model: str) -> None:
        """Sync model combo to current settings (called on startup)."""
        self._model_combo.setCurrentText(model)

    def _clear(self) -> None:
        self._chunks.clear()
        self._text.setText("Listening…")

    # ── Positioning ───────────────────────────────────────────────────────────

    def position_on_screen(self) -> None:
        """Move to the bottom-centre of whichever screen the JARVIS window is on."""
        if self._ref_widget and not self._ref_widget.isHidden():
            center = self._ref_widget.frameGeometry().center()
            screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        else:
            screen = QApplication.primaryScreen()
        sg = screen.availableGeometry()
        w  = min(int(sg.width() * 0.78), 1280)
        h  = 112
        x  = sg.x() + (sg.width()  - w) // 2
        y  = sg.y() +  sg.height() - h - 52
        self.setGeometry(x, y, w, h)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.position_on_screen()
