"""Settings dialog: API credentials + global hotkey + pricing + WebDAV sync."""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QMessageBox, QGroupBox, QKeySequenceEdit,
    QSpinBox, QInputDialog, QScrollArea, QWidget,
)

import config
import webdav


def _format_synced(ts: float) -> str:
    if not ts:
        return "上次同步: 从未"
    try:
        return "上次同步: " + datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "上次同步: —"


class SettingsDialog(QDialog):
    """Dialog for editing API credentials, hotkey, prices, and WebDAV.

    Emits `settings_changed(old_hotkey, new_hotkey)` on accept so the main
    app can re-register the global shortcut.
    """

    settings_changed = pyqtSignal(str, str)  # (old_hotkey, new_hotkey)

    def __init__(self, parent=None, on_purge_now=None):
        super().__init__(parent)
        self.setWindowTitle("ocrmath 设置")
        self.setMinimumWidth(540)
        self.resize(560, 720)

        all_settings = config.load_all()
        self._old_hotkey = all_settings.get("hotkey") or config.DEFAULT_HOTKEY
        wd = config.get_webdav()
        self._sync_worker: webdav.WebDavSyncWorker | None = None
        # `on_purge_now(days) -> int` returns the count of recognitions purged.
        self._on_purge_now = on_purge_now

        # ---- Header ----
        header = QLabel("应用设置")
        header.setProperty("role", "heading")

        intro = QLabel(
            "还没有 API Key？请到 "
            "<a href='https://accounts.mathpix.com/'>accounts.mathpix.com</a> "
            "注册 (pay-as-you-go: 一次性 $19.99 + 按量计费)。"
        )
        intro.setOpenExternalLinks(True)
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")

        # ---- API group ----
        api_box = QGroupBox("API 凭证")
        self.id_edit = QLineEdit(all_settings.get("app_id", ""))
        self.id_edit.setPlaceholderText("Mathpix App ID")
        self.key_edit = QLineEdit(all_settings.get("app_key", ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Mathpix App Key")

        self._show_key_btn = QPushButton("显示")
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.setFixedWidth(64)
        self._show_key_btn.toggled.connect(self._toggle_key_visible)

        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(self._show_key_btn)

        api_form = QFormLayout(api_box)
        api_form.setContentsMargins(10, 14, 10, 10)
        api_form.setSpacing(8)
        api_form.addRow("App ID", self.id_edit)
        api_form.addRow("App Key", key_row)

        # ---- Hotkey group ----
        hk_box = QGroupBox("全局快捷键")
        hk_intro = QLabel(
            "组合至少含 Ctrl / Alt / Shift 之一。按 Esc 取消、Backspace 清空。"
        )
        hk_intro.setProperty("role", "muted")
        hk_intro.setWordWrap(True)

        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumSequenceLength(1)
        self.hotkey_edit.setKeySequence(
            QKeySequence(config.keyboard_to_qt(self._old_hotkey)))

        reset_btn = QPushButton("恢复默认")
        reset_btn.setFixedWidth(96)
        reset_btn.clicked.connect(self._reset_hotkey)

        hk_row = QHBoxLayout()
        hk_row.addWidget(self.hotkey_edit, 1)
        hk_row.addWidget(reset_btn)

        hk_layout = QVBoxLayout(hk_box)
        hk_layout.setContentsMargins(10, 14, 10, 10)
        hk_layout.setSpacing(8)
        hk_layout.addWidget(hk_intro)
        hk_layout.addLayout(hk_row)

        # ---- Pricing group ----
        price_box = QGroupBox("终端定价设置")
        price_intro = QLabel(
            "Mathpix 当前 PAYG 单价：截图 $0.002/张，PDF $0.005/页。")
        price_intro.setProperty("role", "muted")
        price_intro.setWordWrap(True)

        self._pending_image_price = float(all_settings.get(
            "image_price_usd", config.DEFAULT_IMAGE_PRICE))
        self._pending_pdf_price = float(all_settings.get(
            "pdf_price_usd", config.DEFAULT_PDF_PRICE))

        mono_style = "font-family: 'Consolas', monospace; font-size: 11pt;"
        self.image_price_label = QLabel(self._fmt_price(self._pending_image_price))
        self.image_price_label.setStyleSheet(mono_style)
        self.pdf_price_label = QLabel(self._fmt_price(self._pending_pdf_price))
        self.pdf_price_label.setStyleSheet(mono_style)

        image_edit_btn = QPushButton("修改…")
        image_edit_btn.setFixedWidth(96)
        image_edit_btn.clicked.connect(lambda: self._edit_price("image"))
        pdf_edit_btn = QPushButton("修改…")
        pdf_edit_btn.setFixedWidth(96)
        pdf_edit_btn.clicked.connect(lambda: self._edit_price("pdf"))
        price_reset_btn = QPushButton("恢复默认")
        price_reset_btn.setFixedWidth(96)
        price_reset_btn.clicked.connect(self._reset_prices)

        price_grid = QGridLayout()
        price_grid.setHorizontalSpacing(12)
        price_grid.setVerticalSpacing(8)
        price_grid.setColumnStretch(1, 1)
        price_grid.addWidget(QLabel("截图单价 (每张)"), 0, 0)
        price_grid.addWidget(self.image_price_label, 0, 1)
        price_grid.addWidget(image_edit_btn, 0, 2,
                             Qt.AlignmentFlag.AlignRight)
        price_grid.addWidget(QLabel("PDF 单价 (每页)"), 1, 0)
        price_grid.addWidget(self.pdf_price_label, 1, 1)
        price_grid.addWidget(pdf_edit_btn, 1, 2,
                             Qt.AlignmentFlag.AlignRight)
        price_grid.addWidget(price_reset_btn, 2, 2,
                             Qt.AlignmentFlag.AlignRight)

        price_layout = QVBoxLayout(price_box)
        price_layout.setContentsMargins(10, 14, 10, 10)
        price_layout.setSpacing(8)
        price_layout.addWidget(price_intro)
        price_layout.addLayout(price_grid)

        # ---- WebDAV group ----
        wd_box = QGroupBox("WebDAV 同步")
        wd_warn = QLabel(
            "⚠ API Key 以明文 JSON 存放到你的 WebDAV 服务器,请使用 HTTPS。"
        )
        wd_warn.setProperty("role", "warning")
        wd_warn.setWordWrap(True)

        self.wd_url_edit = QLineEdit(wd["url"])
        self.wd_url_edit.setPlaceholderText("https://example.com/dav")
        self.wd_user_edit = QLineEdit(wd["user"])
        self.wd_user_edit.setPlaceholderText("用户名")
        self.wd_pass_edit = QLineEdit(wd["password"])
        self.wd_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.wd_pass_edit.setPlaceholderText("密码")
        self._show_wdpass_btn = QPushButton("显示")
        self._show_wdpass_btn.setCheckable(True)
        self._show_wdpass_btn.setFixedWidth(64)
        self._show_wdpass_btn.toggled.connect(self._toggle_wdpass_visible)
        wdpass_row = QHBoxLayout()
        wdpass_row.addWidget(self.wd_pass_edit, 1)
        wdpass_row.addWidget(self._show_wdpass_btn)

        self.wd_path_edit = QLineEdit(wd["path"])
        self.wd_path_edit.setPlaceholderText(config.DEFAULT_WEBDAV_PATH)

        self.wd_interval_spin = QSpinBox()
        self.wd_interval_spin.setRange(0, 1440)
        self.wd_interval_spin.setSingleStep(1)
        self.wd_interval_spin.setSuffix(" 分钟")
        self.wd_interval_spin.setSpecialValueText("0 (不启用定时)")
        self.wd_interval_spin.setValue(int(wd["interval"]))
        interval_hint = QLabel("启动 / 退出时各自动同步一次。")
        interval_hint.setProperty("role", "muted")
        interval_row = QHBoxLayout()
        interval_row.addWidget(self.wd_interval_spin)
        interval_row.addWidget(interval_hint, 1)

        wd_form = QFormLayout()
        wd_form.setSpacing(8)
        wd_form.addRow("服务器 URL", self.wd_url_edit)
        wd_form.addRow("用户名", self.wd_user_edit)
        wd_form.addRow("密码", wdpass_row)
        wd_form.addRow("远程路径", self.wd_path_edit)
        wd_form.addRow("同步间隔", interval_row)

        self.wd_test_btn = QPushButton("测试连接")
        self.wd_test_btn.clicked.connect(self._test_webdav)
        self.wd_sync_btn = QPushButton("立即同步")
        self.wd_sync_btn.clicked.connect(self._sync_webdav)
        self.wd_status = QLabel(_format_synced(config.get_last_synced()))
        self.wd_status.setProperty("role", "muted")

        wd_btn_row = QHBoxLayout()
        wd_btn_row.addWidget(self.wd_test_btn)
        wd_btn_row.addWidget(self.wd_sync_btn)
        wd_btn_row.addStretch(1)

        wd_layout = QVBoxLayout(wd_box)
        wd_layout.setContentsMargins(10, 14, 10, 10)
        wd_layout.setSpacing(8)
        wd_layout.addWidget(wd_warn)
        wd_layout.addLayout(wd_form)
        wd_layout.addLayout(wd_btn_row)
        wd_layout.addWidget(self.wd_status)

        # ---- Cache group ----
        cache_box = QGroupBox("本地缓存")
        self.cache_retention_spin = QSpinBox()
        self.cache_retention_spin.setRange(0, 3650)
        self.cache_retention_spin.setSuffix(" 天")
        self.cache_retention_spin.setSpecialValueText("0 (不自动清理)")
        self.cache_retention_spin.setValue(int(
            all_settings.get("cache_retention_days", 0) or 0))
        cache_hint = QLabel("启动时自动清理超过此天数的截图历史和用量记录。")
        cache_hint.setProperty("role", "muted")
        cache_now_btn = QPushButton("立即清理")
        cache_now_btn.setFixedWidth(96)
        cache_now_btn.clicked.connect(self._purge_cache_now)
        self.cache_status = QLabel("")
        self.cache_status.setProperty("role", "muted")

        cache_form = QFormLayout()
        cache_form.setSpacing(8)
        cache_form.addRow("保留历史天数", self.cache_retention_spin)

        cache_btn_row = QHBoxLayout()
        cache_btn_row.addStretch(1)
        cache_btn_row.addWidget(cache_now_btn)

        cache_layout = QVBoxLayout(cache_box)
        cache_layout.setContentsMargins(10, 14, 10, 10)
        cache_layout.setSpacing(8)
        cache_layout.addWidget(cache_hint)
        cache_layout.addLayout(cache_form)
        cache_layout.addLayout(cache_btn_row)
        cache_layout.addWidget(self.cache_status)

        # ---- Buttons ----
        save_btn = QPushButton("保存")
        save_btn.setObjectName("accent")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)

        clear_btn = QPushButton("清除已存凭证")
        clear_btn.clicked.connect(self._clear)

        btn_row = QHBoxLayout()
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)

        # ---- Scrollable content ----
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(header)
        content_layout.addWidget(intro)
        content_layout.addWidget(api_box)
        content_layout.addWidget(hk_box)
        content_layout.addWidget(price_box)
        content_layout.addWidget(wd_box)
        content_layout.addWidget(cache_box)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(scroll, 1)
        layout.addLayout(btn_row)

    # ---- handlers ----------------------------------------------------------

    def _toggle_key_visible(self, on: bool) -> None:
        self.key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )
        self._show_key_btn.setText("隐藏" if on else "显示")

    def _toggle_wdpass_visible(self, on: bool) -> None:
        self.wd_pass_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )
        self._show_wdpass_btn.setText("隐藏" if on else "显示")

    def _reset_hotkey(self) -> None:
        self.hotkey_edit.setKeySequence(
            QKeySequence(config.keyboard_to_qt(config.DEFAULT_HOTKEY)))

    @staticmethod
    def _fmt_price(value: float) -> str:
        return f"${value:.4f}"

    def _edit_price(self, kind: str) -> None:
        if kind == "image":
            current = self._pending_image_price
            title = "修改截图单价"
            prompt = "新单价 (USD,每张):"
        else:
            current = self._pending_pdf_price
            title = "修改 PDF 单价"
            prompt = "新单价 (USD,每页):"
        new_value, ok = QInputDialog.getDouble(
            self, title, prompt, current, 0.0, 1.0, 4,
            Qt.WindowType.Dialog,
            0.0001,
        )
        if not ok:
            return
        if kind == "image":
            self._pending_image_price = float(new_value)
            self.image_price_label.setText(self._fmt_price(new_value))
        else:
            self._pending_pdf_price = float(new_value)
            self.pdf_price_label.setText(self._fmt_price(new_value))

    def _reset_prices(self) -> None:
        ret = QMessageBox.question(
            self, "恢复默认价格",
            "恢复截图 $0.002/张、PDF $0.005/页?")
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._pending_image_price = config.DEFAULT_IMAGE_PRICE
        self._pending_pdf_price = config.DEFAULT_PDF_PRICE
        self.image_price_label.setText(self._fmt_price(self._pending_image_price))
        self.pdf_price_label.setText(self._fmt_price(self._pending_pdf_price))

    def _test_webdav(self) -> None:
        url = self.wd_url_edit.text().strip()
        user = self.wd_user_edit.text().strip()
        pw = self.wd_pass_edit.text()
        self.wd_status.setText("测试中…")
        self.wd_status.repaint()
        ok, msg = webdav.test_connection(url, user, pw)
        prefix = "✓" if ok else "✗"
        self.wd_status.setText(f"{prefix} {msg}")

    def _sync_webdav(self) -> None:
        if self._sync_worker is not None:
            return
        url = self.wd_url_edit.text().strip()
        user = self.wd_user_edit.text().strip()
        pw = self.wd_pass_edit.text()
        path = self.wd_path_edit.text().strip() or config.DEFAULT_WEBDAV_PATH
        if not url or not user:
            QMessageBox.warning(self, "缺少字段", "请先填写 URL 和用户名。")
            return
        # Persist current WebDAV config so the worker reads the right values.
        try:
            config.set_webdav(url, user, pw, path,
                              int(self.wd_interval_spin.value()))
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"无法写入配置：{exc}")
            return

        self.wd_sync_btn.setEnabled(False)
        self.wd_sync_btn.setText("同步中…")
        self.wd_status.setText("同步中…")

        w = webdav.WebDavSyncWorker()
        w.finished_ok.connect(self._on_sync_ok)
        w.failed.connect(self._on_sync_fail)
        w.finished.connect(self._sync_cleanup)
        self._sync_worker = w
        w.start()

    def _on_sync_ok(self, ts: float) -> None:
        self.wd_status.setText("✓ " + _format_synced(ts))
        # Refresh local field values from the merged result.
        s = config.load_all()
        self.id_edit.setText(s.get("app_id", ""))
        self.key_edit.setText(s.get("app_key", ""))
        self._pending_image_price = float(s.get(
            "image_price_usd", config.DEFAULT_IMAGE_PRICE))
        self._pending_pdf_price = float(s.get(
            "pdf_price_usd", config.DEFAULT_PDF_PRICE))
        self.image_price_label.setText(
            self._fmt_price(self._pending_image_price))
        self.pdf_price_label.setText(
            self._fmt_price(self._pending_pdf_price))

    def _on_sync_fail(self, msg: str) -> None:
        self.wd_status.setText(f"✗ 同步失败: {msg}")

    def _sync_cleanup(self) -> None:
        self.wd_sync_btn.setEnabled(True)
        self.wd_sync_btn.setText("立即同步")
        self._sync_worker = None

    def _purge_cache_now(self) -> None:
        days = int(self.cache_retention_spin.value())
        if days <= 0:
            QMessageBox.information(
                self, "未设置保留天数",
                "请先填入保留天数 (大于 0),或在「历史记录」标签页用「清空缓存」全量清理。")
            return
        if self._on_purge_now is None:
            self.cache_status.setText("✗ 当前无法清理 (storage 未连接)")
            return
        ret = QMessageBox.question(
            self, "确认清理",
            f"将删除超过 {days} 天的历史记录和用量,继续?")
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            n = int(self._on_purge_now(days))
        except Exception as exc:
            self.cache_status.setText(f"✗ 清理失败: {exc}")
            return
        self.cache_status.setText(f"✓ 已清理 {n} 条历史记录")

    def _save(self) -> None:
        app_id = self.id_edit.text().strip()
        app_key = self.key_edit.text().strip()
        if not app_id or not app_key:
            QMessageBox.warning(self, "缺少字段", "App ID 和 App Key 都不能为空。")
            return

        qt_seq = self.hotkey_edit.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText)
        new_hotkey = config.qt_to_keyboard(qt_seq) or config.DEFAULT_HOTKEY

        # Sanity check: require at least one modifier OR a function/special key
        # to avoid accidentally trapping a single letter that breaks typing.
        parts = new_hotkey.split("+")
        modifiers = {"ctrl", "alt", "shift", "windows"}
        has_modifier = any(p in modifiers for p in parts[:-1])
        last = parts[-1] if parts else ""
        is_special = last.startswith("f") and last[1:].isdigit()
        if not has_modifier and not is_special:
            QMessageBox.warning(
                self, "快捷键不安全",
                f"快捷键 '{config.keyboard_to_qt(new_hotkey)}' 没有修饰键，"
                f"会拦截普通输入。请加上 Ctrl / Alt / Shift。")
            return

        wd_url = self.wd_url_edit.text().strip()
        wd_user = self.wd_user_edit.text().strip()
        wd_interval = int(self.wd_interval_spin.value())
        if wd_url and not wd_user:
            QMessageBox.warning(
                self, "WebDAV 配置不完整",
                "填写 WebDAV URL 后必须同时提供用户名（密码可空，但通常必填）。")
            return

        try:
            cur = config.load_all()
            cur["app_id"] = app_id
            cur["app_key"] = app_key
            cur["hotkey"] = new_hotkey
            cur["image_price_usd"] = float(self._pending_image_price)
            cur["pdf_price_usd"] = float(self._pending_pdf_price)
            cur["webdav_url"] = wd_url
            cur["webdav_user"] = wd_user
            cur["webdav_password"] = self.wd_pass_edit.text()
            cur["webdav_path"] = (
                self.wd_path_edit.text().strip() or config.DEFAULT_WEBDAV_PATH)
            cur["webdav_sync_interval"] = max(0, wd_interval)
            cur["cache_retention_days"] = max(
                0, int(self.cache_retention_spin.value()))
            # Drop deprecated bool field if present from older configs.
            cur.pop("webdav_auto_sync", None)
            config.save_all(cur)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"无法写入配置：{exc}")
            return

        self.settings_changed.emit(self._old_hotkey, new_hotkey)
        self.accept()

    def _clear(self) -> None:
        ret = QMessageBox.question(
            self, "确认", "清除已保存的 API 凭证?其他设置不受影响。")
        if ret == QMessageBox.StandardButton.Yes:
            cur = config.load_all()
            cur.pop("app_id", None)
            cur.pop("app_key", None)
            config.save_all(cur)
            self.id_edit.clear()
            self.key_edit.clear()
