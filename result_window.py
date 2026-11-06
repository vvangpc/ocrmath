"""Compact screenshot/result window with an optional source image."""
from __future__ import annotations

import re
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QFont, QGuiApplication, QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QFrame, QComboBox, QStackedWidget, QSizePolicy, QLayout,
)

import config
from mathjax_view import MathJaxView, WEBENGINE_AVAILABLE
from ui_icons import icon


def _strip_outer_dollars(s: str) -> str:
    s = s.strip()
    for start, end in (("$$", "$$"), ("$", "$"), (r"\[", r"\]"), (r"\(", r"\)")):
        if s.startswith(start) and s.endswith(end) and len(s) >= len(start) + len(end):
            return s[len(start):-len(end)].strip()
    return s


def _is_formula(text: str, latex: str) -> bool:
    if not latex:
        return False
    return not text.strip() or text.strip() == latex.strip() or bool(re.fullmatch(
        r"\s*(?:\$\$[^$]+\$\$|\$[^$]+\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))\s*",
        text, re.DOTALL))


class ResultWindow(QWidget):
    """Primary app surface; PDF, history and usage open through callbacks."""

    def __init__(self, on_recapture=None, *, on_retry=None, on_open_pdf=None,
                 on_open_history=None, on_open_usage=None, on_open_settings=None,
                 on_provider_changed=None):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("resultWindow")
        self.setWindowTitle("OCRmath")
        self.setMinimumSize(460, 420)
        self.resize(580, 560)
        self._on_recapture, self._on_retry = on_recapture, on_retry
        self._on_provider_changed = on_provider_changed
        self._result, self._latex, self._text = {}, "", ""
        self._copy_kind, self._format, self._state = "latex", "preview", "empty"
        self._source = QImage()
        self._collapsed_height = None
        self._busy = False
        self._build_ui(on_open_pdf, on_open_history, on_open_usage, on_open_settings)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)
        self._copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self._copy_shortcut.activated.connect(self._copy_current)
        self._close_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._close_shortcut.activated.connect(self.close)
        self.show_ready(activate=False)

    @staticmethod
    def _button(text, callback=None, *, quiet=False, name=None):
        button = QPushButton(text)
        button.setProperty("flat", quiet)
        if name:
            button.setObjectName(name)
        if callback:
            button.clicked.connect(callback)
        return button

    def _build_ui(self, on_pdf, on_history, on_usage, on_settings):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        header = QFrame()
        header.setObjectName("resultHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(22, 16, 22, 16)
        mark = QLabel("∫")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(29, 30)
        brand = QLabel("OCRmath")
        brand.setObjectName("brandName")
        self.header_caption = QLabel("截图识别")
        self.header_caption.setProperty("role", "muted")
        for widget in (mark, brand, self.header_caption):
            row.addWidget(widget)
        row.addStretch()
        self.source_btn = self._button("查看原图", self._toggle_source, quiet=True)
        self.source_btn.setCheckable(True)
        self.source_btn.setEnabled(False)
        row.addWidget(self.source_btn)
        outer.addWidget(header)

        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(26, 18, 26, 16)
        body.setSpacing(12)
        row = QHBoxLayout()
        self.cache_badge = QLabel("待截图")
        self.cache_badge.setObjectName("statusBadge")
        row.addWidget(self.cache_badge)
        row.addStretch()
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Mathpix", "mathpix")
        self.provider_combo.addItem("大模型", "llm")
        self.provider_combo.setMaximumWidth(265)
        self.provider_combo.setToolTip("用于下一次截图识别；已有结果保留原识别服务")
        self.provider_combo.setAccessibleName("截图识别服务")
        self.provider_combo.currentIndexChanged.connect(self._choose_provider)
        row.addWidget(self.provider_combo)
        body.addLayout(row)
        self.source_frame = QFrame()
        self.source_frame.setObjectName("sourceFrame")
        source_l = QVBoxLayout(self.source_frame)
        source_l.setContentsMargins(12, 12, 12, 12)
        self.source_label = QLabel()
        self.source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source_label.setMinimumHeight(40)
        self.source_label.setMaximumHeight(180)
        self.source_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.source_label.setAccessibleName("当前识别的原图")
        source_l.addWidget(self.source_label)
        self.source_frame.hide()
        body.addWidget(self.source_frame)
        self.warn = QLabel()
        self.warn.setProperty("role", "warning")
        self.warn.setTextFormat(Qt.TextFormat.PlainText)
        self.warn.setWordWrap(True)
        self.warn.hide()
        body.addWidget(self.warn)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.format_buttons = {}
        for key, text in (("preview", "预览"), ("latex", "LaTeX"), ("markdown", "Markdown")):
            button = self._button(text, lambda _checked=False, k=key: self._select_format(k))
            button.setProperty("segment", True)
            button.setCheckable(True)
            self.format_buttons[key] = button
            row.addWidget(button)
        row.addStretch()
        self.latex_style = QComboBox()
        self.latex_style.addItems(["纯 LaTeX", "行内 $…$", "独立 $$…$$"])
        self.latex_style.setAccessibleName("LaTeX 复制格式")
        self.latex_style.currentIndexChanged.connect(self._update_copy)
        self.latex_style.hide()
        row.addWidget(self.latex_style)
        body.addLayout(row)

        self.output_stack = QStackedWidget()
        self.output_stack.setMinimumHeight(158)
        if WEBENGINE_AVAILABLE:
            self.preview = MathJaxView()
            self.preview.setMinimumHeight(158)
            self._preview_is_web = True
        else:
            self.preview = QLabel()
            self.preview.setWordWrap(True)
            self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview.setTextFormat(Qt.TextFormat.PlainText)
            self._preview_is_web = False
        self.preview.setObjectName("formulaPreview")
        self.output_stack.addWidget(self.preview)
        self.code_edit = QPlainTextEdit()
        self.code_edit.setObjectName("resultCode")
        self.code_edit.setReadOnly(True)
        mono = QFont("Consolas", 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.code_edit.setFont(mono)
        self.output_stack.addWidget(self.code_edit)
        self.empty_label = QLabel()
        self.empty_label.setObjectName("resultEmpty")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setTextFormat(Qt.TextFormat.PlainText)
        self.output_stack.addWidget(self.empty_label)
        body.addWidget(self.output_stack, 1)
        self.copy_btn = self._button("截图识别", self._primary_action, name="accent")
        self.copy_btn.setMinimumHeight(42)
        body.addWidget(self.copy_btn)
        row = QHBoxLayout()
        self.meta = QLabel()
        self.meta.setProperty("role", "muted")
        self.meta.setTextFormat(Qt.TextFormat.PlainText)
        self.meta.setWordWrap(True)
        row.addWidget(self.meta, 1)
        self.recapture_btn = self._button("再截一张", self._recapture, quiet=True)
        row.addWidget(self.recapture_btn)
        body.addLayout(row)
        self.toast = QLabel()
        self.toast.setObjectName("copyToast")
        self.toast.setTextFormat(Qt.TextFormat.PlainText)
        self.toast.setWordWrap(True)
        self.toast.hide()
        body.addWidget(self.toast)
        outer.addWidget(content, 1)

        footer = QFrame()
        footer.setObjectName("resultFooter")
        row = QHBoxLayout(footer)
        row.setContentsMargins(16, 10, 16, 10)
        self.pdf_btn = self._button("PDF 任务", on_pdf, quiet=True)
        self.pdf_btn.setIcon(icon("pdf"))
        self.pdf_btn.setIconSize(QSize(16, 16))
        self.history_btn = self._button("历史", on_history, quiet=True)
        self.usage_btn = self._button("用量", on_usage, quiet=True)
        for button in (self.pdf_btn, self.history_btn, self.usage_btn):
            row.addWidget(button)
        row.addStretch()
        self.settings_btn = self._button("设置", on_settings, quiet=True)
        self.settings_btn.setIcon(icon("settings"))
        self.settings_btn.setIconSize(QSize(16, 16))
        row.addWidget(self.settings_btn)
        outer.addWidget(footer)
        self._select_format("preview")

    def refresh_settings(self):
        self.provider_combo.blockSignals(True)
        self.provider_combo.setItemText(1, "大模型 · " + config.get_llm()["model"])
        self.provider_combo.setCurrentIndex(self.provider_combo.findData(config.get_provider()))
        self.provider_combo.blockSignals(False)
        pretty = config.keyboard_to_qt(config.get_hotkey())
        self.recapture_btn.setText("再截一张  " + pretty)
        if self._state == "empty":
            self.meta.setText(pretty)

    def _choose_provider(self):
        try:
            config.save_settings({"image_provider": self.provider_combo.currentData()})
        except Exception as exc:
            self.refresh_settings()
            self.toast.setText("服务切换失败：" + str(exc))
            self.toast.show()
            return
        if self._on_provider_changed:
            self._on_provider_changed()

    def set_source(self, png: bytes | None):
        self._source = QImage.fromData(png, "PNG") if png else QImage()
        self.source_btn.setEnabled(not self._source.isNull())
        if self._source.isNull():
            self.source_btn.setChecked(False)
            self.source_frame.hide()
            self.source_btn.setText("原图不可用")
        else:
            self.source_btn.setText("收起原图" if self.source_btn.isChecked() else "查看原图")
            self.source_frame.setVisible(self.source_btn.isChecked())
            self._scale_source()

    def _toggle_source(self):
        expanded = self.source_btn.isChecked() and not self._source.isNull()
        if expanded:
            self._collapsed_height = self.height()
        self.source_frame.setVisible(expanded)
        self.source_btn.setText("收起原图" if expanded else "查看原图")
        self._scale_source()
        self.layout().activate()
        if expanded:
            self.resize(self.width(), max(self.height(), self.minimumSizeHint().height()))
        elif self._collapsed_height is not None:
            self.resize(self.width(), max(self._collapsed_height, self.minimumSizeHint().height()))

    def _scale_source(self):
        if not self._source.isNull():
            scaled = self._source.scaled(
                QSize(max(100, self.width() - 82), 170), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.source_label.setPixmap(QPixmap.fromImage(scaled))
            self.source_label.setFixedHeight(scaled.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale_source()

    def set_task_count(self, count: int):
        self.pdf_btn.setText(f"PDF 任务  · {count}" if count else "PDF 任务")

    def set_busy(self, busy: bool):
        self._busy = busy
        self.provider_combo.setEnabled(not busy)
        self.recapture_btn.setEnabled(not busy)
        self.copy_btn.setEnabled(not busy and (self._state != "error" or self._on_retry is not None))
        if self._state == "result":
            self._update_copy()

    def show_ready(self, *, activate=True):
        if self._state not in ("result", "error", "loading"):
            self._state = "empty"
            self.cache_badge.setText("待截图")
            self.header_caption.setText("截图识别")
            self.empty_label.setText("截取公式或文字\n识别结果会显示在这里")
            self.output_stack.setCurrentWidget(self.empty_label)
            self.copy_btn.setText("截图识别")
            for button in self.format_buttons.values():
                button.setEnabled(False)
        self.refresh_settings()
        if activate:
            self._present()

    def show_loading(self):
        self._state = "loading"
        self._result, self._text, self._latex = {}, "", ""
        self.cache_badge.setText("识别中")
        self.header_caption.setText("截图识别")
        self.empty_label.setText("正在识别…")
        self.output_stack.setCurrentWidget(self.empty_label)
        self.copy_btn.setText("识别中…")
        self.meta.setText(self.provider_combo.currentText())
        self.warn.hide()
        self._clear_toast()
        for button in self.format_buttons.values():
            button.setEnabled(False)
        self.latex_style.hide()
        self.set_busy(True)
        self._present()

    def show_error(self, message: str):
        self._state = "error"
        self.cache_badge.setText("识别失败")
        self.empty_label.setText("原图已保留，可直接重试")
        self.output_stack.setCurrentWidget(self.empty_label)
        self.warn.setText(message)
        self.warn.show()
        self.copy_btn.setText("重试原图")
        self.latex_style.hide()
        self._clear_toast()
        for button in self.format_buttons.values():
            button.setEnabled(False)
        self.set_busy(self._busy)
        self._present()

    def show_result(self, result: dict, from_cache: bool = False):
        self._state, self._result = "result", dict(result)
        self._latex = _strip_outer_dollars(result.get("latex_styled") or "")
        self._text = result.get("text") or ""
        self._copy_kind = "latex" if _is_formula(self._text, self._latex) else "markdown"
        self.header_caption.setText("识别结果")
        self.cache_badge.setText("本地缓存" if from_cache else "已识别")
        self.cache_badge.setToolTip("已复用本地结果，本次未调用识别服务" if from_cache else "")
        meta = []
        llm = result.get("_provider") == "llm"
        if llm:
            meta.append(result.get("model") or "大模型")
            usage = result.get("usage") or {}
            if "input_tokens" in usage and "output_tokens" in usage:
                meta.append(f"输入 {usage['input_tokens']:,} / 输出 {usage['output_tokens']:,} Token")
        else:
            meta.append("Mathpix")
            if result.get("is_handwritten"):
                meta.append("手写")
            elif result.get("is_printed"):
                meta.append("印刷体")
            if result.get("confidence") is not None:
                meta.append(f"置信度 {result['confidence'] * 100:.1f}%")
        self.meta.setText(" · ".join(meta))
        confidence = result.get("confidence") if not llm else None
        self.warn.setVisible(confidence is not None and confidence < .5)
        if confidence is not None and confidence < .5:
            self.warn.setText(f"置信度 {confidence * 100:.0f}%，复制前请核对原图。")
        self.format_buttons["preview"].setEnabled(True)
        self.format_buttons["latex"].setVisible(bool(self._latex))
        self.format_buttons["latex"].setEnabled(bool(self._latex))
        self.format_buttons["markdown"].setEnabled(bool(self._text or self._latex))
        self._kick_preview(latex=self._latex, text=self._text)
        self._select_format("preview")
        self._clear_toast()
        self.set_busy(self._busy)
        self._present()

    def _kick_preview(self, *, latex, text):
        pure = _is_formula(text, latex)
        content = latex if pure else (text or latex)
        if not content:
            self._set_preview_message("此区域没有可识别的文字")
        elif self._preview_is_web:
            self.preview.set_content(content, is_math=pure)
        else:
            self.preview.setText(text or latex)
            self.preview.setToolTip("公式排版需要 PyQt6-WebEngine；可切换到 LaTeX 或 Markdown 复制")

    def _set_preview_message(self, message):
        if self._preview_is_web:
            self.preview.show_message(message)
        else:
            self.preview.setText(message)

    def _select_format(self, key):
        self._format = key
        for name, button in self.format_buttons.items():
            button.setChecked(name == key)
        self.latex_style.setVisible(key == "latex" and bool(self._latex))
        if self._state == "result":
            self.output_stack.setCurrentWidget(self.preview if key == "preview" else self.code_edit)
        self._update_copy()

    def _copy_text(self):
        kind = self._copy_kind if self._format == "preview" else self._format
        if kind == "latex":
            if self._format == "latex":
                style = self.latex_style.currentIndex()
                if style == 1:
                    return "$" + self._latex + "$"
                if style == 2:
                    return "$$" + self._latex + "$$"
            return self._latex
        return self._text or ("$$" + self._latex + "$$" if self._latex else "")

    def _update_copy(self):
        if self._state != "result":
            return
        text = self._copy_text()
        if self._format != "preview":
            self.code_edit.setPlainText(text)
        kind = self._copy_kind if self._format == "preview" else self._format
        self.copy_btn.setText("复制 LaTeX" if kind == "latex" else "复制 Markdown")
        self.copy_btn.setIcon(icon("copy", "white"))
        self.copy_btn.setEnabled(bool(text) and not self._busy)

    def _primary_action(self):
        if not self._busy:
            if self._state == "empty":
                self._recapture()
            elif self._state == "error":
                if self._on_retry:
                    self._on_retry()
            else:
                self._copy_current()

    def _recapture(self):
        if not self._busy and self._on_recapture:
            self._on_recapture()

    def _copy_current(self):
        if self._state == "result" and not self._busy:
            self._copy(self._copy_text())

    def _copy(self, text):
        if text:
            QGuiApplication.clipboard().setText(text)
            self.toast.setText("已复制到剪贴板")
            self.copy_btn.setText("已复制到剪贴板")
            self._toast_timer.start(2400)

    def _clear_toast(self):
        self.toast.clear()
        self.toast.hide()
        if self._state == "result":
            self._update_copy()

    def _present(self):
        if not self.isVisible():
            screen = QGuiApplication.screenAt(self.pos()) or QGuiApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.resize(min(self.width(), geo.width()), min(self.height(), geo.height()))
                self.move(geo.center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()
