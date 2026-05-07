"""Settings dialog: API credentials + global hotkey."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QMessageBox, QGroupBox, QKeySequenceEdit,
)

import config


class SettingsDialog(QDialog):
    """Dialog for editing API credentials and the screenshot hotkey.

    Emits `settings_changed(old_hotkey, new_hotkey)` on accept so the main
    app can re-register the global shortcut.
    """

    settings_changed = pyqtSignal(str, str)  # (old_hotkey, new_hotkey)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ocrmath 设置")
        self.setMinimumWidth(480)

        all_settings = config.load_all()
        self._old_hotkey = all_settings.get("hotkey") or config.DEFAULT_HOTKEY

        # ---- Header ----
        header = QLabel("应用设置")
        header.setProperty("role", "heading")

        intro = QLabel(
            "在下方填入你的 Mathpix API 凭证，并可自定义全局截屏快捷键。<br>"
            "还没有 API Key？请到 "
            "<a href='https://accounts.mathpix.com/'>accounts.mathpix.com</a> "
            "注册并选择 pay-as-you-go 套餐（一次性 $19.99 启动费 + 按量计费）。"
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
            "点击下方框，按下你想要的组合键（建议至少包含 Ctrl/Alt/Shift 之一）。"
            "按 Esc 取消，按 Backspace 清空。"
        )
        hk_intro.setProperty("role", "muted")
        hk_intro.setWordWrap(True)

        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumSequenceLength(1)
        # Pre-fill with current hotkey in Qt format
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(header)
        layout.addWidget(intro)
        layout.addWidget(api_box)
        layout.addWidget(hk_box)
        layout.addStretch(1)
        layout.addLayout(btn_row)

    # ---- handlers ----------------------------------------------------------

    def _toggle_key_visible(self, on: bool) -> None:
        self.key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )
        self._show_key_btn.setText("隐藏" if on else "显示")

    def _reset_hotkey(self) -> None:
        self.hotkey_edit.setKeySequence(
            QKeySequence(config.keyboard_to_qt(config.DEFAULT_HOTKEY)))

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

        try:
            cur = config.load_all()
            cur["app_id"] = app_id
            cur["app_key"] = app_key
            cur["hotkey"] = new_hotkey
            config.save_all(cur)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"无法写入配置：{exc}")
            return

        self.settings_changed.emit(self._old_hotkey, new_hotkey)
        self.accept()

    def _clear(self) -> None:
        ret = QMessageBox.question(
            self, "确认", "确定要清除已保存的 API 凭证吗？\n（不影响快捷键设置）")
        if ret == QMessageBox.StandardButton.Yes:
            cur = config.load_all()
            cur.pop("app_id", None)
            cur.pop("app_key", None)
            config.save_all(cur)
            self.id_edit.clear()
            self.key_edit.clear()
