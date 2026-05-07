"""Centralized QSS stylesheet + palette helpers.

Apply via:
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(STYLESHEET)
"""
from __future__ import annotations

ACCENT = "#ff6a00"
ACCENT_HOVER = "#ff7a1c"
ACCENT_PRESS = "#e85e00"
TEXT = "#2b2b2b"
MUTED = "#777777"
BORDER = "#d8d8d8"
BORDER_FOCUS = ACCENT
BG = "#fafafa"
SURFACE = "#ffffff"
SURFACE_ALT = "#f3f3f3"
WARNING_BG = "#fff3cd"
WARNING_BORDER = "#ffeeba"
WARNING_TEXT = "#7a5a00"
SUCCESS = "#28a745"


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

/* ---- Buttons ---- */
QPushButton {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 24px;
}}
QPushButton:hover {{
    background-color: {SURFACE_ALT};
    border-color: #b8b8b8;
}}
QPushButton:pressed {{
    background-color: #e6e6e6;
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
    border: 1px solid {ACCENT_PRESS};
    font-weight: 600;
}}
QPushButton#accent:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#accent:pressed {{
    background-color: {ACCENT_PRESS};
}}
QPushButton#accent:disabled {{
    background-color: #ffc89a;
    border-color: #ffc89a;
    color: white;
}}

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QKeySequenceEdit {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    background: {SURFACE};
    selection-background-color: #ffd9b3;
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
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    width: 10px; height: 10px;
}}

/* ---- Tabs ---- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background: #ececec;
    border: 1px solid {BORDER};
    padding: 8px 22px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    color: #555;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    border-bottom-color: {SURFACE};
    color: {ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: #f5f5f5;
    color: {TEXT};
}}

/* ---- Group box ---- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
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
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: #f0f0f0;
    text-align: center;
    height: 22px;
    color: {TEXT};
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}

/* ---- Checkbox ---- */
QCheckBox {{
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid #b8b8b8;
    border-radius: 3px;
    background: {SURFACE};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}

/* ---- Menus (also affects tray menu) ---- */
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    padding: 4px;
    border-radius: 6px;
}}
QMenu::item {{
    padding: 6px 24px 6px 16px;
    border-radius: 4px;
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
    background: #c8c8c8;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #a8a8a8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #c8c8c8;
    border-radius: 5px;
    min-width: 30px;
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
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel[role="heading"] {{
    font-size: 16pt;
    font-weight: 600;
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
    border: 2px dashed #c0c0c0;
    border-radius: 8px;
    padding: 30px;
    color: {MUTED};
    background: {SURFACE_ALT};
    font-size: 11pt;
}}
QLabel[role="dropzone"][active="true"] {{
    border-color: {ACCENT};
    background: #fff7f0;
    color: {ACCENT};
}}
"""
