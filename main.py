"""Application entry: tray icon, global hotkey, and signal wiring."""
from __future__ import annotations

import hashlib
import sys
import traceback

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QPainter, QPixmap, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox,
)

import config
from image_client import ImageOcrWorker
from main_window import MainWindow
from result_window import ResultWindow
from settings_dialog import SettingsDialog
from snipper import Snipper
from storage import Storage, Recognition
from styles import STYLESHEET, ACCENT


def _make_icon(color: str = ACCENT, alpha: int = 255) -> QIcon:
    """Generate a 'Σ' icon at runtime so we don't ship a binary asset.

    Pass a lighter alpha for the 'busy' frame.
    """
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    fill = QColor(color)
    fill.setAlpha(alpha)
    p.setBrush(fill)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    text_color = QColor("white")
    text_color.setAlpha(alpha)
    p.setPen(text_color)
    f = QFont()
    f.setBold(True)
    f.setPixelSize(40)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "Σ")
    p.end()
    return QIcon(pix)


class HotkeyBridge(QObject):
    """Thread-safe bridge from `keyboard` callback to Qt main thread."""
    triggered = pyqtSignal()


class App(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.icon = _make_icon(ACCENT, 255)
        self.icon_busy = _make_icon(ACCENT, 90)  # dim version for blink
        qapp.setWindowIcon(self.icon)
        qapp.setQuitOnLastWindowClosed(False)

        self._current_hotkey: str = ""
        self._pending_sha: str | None = None
        self._pending_png: bytes | None = None

        # Storage
        self.storage = Storage()

        # Widgets
        self.snipper = Snipper()
        self.result_win = ResultWindow(on_recapture=self.on_snip)
        self.main_win = MainWindow(
            on_snip=self.on_snip,
            on_open_settings=self.open_settings,
            get_creds=self._get_creds,
            storage=self.storage,
            on_open_history=self._on_history_open,
        )

        self.snipper.captured.connect(self._on_captured)
        self.snipper.cancelled.connect(lambda: None)
        self._worker: ImageOcrWorker | None = None

        # Tray + busy animation
        self.tray = self._build_tray()
        self._busy_state = False
        self._busy_timer = QTimer(self)
        self._busy_timer.timeout.connect(self._tick_busy)

        # Hotkey
        self.bridge = HotkeyBridge()
        self.bridge.triggered.connect(self.on_snip,
                                      Qt.ConnectionType.QueuedConnection)
        self._install_hotkey(config.get_hotkey())

        # First-run prompt
        if config.load() is None:
            self.open_settings(first_run=True)

    # ---- credentials -------------------------------------------------------

    def _get_creds(self) -> dict | None:
        return config.load()

    def open_settings(self, first_run: bool = False) -> None:
        dlg = SettingsDialog(self.main_win)
        if first_run:
            dlg.setWindowTitle("欢迎 - 请先设置 Mathpix API")
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _on_settings_changed(self, old_hotkey: str, new_hotkey: str) -> None:
        if new_hotkey != self._current_hotkey:
            self._uninstall_hotkey()
            self._install_hotkey(new_hotkey)
        self.main_win.refresh_hotkey_display()
        self._refresh_tray_text()

    # ---- tray --------------------------------------------------------------

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self.icon)
        menu = QMenu()

        self.act_snip = QAction("截屏识别", self)
        self.act_snip.triggered.connect(self.on_snip)
        menu.addAction(self.act_snip)

        act_main = QAction("打开主窗口…", self)
        act_main.triggered.connect(self._show_main)
        menu.addAction(act_main)

        menu.addSeparator()

        act_settings = QAction("设置…", self)
        act_settings.triggered.connect(lambda: self.open_settings())
        menu.addAction(act_settings)

        menu.addSeparator()

        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_quit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        return tray

    def _refresh_tray_text(self) -> None:
        hk_pretty = config.keyboard_to_qt(self._current_hotkey or config.get_hotkey())
        self.tray.setToolTip(f"ocrmath - 截屏 ({hk_pretty})")
        self.act_snip.setText(f"截屏识别  {hk_pretty}")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.on_snip()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_main()

    def _show_main(self) -> None:
        self.main_win.show()
        self.main_win.raise_()
        self.main_win.activateWindow()

    def _quit(self) -> None:
        self._uninstall_hotkey()
        self._stop_busy()
        self.tray.hide()
        try:
            self.storage.close()
        except Exception:
            pass
        self.main_win.request_real_close()
        self.qapp.quit()

    # ---- busy indicator ----------------------------------------------------

    def _start_busy(self) -> None:
        self._busy_state = False
        self._busy_timer.start(550)
        self.tray.setToolTip("ocrmath - 识别中…")

    def _tick_busy(self) -> None:
        self._busy_state = not self._busy_state
        self.tray.setIcon(self.icon_busy if self._busy_state else self.icon)

    def _stop_busy(self) -> None:
        self._busy_timer.stop()
        self.tray.setIcon(self.icon)
        self._refresh_tray_text()

    # ---- hotkey ------------------------------------------------------------

    def _install_hotkey(self, hotkey: str) -> None:
        try:
            import keyboard
        except ImportError:
            QMessageBox.warning(
                None, "缺少依赖",
                "未安装 keyboard 库，全局快捷键将不可用。\n"
                "请在命令行运行: pip install keyboard")
            self._current_hotkey = hotkey
            self._refresh_tray_text()
            return
        try:
            keyboard.add_hotkey(hotkey, lambda: self.bridge.triggered.emit())
            self._current_hotkey = hotkey
        except Exception as exc:
            QMessageBox.warning(
                None, "热键注册失败",
                f"无法注册全局快捷键 "
                f"{config.keyboard_to_qt(hotkey)}: {exc}\n"
                "可以从托盘菜单或主窗口手动触发。")
            self._current_hotkey = ""
        self._refresh_tray_text()

    def _uninstall_hotkey(self) -> None:
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self._current_hotkey = ""

    # ---- snipping ----------------------------------------------------------

    @pyqtSlot()
    def on_snip(self) -> None:
        if not config.load():
            self.open_settings()
            if not config.load():
                return
        self.snipper.start()

    def _on_captured(self, png: bytes) -> None:
        sha = hashlib.sha256(png).hexdigest()
        cached = self.storage.lookup(sha)
        if cached is not None:
            self.result_win.show_result(cached.result, from_cache=True)
            return
        creds = config.load()
        if not creds:
            self.open_settings()
            return
        self._pending_sha = sha
        self._pending_png = png
        self._start_busy()
        self._worker = ImageOcrWorker(png, creds["app_id"], creds["app_key"])
        self._worker.finished_ok.connect(self._on_ocr_ok)
        self._worker.failed.connect(self._on_ocr_failed)
        self._worker.start()

    def _on_ocr_ok(self, result: dict) -> None:
        self._stop_busy()
        # Persist to cache + history
        if self._pending_sha and self._pending_png:
            try:
                self.storage.insert(self._pending_sha, self._pending_png, result)
            except Exception as exc:
                # Don't block the user from seeing the result if cache write fails
                sys.stderr.write(f"cache write failed: {exc}\n")
        self.result_win.show_result(result, from_cache=False)
        self._pending_sha = None
        self._pending_png = None
        self._worker = None
        # Refresh history tab if it's been viewed
        try:
            self.main_win.refresh_history_panel()
        except Exception:
            pass

    def _on_ocr_failed(self, msg: str) -> None:
        self._stop_busy()
        QMessageBox.critical(None, "识别失败", msg)
        self._pending_sha = None
        self._pending_png = None
        self._worker = None

    def _on_history_open(self, rec: Recognition) -> None:
        self.result_win.show_result(rec.result, from_cache=True)


def _excepthook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    sys.stderr.write(text)
    try:
        QMessageBox.critical(None, "未捕获错误", text[-2000:])
    except Exception:
        pass


def main() -> int:
    sys.excepthook = _excepthook
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("ocrmath")
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(STYLESHEET)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "系统托盘不可用",
                             "当前桌面环境不支持系统托盘。")
        return 1

    _ = App(qapp)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
