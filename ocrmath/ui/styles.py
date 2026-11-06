"""Light black-and-white theme for what Qt still draws: tray menu, native
dialogs and the screenshot overlay. The windows themselves live in web/."""
from __future__ import annotations

ACCENT = "#1a1a1a"
TEXT = "#1a1a1a"
MUTED = "#666666"
BORDER = "#e8e8e8"
SURFACE = "#ffffff"

STYLESHEET = f"""
* {{ font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; color: {TEXT}; }}
QWidget {{ font-size: 10pt; }}
QDialog, QMessageBox {{ background: {SURFACE}; }}
QPushButton {{
    background: {SURFACE}; border: 1px solid #cfcfcf; border-radius: 5px;
    padding: 5px 14px; min-height: 22px;
}}
QPushButton:hover {{ background: #f5f5f5; }}
QLineEdit, QComboBox {{
    background: {SURFACE}; border: 1px solid #cfcfcf; border-radius: 5px; padding: 4px 8px;
}}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 5px; border-radius: 6px; }}
QMenu::item {{ padding: 6px 26px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: #f0f0f0; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 4px 8px; }}
"""


def apply_theme(app) -> None:
    """The app is always light, whatever the system appearance is."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QPalette

    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    palette = QPalette(app.palette())
    for role, color in (
        (QPalette.ColorRole.Window, SURFACE),
        (QPalette.ColorRole.Base, SURFACE),
        (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.ButtonText, TEXT),
        (QPalette.ColorRole.Button, SURFACE),
        (QPalette.ColorRole.Highlight, TEXT),
        (QPalette.ColorRole.HighlightedText, SURFACE),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
