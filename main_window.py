"""Main window — tabbed UI hosting the snipping launcher, PDF panel, history."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from PyQt6.QtCore import QSize, Qt
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
from ui_icons import icon


def _format_synced(ts: float) -> str:
    if not ts:
        return "上次同步: —"
    try:
        dt = datetime.fromtimestamp(ts)
    except Exception:
        return "上次同步: —"
    return "上次同步: " + dt.strftime("%Y-%m-%d %H:%M")


def _start_of_today() -> float:
    now = datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _start_of_month() -> float:
    now = datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0,
                       microsecond=0).timestamp()


class MainWindow(QMainWindow):
    def __init__(self,
                 on_snip: Callable[[], None],
                 on_open_settings: Callable[[], None],
                 get_creds: Callable[[], dict | None],
                 storage: Storage,
                 on_open_history: Callable[[Recognition], None],
                 on_sync_now: Callable[[], None] | None = None):
        super().__init__()
        self.setWindowTitle("ocrmath - Mathpix OCR 工具")
        self.resize(700, 800)
        self._on_snip = on_snip
        self._on_open_settings = on_open_settings
        self._on_sync_now = on_sync_now
        self._storage = storage
        self._allow_close = False  # close button minimizes to tray instead

        self.snip_tab = self._build_snip_tab()
        self.pdf_panel = PdfPanel(get_creds,
                                  on_pages_processed=self._on_pages_processed)
        self.history_panel = HistoryPanel(storage, on_open=on_open_history)

        tabs = QTabWidget()
        tabs.setIconSize(QSize(18, 18))
        tabs.addTab(self.snip_tab, icon("snip", ACCENT), "  截屏识别  ")
        tabs.addTab(self.pdf_panel, icon("pdf", ACCENT), "  PDF 转换  ")
        tabs.addTab(self.history_panel, icon("history", ACCENT), "  历史记录  ")
        tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs = tabs

        wrap = QWidget()
        wlay = QVBoxLayout(wrap)
        wlay.setContentsMargins(12, 12, 12, 12)
        wlay.addWidget(tabs)
        self.setCentralWidget(wrap)

        self.refresh_hotkey_display()
        self.refresh_stats()

    def _build_snip_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("截屏公式识别")
        title.setProperty("role", "heading")
        layout.addWidget(title)

        subtitle = QLabel("用全局快捷键唤起截屏,识别公式并复制到剪贴板。"
                          "相同图像命中本地缓存。")
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
        change_btn.setIcon(icon("settings"))
        change_btn.setIconSize(QSize(16, 16))
        change_btn.setFixedWidth(80)
        change_btn.clicked.connect(lambda: self._on_open_settings())

        card_l.addWidget(hk_left)
        card_l.addWidget(self.hotkey_label, 1)
        card_l.addWidget(change_btn)
        layout.addWidget(card)

        snip_btn = QPushButton("立即截屏识别")
        snip_btn.setObjectName("accent")
        snip_btn.setIcon(icon("snip", "white"))
        snip_btn.setIconSize(QSize(22, 22))
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

        # Stats card
        layout.addWidget(self._build_stats_card())

        layout.addStretch(1)

        bottom = QHBoxLayout()
        settings_btn = QPushButton("设置")
        settings_btn.setIcon(icon("settings"))
        settings_btn.setIconSize(QSize(16, 16))
        settings_btn.clicked.connect(lambda: self._on_open_settings())
        bottom.addWidget(settings_btn)
        bottom.addStretch(1)

        self.cost_hint = QLabel("$0.002/张 · $0.005/页")
        self.cost_hint.setProperty("role", "muted")
        bottom.addWidget(self.cost_hint)
        layout.addLayout(bottom)
        return w

    def _build_stats_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", "true")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(10)

        head = QLabel("使用统计")
        head.setProperty("role", "subheading")
        outer.addWidget(head)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.stat_image_value = self._build_stat_value("0 次")
        self.stat_pdf_value = self._build_stat_value("0 页")
        self.stat_cost_value = self._build_stat_value("$0.000")
        tiles.addLayout(self._wrap_tile(self.stat_image_value, "截图识别"), 1)
        tiles.addLayout(self._wrap_tile(self.stat_pdf_value, "PDF 转换"), 1)
        tiles.addLayout(self._wrap_tile(self.stat_cost_value, "累计花费"), 1)
        outer.addLayout(tiles)

        self.period_summary_label = QLabel("本月: $0.000 (0 张 · 0 页)  ·  "
                                            "今日: $0.000 (0 张 · 0 页)")
        self.period_summary_label.setProperty("role", "muted")
        self.period_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.period_summary_label)

        actions = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.setIcon(icon("refresh"))
        refresh_btn.setIconSize(QSize(16, 16))
        refresh_btn.setFixedWidth(80)
        refresh_btn.clicked.connect(self.refresh_stats)
        actions.addWidget(refresh_btn)
        actions.addStretch(1)
        sync_btn = QPushButton("立即同步")
        sync_btn.setObjectName("accent")
        sync_btn.setIcon(icon("sync", "white"))
        sync_btn.setIconSize(QSize(16, 16))
        sync_btn.setFixedWidth(96)
        sync_btn.clicked.connect(self._handle_sync_clicked)
        self.sync_btn = sync_btn
        actions.addWidget(sync_btn)
        outer.addLayout(actions)

        self.last_synced_label = QLabel(_format_synced(0))
        self.last_synced_label.setProperty("role", "muted")
        outer.addWidget(self.last_synced_label)

        return card

    def _build_stat_value(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"font-size: 18pt; font-weight: 700; color: {ACCENT};")
        return lbl

    def _wrap_tile(self, value_label: QLabel, caption: str) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(value_label)
        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setStyleSheet(f"color: {MUTED}; font-size: 9pt;")
        col.addWidget(cap)
        return col

    # ---- public API --------------------------------------------------------

    def refresh_hotkey_display(self) -> None:
        hk = config.get_hotkey()
        self.hotkey_label.setText(config.keyboard_to_qt(hk))

    def refresh_stats(self) -> None:
        img_n, pdf_n = config.get_counters()
        ip = config.get_image_price()
        pp = config.get_pdf_price()
        cost = img_n * ip + pdf_n * pp
        self.stat_image_value.setText(f"{img_n} 次")
        self.stat_pdf_value.setText(f"{pdf_n} 页")
        self.stat_cost_value.setText(f"${cost:.3f}")
        self.cost_hint.setText(f"${ip:.3f}/张 · ${pp:.3f}/页")
        self.last_synced_label.setText(_format_synced(config.get_last_synced()))
        self._refresh_period_summary()
        try:
            self.pdf_panel.refresh_price_display()
        except Exception:
            pass

    def _refresh_period_summary(self) -> None:
        try:
            month = self._storage.usage_summary(_start_of_month())
            today = self._storage.usage_summary(_start_of_today())
        except Exception:
            return
        self.period_summary_label.setText(
            f"本月: ${month['total_cost']:.3f} "
            f"({month['image_count']} 张 · {month['pdf_pages']} 页)"
            f"  ·  "
            f"今日: ${today['total_cost']:.3f} "
            f"({today['image_count']} 张 · {today['pdf_pages']} 页)")

    def on_counters_changed(self) -> None:
        """Called by App after image OCR or PDF conversion bumps a counter."""
        self.refresh_stats()

    def set_sync_busy(self, busy: bool) -> None:
        try:
            self.sync_btn.setEnabled(not busy)
            self.sync_btn.setText("同步中…" if busy else "立即同步")
        except Exception:
            pass

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
        if self._tabs.widget(idx) is self.history_panel:
            self.history_panel.refresh()
        elif self._tabs.widget(idx) is self.snip_tab:
            self.refresh_stats()

    def _on_pages_processed(self, n: int) -> None:
        try:
            self._storage.log_usage("pdf", n, config.get_pdf_price())
        except Exception:
            pass
        self.refresh_stats()

    def _handle_sync_clicked(self) -> None:
        if self._on_sync_now:
            self._on_sync_now()
