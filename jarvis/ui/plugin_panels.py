"""Floating panel dialogs for JARVIS plugins."""

import json
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QTextEdit,
    QComboBox, QCheckBox, QWidget, QScrollArea, QFrame,
    QSizePolicy, QSplitter,
)
from loguru import logger

_DARK = "#1a1a2e"
_PANEL = "#16213e"
_ACCENT = "#8B7CFF"
_TEXT = "#e0e0e0"
_MUTED = "#888"
_BASE_STYLE = f"""
    QDialog {{ background: {_DARK}; color: {_TEXT}; font-family: 'Segoe UI'; }}
    QLabel {{ color: {_TEXT}; }}
    QLineEdit, QTextEdit, QListWidget, QComboBox {{
        background: {_PANEL}; color: {_TEXT}; border: 1px solid #333;
        border-radius: 4px; padding: 4px;
    }}
    QPushButton {{
        background: {_ACCENT}; color: white; border: none;
        border-radius: 4px; padding: 6px 14px;
    }}
    QPushButton:hover {{ background: #7b6ee8; }}
    QPushButton[flat="true"] {{
        background: transparent; color: {_MUTED}; padding: 4px 8px;
    }}
    QPushButton[flat="true"]:hover {{ color: {_TEXT}; }}
    QScrollBar:vertical {{ background: {_PANEL}; width: 6px; }}
    QScrollBar::handle:vertical {{ background: #444; border-radius: 3px; }}
"""


def _title_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
    lbl.setStyleSheet(f"color: {_ACCENT};")
    return lbl


# ---------------------------------------------------------------------------
# UIBridge — lets async tool calls open panels on the Qt main thread
# ---------------------------------------------------------------------------

class UIBridge:
    _instance: "UIBridge | None" = None
    _parent: QWidget | None = None

    @classmethod
    def init(cls) -> None:
        cls._instance = cls()

    @classmethod
    def set_parent_window(cls, window: QWidget) -> None:
        cls._parent = window

    @classmethod
    def open_panel(cls, name: str) -> None:
        if cls._parent is None:
            return
        opener = getattr(cls._parent, "_open_panel_by_name", None)
        if opener:
            QTimer.singleShot(0, lambda: opener(name))


# ---------------------------------------------------------------------------
# TodoDialog
# ---------------------------------------------------------------------------

_TODO_FILE = Path.home() / ".jarvis" / "todos.json"


def _load_todos() -> list[dict]:
    try:
        return json.loads(_TODO_FILE.read_text(encoding="utf-8")) if _TODO_FILE.exists() else []
    except Exception:
        return []


def _save_todos(todos: list[dict]) -> None:
    _TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TODO_FILE.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")


class TodoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Todo")
        self.setMinimumSize(420, 500)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("Todo List"))

        self._list = QListWidget()
        layout.addWidget(self._list)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("New task…")
        self._input.returnPressed.connect(self._add)
        row.addWidget(self._input)
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._add)
        row.addWidget(btn_add)
        layout.addLayout(row)

        btn_done = QPushButton("Mark done")
        btn_done.clicked.connect(self._mark_done)
        layout.addWidget(btn_done)

        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for t in _load_todos():
            text = ("✓ " if t.get("done") else "○ ") + t.get("text", "")
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, t["id"])
            if t.get("done"):
                item.setForeground(QColor(_MUTED))
            self._list.addItem(item)

    def _add(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        todos = _load_todos()
        todos.append({"id": str(uuid.uuid4()), "text": text, "done": False,
                      "created": datetime.now().isoformat()})
        _save_todos(todos)
        self._input.clear()
        self._refresh()

    def _mark_done(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        tid = item.data(Qt.ItemDataRole.UserRole)
        todos = _load_todos()
        for t in todos:
            if t["id"] == tid:
                t["done"] = not t.get("done", False)
        _save_todos(todos)
        self._refresh()


# ---------------------------------------------------------------------------
# NotesDialog
# ---------------------------------------------------------------------------

_NOTES_FILE = Path.home() / ".jarvis" / "notes.json"


def _load_notes() -> list[dict]:
    try:
        return json.loads(_NOTES_FILE.read_text(encoding="utf-8")) if _NOTES_FILE.exists() else []
    except Exception:
        return []


def _save_notes(notes: list[dict]) -> None:
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _NOTES_FILE.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")


class NotesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notes")
        self.setMinimumSize(500, 520)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QHBoxLayout(self)
        self._list = QListWidget()
        self._list.setMaximumWidth(160)
        self._list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self._list)

        right = QVBoxLayout()
        layout.addLayout(right)

        right.addWidget(_title_label("Notes"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Title")
        right.addWidget(self._title_edit)
        self._body_edit = QTextEdit()
        self._body_edit.setPlaceholderText("Write a note…")
        right.addWidget(self._body_edit)

        btns = QHBoxLayout()
        btn_new = QPushButton("New")
        btn_new.clicked.connect(self._new_note)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._save_note)
        btn_del = QPushButton("Delete")
        btn_del.setProperty("flat", True)
        btn_del.clicked.connect(self._delete_note)
        btns.addWidget(btn_new)
        btns.addWidget(btn_save)
        btns.addWidget(btn_del)
        right.addLayout(btns)

        self._current_id: str | None = None
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for n in _load_notes():
            self._list.addItem(QListWidgetItem(n.get("title", "Untitled")))

    def _on_select(self, row: int) -> None:
        notes = _load_notes()
        if 0 <= row < len(notes):
            n = notes[row]
            self._current_id = n["id"]
            self._title_edit.setText(n.get("title", ""))
            self._body_edit.setPlainText(n.get("body", ""))

    def _new_note(self) -> None:
        self._current_id = None
        self._title_edit.clear()
        self._body_edit.clear()

    def _save_note(self) -> None:
        title = self._title_edit.text().strip() or "Untitled"
        body = self._body_edit.toPlainText()
        notes = _load_notes()
        now = datetime.now().isoformat(timespec="seconds")
        if self._current_id:
            for n in notes:
                if n["id"] == self._current_id:
                    n["title"] = title
                    n["body"] = body
                    n["updated"] = now
        else:
            self._current_id = str(uuid.uuid4())
            notes.append({"id": self._current_id, "title": title, "body": body,
                          "tags": [], "created": now, "updated": now})
        _save_notes(notes)
        self._refresh()

    def _delete_note(self) -> None:
        if not self._current_id:
            return
        notes = [n for n in _load_notes() if n["id"] != self._current_id]
        _save_notes(notes)
        self._current_id = None
        self._title_edit.clear()
        self._body_edit.clear()
        self._refresh()


# ---------------------------------------------------------------------------
# ClipboardDialog
# ---------------------------------------------------------------------------

class ClipboardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clipboard History")
        self.setMinimumSize(420, 480)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("Clipboard History"))

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._copy_item)
        layout.addWidget(self._list)

        lbl = QLabel("Double-click an entry to copy it again")
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        layout.addWidget(lbl)

        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        try:
            from jarvis.control.clipboard_history import get_history
            entries = get_history().get_entries(limit=50)
            for e in entries:
                text = e.get("text", "")[:120].replace("\n", " ")
                self._list.addItem(QListWidgetItem(text))
                self._list.item(self._list.count() - 1).setData(
                    Qt.ItemDataRole.UserRole, e.get("text", ""))
        except Exception as exc:
            logger.debug(f"ClipboardDialog: {exc}")

    def _copy_item(self, item: QListWidgetItem) -> None:
        import pyperclip
        text = item.data(Qt.ItemDataRole.UserRole) or item.text()
        try:
            pyperclip.copy(text)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# SpotifyDialog
# ---------------------------------------------------------------------------

class SpotifyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spotify")
        self.setMinimumSize(380, 300)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("Spotify"))

        self._status = QLabel("Loading…")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        btns = QHBoxLayout()
        for label, cmd in [("⏮", "previous"), ("⏸ / ▶", "toggle"), ("⏭", "next")]:
            b = QPushButton(label)
            b.clicked.connect(lambda _, c=cmd: self._cmd(c))
            btns.addWidget(b)
        layout.addLayout(btns)

        self._vol = QLineEdit()
        self._vol.setPlaceholderText("Volume 0-100")
        vol_btn = QPushButton("Set volume")
        vol_btn.clicked.connect(self._set_vol)
        vrow = QHBoxLayout()
        vrow.addWidget(self._vol)
        vrow.addWidget(vol_btn)
        layout.addLayout(vrow)

        layout.addStretch()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)
        self._refresh()

    def _get_ctrl(self):
        from jarvis.brain.spotify_controller import SpotifyController
        if not hasattr(self, "_ctrl"):
            self._ctrl = SpotifyController()
        return self._ctrl

    def _refresh(self) -> None:
        try:
            info = self._get_ctrl().now_playing()
            if info:
                self._status.setText(f"▶ {info.get('title', '?')} — {info.get('artist', '?')}")
            else:
                self._status.setText("Nothing playing")
        except Exception as e:
            self._status.setText(f"Spotify unavailable: {e}")

    def _cmd(self, cmd: str) -> None:
        try:
            ctrl = self._get_ctrl()
            if cmd == "toggle":
                ctrl.pause() if ctrl.is_playing() else ctrl.resume()
            elif cmd == "next":
                ctrl.next_track()
            elif cmd == "previous":
                ctrl.previous_track()
            QTimer.singleShot(500, self._refresh)
        except Exception as e:
            self._status.setText(str(e))

    def _set_vol(self) -> None:
        try:
            vol = int(self._vol.text())
            self._get_ctrl().set_volume(vol)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# TranslatorDialog
# ---------------------------------------------------------------------------

class TranslatorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translator")
        self.setMinimumSize(460, 400)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("Translator"))

        self._input = QTextEdit()
        self._input.setPlaceholderText("Text to translate…")
        self._input.setMaximumHeight(120)
        layout.addWidget(self._input)

        row = QHBoxLayout()
        self._lang = QLineEdit()
        self._lang.setPlaceholderText("Target language (e.g. Spanish)")
        row.addWidget(self._lang)
        btn = QPushButton("Translate via JARVIS")
        btn.clicked.connect(self._translate)
        row.addWidget(btn)
        layout.addLayout(row)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("Translation appears here…")
        layout.addWidget(self._output)

    def _translate(self) -> None:
        text = self._input.toPlainText().strip()
        lang = self._lang.text().strip() or "Spanish"
        if not text:
            return
        self._output.setPlainText(f"Ask JARVIS: translate this to {lang}:\n{text}")


# ---------------------------------------------------------------------------
# QRDialog
# ---------------------------------------------------------------------------

class QRDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QR Code")
        self.setMinimumSize(380, 300)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("QR Code Generator"))

        self._input = QLineEdit()
        self._input.setPlaceholderText("URL or text to encode…")
        layout.addWidget(self._input)

        btn = QPushButton("Generate")
        btn.clicked.connect(self._generate)
        layout.addWidget(btn)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch()

    def _generate(self) -> None:
        from jarvis.brain.qr_tool import generate_qr
        data = self._input.text().strip()
        if not data:
            return
        result = generate_qr(data)
        if result.get("ok"):
            self._status.setText(f"Saved: {result['path']}")
        else:
            self._status.setText(result.get("error", "Failed"))


# ---------------------------------------------------------------------------
# VoiceMemoDialog
# ---------------------------------------------------------------------------

class VoiceMemoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Voice Memos")
        self.setMinimumSize(420, 460)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("Voice Memos"))

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self._list)

        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        layout.addWidget(self._detail)

        self._transcript = QTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setMaximumHeight(100)
        layout.addWidget(self._transcript)

        self._refresh()

    def _refresh(self) -> None:
        from jarvis.brain.voice_memo import VoiceMemoStore
        self._list.clear()
        try:
            store = VoiceMemoStore()
            self._memos = store.list_memos()
            for m in self._memos:
                self._list.addItem(QListWidgetItem(m.get("title", "Memo")))
        except Exception:
            self._memos = []

    def _on_select(self, row: int) -> None:
        if 0 <= row < len(self._memos):
            m = self._memos[row]
            dur = m.get("duration_s", 0)
            self._detail.setText(f"{m.get('created', '')[:16]}  •  {dur:.0f}s")
            self._transcript.setPlainText(m.get("transcript", ""))


# ---------------------------------------------------------------------------
# HabitDialog
# ---------------------------------------------------------------------------

_HABIT_FILE = Path.home() / ".jarvis" / "habits.json"


def _load_habits() -> list[dict]:
    try:
        return json.loads(_HABIT_FILE.read_text(encoding="utf-8")) if _HABIT_FILE.exists() else []
    except Exception:
        return []


class HabitDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Habits")
        self.setMinimumSize(400, 460)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("Habit Tracker"))

        self._list = QListWidget()
        layout.addWidget(self._list)

        row = QHBoxLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("Habit name…")
        row.addWidget(self._name)
        btn = QPushButton("Add")
        btn.clicked.connect(self._add)
        row.addWidget(btn)
        layout.addLayout(row)

        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for h in _load_habits():
            self._list.addItem(QListWidgetItem(h.get("name", "")))

    def _add(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        habits = _load_habits()
        habits.append({"id": str(uuid.uuid4()), "name": name,
                       "frequency": "daily", "created": datetime.now().isoformat()})
        _HABIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _HABIT_FILE.write_text(json.dumps(habits, indent=2), encoding="utf-8")
        self._name.clear()
        self._refresh()


# ---------------------------------------------------------------------------
# AlertDialog
# ---------------------------------------------------------------------------

class AlertDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alerts")
        self.setMinimumSize(400, 420)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("Alerts"))

        self._list = QListWidget()
        layout.addWidget(self._list)

        form = QVBoxLayout()
        self._cond = QLineEdit()
        self._cond.setPlaceholderText("Condition (e.g. CPU > 90%)")
        form.addWidget(self._cond)
        self._msg = QLineEdit()
        self._msg.setPlaceholderText("Alert message")
        form.addWidget(self._msg)
        btn = QPushButton("Add Alert")
        btn.clicked.connect(self._add)
        form.addWidget(btn)
        layout.addLayout(form)

        self._alerts: list[dict] = []
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        try:
            from jarvis.brain.alert_engine import AlertEngine
            engine = AlertEngine()
            self._alerts = engine.list_alerts()
            for a in self._alerts:
                self._list.addItem(QListWidgetItem(
                    f"{a.get('condition', '')} → {a.get('message', '')}"))
        except Exception:
            pass

    def _add(self) -> None:
        cond = self._cond.text().strip()
        msg = self._msg.text().strip()
        if not cond:
            return
        try:
            from jarvis.brain.alert_engine import AlertEngine
            AlertEngine().add_alert(condition=cond, message=msg or cond)
            self._cond.clear()
            self._msg.clear()
            self._refresh()
        except Exception as e:
            logger.warning(f"AlertDialog add: {e}")


# ---------------------------------------------------------------------------
# WebRemoteDialog
# ---------------------------------------------------------------------------

class WebRemoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Web Remote")
        self.setMinimumSize(380, 300)
        self.setStyleSheet(_BASE_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.addWidget(_title_label("Web Remote"))

        info = QLabel(
            "JARVIS local server lets you send commands from your phone or another device.\n\n"
            "Start the server via: Settings → Web Remote"
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {_MUTED};")
        layout.addWidget(info)

        self._url_label = QLabel("")
        self._url_label.setStyleSheet(f"color: {_ACCENT}; font-size: 13px;")
        layout.addWidget(self._url_label)

        btn = QPushButton("Copy URL")
        btn.clicked.connect(self._copy_url)
        layout.addWidget(btn)
        layout.addStretch()

        self._load_url()

    def _load_url(self) -> None:
        try:
            import socket
            host = socket.gethostbyname(socket.gethostname())
            self._url_label.setText(f"http://{host}:7799")
        except Exception:
            self._url_label.setText("http://localhost:7799")

    def _copy_url(self) -> None:
        import pyperclip
        try:
            pyperclip.copy(self._url_label.text())
        except Exception:
            pass
