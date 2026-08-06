"""Application entry: tray icon, global hotkey, and signal wiring."""
from __future__ import annotations

import hashlib
import os
import sys
import traceback

from PyQt6.QtCore import Qt, QObject, QTimer, QEventLoop, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox,
)

import config
import webdav
from image_client import ImageOcrWorker
from main_window import MainWindow
from result_window import ResultWindow
from settings_dialog import SettingsDialog
from snipper import Snipper
from storage import Storage, Recognition
from styles import STYLESHEET, ACCENT
from ui_icons import app_icon, icon


class HotkeyBridge(QObject):
    """Thread-safe bridge from `keyboard` callback to Qt main thread."""
    triggered = pyqtSignal()


class App(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.icon = app_icon()
        self.icon_busy = app_icon(busy=True)
        qapp.setWindowIcon(self.icon)
        qapp.setQuitOnLastWindowClosed(False)

        self._current_hotkey: str = ""
        self._pending_sha: str | None = None
        self._pending_png: bytes | None = None
        self._sync_worker: webdav.WebDavSyncWorker | None = None
        self._exit_sync_worker: webdav.WebDavSyncWorker | None = None

        self._periodic_timer = QTimer(self)
        self._periodic_timer.setSingleShot(False)
        self._periodic_timer.timeout.connect(self._on_periodic_tick)

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
            on_sync_now=self._sync_now_manual,
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
            self.open_settings()

        # Startup auto-sync (best-effort, after UI is up)
        self._reconfigure_periodic_timer()
        QTimer.singleShot(1000, self._maybe_backfill_usage)
        QTimer.singleShot(2000, self._kickoff_startup_sync)
        QTimer.singleShot(3000, self._kickoff_cache_purge)

    # ---- credentials -------------------------------------------------------

    def _get_creds(self) -> dict | None:
        return config.load()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.main_win, on_purge_now=self._purge_now)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _purge_now(self, days: int) -> int:
        """Synchronous purge invoked from the settings dialog."""
        n = self.storage.purge_older_than(days)
        self.storage.purge_old_usage(days)
        try:
            self.main_win.refresh_history_panel()
            self.main_win.refresh_stats()
        except Exception:
            pass
        return n

    def _on_settings_changed(self, old_hotkey: str, new_hotkey: str) -> None:
        if new_hotkey != self._current_hotkey:
            self._uninstall_hotkey()
            self._install_hotkey(new_hotkey)
        self.main_win.refresh_hotkey_display()
        self.main_win.refresh_stats()
        self._refresh_tray_text()
        self._reconfigure_periodic_timer()

    # ---- tray --------------------------------------------------------------

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self.icon)
        menu = QMenu()

        self.act_snip = QAction("截屏识别", self)
        self.act_snip.setIcon(icon("snip", ACCENT))
        self.act_snip.triggered.connect(self.on_snip)
        menu.addAction(self.act_snip)

        act_main = QAction("打开主窗口…", self)
        act_main.setIcon(icon("open"))
        act_main.triggered.connect(self._show_main)
        menu.addAction(act_main)

        menu.addSeparator()

        act_settings = QAction("设置…", self)
        act_settings.setIcon(icon("settings"))
        act_settings.triggered.connect(lambda: self.open_settings())
        menu.addAction(act_settings)

        menu.addSeparator()

        act_quit = QAction("退出", self)
        act_quit.setIcon(icon("close"))
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
        try:
            self._periodic_timer.stop()
        except Exception:
            pass
        # Best-effort exit sync (max 5s).
        try:
            self._run_exit_sync_blocking(timeout_ms=5000)
        except Exception as exc:
            sys.stderr.write(f"exit sync failed: {exc}\n")
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
                f"{config.keyboard_to_qt(hotkey)}: {exc}")
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
        # Single-flight: _pending_sha/_pending_png are shared state, so a
        # second capture while one is recognizing must be ignored.
        if self._worker is not None:
            return
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
        # Drop our reference only after the thread has fully wound down —
        # clearing it inside a result slot can GC a still-running QThread.
        self._worker.finished.connect(self._clear_image_worker)
        self._worker.start()

    def _clear_image_worker(self) -> None:
        self._worker = None

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
        # Bill the API call: cache hits exit before we get here.
        try:
            config.bump_image_count(1)
        except Exception as exc:
            sys.stderr.write(f"counter bump failed: {exc}\n")
        try:
            self.storage.log_usage("image", 1, config.get_image_price())
        except Exception as exc:
            sys.stderr.write(f"usage log failed: {exc}\n")
        try:
            self.main_win.on_counters_changed()
        except Exception:
            pass
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

    def _on_history_open(self, rec: Recognition) -> None:
        self.result_win.show_result(rec.result, from_cache=True)

    # ---- usage backfill ----------------------------------------------------

    def _maybe_backfill_usage(self) -> None:
        """One-shot migration: copy historical recognitions into usage table."""
        if config.is_usage_backfilled():
            return
        try:
            n = self.storage.backfill_image_usage(config.get_image_price())
            config.mark_usage_backfilled()
            if n:
                sys.stderr.write(
                    f"backfilled {n} historical image usage events\n")
                try:
                    self.main_win.refresh_stats()
                except Exception:
                    pass
        except Exception as exc:
            sys.stderr.write(f"usage backfill failed: {exc}\n")

    # ---- cache retention ---------------------------------------------------

    def _kickoff_cache_purge(self) -> None:
        days = config.get_cache_retention()
        if days <= 0:
            return
        try:
            n_recs = self.storage.purge_older_than(days)
            n_usage = self.storage.purge_old_usage(days)
            if (n_recs or n_usage):
                sys.stderr.write(
                    f"cache purge: removed {n_recs} recognitions + "
                    f"{n_usage} usage rows older than {days} days\n")
                try:
                    self.main_win.refresh_history_panel()
                    self.main_win.refresh_stats()
                except Exception:
                    pass
        except Exception as exc:
            sys.stderr.write(f"cache purge failed: {exc}\n")

    # ---- WebDAV sync -------------------------------------------------------

    def _webdav_configured(self) -> bool:
        wd = config.get_webdav()
        return bool(wd["url"] and wd["user"])

    def _reconfigure_periodic_timer(self) -> None:
        """(Re)start or stop the periodic-sync QTimer based on settings.
        Called at app startup and whenever settings are saved."""
        wd = config.get_webdav()
        interval_min = int(wd.get("interval") or 0)
        if interval_min > 0 and self._webdav_configured():
            self._periodic_timer.start(interval_min * 60_000)
        else:
            self._periodic_timer.stop()

    def _on_periodic_tick(self) -> None:
        self._sync_in_background()

    def _kickoff_startup_sync(self) -> None:
        if self._webdav_configured():
            self._sync_in_background()

    def _sync_in_background(self) -> None:
        if not self._webdav_configured():
            return
        if self._sync_worker is not None:
            return
        self._sync_worker = webdav.start_worker(
            on_ok=self._on_sync_ok, on_fail=self._on_sync_fail,
            on_finished=self._sync_cleanup)

    def _run_exit_sync_blocking(self, timeout_ms: int = 5000) -> None:
        """Block UI for up to timeout_ms while a final sync completes."""
        if not self._webdav_configured():
            return
        loop = QEventLoop()
        finish_timer = QTimer()
        finish_timer.setSingleShot(True)
        finish_timer.timeout.connect(loop.quit)

        # Keep a reference on self: if the sync outlives the timeout, letting
        # the QThread be garbage-collected while still running aborts the app
        # ("QThread: Destroyed while thread is still running").
        finish_timer.start(timeout_ms)
        worker = webdav.start_worker(
            on_ok=lambda *_a: loop.quit(),
            on_fail=lambda msg: (
                sys.stderr.write(f"exit sync failed: {msg}\n"), loop.quit()))
        self._exit_sync_worker = worker
        loop.exec()
        # Best-effort: give the worker a brief grace window to land its result.
        worker.wait(500)

    def _sync_now_manual(self) -> None:
        wd = config.get_webdav()
        if not wd["url"] or not wd["user"]:
            QMessageBox.information(
                None, "WebDAV 未配置",
                "请先在设置中填写 WebDAV 服务器 URL 和用户名。")
            return
        if self._sync_worker is not None:
            return
        self.main_win.set_sync_busy(True)
        self._sync_worker = webdav.start_worker(
            on_ok=self._on_sync_ok, on_fail=self._on_sync_fail_manual,
            on_finished=self._sync_cleanup)

    def _on_sync_ok(self, _ts: float) -> None:
        try:
            self.main_win.refresh_stats()
        except Exception:
            pass

    def _on_sync_fail(self, msg: str) -> None:
        sys.stderr.write(f"webdav auto-sync failed: {msg}\n")

    def _on_sync_fail_manual(self, msg: str) -> None:
        QMessageBox.warning(None, "同步失败", msg)

    def _sync_cleanup(self) -> None:
        try:
            self.main_win.set_sync_busy(False)
        except Exception:
            pass
        self._sync_worker = None


def _excepthook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        sys.stderr.write(text)
    except Exception:
        pass
    try:
        QMessageBox.critical(None, "未捕获错误", text[-2000:])
    except Exception:
        pass


def main() -> int:
    # Windowed (console=False) PyInstaller builds run with the std streams set
    # to None; every sys.stderr.write() in the codebase would AttributeError.
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    sys.excepthook = _excepthook
    # QtWebEngine requires this before QApplication is constructed.
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
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
