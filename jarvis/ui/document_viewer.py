
import mimetypes
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import Qt, QPropertyAnimation, QRect, QEasingCurve
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


def _glow(color: str = "#3B9EFF", r: int = 20) -> QGraphicsDropShadowEffect:
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(r)
    fx.setColor(QColor(color))
    fx.setOffset(0, 0)
    return fx


class DocumentTab(QWidget):
    """One tab: renders an image, text, markdown, or PDF."""

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = Path(path)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        mime, _ = mimetypes.guess_type(str(self._path))
        mime = mime or ""
        if mime.startswith("image/"):
            self._render_image(layout)
        elif self._path.suffix.lower() == ".pdf":
            self._render_pdf(layout)
        else:
            self._render_text(layout)

    def _render_image(self, layout: QVBoxLayout) -> None:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        px = QPixmap(str(self._path))
        if not px.isNull():
            label.setPixmap(
                px.scaledToWidth(480, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            label.setText("Could not load image.")
        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        layout.addWidget(scroll)

    def _render_pdf(self, layout: QVBoxLayout) -> None:
        browser = QTextBrowser()
        browser.setStyleSheet(
            "QTextBrowser { background: #0D1117; color: #E6EDF3; "
            "border: none; font-size: 13px; }"
        )
        try:
            import fitz
            doc = fitz.open(str(self._path))
            parts = []
            for i, page in enumerate(doc):
                parts.append(f"<pre>{page.get_text('text')}</pre>")
                if i >= 19:
                    break
            browser.setHtml("<hr>".join(parts))
        except ImportError:
            browser.setPlainText("Install pymupdf to render PDFs: pip install pymupdf")
        except Exception as e:
            browser.setPlainText(f"Could not render PDF: {e}")
        layout.addWidget(browser)

    def _render_text(self, layout: QVBoxLayout) -> None:
        browser = QTextBrowser()
        browser.setStyleSheet(
            "QTextBrowser { background: #0D1117; color: #E6EDF3; border: none; "
            "font-family: 'Consolas', monospace; font-size: 13px; }"
        )
        try:
            text = self._path.read_text(encoding="utf-8", errors="replace")
            if self._path.suffix.lower() in (".md", ".markdown"):
                try:
                    import markdown as _md
                    html = _md.markdown(text, extensions=["fenced_code", "tables"])
                    styled = (
                        "<style>body{background:#0D1117;color:#E6EDF3;font-family:sans-serif;}"
                        "pre{background:#161B22;padding:12px;border-radius:6px;}"
                        "code{color:#79C0FF;}</style>" + html
                    )
                    browser.setHtml(styled)
                except ImportError:
                    browser.setPlainText(text)
            else:
                browser.setPlainText(text)
        except Exception as e:
            browser.setPlainText(f"Could not read file: {e}")
        layout.addWidget(browser)


class DocumentViewer(QWidget):
    """Slide-in side panel for viewing documents."""

    _WIDTH = 520

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("JARVIS Documents")
        self._visible = False
        self._anim: QPropertyAnimation | None = None
        # Keep live animation references so Qt doesn't GC them mid-run
        self._anims: set = set()
        self._build_ui()
        self.setGraphicsEffect(_glow("#3B9EFF", 30))

    def _build_ui(self) -> None:
        self.setFixedWidth(self._WIDTH)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        container = QWidget()
        container.setStyleSheet(
            "QWidget { background: rgba(10,15,25,0.97); "
            "border-left: 1px solid rgba(59, 158, 255,0.25); border-radius: 12px; }"
        )
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet(
            "QWidget { background: rgba(59, 158, 255,0.07); "
            "border-bottom: 1px solid rgba(59, 158, 255,0.15); border-radius: 0; }"
        )
        hr = QHBoxLayout(header)
        hr.setContentsMargins(12, 0, 8, 0)

        title = QLabel("📄  JARVIS Documents")
        title.setStyleSheet(
            "color: #3B9EFF; font-size: 13px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        hr.addWidget(title)
        hr.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: rgba(255,80,80,0.15); color: #FF5C5C; "
            "border: 1px solid rgba(255,80,80,0.3); border-radius: 6px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(255,80,80,0.3); }"
        )
        close_btn.clicked.connect(self.slide_out)
        hr.addWidget(close_btn)
        cl.addWidget(header)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: transparent; }"
            "QTabBar::tab { background: rgba(59, 158, 255,0.08); color: rgba(59, 158, 255,0.7); "
            "padding: 6px 14px; border-radius: 4px; margin: 2px; font-size: 11px; }"
            "QTabBar::tab:selected { background: rgba(59, 158, 255,0.2); color: #3B9EFF; }"
        )
        cl.addWidget(self._tabs)
        root.addWidget(container)

    def open_document(self, path: str, title: str | None = None) -> None:
        p = Path(path)
        if not p.exists():
            logger.warning(f"DocumentViewer: not found: {path}")
            return
        tab = DocumentTab(str(p))
        idx = self._tabs.addTab(tab, title or p.name)
        self._tabs.setCurrentIndex(idx)
        if not self._visible:
            self.slide_in()
        logger.info(f"DocumentViewer opened: {p.name}")

    def slide_in(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        h = screen.height()
        w = self._WIDTH
        self.setGeometry(QRect(screen.right(), 60, w, h - 80))
        self.show()
        self.raise_()
        self._run_anim(
            self.geometry(),
            QRect(screen.right() - w - 8, 60, w, h - 80),
        )
        self._visible = True

    def slide_out(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        h = screen.height()
        anim = self._run_anim(
            self.geometry(),
            QRect(screen.right(), 60, self._WIDTH, h - 80),
        )
        anim.finished.connect(self.hide)
        self._visible = False

    def _run_anim(self, start: QRect, end: QRect) -> QPropertyAnimation:
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(320)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # Hold a reference in the set until finished — prevents GC mid-animation
        self._anims.add(anim)
        anim.finished.connect(lambda a=anim: self._anims.discard(a))
        anim.start()
        self._anim = anim
        return anim

    def _close_tab(self, index: int) -> None:
        self._tabs.removeTab(index)
        if self._tabs.count() == 0:
            self.slide_out()

    def toggle(self) -> None:
        self.slide_out() if self._visible else self.slide_in()

    @property
    def is_visible(self) -> bool:
        return self._visible


_viewer: DocumentViewer | None = None
_viewer_lock = __import__("threading").Lock()


def get_document_viewer(parent=None) -> DocumentViewer:
    global _viewer
    if _viewer is None:
        with _viewer_lock:
            if _viewer is None:
                _viewer = DocumentViewer(parent)
    return _viewer
