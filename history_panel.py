"""History tab: browse, search, copy, re-open and delete past recognitions."""
from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QGuiApplication, QShowEvent
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


class _ThumbLoader(QThread):
    """Reads and decodes cached PNGs off the UI thread.

    Emits one thumbnail_ready per sha (a null QImage marks a missing file).
    The generation number lets the panel drop results from a superseded
    refresh."""

    thumbnail_ready = pyqtSignal(int, str, QImage)  # generation, sha, image

    def __init__(self, storage: Storage, shas: list[str], generation: int,
                 parent=None):
        super().__init__(parent)
        self._storage = storage
        self._shas = shas
        self._generation = generation

    def run(self) -> None:
        for sha in self._shas:
            if self.isInterruptionRequested():
                return
            png = self._storage.png_bytes(sha)
            img = QImage.fromData(png, "PNG") if png else QImage()
            self.thumbnail_ready.emit(self._generation, sha, img)


class HistoryRow(QWidget):
    """One row in the history list."""

    def __init__(self,
                 rec: Recognition,
                 on_open: Callable[[Recognition], None],
                 on_delete: Callable[[Recognition], None]):
        super().__init__()
        self.rec = rec

        # Thumbnail placeholder; the real image arrives via set_thumbnail()
        # once the background loader has decoded it.
        thumb_lbl = QLabel("…")
        thumb_lbl.setFixedSize(96, 56)
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_lbl.setStyleSheet(
            "background:#fafafa; border:1px solid #e2e2e2; border-radius:4px;"
        )
        thumb_lbl.setProperty("role", "muted")
        self._thumb_lbl = thumb_lbl

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

    def set_thumbnail(self, thumb: QPixmap) -> None:
        if thumb.isNull():
            self._thumb_lbl.setText("(无图)")
            return
        scaled = thumb.scaled(
            94, 54,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumb_lbl.setText("")
        self._thumb_lbl.setPixmap(scaled)

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
        self._generation = 0
        self._thumb_loader: _ThumbLoader | None = None
        self._rows_by_sha: dict[str, HistoryRow] = {}

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

    # ---- public ------------------------------------------------------------

    def showEvent(self, evt: QShowEvent) -> None:
        # The panel lives inside a QTabWidget: it is shown each time its tab
        # becomes current, so this doubles as the tab-switch refresh. It also
        # means the panel loads nothing at app startup.
        super().showEvent(evt)
        self.refresh()

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        recs = self._storage.list_recent(query=query, limit=300)
        self.list_widget.clear()
        self._rows_by_sha.clear()
        self._generation += 1
        if self._thumb_loader is not None and self._thumb_loader.isRunning():
            self._thumb_loader.requestInterruption()

        for rec in recs:
            row = HistoryRow(rec,
                             on_open=self._on_open,
                             on_delete=self._on_delete)
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(row.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
            self._rows_by_sha[rec.image_sha256] = row

        if recs:
            loader = _ThumbLoader(self._storage,
                                  [r.image_sha256 for r in recs],
                                  self._generation, self)
            loader.thumbnail_ready.connect(self._on_thumbnail_ready)
            # Drop our reference before deleteLater destroys the C++ object,
            # otherwise the next refresh calls isRunning() on a dead wrapper.
            loader.finished.connect(lambda: self._on_loader_finished(loader))
            self._thumb_loader = loader
            loader.start()

        stats = self._storage.stats()
        size_mb = stats["cache_bytes"] / 1024 / 1024
        self.summary.setText(
            f"共 {stats['count']} 条记录"
            f"{'（已过滤显示 ' + str(len(recs)) + ' 条）' if query else ''}    "
            f"缓存占用: {size_mb:.2f} MB"
        )

    # ---- internal ----------------------------------------------------------

    def _on_loader_finished(self, loader: _ThumbLoader) -> None:
        if self._thumb_loader is loader:
            self._thumb_loader = None
        loader.deleteLater()

    def _on_thumbnail_ready(self, generation: int, sha: str,
                            img: QImage) -> None:
        if generation != self._generation:
            return
        row = self._rows_by_sha.get(sha)
        if row is not None:
            row.set_thumbnail(QPixmap.fromImage(img))

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
            f"将永久删除 {n} 条记录和图像缓存（费用统计保留）。继续?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._storage.clear_all()
        self.refresh()
