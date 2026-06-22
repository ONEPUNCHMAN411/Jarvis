import threading

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QTextEdit, QSplitter, QWidget, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from jarvis.brain.macro_store import get_macro_store
from jarvis.brain.macro_executor import run_macro


class MacrosDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS — Automation Macros")
        self.setMinimumSize(780, 520)
        self._store = get_macro_store()
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        self.setStyleSheet("QDialog { background: #0A0F22; } QLabel { color: #E7ECFB; }")

        hdr = QHBoxLayout()
        title = QLabel("Automation Macros")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #5BC8FF;")
        hdr.addWidget(title)
        hdr.addStretch()
        hint = QLabel('Ask JARVIS in chat: "create a macro that opens Chrome and goes to GitHub"')
        hint.setStyleSheet("color:#475569;font-size:11px;font-style:italic;")
        hdr.addWidget(hint)
        root.addLayout(hdr)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(6)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background:#141A33; border:1px solid #334155; border-radius:8px; color:#E7ECFB; font-size:13px; }
            QListWidget::item { padding:10px 14px; border-bottom:1px solid #0A0F22; }
            QListWidget::item:selected { background:#082f49; color:#5BC8FF; border-left:3px solid #5BC8FF; }
            QListWidget::item:hover { background:#1e3a5f; }
        """)
        self._list.currentRowChanged.connect(self._on_select)
        lv.addWidget(self._list)

        btns = QHBoxLayout()
        self._run_btn = QPushButton("▶  Run")
        self._del_btn = QPushButton("Delete")
        self._run_btn.setFixedHeight(36)
        self._del_btn.setFixedHeight(36)
        self._run_btn.setStyleSheet("background:#0ea5e9;color:#fff;border-radius:7px;font-weight:bold;font-size:13px;")
        self._del_btn.setStyleSheet("background:#dc2626;color:#fff;border-radius:7px;font-size:13px;")
        self._run_btn.setEnabled(False)
        self._del_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_selected)
        self._del_btn.clicked.connect(self._delete_selected)
        btns.addWidget(self._run_btn)
        btns.addWidget(self._del_btn)
        lv.addLayout(btns)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 4, 0)
        rv.setSpacing(6)

        self._name_lbl = QLabel("Select a macro to inspect")
        self._name_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        rv.addWidget(self._name_lbl)

        self._desc_lbl = QLabel("")
        self._desc_lbl.setStyleSheet("color:#8A94B8;font-size:12px;")
        self._desc_lbl.setWordWrap(True)
        rv.addWidget(self._desc_lbl)

        self._steps_view = QTextEdit()
        self._steps_view.setReadOnly(True)
        self._steps_view.setFont(QFont("Consolas", 10))
        self._steps_view.setStyleSheet(
            "background:#060914;color:#a5f3fc;border:1px solid #164e63;border-radius:6px;padding:6px;"
        )
        rv.addWidget(self._steps_view)

        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet("color:#475569;font-size:11px;")
        rv.addWidget(self._stats_lbl)
        rv.addStretch()
        splitter.addWidget(right)

        splitter.setSizes([270, 490])
        root.addWidget(splitter)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet("background:#141A33;color:#8A94B8;border:1px solid #334155;border-radius:6px;")
        close_btn.clicked.connect(self.close)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _refresh(self):
        self._list.clear()
        for m in self._store.list_all():
            item = QListWidgetItem(f"⚡  {m.name}")
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            item.setToolTip(m.description)
            self._list.addItem(item)
        self._run_btn.setEnabled(False)
        self._del_btn.setEnabled(False)

    def _on_select(self, row: int):
        if row < 0:
            return
        macro_id = self._list.item(row).data(Qt.ItemDataRole.UserRole)
        m = self._store.get(macro_id)
        if not m:
            return
        self._name_lbl.setText(m.name)
        self._desc_lbl.setText(m.description)
        lines = []
        for i, step in enumerate(m.steps, 1):
            lines.append(f"Step {i:02d}  [{step.action}]")
            for k, v in step.params.items():
                lines.append(f"          {k}: {v}")
        self._steps_view.setPlainText("\n".join(lines))
        last = m.last_run[:19].replace("T", " ") if m.last_run else "never"
        self._stats_lbl.setText(
            f"ID: {m.id}    Created: {m.created_at[:10]}    Last run: {last}    Runs: {m.run_count}"
        )
        self._run_btn.setEnabled(True)
        self._del_btn.setEnabled(True)

    def _run_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        macro_id = item.data(Qt.ItemDataRole.UserRole)
        m = self._store.get(macro_id)
        QMessageBox.information(
            self,
            "Running Macro",
            f"Switch to your target window now.\n'{m.name}' starts in 2 seconds.\n\nMove mouse to a screen corner to abort.",
        )
        self.close()
        threading.Thread(target=lambda: run_macro(macro_id, delay_before=2.0), daemon=True).start()

    def _delete_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        macro_id = item.data(Qt.ItemDataRole.UserRole)
        m = self._store.get(macro_id)
        reply = QMessageBox.question(
            self,
            "Delete Macro",
            f"Delete '{m.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._store.delete(macro_id)
            self._refresh()
            self._steps_view.clear()
            self._name_lbl.setText("Select a macro to inspect")
            self._desc_lbl.setText("")
            self._stats_lbl.setText("")
