
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QLabel,
    QSplitter,
)
from PyQt6.QtCore import Qt


class BookmarksDialog(QDialog):
    """Browse and delete bookmarked JARVIS responses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bookmarks")
        self.resize(740, 540)
        if parent:
            self.setStyleSheet(parent.styleSheet())

        from jarvis.brain.bookmark_store import get_bookmark_store
        self._store = get_bookmark_store()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hdr = QLabel("BOOKMARKED RESPONSES")
        hdr.setStyleSheet(
            "color: #F59E0B;"
            "font-family: Consolas;"
            "font-size: 10px;"
            "letter-spacing: 1px;"
            "font-weight: 700;"
        )
        layout.addWidget(hdr)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget {"
            "background: rgba(10,16,32,0.9);"
            "border: 1px solid rgba(59, 158, 255,0.15);"
            "border-radius: 10px; padding: 4px;"
            "}"
            "QListWidget::item {"
            "padding: 10px 14px; border-radius: 6px;"
            "color: #E7ECFB; font-size: 12px;"
            "}"
            "QListWidget::item:selected {"
            "background: rgba(59, 158, 255,0.18); color: #FFFFFF;"
            "}"
            "QListWidget::item:hover {"
            "background: rgba(59, 158, 255,0.08);"
            "}"
        )
        self._list.currentRowChanged.connect(self._on_select)
        splitter.addWidget(self._list)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setStyleSheet(
            "background: rgba(8,14,28,0.90);"
            "border: 1px solid rgba(59, 158, 255,0.12);"
            "border-radius: 10px; padding: 12px;"
            "color: #E7ECFB; font-size: 13px; line-height: 1.65;"
        )
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        from jarvis.ui.orb_widgets import AnimatedButton
        btn_row = QHBoxLayout()

        del_btn = AnimatedButton("Delete bookmark", accent="#FF2244")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(del_btn)

        btn_row.addStretch()
        close_btn = AnimatedButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._populate()

    def _populate(self) -> None:
        self._list.clear()
        self._preview.clear()
        for b in self._store.list_all():
            ts = b.created[:16].replace("T", " ")
            item = QListWidgetItem(f"{ts}  ·  {b.preview}")
            item.setData(256, b.id)
            self._list.addItem(item)
        if not self._store.list_all():
            self._preview.setPlainText(
                "No bookmarks yet.\n\n"
                "Use the '☆ Bookmark' button below the chat input "
                "to save any JARVIS response."
            )

    def _on_select(self, row: int) -> None:
        item = self._list.item(row)
        if not item:
            return
        bm = self._store.get(item.data(256))
        if bm:
            self._preview.setPlainText(bm.text)

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        self._store.remove(item.data(256))
        self._populate()
