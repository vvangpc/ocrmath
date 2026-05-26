"""History tab: browse, search, copy, re-open and delete past recognitions."""
from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox,
)

from storage import Recognition, Storage
from styles import ACCENT
from ui_icons import icon


def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _truncate(s: str, n: int = 80) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


class HistoryRow(QWidget):
    """One row in the history list."""

    def __init__(self,
                 rec: Recognition,
                 thumb: QPixmap | None,
                 on_open: Callable[[Recognition], None],
                 on_delete: Callable[[Recognition], None]):
        super().__init__()
        self.rec = rec

        # Thumbnail
        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(96, 56)
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_lbl.setStyleSheet(
            "background:#fafafa; border:1px solid #e2e2e2; border-radius:4px;"
        )
        if thumb is not None and not thumb.isNull():
            scaled = thumb.scaled(
                94, 54,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb_lbl.setPixmap(scaled)
        else:
            thumb_lbl.setText("(无图)")
            thumb_lbl.setProperty("role", "muted")

        # Header line: timestamp + confidence
        header = QHBoxLayout()
        ts_lbl = QLabel(_fmt_ts(rec.created_at))
        ts_lbl.setStyleSheet("color:#666;")
        header.addWidget(ts_lbl)
        header.addStretch(1)
        if rec.confidence is not None:
            conf_lbl = QLabel(f"♻ {rec.confidence * 100:.0f}%")
            conf_lbl.setStyleSheet("color:#888;")
            header.addWidget(conf_lbl)

        # LaTeX preview line
        latex_text = rec.latex or rec.text or "(空)"
        latex_lbl = QLabel(_truncate(f"${latex_text}$" if rec.latex else latex_text))
        latex_lbl.setStyleSheet(
            "font-family: Consolas, monospace; color:#333; padding:2px 0;"
        )
        latex_lbl.setWordWrap(True)

        # Action buttons
        copy_btn = QPushButton("复制 LaTeX")
        copy_btn.setIcon(icon("copy"))
        copy_btn.setIconSize(QSize(15, 15))
        copy_btn.setFixedHeight(28)
        copy_btn.clicked.connect(self._copy)
        open_btn = QPushButton("打开")
        open_btn.setIcon(icon("open"))
        open_btn.setIconSize(QSize(15, 15))
        open_btn.setFixedHeight(28)
        open_btn.clicked.connect(lambda: on_open(rec))
        del_btn = QPushButton("删除")
        del_btn.setIcon(icon("trash"))
        del_btn.setIconSize(QSize(15, 15))
        del_btn.setFixedHeight(28)
        del_btn.clicked.connect(lambda: on_delete(rec))

        actions = QHBoxLayout()
        actions.addWidget(copy_btn)
        actions.addWidget(open_btn)
        actions.addWidget(del_btn)
        actions.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.setContentsMargins(0, 0, 0, 0)
        right.addLayout(header)
        right.addWidget(latex_lbl)
        right.addLayout(actions)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(12)
        outer.addWidget(thumb_lbl)
        outer.addLayout(right, 1)

    def _copy(self) -> None:
        latex = self.rec.latex or self.rec.text
        if not latex:
            return
        QGuiApplication.clipboard().setText(f"${latex}$")


class HistoryPanel(QWidget):
    """Browse / search / re-open recognitions stored locally."""

    def __init__(self,
                 storage: Storage,
                 on_open: Callable[[Recognition], None],
                 parent=None):
        super().__init__(parent)
        self._storage = storage
        self._on_open_cb = on_open

        # ---- top bar ----
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索 LaTeX 或文本…")
        self.search_edit.setClearButtonEnabled(True)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.refresh)
        self.search_edit.textChanged.connect(lambda _t: self._debounce.start())

        refresh_btn = QPushButton("刷新")
        refresh_btn.setIcon(icon("refresh", ACCENT))
        refresh_btn.setIconSize(QSize(16, 16))
        refresh_btn.clicked.connect(self.refresh)
        clear_btn = QPushButton("清空缓存")
        clear_btn.setIcon(icon("trash"))
        clear_btn.setIconSize(QSize(16, 16))
        clear_btn.clicked.connect(self._clear_all)

        self.summary = QLabel("")
        self.summary.setProperty("role", "muted")

        top = QHBoxLayout()
        top.addWidget(self.search_edit, 1)
        top.addWidget(refresh_btn)
        top.addWidget(clear_btn)

        # ---- list ----
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)

        # ---- layout ----
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addLayout(top)
        layout.addWidget(self.summary)
        layout.addWidget(self.list_widget, 1)

        self.refresh()

    # ---- public ------------------------------------------------------------

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        recs = self._storage.list_recent(query=query, limit=300)
        self.list_widget.clear()

        for rec in recs:
            png = self._storage.png_bytes(rec.image_sha256)
            thumb: QPixmap | None = None
            if png:
                img = QImage.fromData(png, "PNG")
                if not img.isNull():
                    thumb = QPixmap.fromImage(img)
            row = HistoryRow(rec, thumb,
                             on_open=self._on_open,
                             on_delete=self._on_delete)
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(row.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)

        stats = self._storage.stats()
        size_mb = stats["cache_bytes"] / 1024 / 1024
        self.summary.setText(
            f"共 {stats['count']} 条记录"
            f"{'（已过滤显示 ' + str(len(recs)) + ' 条）' if query else ''}    "
            f"缓存占用: {size_mb:.2f} MB"
        )

    # ---- internal ----------------------------------------------------------

    def _on_open(self, rec: Recognition) -> None:
        self._on_open_cb(rec)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        row = self.list_widget.itemWidget(item)
        if isinstance(row, HistoryRow):
            self._on_open_cb(row.rec)

    def _on_delete(self, rec: Recognition) -> None:
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除这条 {_fmt_ts(rec.created_at)} 的记录吗？",
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._storage.delete(rec.id)
            self.refresh()

    def _clear_all(self) -> None:
        stats = self._storage.stats()
        n = stats["count"]
        if n == 0:
            QMessageBox.information(self, "无记录", "缓存已经是空的。")
            return
        ret = QMessageBox.warning(
            self, "确认清空缓存",
            f"将永久删除 {n} 条记录和图像缓存,被删除的图像再次截屏会重新调用 API。继续?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._storage.clear_all()
        self.refresh()
