"""Floating window that shows the OCR result and lets the user copy it."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSizePolicy,
)

from mathjax_view import MathJaxView, WEBENGINE_AVAILABLE
from styles import ACCENT
from ui_icons import icon


def _strip_outer_dollars(s: str) -> str:
    s = s.strip()
    if s.startswith("$$") and s.endswith("$$"):
        return s[2:-2].strip()
    if s.startswith("$") and s.endswith("$"):
        return s[1:-1].strip()
    return s


class ResultWindow(QWidget):
    """Top-level window. Caller fills it via show_result()."""

    def __init__(self, on_recapture: Callable[[], None] | None = None):
        super().__init__(
            None,
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setWindowTitle("识别结果 - ocrmath")
        self.setMinimumWidth(580)
        self._on_recapture = on_recapture
        self._build_ui()

    def _build_ui(self) -> None:
        # ---- header (cache badge + meta) ----
        self.cache_badge = QLabel("♻ 已缓存")
        self.cache_badge.setStyleSheet(
            f"background:#fff7ed; color:{ACCENT}; "
            f"border:1px solid #ffd9b3; border-radius:10px;"
            f"padding:2px 10px; font-weight:600;"
        )
        self.cache_badge.hide()

        self.meta = QLabel()
        self.meta.setProperty("role", "muted")

        header = QHBoxLayout()
        header.addWidget(self.meta, 1)
        header.addWidget(self.cache_badge)

        # ---- warning bar ----
        self.warn = QLabel()
        self.warn.setProperty("role", "warning")
        self.warn.setWordWrap(True)
        self.warn.hide()

        # ---- preview area ----
        if WEBENGINE_AVAILABLE:
            self.preview = MathJaxView()
            self.preview.setStyleSheet(
                "border:1px solid #e2e2e2; border-radius:6px; background:white;")
            self._preview_is_web = True
        else:
            self.preview = QLabel(
                "未安装 PyQt6-WebEngine，无法渲染公式预览。\n"
                "请运行: pip install PyQt6-WebEngine")
            self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview.setMinimumHeight(72)
            self.preview.setStyleSheet(
                "background:white; border:1px solid #e2e2e2;"
                "border-radius:6px; padding:10px;")
            self.preview.setProperty("role", "muted")
            self._preview_is_web = False

        # ---- text outputs ----
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)

        self.inline_edit = QPlainTextEdit()
        self.inline_edit.setReadOnly(True)
        self.inline_edit.setFont(mono)
        self.inline_edit.setMaximumHeight(80)

        self.display_edit = QPlainTextEdit()
        self.display_edit.setReadOnly(True)
        self.display_edit.setFont(mono)
        self.display_edit.setMaximumHeight(80)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(mono)
        self.text_edit.setMaximumHeight(120)

        copy_inline = QPushButton("复制")
        copy_inline.setIcon(icon("copy"))
        copy_inline.setIconSize(QSize(16, 16))
        copy_inline.clicked.connect(
            lambda: self._copy(self.inline_edit.toPlainText()))
        copy_display = QPushButton("复制")
        copy_display.setIcon(icon("copy"))
        copy_display.setIconSize(QSize(16, 16))
        copy_display.clicked.connect(
            lambda: self._copy(self.display_edit.toPlainText()))
        copy_text = QPushButton("复制")
        copy_text.setIcon(icon("copy"))
        copy_text.setIconSize(QSize(16, 16))
        copy_text.clicked.connect(
            lambda: self._copy(self.text_edit.toPlainText()))

        # ---- layout ----
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addLayout(header)
        layout.addWidget(self.warn)
        layout.addWidget(self.preview)

        layout.addWidget(_section("行内 LaTeX  $...$", self.inline_edit, copy_inline))
        layout.addWidget(_section("独立 LaTeX  $$...$$", self.display_edit, copy_display))
        layout.addWidget(_section("Mathpix Markdown (text)", self.text_edit, copy_text))

        bottom = QHBoxLayout()
        self.toast = QLabel("")
        self.toast.setStyleSheet("color: #28a745; font-weight: 600;")
        bottom.addWidget(self.toast, 1)

        if self._on_recapture is not None:
            recap = QPushButton("重新截图")
            recap.setIcon(icon("snip"))
            recap.setIconSize(QSize(16, 16))
            recap.clicked.connect(self._on_recapture)
            bottom.addWidget(recap)

        close = QPushButton("关闭")
        close.setIcon(icon("close"))
        close.setIconSize(QSize(16, 16))
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        layout.addLayout(bottom)

    # ---- public ------------------------------------------------------------

    def show_result(self, result: dict, from_cache: bool = False) -> None:
        latex = result.get("latex_styled") or ""
        latex = _strip_outer_dollars(latex)
        text = result.get("text") or ""
        confidence = result.get("confidence")
        is_handwritten = result.get("is_handwritten")
        is_printed = result.get("is_printed")

        self.inline_edit.setPlainText(f"${latex}$" if latex else "")
        self.display_edit.setPlainText(f"$${latex}$$" if latex else "")
        self.text_edit.setPlainText(text)

        meta_bits = []
        if confidence is not None:
            meta_bits.append(f"置信度: {confidence * 100:.1f}%")
        if is_handwritten:
            meta_bits.append("手写")
        elif is_printed:
            meta_bits.append("印刷")
        rid = result.get("request_id")
        if rid:
            meta_bits.append(f"req={rid[:8]}…")
        self.meta.setText("    ".join(meta_bits))

        if from_cache:
            self.cache_badge.show()
        else:
            self.cache_badge.hide()

        if confidence is not None and confidence < 0.5:
            self.warn.setText(
                f"⚠ 置信度 {confidence * 100:.0f}%,建议截取更清晰的区域。")
            self.warn.show()
        else:
            self.warn.hide()

        self._kick_preview(latex=latex, text=text)

        self.toast.setText("")
        self.adjustSize()
        self._center()
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- preview rendering ------------------------------------------------

    def _kick_preview(self, *, latex: str, text: str) -> None:
        # Decide what to render:
        # - text contains $-delimited math regions → render Mathpix Markdown
        # - text empty but latex_styled present → render latex_styled as math
        # - pure prose / empty → show a hint
        has_math_in_text = bool(text) and ("$" in text)
        if has_math_in_text:
            content, is_math = text, False
        elif latex:
            content, is_math = latex, True
        elif text:
            self._set_preview_message("(纯文本无需预览，直接在下方复制)")
            return
        else:
            self._set_preview_message("(空结果)")
            return

        if self._preview_is_web:
            self.preview.set_content(content, is_math=is_math)
        # else: QLabel fallback already shows the WebEngine-missing message

    def _set_preview_message(self, msg: str) -> None:
        if self._preview_is_web:
            self.preview.show_message(msg)
        else:
            self.preview.setText(msg)

    # ---- internal ----------------------------------------------------------

    def _copy(self, s: str) -> None:
        if not s:
            return
        QGuiApplication.clipboard().setText(s)
        self.toast.setText("已复制到剪贴板 ✓ 即将关闭…")
        QTimer.singleShot(220, self.close)

    def _center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        self.move(
            geo.center().x() - self.width() // 2,
            geo.center().y() - self.height() // 2,
        )


def _section(title: str, edit: QPlainTextEdit, copy_btn: QPushButton) -> QWidget:
    head = QHBoxLayout()
    label = QLabel(title)
    label.setProperty("role", "subheading")
    head.addWidget(label, 1)
    copy_btn.setFixedWidth(80)
    head.addWidget(copy_btn)

    box = QVBoxLayout()
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)
    box.addLayout(head)
    box.addWidget(edit)

    container = QWidget()
    container.setLayout(box)
    container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return container
