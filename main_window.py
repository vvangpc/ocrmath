"""Main window — tabbed UI hosting the snipping launcher, PDF panel, history."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame,
)

import config
from history_panel import HistoryPanel
from pdf_panel import PdfPanel
from storage import Recognition, Storage
from styles import ACCENT, MUTED


class MainWindow(QMainWindow):
    def __init__(self,
                 on_snip: Callable[[], None],
                 on_open_settings: Callable[[], None],
                 get_creds: Callable[[], dict | None],
                 storage: Storage,
                 on_open_history: Callable[[Recognition], None]):
        super().__init__()
        self.setWindowTitle("ocrmath - Mathpix OCR 工具")
        self.resize(700, 800)
        self._on_snip = on_snip
        self._on_open_settings = on_open_settings
        self._allow_close = False  # close button minimizes to tray instead

        self.snip_tab = self._build_snip_tab()
        self.history_panel = HistoryPanel(storage, on_open=on_open_history)

        tabs = QTabWidget()
        tabs.addTab(self.snip_tab, "  截屏识别  ")
        tabs.addTab(PdfPanel(get_creds), "  PDF 转换  ")
        tabs.addTab(self.history_panel, "  历史记录  ")
        tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs = tabs

        wrap = QWidget()
        wlay = QVBoxLayout(wrap)
        wlay.setContentsMargins(12, 12, 12, 12)
        wlay.addWidget(tabs)
        self.setCentralWidget(wrap)

        self.refresh_hotkey_display()

    def _build_snip_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("截屏公式识别")
        title.setProperty("role", "heading")
        layout.addWidget(title)

        subtitle = QLabel("用全局快捷键唤起截屏，自动识别公式并复制到剪贴板。"
                          "相同图像会命中本地缓存，零网络零费用。")
        subtitle.setProperty("role", "muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Hotkey card
        card = QFrame()
        card.setProperty("card", "true")
        card_l = QHBoxLayout(card)
        card_l.setContentsMargins(16, 12, 16, 12)

        hk_left = QLabel("当前快捷键")
        hk_left.setProperty("role", "muted")
        self.hotkey_label = QLabel("Ctrl+Alt+M")
        self.hotkey_label.setStyleSheet(
            f"font-family: 'Consolas', monospace; font-size: 13pt;"
            f"font-weight: 600; color: {ACCENT};"
        )
        change_btn = QPushButton("修改…")
        change_btn.setFixedWidth(80)
        change_btn.clicked.connect(lambda: self._on_open_settings())

        card_l.addWidget(hk_left)
        card_l.addWidget(self.hotkey_label, 1)
        card_l.addWidget(change_btn)
        layout.addWidget(card)

        snip_btn = QPushButton("立即截屏识别")
        snip_btn.setObjectName("accent")
        snip_btn.setMinimumHeight(48)
        snip_btn.setStyleSheet("font-size: 12pt;")
        snip_btn.clicked.connect(lambda: self._on_snip())
        layout.addWidget(snip_btn)

        # Steps card
        steps = QFrame()
        steps.setProperty("card", "true")
        steps_l = QVBoxLayout(steps)
        steps_l.setContentsMargins(16, 12, 16, 12)
        steps_l.setSpacing(6)
        head = QLabel("使用步骤")
        head.setProperty("role", "subheading")
        steps_l.addWidget(head)
        for line in [
            "1. 按下全局快捷键（或点击上方按钮）",
            "2. 屏幕变暗后用鼠标拖拽圈选公式区域",
            "3. 等待识别（约 1-2 秒），结果窗口弹出",
            "4. 点击行内 / 独立 LaTeX 旁的「复制」即可粘贴",
        ]:
            lbl = QLabel(line)
            lbl.setStyleSheet(f"color: {MUTED};")
            steps_l.addWidget(lbl)
        layout.addWidget(steps)

        layout.addStretch(1)

        bottom = QHBoxLayout()
        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(lambda: self._on_open_settings())
        bottom.addWidget(settings_btn)
        bottom.addStretch(1)

        cost = QLabel("成本: 截屏 ≈ $0.002/张 ・ PDF ≈ $0.005/页")
        cost.setProperty("role", "muted")
        bottom.addWidget(cost)
        layout.addLayout(bottom)
        return w

    # ---- public API --------------------------------------------------------

    def refresh_hotkey_display(self) -> None:
        hk = config.get_hotkey()
        self.hotkey_label.setText(config.keyboard_to_qt(hk))

    def refresh_history_panel(self) -> None:
        try:
            self.history_panel.refresh()
        except Exception:
            pass

    def request_real_close(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, evt: QCloseEvent) -> None:
        if self._allow_close:
            evt.accept()
        else:
            evt.ignore()
            self.hide()

    # ---- internal ----------------------------------------------------------

    def _on_tab_changed(self, idx: int) -> None:
        # Refresh history when user switches to that tab
        if self._tabs.widget(idx) is self.history_panel:
            self.history_panel.refresh()
