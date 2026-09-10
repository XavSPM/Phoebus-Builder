"""
Clean and professional theme management for Phoebus Builder GUI (PySide6).
Uses clean Qt QPalette and targeted styling to eliminate visual artifacts on Linux/Wayland.
"""

from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


def apply_app_theme(app: QApplication):
    """
    Applies clean color palette and non-invasive styling to avoid any visual artifacts.
    """
    # Primary accent (Modern Blue)
    primary_color = QColor("#0284c7")

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Highlight, primary_color)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, primary_color)

    app.setPalette(palette)

    # Apply clean styling: buttons, dialogs, and log_console
    app.setStyleSheet("""
        QPushButton {
            min-height: 24px;
            padding: 4px 10px;
        }
        QDialogButtonBox QPushButton {
            min-width: 80px;
            min-height: 26px;
        }
        QPlainTextEdit#log_console {
            background-color: #0f172a;
            color: #f8fafc;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 8px;
        }
    """)
