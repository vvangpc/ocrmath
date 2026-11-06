"""Tool window opened from the compact screenshot surface."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
)

import config
from history_panel import HistoryPanel
from pdf_panel import PdfPanel
from storage import Recognition, Storage
from styles import ACCENT, MUTED
from ui_icons import icon
from ui_utils import format_cost, format_synced, format_unit_price
from llm_store import LlmStore


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
                 on_sync_now: Callable[[], None] | None = None,
                 on_show_result: Callable[[], None] | None = None):
        super().__init__()
        self.setWindowTitle("OCRmath · 文档与用量")
        self.resize(760, 700)
        self.setMinimumSize(600, 500)
        self._on_snip = on_snip
        self._on_open_settings = on_open_settings
        self._on_sync_now = on_sync_now
        self._on_show_result = on_show_result
        self._storage = storage
        self._llm_store = LlmStore()
        self._allow_close = False  # close button minimizes to tray instead

        self.snip_tab = self._build_usage_page()
        self.pdf_panel = PdfPanel(get_creds,
                                  on_pages_processed=self._on_pages_processed)
        self.pdf_panel.activity_finished.connect(self.refresh_stats)
        self.history_panel = HistoryPanel(storage, on_open=on_open_history)

        # Scroll wrapper keeps the taller PDF panel from dictating the
        # window's minimum size — the compact snip tab sets it instead.
        pdf_scroll = QScrollArea()
        pdf_scroll.setWidget(self.pdf_panel)
        pdf_scroll.setWidgetResizable(True)
        pdf_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        tabs = QTabWidget()
        tabs.setIconSize(QSize(18, 18))
        tabs.addTab(pdf_scroll, "PDF 转换")
        tabs.addTab(self.history_panel, "识别历史")
        tabs.addTab(self.snip_tab, "Mathpix 用量")
        tabs.addTab(self._build_token_tab(), "模型 Token")
        tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs = tabs

        wrap = QWidget()
        wlay = QVBoxLayout(wrap)
        wlay.setContentsMargins(18, 16, 18, 16)
        header = QHBoxLayout()
        title = QLabel("OCRmath")
        title.setObjectName("brandName")
        header.addWidget(title)
        header.addStretch()
        back = QPushButton("返回浮窗")
        back.setProperty("flat", True)
        back.clicked.connect(self._return_to_result)
        header.addWidget(back)
        settings = QPushButton("设置")
        settings.setProperty("flat", True)
        settings.clicked.connect(self._on_open_settings)
        header.addWidget(settings)
        wlay.addLayout(header)
        wlay.addWidget(tabs)
        self.setCentralWidget(wrap)

        self.refresh_hotkey_display()
        self.refresh_stats()

    def _build_usage_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(self._build_stats_card())
        self.cost_hint = QLabel("")
        self.cost_hint.setProperty("role", "muted")
        layout.addWidget(self.cost_hint)
        note = QLabel("本月与今日费用来自本机用量记录；多设备累计按当前单价估算。")
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)
        layout.addStretch(1)
        return w

    def _build_stats_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", "true")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(10)

        head = QLabel("多设备累计")
        head.setProperty("role", "subheading")
        outer.addWidget(head)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.stat_image_value = self._build_stat_value("0 次")
        self.stat_pdf_value = self._build_stat_value("0 页")
        self.stat_cost_value = self._build_stat_value("")
        tiles.addLayout(self._wrap_tile(self.stat_image_value, "截图识别"), 1)
        tiles.addLayout(self._wrap_tile(self.stat_pdf_value, "PDF 转换"), 1)
        tiles.addLayout(self._wrap_tile(self.stat_cost_value, "累计估算"), 1)
        outer.addLayout(tiles)

        self.period_summary_label = QLabel("")
        self.period_summary_label.setProperty("role", "muted")
        self.period_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.period_summary_label.setWordWrap(True)
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

        self.last_synced_label = QLabel(format_synced(0))
        self.last_synced_label.setProperty("role", "muted")
        outer.addWidget(self.last_synced_label)

        return card

    def _build_token_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.token_period = QComboBox()
        self.token_period.addItems(["本月", "今日", "全部"])
        self.token_period.currentIndexChanged.connect(self._refresh_tokens)
        layout.addWidget(self.token_period)
        self.token_table = QTableWidget(0, 5)
        self.token_table.setHorizontalHeaderLabels(["模型", "请求", "输入", "缓存输入", "输出"])
        self.token_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.token_table.horizontalHeader().setMinimumSectionSize(60)
        self.token_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.token_table.verticalHeader().hide()
        self.token_table.verticalHeader().setDefaultSectionSize(34)
        self.token_table.setShowGrid(False)
        self.token_table.setAlternatingRowColors(True)
        self.token_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.token_table)
        self.token_note = QLabel("本机 API 返回的用量；缓存输入已包含在输入中。")
        self.token_note.setWordWrap(True)
        layout.addWidget(self.token_note)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._refresh_tokens)
        layout.addWidget(refresh)
        return page

    def _refresh_tokens(self):
        since = [_start_of_month(), _start_of_today(), 0][self.token_period.currentIndex()]
        rows = self._llm_store.summary(since)
        self.token_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, key in enumerate(("model", "requests", "input_tokens", "cached_tokens", "output_tokens")):
                item = QTableWidgetItem(str(row[key]))
                if j:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.token_table.setItem(i, j, item)
        unknown = sum(r["unknown"] for r in rows)
        self.token_note.setText("本机 API 返回的用量；缓存输入已包含在输入中。"
                               + (f"有 {unknown} 次响应未返回完整用量。" if unknown else ""))

    def _build_stat_value(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setProperty("role", "statValue")
        return lbl

    def _wrap_tile(self, value_label: QLabel, caption: str) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(value_label)
        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setProperty("role", "muted")
        cap.setStyleSheet("font-size: 9pt;")
        col.addWidget(cap)
        return col

    # ---- public API --------------------------------------------------------

    def refresh_hotkey_display(self) -> None:
        if not self.pdf_panel.is_busy():
            self.pdf_panel.refresh_price_display()

    def refresh_stats(self) -> None:
        self._refresh_tokens()
        img_n, pdf_n = config.get_counters()
        ip = config.get_image_price()
        pp = config.get_pdf_price()
        cost = img_n * ip + pdf_n * pp
        self.stat_image_value.setText(f"{img_n} 次")
        self.stat_pdf_value.setText(f"{pdf_n} 页")
        self.stat_cost_value.setText(format_cost(cost))
        self.cost_hint.setText(
            f"{format_unit_price(ip, cny=False)}/张 · "
            f"{format_unit_price(pp, cny=False)}/页")
        self.last_synced_label.setText(format_synced(config.get_last_synced()))
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
            f"本月: {format_cost(month['total_cost'])} "
            f"({month['image_count']} 张 · {month['pdf_pages']} 页)"
            f"  ·  "
            f"今日: {format_cost(today['total_cost'])} "
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
        """Storage changed: the panel rebuilds now if visible, else when next
        shown."""
        try:
            self.history_panel.invalidate()
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
            if self._on_show_result:
                self._on_show_result()

    def show_page(self, name: str) -> None:
        self._tabs.setCurrentIndex({"pdf": 0, "history": 1, "usage": 2, "tokens": 3}[name])
        self.refresh_stats()
        self.show()
        self.raise_()
        self.activateWindow()

    def _return_to_result(self) -> None:
        self.hide()
        if self._on_show_result:
            self._on_show_result()

    # ---- internal ----------------------------------------------------------

    def _on_tab_changed(self, idx: int) -> None:
        # History reloads itself in showEvent when its data changed.
        if self._tabs.widget(idx) is self.snip_tab:
            self.refresh_stats()
        self._refresh_tokens()

    def _on_pages_processed(self, n: int, job_id: str | None = None) -> None:
        try:
            if job_id:
                self._storage.log_pdf_usage(job_id, n, config.get_pdf_price())
            else:
                self._storage.log_usage("pdf", n, config.get_pdf_price())
        except Exception:
            pass
        self.refresh_stats()

    def _handle_sync_clicked(self) -> None:
        if self._on_sync_now:
            self._on_sync_now()
