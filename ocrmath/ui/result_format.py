"""State of the compact result window, independent of how it is drawn.

The web page renders `FloatModel.snapshot()` and sends user actions back, so
every rule about what may be copied or clicked lives here and can be tested
without a browser.
"""
from __future__ import annotations

import re

from ocrmath.core import config


def strip_outer_dollars(s: str) -> str:
    s = s.strip()
    for start, end in (("$$", "$$"), ("$", "$"), (r"\[", r"\]"), (r"\(", r"\)")):
        if s.startswith(start) and s.endswith(end) and len(s) >= len(start) + len(end):
            return s[len(start):-len(end)].strip()
    return s


def is_formula(text: str, latex: str) -> bool:
    if not latex:
        return False
    return not text.strip() or text.strip() == latex.strip() or bool(re.fullmatch(
        r"\s*(?:\$\$[^$]+\$\$|\$[^$]+\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))\s*",
        text, re.DOTALL))


def history_copy_text(latex: str, text: str) -> str:
    """What the copy button of a history row puts on the clipboard."""
    return f"${strip_outer_dollars(latex)}$" if latex else text


class FloatModel:
    LOW_CONFIDENCE = .5

    def __init__(self):
        self.state = "empty"          # empty | loading | result | error
        self.busy = False
        self.format = "preview"       # preview | latex | markdown
        style = config.get_ui_state().get("latex_style")
        self.latex_style = style if style in (0, 1, 2) else 0   # plain, $…$, $$…$$
        self.latex = self.text = ""
        self.kind = "latex"           # what this result is copied as
        self.meta = ""
        self.warning = ""
        self.warning_is_error = False
        self.from_cache = False
        self.source: bytes | None = None
        self.source_rev = 0
        self.task_count = 0

    # ---- transitions -------------------------------------------------------

    def show_ready(self) -> None:
        if self.state not in ("result", "error", "loading"):
            self.state = "empty"

    def show_loading(self) -> None:
        self.state = "loading"
        self.latex = self.text = self.meta = self.warning = ""
        self.format = "preview"
        self.from_cache = False
        self.busy = True

    def show_error(self, message: str) -> None:
        self.state = "error"
        self.warning, self.warning_is_error = message, True
        self.latex = self.text = self.meta = ""

    def show_result(self, result: dict, from_cache: bool = False) -> None:
        self.state, self.from_cache = "result", from_cache
        self.latex = strip_outer_dollars(result.get("latex_styled") or "")
        self.text = result.get("text") or ""
        self.kind = "latex" if is_formula(self.text, self.latex) else "markdown"
        self.format = "preview"
        self.warning, self.warning_is_error = "", False
        llm = result.get("_provider") == "llm"
        confidence = None if llm else result.get("confidence")
        if confidence is not None and confidence < self.LOW_CONFIDENCE:
            self.warning = f"置信度 {confidence * 100:.0f}%，复制前请核对原图。"
        self.meta = self._meta(result, llm, from_cache)

    @staticmethod
    def _meta(result: dict, llm: bool, from_cache: bool) -> str:
        if from_cache:
            return "本地缓存 · 本次未调用识别服务"
        parts = []
        if llm:
            parts.append(result.get("model") or "大模型")
            usage = result.get("usage") or {}
            if "input_tokens" in usage and "output_tokens" in usage:
                parts.append(f"输入 {usage['input_tokens']:,} / 输出 {usage['output_tokens']:,} Token")
            if result.get("_cost_usd") is not None:
                parts.append(f"${result['_cost_usd']:.3f}")
        else:
            parts.append("Mathpix")
            if result.get("is_handwritten"):
                parts.append("手写")
            elif result.get("is_printed"):
                parts.append("印刷体")
            if result.get("confidence") is not None:
                parts.append(f"置信度 {result['confidence'] * 100:.1f}%")
            parts.append(f"${config.get_image_price():.3f}")
        return " · ".join(parts)

    def set_source(self, png: bytes | None) -> None:
        self.source = png or None
        self.source_rev += 1

    def set_busy(self, busy: bool) -> None:
        self.busy = busy

    def select_format(self, key: str) -> None:
        if key in self.formats():
            self.format = key

    def set_latex_style(self, index: int) -> None:
        if index in (0, 1, 2):
            self.latex_style = index
            config.update_ui_state(latex_style=index)

    # ---- derived -----------------------------------------------------------

    def formats(self) -> list[str]:
        """A formula is LaTeX and mixed text is Markdown: never offer both,
        they would only differ by their delimiters."""
        if self.state != "result":
            return []
        return ["preview", "latex" if self.kind == "latex" else "markdown"]

    def copy_text(self) -> str:
        if self.state != "result":
            return ""
        if self.kind == "latex":
            # Applies from the preview too: the remembered style must spare
            # the user from opening the LaTeX tab before every copy.
            if self.latex_style == 1:
                return f"${self.latex}$"
            if self.latex_style == 2:
                return f"$${self.latex}$$"
            return self.latex
        return self.text or (f"$${self.latex}$$" if self.latex else "")

    def primary_action(self) -> str | None:
        """capture | retry | copy, or None while nothing may be done."""
        if self.busy:
            return None
        if self.state == "empty":
            return "capture"
        if self.state == "error":
            return "retry"
        if self.state == "result" and self.copy_text():
            return "copy"
        return None

    def _primary_label(self) -> str:
        return {"empty": "截图识别", "loading": "识别中…", "error": "重试原图"}.get(
            self.state, "复制 LaTeX" if self.kind == "latex" else "复制 Markdown")

    def snapshot(self) -> dict:
        provider = config.get_provider()
        hotkey = config.keyboard_to_qt(config.get_hotkey())
        pure = self.kind == "latex"
        meta = self.meta
        if self.state == "empty":
            meta = hotkey
        elif self.state == "loading":
            meta = provider_label(provider)
        preview = None
        if self.state == "result":
            content = self.latex if pure else (self.text or self.latex)
            preview = {"content": content, "is_math": pure}
        return {
            "state": self.state,
            "preview": preview,
            "code": self.copy_text() if self.format != "preview" else "",
            "formats": self.formats(),
            "format": self.format,
            "latex_style": self.latex_style,
            "primary": {"label": self._primary_label(),
                        "enabled": self.primary_action() is not None},
            "meta": meta,
            "warning": self.warning,
            "warning_is_error": self.warning_is_error,
            "can_recapture": self.state in ("result", "error") and not self.busy,
            "recapture_hint": hotkey,
            "provider": {"key": provider, "label": "大模型" if provider == "llm" else "Mathpix",
                         "title": provider_label(provider), "enabled": not self.busy},
            "has_source": self.source is not None,
            "source_rev": self.source_rev,
            "task_count": self.task_count,
        }


def provider_label(provider: str) -> str:
    return "大模型 · " + config.get_llm()["model"] if provider == "llm" else "Mathpix"
