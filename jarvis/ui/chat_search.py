
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
)


class ChatSearchBar(QFrame):
    """
    Floating search bar that highlights matches in a QTextEdit.
    Uses ExtraSelections so it never corrupts the document's own formatting.
    """

    closed = pyqtSignal()

    def __init__(self, chat_display: QTextEdit, parent=None):
        super().__init__(parent)
        self._display = chat_display
        self._matches: list[QTextCursor] = []
        self._idx = -1

        self._hl_fmt = QTextCharFormat()
        self._hl_fmt.setBackground(QColor("#3B9EFF33"))

        self._cur_fmt = QTextCharFormat()
        self._cur_fmt.setBackground(QColor("#F59E0B"))
        self._cur_fmt.setForeground(QColor("#000000"))

        self.setObjectName("hudIntelFeed")
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        self._field = QLineEdit()
        self._field.setPlaceholderText("Search chat...")
        self._field.setObjectName("msgInput")
        self._field.textChanged.connect(
            lambda _: QTimer.singleShot(150, self._search)
        )
        self._field.returnPressed.connect(self._next)
        layout.addWidget(self._field, 1)

        self._lbl = QLabel("0 / 0")
        self._lbl.setObjectName("muted")
        self._lbl.setFixedWidth(52)
        layout.addWidget(self._lbl)

        for label, slot, tip in [
            ("▲", self._prev, "Previous match"),
            ("▼", self._next, "Next match"),
            ("✕", self._close, "Close (Esc)"),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(28, 26)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def focus(self) -> None:
        self._field.setFocus()
        self._field.selectAll()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._close()
        else:
            super().keyPressEvent(event)

    def _close(self) -> None:
        self._display.setExtraSelections([])
        self._field.clear()
        self._matches = []
        self._idx = -1
        self.closed.emit()

    def _search(self) -> None:
        self._display.setExtraSelections([])
        self._matches = []
        self._idx = -1
        query = self._field.text().strip()
        if not query:
            self._refresh_label()
            return
        doc = self._display.document()
        cur = QTextCursor(doc)
        while True:
            cur = doc.find(query, cur)
            if cur.isNull():
                break
            self._matches.append(QTextCursor(cur))
        if self._matches:
            self._idx = 0
            self._apply_highlights()
            self._scroll_to_current()
        self._refresh_label()

    def _next(self) -> None:
        if not self._matches:
            return
        self._idx = (self._idx + 1) % len(self._matches)
        self._apply_highlights()
        self._scroll_to_current()

    def _prev(self) -> None:
        if not self._matches:
            return
        self._idx = (self._idx - 1) % len(self._matches)
        self._apply_highlights()
        self._scroll_to_current()

    def _apply_highlights(self) -> None:
        extras = []
        for i, c in enumerate(self._matches):
            sel = QTextEdit.ExtraSelection()
            sel.cursor = c
            sel.format = self._cur_fmt if i == self._idx else self._hl_fmt
            extras.append(sel)
        self._display.setExtraSelections(extras)
        self._refresh_label()

    def _scroll_to_current(self) -> None:
        if 0 <= self._idx < len(self._matches):
            self._display.setTextCursor(self._matches[self._idx])
            self._display.ensureCursorVisible()

    def _refresh_label(self) -> None:
        total = len(self._matches)
        cur = self._idx + 1 if total > 0 else 0
        self._lbl.setText(f"{cur} / {total}")
