"""Centralized QSS stylesheet + palette helpers.

Apply via:
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(STYLESHEET)
"""
from __future__ import annotations

ACCENT = "#277d68"
ACCENT_HOVER = "#318e77"
ACCENT_PRESS = "#206653"
TEXT = "#242b30"
MUTED = "#727d78"
BORDER = "#e4e8e6"
BORDER_FOCUS = ACCENT
BG = "#f5f7f6"
SURFACE = "#ffffff"
WARNING_BG = "#fff3cd"
WARNING_BORDER = "#ffeeba"
WARNING_TEXT = "#7a5a00"
SUCCESS = ACCENT


STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    color: {TEXT};
}}
QWidget {{
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background-color: {BG};
}}
QFrame {{
    background: transparent;
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 7px 14px;
    min-height: 26px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: #f8fafc;
    border-color: #b9c5d1;
}}
QPushButton:pressed {{
    background-color: #edf1f6;
}}
QPushButton:disabled {{
    color: #b0b0b0;
    background-color: #f5f5f5;
    border-color: #e2e2e2;
}}

/* Accent button (set objectName="accent") */
QPushButton#accent {{
    background-color: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#accent:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#accent:pressed {{
    background-color: {ACCENT_PRESS};
}}
QPushButton#accent:disabled {{
    background-color: #a9cfc1;
    border-color: #a9cfc1;
    color: white;
}}

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QKeySequenceEdit {{
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 9px;
    background: {SURFACE};
    selection-background-color: #d9ebe2;
    selection-color: {TEXT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox:focus, QKeySequenceEdit:focus {{
    border-color: {BORDER_FOCUS};
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{
    background: #f3f3f3;
    color: #999;
}}

/* ---- Tabs ---- */
QTabWidget::pane {{
    border: 1px solid #e4e9f0;
    border-radius: 8px;
    background: {SURFACE};
    top: -2px;
}}
QTabBar::tab {{
    background: #eef2f7;
    border: 1px solid #e1e7ef;
    padding: 9px 22px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
    color: #59636f;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    border-bottom-color: {SURFACE};
    color: {ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: #f8fafc;
    color: {TEXT};
}}

/* ---- Group box ---- */
QGroupBox {{
    border: 1px solid #e4e9f0;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 8px 10px;
    background: {SURFACE};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {ACCENT};
    font-weight: 600;
}}

/* ---- Progress bar ---- */
QProgressBar {{
    border: 1px solid #e0e6ee;
    border-radius: 7px;
    background: #edf1f6;
    text-align: center;
    height: 24px;
    color: {TEXT};
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 6px;
}}

/* ---- Checkbox ---- */
QCheckBox {{
    spacing: 7px;
}}

/* ---- Menus (also affects tray menu) ---- */
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    padding: 6px;
    border-radius: 8px;
}}
QMenu::item {{
    padding: 7px 28px 7px 18px;
    border-radius: 6px;
    margin: 1px 2px;
}}
QMenu::item:selected {{
    background: {ACCENT};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: #e0e0e0;
    margin: 4px 8px;
}}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #c5ced8;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #aab5c2; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #c5ced8;
    border-radius: 5px;
    min-width: 30px;
}}

/* ---- Lists ---- */
QListWidget {{
    background: #f8fafc;
    border: 1px solid #e4e9f0;
    border-radius: 8px;
    padding: 6px;
    outline: 0;
}}
QListWidget::item {{
    border-radius: 8px;
    margin: 3px;
}}
QListWidget::item:selected {{
    background: #edf4f0;
    color: {TEXT};
}}

/* ---- Tooltips ---- */
QToolTip {{
    background: #2b2b2b;
    color: white;
    border: 1px solid #2b2b2b;
    padding: 4px 8px;
    border-radius: 4px;
}}

/* ---- Custom card classes ----
   Widgets with property card="true" get a soft white card look. */
QWidget[card="true"] {{
    background: {SURFACE};
    border: 1px solid #e4e9f0;
    border-radius: 8px;
}}
QLabel[role="heading"] {{
    font-size: 18pt;
    font-weight: 700;
    color: {TEXT};
}}
QLabel[role="subheading"] {{
    font-size: 11pt;
    font-weight: 600;
    color: {TEXT};
}}
QLabel[role="muted"] {{
    color: {MUTED};
}}
QLabel[role="warning"] {{
    background: {WARNING_BG};
    color: {WARNING_TEXT};
    border: 1px solid {WARNING_BORDER};
    border-radius: 4px;
    padding: 8px 10px;
}}
QLabel[role="dropzone"] {{
    border: 2px dashed #c9d3df;
    border-radius: 8px;
    padding: 18px;
    color: {MUTED};
    background: #f8fafc;
    font-size: 11pt;
}}
QLabel[role="dropzone"][active="true"] {{
    border-color: {ACCENT};
    background: #edf4f0;
    color: {ACCENT};
}}
"""

# Focus window and tool chrome share the same palette and spacing.
STYLESHEET += f"""
QWidget#resultWindow {{ background: {SURFACE}; }}
QFrame#resultHeader {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QFrame#resultFooter {{ background: {BG}; border-top: 1px solid {BORDER}; }}
QLabel#brandMark {{
    background: {ACCENT}; color: white; border-radius: 7px;
    font-family: Georgia; font-size: 23pt;
}}
QLabel#brandName {{ font-size: 12pt; font-weight: 600; }}
QLabel#statusBadge {{
    background: #edf4f0; color: {ACCENT}; border-radius: 5px;
    padding: 4px 9px; font-size: 9pt;
}}
QFrame#sourceFrame {{ background: #fcfbf7; border-radius: 8px; }}
QLabel#historyThumb {{ background: #fcfbf7; border: 1px solid {BORDER}; border-radius: 5px; }}
QLabel#formulaPreview, QLabel#resultEmpty {{
    background: {BG}; border-radius: 9px; padding: 20px;
}}
QPlainTextEdit#resultCode {{
    background: {BG}; border: none; border-radius: 9px; padding: 14px;
}}
QLabel#copyToast {{ color: {ACCENT}; font-size: 9pt; }}
QLabel[role="statValue"] {{ font-size: 17pt; font-weight: 600; }}
QPushButton[flat="true"] {{
    background: transparent; border: 1px solid transparent; padding: 5px 10px;
}}
QPushButton[flat="true"]:hover {{ background: #edf4f0; }}
QPushButton[segment="true"] {{
    background: transparent; color: {MUTED}; border: none;
    padding: 5px 10px; min-height: 22px; font-size: 9pt;
}}
QPushButton[segment="true"]:checked {{
    background: #edf4f0; color: {ACCENT}; font-weight: 600;
}}
QPushButton[segment="true"]:disabled {{ color: #a1aaa5; }}
QTabWidget::pane {{ border: none; background: {SURFACE}; }}
QTabBar::tab {{
    background: transparent; border: none; border-radius: 6px;
    padding: 8px 18px; margin: 3px 4px; color: {MUTED};
}}
QTabBar::tab:selected {{ background: #edf4f0; color: {ACCENT}; }}
QTableWidget {{
    background: {SURFACE}; alternate-background-color: {BG};
    border: none; selection-background-color: #edf4f0;
}}
QHeaderView::section {{
    background: {BG}; border: none; padding: 8px; color: {MUTED};
}}
QTableWidget::item {{ padding: 6px; }}
"""


def apply_theme(app, dark: bool | None = None) -> None:
    """Use the system appearance at startup; callers may explicitly preview either."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QPalette

    if dark is None:
        dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    app.setProperty("darkMode", dark)
    sheet = STYLESHEET
    palette = QPalette(app.palette())
    if dark:
        replacements = {
            SURFACE: "#1c2122", BG: "#171c1d", TEXT: "#e6ebe9", MUTED: "#a2ada8",
            BORDER: "#353d3b", "#edf4f0": "#233c33", "#fcfbf7": "#282b29",
            "#f8fafc": "#202729", "#eef2f7": "#252c2d", "#f1f5f9": "#252c2d",
            "#e4e9f0": "#353d3b", "#e1e7ef": "#353d3b", "#e0e6ee": "#353d3b",
            "#edf1f6": "#252c2d", "#f3f3f3": "#252c2d", "#f5f5f5": "#252c2d",
            "#fff3cd": "#413620", "#ffeeba": "#6c5830", "#7a5a00": "#edd6a1",
        }
        for old, new in replacements.items():
            sheet = sheet.replace(old, new)
        # Foreground accents need more contrast than the solid action buttons.
        import re
        sheet = re.sub(r"(?<![-\w])color: " + re.escape(ACCENT), "color: #78c9ab", sheet)
    for role, color in (
        (QPalette.ColorRole.Window, "#171c1d" if dark else BG),
        (QPalette.ColorRole.Base, "#1c2122" if dark else SURFACE),
        (QPalette.ColorRole.WindowText, "#e6ebe9" if dark else TEXT),
        (QPalette.ColorRole.Text, "#e6ebe9" if dark else TEXT),
        (QPalette.ColorRole.ButtonText, "#e6ebe9" if dark else TEXT),
        (QPalette.ColorRole.Button, "#1c2122" if dark else SURFACE),
        (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(sheet)
