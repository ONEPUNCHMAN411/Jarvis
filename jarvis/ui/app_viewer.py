import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QPlainTextEdit, QSplitter, QWidget,
    QLineEdit, QApplication,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import (
    QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QTextDocument,
)

_JARVIS_ROOT = Path(__file__).parent.parent
_READABLE = {".py", ".toml", ".spec", ".md", ".json", ".txt", ".yaml", ".yml", ".cfg", ".ini"}


class _PythonHighlighter(QSyntaxHighlighter):
    _KW = re.compile(
        r"\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del"
        r"|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal"
        r"|not|or|pass|raise|return|try|while|with|yield|self|cls)\b"
    )
    _STR1 = re.compile(r"\"[^\"\\]*(?:\\.[^\"\\]*)*\"")
    _STR2 = re.compile(r"\'[^\'\\]*(?:\\.[^\'\\]*)*\'")
    _COMMENT = re.compile(r"#.*$")
    _NUMBER = re.compile(r"\b\d+\.?\d*\b")
    _DECORATOR = re.compile(r"@\w+")
    _FUNC = re.compile(r"(?<=def )\w+")
    _CLASS = re.compile(r"(?<=class )\w+")

    def __init__(self, doc: QTextDocument):
        super().__init__(doc)

        def _f(hex_color: str, bold=False, italic=False) -> QTextCharFormat:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(hex_color))
            if bold:
                fmt.setFontWeight(700)
            if italic:
                fmt.setFontItalic(True)
            return fmt

        self._rules = [
            (self._KW, _f("#82AAFF", bold=True)),
            (self._STR1, _f("#c3e88d")),
            (self._STR2, _f("#c3e88d")),
            (self._COMMENT, _f("#546e7a", italic=True)),
            (self._NUMBER, _f("#f78c6c")),
            (self._DECORATOR, _f("#89ddff")),
            (self._FUNC, _f("#82aaff", bold=True)),
            (self._CLASS, _f("#ffcb6b", bold=True)),
        ]

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class AppViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS — Source Viewer")
        self.setMinimumSize(1120, 680)
        self._current_path: Path | None = None
        self._all_items: list[tuple[QTreeWidgetItem, Path]] = []
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)
        self._build_ui()
        self._load_tree()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(8)
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
            QTreeWidget { background: #161b22; border: 1px solid #30363d; border-radius: 6px; color: #e6edf3; font-size: 12px; }
            QTreeWidget::item:selected { background: #1f6feb; color: #ffffff; }
            QTreeWidget::item:hover { background: #21262d; }
            QLineEdit { background: #21262d; color: #e6edf3; border: 1px solid #30363d; border-radius: 5px; padding: 4px 8px; font-size: 12px; }
        """)

        top = QHBoxLayout()
        title_lbl = QLabel("JARVIS — Source Viewer")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color:#58a6ff;")
        top.addWidget(title_lbl)
        top.addStretch()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search in file")
        self._search_box.setFixedWidth(260)
        self._search_box.textChanged.connect(lambda: self._search_timer.start(200))
        top.addWidget(self._search_box)
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)

        self._filter_box = QLineEdit()
        self._filter_box.setPlaceholderText("Filter files")
        self._filter_box.textChanged.connect(self._filter_tree)
        lv.addWidget(self._filter_box)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Project Files")
        self._tree.setFont(QFont("Consolas", 10))
        self._tree.itemClicked.connect(self._on_item_click)
        lv.addWidget(self._tree)

        self._tree_stats = QLabel("")
        self._tree_stats.setStyleSheet("color:#6e7681;font-size:10px;")
        lv.addWidget(self._tree_stats)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(4)

        self._path_lbl = QLabel("Select a file from the tree")
        self._path_lbl.setStyleSheet("color:#8b949e;font-size:11px;")
        rv.addWidget(self._path_lbl)

        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setFont(QFont("Consolas", 11))
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.setStyleSheet("""
            QPlainTextEdit {
                background: #0d1117; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 6px;
                padding: 8px; selection-background-color: #264f78;
            }
        """)
        self._highlighter = _PythonHighlighter(self._editor.document())
        rv.addWidget(self._editor)

        status_row = QHBoxLayout()
        self._cursor_lbl = QLabel("")
        self._size_lbl = QLabel("")
        for lbl in (self._cursor_lbl, self._size_lbl):
            lbl.setStyleSheet("color:#6e7681;font-size:11px;")
        status_row.addWidget(self._cursor_lbl)
        status_row.addStretch()
        status_row.addWidget(self._size_lbl)
        rv.addLayout(status_row)
        splitter.addWidget(right)

        splitter.setSizes([280, 820])
        root.addWidget(splitter)

        self._editor.cursorPositionChanged.connect(self._update_cursor)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("Copy File")
        copy_btn.setFixedHeight(30)
        copy_btn.setStyleSheet("background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px;font-size:12px;")
        copy_btn.clicked.connect(self._copy_file)
        btn_row.addWidget(copy_btn)
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(30)
        close_btn.setStyleSheet("background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px;font-size:12px;")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _load_tree(self):
        self._tree.clear()
        self._all_items = []
        total_files = total_lines = 0

        def _add_dir(parent_item, directory: Path):
            nonlocal total_files, total_lines
            dirs, files = [], []
            try:
                for child in sorted(directory.iterdir()):
                    if child.name.startswith((".", "__pycache__")):
                        continue
                    if child.is_dir():
                        dirs.append(child)
                    elif child.suffix in _READABLE:
                        files.append(child)
            except PermissionError:
                return

            for d in dirs:
                node = QTreeWidgetItem(parent_item, [f"📁  {d.name}"])
                node.setData(0, Qt.ItemDataRole.UserRole, None)
                _add_dir(node, d)

            for f in files:
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    n_lines = len(content.splitlines())
                except Exception:
                    n_lines = 0
                item = QTreeWidgetItem(parent_item, [f"  {f.name}   ({n_lines} L)"])
                item.setData(0, Qt.ItemDataRole.UserRole, f)
                self._all_items.append((item, f))
                total_files += 1
                total_lines += n_lines

        root_node = QTreeWidgetItem(self._tree, ["📦  jarvis/"])
        root_node.setData(0, Qt.ItemDataRole.UserRole, None)
        _add_dir(root_node, _JARVIS_ROOT)
        self._tree.expandToDepth(1)
        self._tree_stats.setText(f"{total_files} files    {total_lines:,} total lines")

    def _on_item_click(self, item: QTreeWidgetItem, _col: int):
        path: Path | None = item.data(0, Qt.ItemDataRole.UserRole)
        if not path or not path.is_file():
            return
        self._current_path = path
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            text = f"# Could not read: {e}"
        self._editor.setPlainText(text)
        try:
            rel = path.relative_to(_JARVIS_ROOT.parent)
        except ValueError:
            rel = path
        self._path_lbl.setText(str(rel))
        self._update_cursor()

    def _update_cursor(self):
        cur = self._editor.textCursor()
        line = cur.blockNumber() + 1
        col = cur.columnNumber() + 1
        total = self._editor.document().blockCount()
        chars = len(self._editor.toPlainText())
        self._cursor_lbl.setText(f"Ln {line}/{total}  Col {col}")
        self._size_lbl.setText(f"{chars:,} chars")

    def _filter_tree(self, text: str):
        low = text.lower()
        for item, path in self._all_items:
            item.setHidden(bool(low) and low not in path.name.lower())

    def _do_search(self):
        query = self._search_box.text()
        if not query:
            return
        from PyQt6.QtGui import QTextCursor
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self._editor.setTextCursor(cursor)
        self._editor.find(query)

    def _copy_file(self):
        if self._current_path:
            QApplication.clipboard().setText(self._editor.toPlainText())
