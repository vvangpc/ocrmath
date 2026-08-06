"""Centralized QSS stylesheet + palette helpers.

Apply via:
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(STYLESHEET)
"""
from __future__ import annotations

ACCENT = "#ff6a00"
ACCENT_HOVER = "#ff812f"
ACCENT_PRESS = "#de5700"
TEXT = "#202124"
MUTED = "#6f7782"
BORDER = "#dde3ea"
BORDER_FOCUS = ACCENT
BG = "#f6f8fb"
SURFACE = "#ffffff"
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
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #ff8a2a, stop:1 {ACCENT_PRESS});
    color: white;
    border: 1px solid #d95300;
    font-weight: 600;
}}
QPushButton#accent:hover {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #ff9845, stop:1 {ACCENT});
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
    border-radius: 7px;
    padding: 6px 9px;
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
    width: 24px;
}}
QComboBox::down-arrow {{
    width: 10px; height: 10px;
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
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                      stop:0 #ff8a2a, stop:1 {ACCENT_PRESS});
    border-radius: 6px;
}}

/* ---- Checkbox ---- */
QCheckBox {{
    spacing: 7px;
}}
QCheckBox::indicator {{
    width: 17px; height: 17px;
    border: 1px solid #b8c2cc;
    border-radius: 5px;
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
    background: #fff2e8;
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
    padding: 30px;
    color: {MUTED};
    background: #f8fafc;
    font-size: 11pt;
}}
QLabel[role="dropzone"][active="true"] {{
    border-color: {ACCENT};
    background: #fff7f0;
    color: {ACCENT};
}}
"""
