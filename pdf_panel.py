"""PDF conversion tab: drag-drop a PDF, pick formats, watch progress."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QLineEdit, QFileDialog, QProgressBar, QPlainTextEdit,
    QMessageBox, QComboBox, QGroupBox,
)

import config
from pdf_client import PdfOptions, PdfWorker
from ui_icons import icon


def _count_pdf_pages(p: Path) -> int | None:
    """Return page count, or None if pypdf isn't installed / file unreadable."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        return len(PdfReader(str(p)).pages)
    except Exception:
        return None


class PdfPanel(QWidget):
    def __init__(self, get_creds: Callable[[], dict | None],
                 on_pages_processed: Callable[[int], None] | None = None,
                 parent=None):
        super().__init__(parent)
        self._get_creds = get_creds
        self._on_pages_processed = on_pages_processed
        self._pdf_path: Path | None = None
        self._page_count: int | None = None
        self._worker: PdfWorker | None = None
        self.setAcceptDrops(True)
        self._build_ui()

    def refresh_price_display(self) -> None:
        """Recompute the cost label after the user changes pricing."""
        if self._pdf_path:
            self._set_pdf(self._pdf_path)

    # ---- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        # Drop target — styled via QSS [role="dropzone"]
        self.drop_label = QLabel("📄  将 PDF 文件拖到这里\n或点击下方按钮选择")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setProperty("role", "dropzone")
        self.drop_label.setMinimumHeight(110)

        pick_btn = QPushButton("选择 PDF…")
        pick_btn.setIcon(icon("pdf"))
        pick_btn.setIconSize(QSize(16, 16))
        pick_btn.clicked.connect(self._pick_file)

        self.file_info = QLabel("尚未选择文件")
        self.file_info.setProperty("role", "muted")

        # Format checkboxes
        fmt_box = QGroupBox("输出格式")
        self.cb_mmd = QCheckBox("MMD (Mathpix Markdown，含 LaTeX)")
        self.cb_md = QCheckBox("MD (标准 Markdown)")
        self.cb_docx = QCheckBox("DOCX")
        self.cb_tex = QCheckBox("LaTeX zip (tex.zip)")
        self.cb_html = QCheckBox("HTML")
        self.cb_pdf_overlay = QCheckBox("带文字层 PDF")
        self.cb_mmd.setChecked(True)
        self.cb_md.setChecked(True)
        self.cb_docx.setChecked(True)
        fmt_grid = QHBoxLayout()
        col1 = QVBoxLayout()
        col1.addWidget(self.cb_mmd)
        col1.addWidget(self.cb_md)
        col1.addWidget(self.cb_docx)
        col2 = QVBoxLayout()
        col2.addWidget(self.cb_tex)
        col2.addWidget(self.cb_html)
        col2.addWidget(self.cb_pdf_overlay)
        col2.addStretch(1)
        fmt_grid.addLayout(col1)
        fmt_grid.addLayout(col2)
        fmt_grid.addStretch(1)
        QVBoxLayout(fmt_box).addLayout(fmt_grid)

        # Options group
        opts_box = QGroupBox("转换选项")
        opts_layout = QVBoxLayout(opts_box)

        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("默认与所选 PDF 同目录")
        out_browse = QPushButton("浏览…")
        out_browse.setIcon(icon("folder"))
        out_browse.setIconSize(QSize(16, 16))
        out_browse.clicked.connect(self._pick_out_dir)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("输出目录"))
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(out_browse)
        opts_layout.addLayout(out_row)

        self.range_combo = QComboBox()
        self.range_combo.addItems(["全部页面", "自定义范围"])
        self.range_combo.currentIndexChanged.connect(self._toggle_range)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("例如 2,4-6")
        self.range_edit.setEnabled(False)
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("页面范围"))
        range_row.addWidget(self.range_combo)
        range_row.addWidget(self.range_edit, 1)
        opts_layout.addLayout(range_row)

        self.cb_rm_spaces = QCheckBox("删除公式多余空格 (rm_spaces)")
        self.cb_rm_spaces.setChecked(True)
        opts_layout.addWidget(self.cb_rm_spaces)

        # Action row
        self.start_btn = QPushButton("开始转换")
        self.start_btn.setObjectName("accent")
        self.start_btn.setIcon(icon("play", "white"))
        self.start_btn.setIconSize(QSize(17, 17))
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setIcon(icon("close"))
        self.cancel_btn.setIconSize(QSize(16, 16))
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        self.cost_label = QLabel("预估成本: —")
        self.cost_label.setProperty("role", "muted")

        action_row = QHBoxLayout()
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.cancel_btn)
        action_row.addStretch(1)
        action_row.addWidget(self.cost_label)

        # Progress + log
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status_label = QLabel("")
        self.status_label.setProperty("role", "muted")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(160)
        self.log_view.setPlaceholderText("日志将显示在这里…")

        # Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(self.drop_label)
        top_row = QHBoxLayout()
        top_row.addWidget(pick_btn)
        top_row.addWidget(self.file_info, 1)
        layout.addLayout(top_row)
        layout.addWidget(fmt_box)
        layout.addWidget(opts_box)
        layout.addLayout(action_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        layout.addWidget(self.log_view)

    # ---- file selection ----------------------------------------------------

    def _pick_file(self) -> None:
        fn, _ = QFileDialog.getOpenFileName(
            self, "选择 PDF 文件", "",
            "PDF Files (*.pdf);;All files (*)")
        if fn:
            self._set_pdf(Path(fn))

    def _pick_out_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    def dragEnterEvent(self, evt: QDragEnterEvent) -> None:
        if evt.mimeData().hasUrls():
            for u in evt.mimeData().urls():
                if u.toLocalFile().lower().endswith(".pdf"):
                    self._set_dropzone_active(True)
                    evt.acceptProposedAction()
                    return
        evt.ignore()

    def dragLeaveEvent(self, _evt) -> None:
        self._set_dropzone_active(False)

    def dropEvent(self, evt: QDropEvent) -> None:
        self._set_dropzone_active(False)
        for u in evt.mimeData().urls():
            p = Path(u.toLocalFile())
            if p.suffix.lower() == ".pdf":
                self._set_pdf(p)
                evt.acceptProposedAction()
                return

    def _set_dropzone_active(self, on: bool) -> None:
        self.drop_label.setProperty("active", "true" if on else "false")
        # Force re-polish to apply the QSS rule
        self.drop_label.style().unpolish(self.drop_label)
        self.drop_label.style().polish(self.drop_label)

    def _set_pdf(self, p: Path) -> None:
        self._pdf_path = p
        self._page_count = _count_pdf_pages(p)
        # Default the output dir to the PDF's own folder. Always overwrite —
        # if the user wants a different folder they can edit after picking.
        self.out_edit.setText(str(p.parent))
        if self._page_count:
            self.file_info.setText(f"{p.name}  ({self._page_count} 页)")
            price = config.get_pdf_price()
            cost = self._page_count * price
            self.cost_label.setText(
                f"预估成本: ${cost:.3f}  "
                f"(${price:.3f}/页 × {self._page_count})"
            )
        else:
            self.file_info.setText(f"{p.name}  (页数未知，安装 pypdf 可显示)")
            self.cost_label.setText("预估成本: 未知")

    def _toggle_range(self, idx: int) -> None:
        self.range_edit.setEnabled(idx == 1)

    # ---- run ---------------------------------------------------------------

    def _selected_formats(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.cb_mmd.isChecked(): out.append("mmd")
        if self.cb_md.isChecked(): out.append("md")
        if self.cb_docx.isChecked(): out.append("docx")
        if self.cb_tex.isChecked(): out.append("tex.zip")
        if self.cb_html.isChecked(): out.append("html")
        if self.cb_pdf_overlay.isChecked(): out.append("pdf")
        return tuple(out)

    def _start(self) -> None:
        if self._worker is not None:
            return
        if not self._pdf_path or not self._pdf_path.exists():
            QMessageBox.warning(self, "缺少文件", "请先选择 PDF 文件。")
            return
        formats = self._selected_formats()
        if not formats:
            QMessageBox.warning(self, "未选格式", "请至少勾选一种输出格式。")
            return
        creds = self._get_creds()
        if not creds:
            QMessageBox.warning(self, "缺少 API Key",
                                "请先在设置中填入 Mathpix API Key。")
            return

        # Confirm cost for big files (threshold = 100 pages)
        if self._page_count and self._page_count > 100:
            est = self._page_count * config.get_pdf_price()
            ret = QMessageBox.question(
                self, "确认转换",
                f"该 PDF 共 {self._page_count} 页，预估消耗约 ${est:.3f}。继续？")
            if ret != QMessageBox.StandardButton.Yes:
                return

        page_ranges = None
        if self.range_combo.currentIndex() == 1:
            page_ranges = self.range_edit.text().strip() or None

        opts = PdfOptions(
            formats=formats,
            page_ranges=page_ranges,
            rm_spaces=self.cb_rm_spaces.isChecked(),
        )
        out_dir = Path(self.out_edit.text().strip() or ".")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.log_view.clear()
        self.progress.setValue(0)
        self.status_label.setText("启动…")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self._worker = PdfWorker(
            self._pdf_path, opts, out_dir,
            creds["app_id"], creds["app_key"], parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.status_label.setText("正在取消…")

    # ---- worker callbacks --------------------------------------------------

    def _on_progress(self, pct: int, text: str) -> None:
        self.progress.setValue(pct)
        self.status_label.setText(text)

    def _on_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def _on_done(self, paths: list) -> None:
        self.status_label.setText(f"完成，共 {len(paths)} 个文件")
        self.progress.setValue(100)
        if self._page_count:
            try:
                config.bump_pdf_pages(self._page_count)
            except Exception as exc:
                sys.stderr.write(f"counter bump failed: {exc}\n")
            if self._on_pages_processed:
                try:
                    self._on_pages_processed(self._page_count)
                except Exception:
                    pass
        QMessageBox.information(
            self, "完成",
            "转换完成：\n" + "\n".join(str(p) for p in paths))
        # Best-effort: open the output folder
        out = Path(self.out_edit.text().strip() or ".")
        try:
            os.startfile(out)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_failed(self, msg: str) -> None:
        self.status_label.setText("失败")
        self.log_view.appendPlainText(f"错误: {msg}")
        QMessageBox.critical(self, "转换失败", msg)

    def _cleanup_worker(self) -> None:
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._worker = None
