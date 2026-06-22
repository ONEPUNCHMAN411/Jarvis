
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QTextEdit,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import pyqtSignal


class TemplatesDialog(QDialog):
    """Browse, use, add, and remove saved prompt templates."""

    template_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt Templates")
        self.resize(620, 520)
        if parent:
            self.setStyleSheet(parent.styleSheet())

        from jarvis.brain.template_store import get_template_store
        self._store = get_template_store()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hdr = QLabel("PROMPT TEMPLATES")
        hdr.setStyleSheet(
            "color: #3B9EFF;"
            "font-family: Consolas;"
            "font-size: 10px;"
            "letter-spacing: 1px;"
            "font-weight: 700;"
        )
        layout.addWidget(hdr)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget {"
            "background: rgba(10,16,32,0.9);"
            "border: 1px solid rgba(59, 158, 255,0.15);"
            "border-radius: 10px; padding: 4px;"
            "}"
            "QListWidget::item {"
            "padding: 10px 14px; border-radius: 6px; color: #E7ECFB;"
            "}"
            "QListWidget::item:selected {"
            "background: rgba(59, 158, 255,0.18); color: #FFFFFF;"
            "}"
            "QListWidget::item:hover {"
            "background: rgba(59, 158, 255,0.08);"
            "}"
        )
        self._list.itemDoubleClicked.connect(self._use_selected)
        layout.addWidget(self._list, 1)

        add_frame = QFrame()
        add_frame.setStyleSheet(
            "QFrame {"
            "background: rgba(16, 22, 44,0.60);"
            "border: 1px solid rgba(59, 158, 255,0.12);"
            "border-radius: 8px;"
            "}"
        )
        add_layout = QVBoxLayout(add_frame)
        add_layout.setContentsMargins(10, 10, 10, 10)
        add_layout.setSpacing(6)

        name_row = QHBoxLayout()
        name_lbl = QLabel("Name:")
        name_lbl.setStyleSheet(
            "color: rgba(148,163,184,0.70); font-size: 12px;"
        )
        name_lbl.setFixedWidth(44)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Template name…")
        self._name_input.setStyleSheet(
            "background: rgba(6, 9, 20,0.80);"
            "border: 1px solid rgba(59, 158, 255,0.20);"
            "border-radius: 6px; padding: 4px 10px;"
            "color: #F8FAFC; font-size: 12px;"
        )
        name_row.addWidget(name_lbl)
        name_row.addWidget(self._name_input, 1)
        add_layout.addLayout(name_row)

        self._text_input = QTextEdit()
        self._text_input.setPlaceholderText(
            "Template text (use {variable} for fill-in placeholders)…"
        )
        self._text_input.setFixedHeight(72)
        self._text_input.setStyleSheet(
            "background: rgba(6, 9, 20,0.80);"
            "border: 1px solid rgba(59, 158, 255,0.20);"
            "border-radius: 6px; padding: 6px;"
            "color: #F8FAFC; font-size: 12px;"
        )
        add_layout.addWidget(self._text_input)
        layout.addWidget(add_frame)

        from jarvis.ui.animated_button import AnimatedButton
        btn_row = QHBoxLayout()

        use_btn = AnimatedButton("Use template")
        use_btn.clicked.connect(self._use_selected)
        btn_row.addWidget(use_btn)

        add_btn = AnimatedButton("Save new")
        add_btn.clicked.connect(self._add_template)
        btn_row.addWidget(add_btn)

        del_btn = AnimatedButton("Delete", accent="#FF2244")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(del_btn)

        btn_row.addStretch()
        close_btn = AnimatedButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._populate()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        if self._store.list_all():
            return
        defaults = [
            ("Explain this", "Explain the following in simple terms:\n\n"),
            ("Fix this code", "Find and fix any bugs in this code:\n\n"),
            ("Summarize", "Summarize the following text concisely:\n\n"),
            ("Write email", "Write a professional email about: "),
            ("Brainstorm ideas", "Give me 5 creative ideas for: "),
            ("Debug help", "I'm getting this error. What's wrong and how do I fix it?\n\nError:\n"),
            ("Code review", "Review this code for bugs, style issues, and improvements:\n\n"),
        ]
        for name, text in defaults:
            self._store.add(name, text, category="general")
        self._populate()

    def _populate(self) -> None:
        self._list.clear()
        for t in self._store.list_all():
            item = QListWidgetItem(f"[{t.category}]  {t.name}")
            item.setData(256, t.id)
            item.setToolTip(t.text[:200])
            self._list.addItem(item)

    def _use_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        template = self._store.get(item.data(256))
        if template:
            self.template_selected.emit(template.text)
            self.close()

    def _add_template(self) -> None:
        name = self._name_input.text().strip()
        text = self._text_input.toPlainText().strip()
        if not name or not text:
            return
        self._store.add(name, text)
        self._name_input.clear()
        self._text_input.clear()
        self._populate()

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        self._store.remove(item.data(256))
        self._populate()
