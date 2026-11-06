"""The two native windows, each hosting one page from web/."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QByteArray, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QCloseEvent, QColor, QDragEnterEvent, QDropEvent, QGuiApplication, QHideEvent,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

import config
from pdf_service import PdfService
from result_format import FloatModel
from storage import Storage
from ui_utils import UserError

PAGES = ("pdf", "history", "usage", "settings")
# Long enough to read "已复制到剪贴板" before the window leaves.
HIDE_AFTER_COPY_MS = 400


def web_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "web" if base else Path(__file__).resolve().parent / "web"


class _Page(QWebEnginePage):
    """Stays on our own files: a link inside recognized text can't navigate."""

    def acceptNavigationRequest(self, url: QUrl, _type, is_main_frame: bool) -> bool:
        if not is_main_frame:
            return False
        try:
            Path(url.toLocalFile()).resolve().relative_to(web_dir().resolve())
        except ValueError:
            return False
        return url.isLocalFile()

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:
        if level != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
            sys.stderr.write(f"{Path(source).name}:{line}: {message}\n")


def make_view(page_file: str, bridge, parent: QWidget) -> QWebEngineView:
    view = QWebEngineView(parent)
    page = _Page(view)
    page.setBackgroundColor(QColor("#ffffff"))
    view.setPage(page)
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    # Dropped files go to the window, which can read their real paths.
    view.setAcceptDrops(False)
    channel = QWebChannel(page)
    channel.registerObject("bridge", bridge)
    page.setWebChannel(channel)
    view.load(QUrl.fromLocalFile(str(web_dir() / page_file)))
    return view


def _fill(window: QWidget, view: QWebEngineView) -> None:
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)


def _restore_geometry(window: QWidget, key: str) -> bool:
    """Qt moves the window back on screen if that monitor is gone."""
    saved = config.get_ui_state().get(key)
    return isinstance(saved, str) and window.restoreGeometry(
        QByteArray.fromBase64(saved.encode("ascii")))


def _save_geometry(window: QWidget, key: str) -> None:
    try:
        config.update_ui_state(**{key: bytes(window.saveGeometry().toBase64()).decode("ascii")})
    except Exception as exc:
        sys.stderr.write(f"saving window position failed: {exc}\n")


class FloatWindow(QWidget):
    """Primary surface: capture, read and copy one result."""

    def __init__(self, bridge):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("OCRmath")
        self.setMinimumSize(380, 420)
        self.resize(440, 520)
        self.model = FloatModel()
        self._bridge = bridge
        self.view = make_view("float.html", bridge, self)
        _fill(self, self.view)
        self._positioned = _restore_geometry(self, "float_geometry")

    def hideEvent(self, event: QHideEvent) -> None:
        _save_geometry(self, "float_geometry")
        super().hideEvent(event)

    def hide_after_copy(self) -> None:
        QTimer.singleShot(HIDE_AFTER_COPY_MS, self.hide)

    def refresh(self) -> None:
        self._bridge.push("float", self.model.snapshot())

    def refresh_settings(self) -> None:
        self.refresh()

    def set_source(self, png: bytes | None) -> None:
        self.model.set_source(png)
        self.refresh()

    def set_task_count(self, count: int) -> None:
        self.model.task_count = count
        self.refresh()

    def set_busy(self, busy: bool) -> None:
        self.model.set_busy(busy)
        self.refresh()

    def show_ready(self, *, activate: bool = True) -> None:
        self.model.show_ready()
        self.refresh()
        if activate:
            self._present()

    def show_loading(self) -> None:
        self.model.show_loading()
        self.refresh()
        self._present()

    def show_error(self, message: str) -> None:
        self.model.show_error(message)
        self.refresh()
        self._present()

    def show_result(self, result: dict, from_cache: bool = False) -> None:
        self.model.show_result(result, from_cache)
        self.refresh()
        self._present()

    def _present(self) -> None:
        if not self._positioned:
            self._positioned = True
            screen = QGuiApplication.screenAt(self.pos()) or QGuiApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.resize(min(self.width(), geo.width()), min(self.height(), geo.height()))
                self.move(geo.center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()


class ToolWindow(QWidget):
    """PDF, history, usage and settings."""

    def __init__(self, bridge, storage: Storage,
                 get_creds: Callable[[], dict | None],
                 on_show_result: Callable[[], None] | None = None):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("OCRmath")
        self.setMinimumSize(600, 480)
        self.resize(720, 640)
        self.setAcceptDrops(True)
        self.page = "pdf"
        self._bridge = bridge
        self._storage = storage
        self._on_show_result = on_show_result
        self._allow_close = False  # the close button returns to the float window
        self.pdf_service = PdfService(get_creds, self._on_pages_processed, parent=self)
        self.pdf_service.changed.connect(self._push_pdf)
        self.pdf_service.activity_finished.connect(self.refresh_stats)
        self.view = make_view("tool.html", bridge, self)
        _fill(self, self.view)
        _restore_geometry(self, "tool_geometry")

    def hideEvent(self, event: QHideEvent) -> None:
        _save_geometry(self, "tool_geometry")
        super().hideEvent(event)

    def _push_pdf(self) -> None:
        self._bridge.push("pdf", self.pdf_service.state())

    def _on_pages_processed(self, pages: int, job_id: str | None = None) -> None:
        try:
            if job_id:
                self._storage.log_pdf_usage(job_id, pages, config.get_pdf_price())
            else:
                self._storage.log_usage("pdf", pages, config.get_pdf_price())
        except Exception as exc:
            sys.stderr.write(f"usage log failed: {exc}\n")
        self.refresh_stats()

    # ---- what the app asks of this window ----------------------------------

    def show_page(self, name: str) -> None:
        self.page = name if name in PAGES else "pdf"
        self._bridge.push("page", self.page)
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh_stats(self) -> None:
        self._bridge.push("usage")

    def on_counters_changed(self) -> None:
        self.refresh_stats()

    def refresh_history_panel(self) -> None:
        self._bridge.push("history")

    def refresh_hotkey_display(self) -> None:
        self._push_pdf()

    def set_sync_busy(self, busy: bool) -> None:
        self._bridge.push("sync_busy", busy)

    def notify(self, title: str, message: str) -> None:
        self._bridge.push("notice", {"title": title, "message": message})

    def request_real_close(self) -> None:
        self._allow_close = True
        self.close()

    # ---- events ------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
        if self._on_show_result:
            self._on_show_result()

    @staticmethod
    def _dropped_pdf(mime) -> str | None:
        for url in mime.urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._dropped_pdf(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._dropped_pdf(event.mimeData())
        if not path:
            return
        event.acceptProposedAction()
        self.show_page("pdf")
        try:
            self._bridge.push("pdf_selected", self.pdf_service.inspect(path))
        except UserError as exc:
            self.notify("无法打开文件", str(exc))
