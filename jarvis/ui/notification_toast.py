"""
Non-intrusive notification toast for proactive help suggestions.
Slides in from the bottom-right corner, auto-dismisses after 10 seconds.
"""


from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
    QApplication,
)

class NotificationToast(QFrame):
    help_requested = pyqtSignal(str)
    dismissed = pyqtSignal(str)

    # Class-level instances for static show method
    _instances: dict[str, "NotificationToast"] = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._category = ""
        self._suggestion = ""
        self._level = "info"  # info, success, warning, error
        self._auto_dismiss_timer = QTimer(self)
        self._auto_dismiss_timer.setSingleShot(True)
        self._auto_dismiss_timer.timeout.connect(self._on_dismiss)

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(380)

        self._build_ui()
        self.hide()

    def _update_level_styles(self) -> None:
        """Apply color styling based on notification level."""
        level_config = {
            "info": {
                "icon": "💡",
                "title": "JARVIS INFO",
                "title_color": "rgba(0, 229, 255, 0.70)",
                "bg_color": "rgba(0, 100, 150, 0.15)",
                "border_color": "rgba(0, 229, 255, 0.25)",
                "help_bg": "rgba(0, 229, 255, 0.12)",
                "help_color": "#00E5FF",
                "help_border": "rgba(0, 229, 255, 0.25)",
            },
            "success": {
                "icon": "✓",
                "title": "SUCCESS",
                "title_color": "rgba(16, 185, 129, 0.80)",
                "bg_color": "rgba(16, 100, 80, 0.15)",
                "border_color": "rgba(16, 185, 129, 0.25)",
                "help_bg": "rgba(16, 185, 129, 0.12)",
                "help_color": "#10B981",
                "help_border": "rgba(16, 185, 129, 0.25)",
            },
            "warning": {
                "icon": "⚠",
                "title": "WARNING",
                "title_color": "rgba(245, 158, 11, 0.80)",
                "bg_color": "rgba(180, 120, 0, 0.15)",
                "border_color": "rgba(245, 158, 11, 0.25)",
                "help_bg": "rgba(245, 158, 11, 0.12)",
                "help_color": "#F59E0B",
                "help_border": "rgba(245, 158, 11, 0.25)",
            },
            "error": {
                "icon": "✕",
                "title": "ERROR",
                "title_color": "rgba(239, 68, 68, 0.80)",
                "bg_color": "rgba(200, 50, 50, 0.15)",
                "border_color": "rgba(239, 68, 68, 0.25)",
                "help_bg": "rgba(239, 68, 68, 0.12)",
                "help_color": "#EF4444",
                "help_border": "rgba(239, 68, 68, 0.25)",
            },
        }

        config = level_config.get(self._level, level_config["info"])

        # Update icon and title
        self._icon_label.setText(config["icon"])
        self._title_label.setText(config["title"])
        self._title_label.setStyleSheet(
            f"color: {config['title_color']}; font-weight: 600; font-size: 11px; letter-spacing: 2px;"
        )

        # Update frame background and border
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {config['bg_color']};
                border: 1px solid {config['border_color']};
                border-radius: 12px;
            }}
            """
        )

        # Update help button styling
        self._help_btn.setStyleSheet(f"""
            QPushButton {{
                background: {config['help_bg']};
                color: {config['help_color']};
                border: 1px solid {config['help_border']};
                border-radius: 8px;
                padding: 6px 18px;
                font-family: "Segoe UI Variable", "Segoe UI";
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid {config['help_color']};
            }}
        """)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self._icon_label = QLabel("💡")
        self._icon_label.setFont(QFont("Segoe UI Emoji", 14))
        self._title_label = QLabel("JARVIS SUGGESTION")
        self._title_label.setStyleSheet(
            "color: rgba(0, 229, 255, 0.70); font-weight: 600; font-size: 11px; letter-spacing: 2px;"
        )
        header.addWidget(self._icon_label)
        header.addWidget(self._title_label)
        header.addStretch()
        layout.addLayout(header)
        self._suggestion_label = QLabel()
        self._suggestion_label.setWordWrap(True)
        self._suggestion_label.setStyleSheet(
            'color: #E2E8F0; font-family: "Segoe UI Variable", "Segoe UI"; '
            "font-size: 14px; padding: 2px 0; line-height: 1.5;"
        )
        layout.addWidget(self._suggestion_label)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._help_btn = QPushButton("Help me")
        self._help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._help_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 229, 255, 0.12);
                color: #00E5FF;
                border: 1px solid rgba(0, 229, 255, 0.25);
                border-radius: 8px;
                padding: 6px 18px;
                font-family: "Segoe UI Variable", "Segoe UI";
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.22);
                border: 1px solid rgba(0, 229, 255, 0.40);
            }
        """)
        self._help_btn.clicked.connect(self._on_help)
        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(148, 163, 184, 0.60);
                border: 1px solid rgba(51, 65, 85, 0.35);
                border-radius: 8px;
                padding: 6px 18px;
                font-family: "Segoe UI Variable", "Segoe UI";
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(51, 65, 85, 0.15);
                color: rgba(148, 163, 184, 0.90);
                border: 1px solid rgba(51, 65, 85, 0.50);
            }
        """)
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        btn_row.addStretch()
        btn_row.addWidget(self._help_btn)
        btn_row.addWidget(self._dismiss_btn)
        layout.addLayout(btn_row)
        # Apply initial level styles now that all widgets are created
        self._update_level_styles()

    def show_suggestion(self, suggestion: str, category: str, level: str = "info", auto_dismiss_ms: int = 10000) -> None:
        self._suggestion = suggestion
        self._category = category
        self._level = level

        # Update styles for the new level
        self._update_level_styles()
        self._suggestion_label.setText(suggestion)

        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 20
            y = geo.bottom() - self.height() - 20
            self.move(x, y)

        QFrame.show(self)  # explicitly call QWidget.show, not our classmethod
        self.raise_()
        self._auto_dismiss_timer.start(auto_dismiss_ms)

    @classmethod
    def show_toast(cls, message: str, level: str = "info", parent=None, category: str = "", auto_dismiss_ms: int = None) -> "NotificationToast":
        """Class method to show a notification toast with auto-dismiss.

        Args:
            message: The notification message to display
            level: Notification level - "info", "success", "warning", or "error" (default: "info")
            parent: Parent widget (optional)
            category: Category for the notification (used in dismissed signal)
            auto_dismiss_ms: Auto-dismiss delay in milliseconds (default: 10000 for info/success, 15000 for warning/error)

        Returns:
            The NotificationToast instance
        """
        # Determine auto-dismiss time based on level if not specified
        if auto_dismiss_ms is None:
            auto_dismiss_ms = 15000 if level in ("warning", "error") else 10000

        # Get or create instance
        instance_key = f"toast_{id(parent)}" if parent else "toast_global"
        if instance_key not in cls._instances:
            cls._instances[instance_key] = cls(parent)

        toast = cls._instances[instance_key]
        toast.show_suggestion(message, category if category else level, level, auto_dismiss_ms)
        return toast

    # Keep backward-compat alias so old call-sites still work
    show = show_toast

    def _on_help(self) -> None:
        self._auto_dismiss_timer.stop()
        self.hide()
        self.help_requested.emit(self._suggestion)

    def _on_dismiss(self) -> None:
        self._auto_dismiss_timer.stop()
        self.hide()
        self.dismissed.emit(self._category)
