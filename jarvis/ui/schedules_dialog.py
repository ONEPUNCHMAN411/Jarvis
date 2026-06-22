from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QTextEdit, QSplitter, QWidget, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from jarvis.brain.schedule_store import get_schedule_store


class SchedulesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS — Scheduled Prompts")
        self.setMinimumSize(840, 540)
        self._store = get_schedule_store()
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        self.setStyleSheet("QDialog { background: #0A0F22; } QLabel { color: #E7ECFB; }")

        hdr = QHBoxLayout()
        title = QLabel("Scheduled Prompts")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #5EA8FF;")
        hdr.addWidget(title)
        hdr.addStretch()
        hint = QLabel('Ask JARVIS: "every weekday at 9am give me a morning briefing"')
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
            QListWidget::item:selected { background:#0A1A3A; color:#5EA8FF; border-left:3px solid #3B82F6; }
            QListWidget::item:hover { background:#14274F; }
        """)
        self._list.currentRowChanged.connect(self._on_select)
        lv.addWidget(self._list)

        btns = QHBoxLayout()
        self._run_btn = QPushButton("▶  Run Now")
        self._toggle_btn = QPushButton("⏸  Toggle")
        self._del_btn = QPushButton("Delete")
        for b in (self._run_btn, self._toggle_btn, self._del_btn):
            b.setFixedHeight(34)
            b.setEnabled(False)
        self._run_btn.setStyleSheet("background:#1E6FE0;color:#fff;border-radius:7px;font-weight:bold;")
        self._toggle_btn.setStyleSheet("background:#334155;color:#E7ECFB;border-radius:7px;")
        self._del_btn.setStyleSheet("background:#dc2626;color:#fff;border-radius:7px;")
        self._run_btn.clicked.connect(self._run_now)
        self._toggle_btn.clicked.connect(self._toggle)
        self._del_btn.clicked.connect(self._delete)
        btns.addWidget(self._run_btn)
        btns.addWidget(self._toggle_btn)
        btns.addWidget(self._del_btn)
        lv.addLayout(btns)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 4, 0)
        rv.setSpacing(6)

        self._name_lbl = QLabel("Select a schedule")
        self._name_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        rv.addWidget(self._name_lbl)

        self._time_lbl = QLabel("")
        self._time_lbl.setStyleSheet("color:#8A94B8;font-size:12px;")
        rv.addWidget(self._time_lbl)

        plbl = QLabel("Prompt sent at fire time:")
        plbl.setStyleSheet("color:#64748b;font-size:11px;margin-top:8px;")
        rv.addWidget(plbl)

        self._prompt_view = QTextEdit()
        self._prompt_view.setReadOnly(True)
        self._prompt_view.setFont(QFont("Segoe UI", 11))
        self._prompt_view.setMaximumHeight(130)
        self._prompt_view.setStyleSheet(
            "background:#141A33;color:#E7ECFB;border:1px solid #334155;border-radius:6px;padding:6px;"
        )
        rv.addWidget(self._prompt_view)

        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet("color:#475569;font-size:11px;margin-top:4px;")
        rv.addWidget(self._stats_lbl)
        rv.addStretch()
        splitter.addWidget(right)

        splitter.setSizes([300, 520])
        root.addWidget(splitter)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet("background:#141A33;color:#8A94B8;border:1px solid #334155;border-radius:6px;")
        close_btn.clicked.connect(self.close)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _refresh(self):
        self._list.clear()
        for s in self._store.list_all():
            icon = "✅" if s.enabled else "⏸"
            item = QListWidgetItem(f"{icon}  {s.name}")
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            item.setToolTip(f"{s.time_str}  {', '.join(s.days)}")
            self._list.addItem(item)
        for b in (self._run_btn, self._toggle_btn, self._del_btn):
            b.setEnabled(False)

    def _on_select(self, row: int):
        if row < 0:
            return
        item = self._list.item(row)
        s = self._store.get(item.data(Qt.ItemDataRole.UserRole))
        if not s:
            return
        self._name_lbl.setText(s.name)
        status = "✅ Enabled" if s.enabled else "⏸ Paused"
        self._time_lbl.setText(f"Fires at  {s.time_str}  on  {', '.join(s.days)}    {status}")
        self._prompt_view.setPlainText(s.prompt)
        last = s.last_run[:19].replace("T", " ") if s.last_run else "never"
        self._stats_lbl.setText(f"ID: {s.id}    Last run: {last}    Run count: {s.run_count}")
        for b in (self._run_btn, self._toggle_btn, self._del_btn):
            b.setEnabled(True)

    def _run_now(self):
        item = self._list.currentItem()
        if item:
            self._store.fire_now(item.data(Qt.ItemDataRole.UserRole))
            QMessageBox.information(self, "Fired", "Prompt sent to JARVIS. Check for a desktop notification.")

    def _toggle(self):
        item = self._list.currentItem()
        if item:
            self._store.toggle(item.data(Qt.ItemDataRole.UserRole))
            self._refresh()

    def _delete(self):
        item = self._list.currentItem()
        if not item:
            return
        s = self._store.get(item.data(Qt.ItemDataRole.UserRole))
        reply = QMessageBox.question(
            self,
            "Delete",
            f"Delete schedule '{s.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._store.delete(s.id)
            self._refresh()
            self._name_lbl.setText("Select a schedule")
            self._prompt_view.clear()
            self._time_lbl.setText("")
            self._stats_lbl.setText("")
