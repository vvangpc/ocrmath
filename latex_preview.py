"""Render a LaTeX expression — or a mixed Markdown blob — to a PNG.

matplotlib `mathtext` is a built-in subset of LaTeX. It supports:
- math regions delimited by single `$...$`
- regular text outside `$...$`
- common math syntax: super/subscripts, fractions, integrals, sums, greek
  letters, `\\frac`, `\\sqrt`, `\\begin{matrix}` etc.

It does NOT support:
- `$$...$$` display delimiters → we normalize them to `$...$` before rendering
- `\\begin{tabular}`, chemistry packages, custom user macros → these throw

Two modes:
- `is_math=True` (legacy): wrap the whole input in `$...$` and render as pure math
- `is_math=False`: treat input as Mathpix Markdown — text + inline math regions

We import matplotlib lazily inside the worker so app startup stays fast.
"""
from __future__ import annotations

import re

from PyQt6.QtCore import QThread, pyqtSignal


_DISPLAY_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)


def _strip_math_delim(s: str) -> str:
    s = s.strip()
    if s.startswith("$$") and s.endswith("$$"):
        return s[2:-2].strip()
    if s.startswith("$") and s.endswith("$"):
        return s[1:-1].strip()
    return s


def _normalize_for_mathtext(s: str) -> str:
    # mathtext doesn't understand $$...$$. Convert to $...$ so the math actually
    # renders (otherwise the $$ pair is read as an empty math span).
    return _DISPLAY_RE.sub(lambda m: f"${m.group(1).strip()}$", s)


_CJK_SETUP_DONE = False
_CJK_FONT_NAME: str | None = None


def _setup_cjk_font() -> str | None:
    """Configure matplotlib to use a CJK-capable font as fallback.

    Returns the font name that was selected, or None if no CJK font was found.
    Runs only once per process; safe to call multiple times.
    """
    global _CJK_SETUP_DONE, _CJK_FONT_NAME
    if _CJK_SETUP_DONE:
        return _CJK_FONT_NAME
    _CJK_SETUP_DONE = True
    try:
        import matplotlib
        from matplotlib import font_manager
    except ImportError:
        return None
    # Order: Windows-shipped fonts first, then common cross-platform CJK fonts
    candidates = [
        "Microsoft YaHei", "Microsoft YaHei UI",
        "SimHei", "SimSun", "NSimSun",
        "Microsoft JhengHei",
        "PingFang SC", "Heiti SC",
        "Noto Sans CJK SC", "Source Han Sans SC", "Source Han Sans CN",
        "WenQuanYi Micro Hei",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for cand in candidates:
        if cand in available:
            current = matplotlib.rcParams.get("font.sans-serif", [])
            if isinstance(current, str):
                current = [current]
            # Put the CJK font first; keep DejaVu Sans as backup for Latin glyphs
            new_list = [cand] + [f for f in current if f != cand]
            matplotlib.rcParams["font.sans-serif"] = new_list
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["axes.unicode_minus"] = False
            _CJK_FONT_NAME = cand
            return cand
    return None


def render_to_png(content: str, *, is_math: bool = True,
                  fontsize: int = 18, dpi: int = 160,
                  fg: str = "#222222",
                  max_chars: int = 1500) -> bytes:
    """Synchronous render. Raises ValueError on unsupported syntax / empty input.

    Args:
        content: the LaTeX expression (when is_math=True) or Mathpix Markdown
            text (when is_math=False).
        is_math: True → wrap content in `$...$` and render as pure math;
            False → render content directly with embedded `$math$` regions.
    """
    import io
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    _setup_cjk_font()  # idempotent; ensures CJK chars don't render as boxes

    raw = content.strip()
    if not raw:
        raise ValueError("empty expression")

    if is_math:
        expr = f"${_strip_math_delim(raw)}$"
    else:
        expr = _normalize_for_mathtext(raw)

    # Cap absurdly long content (a 5000-char text dump produces a multi-MB PNG)
    if len(expr) > max_chars:
        expr = expr[:max_chars] + "…"

    fig = Figure(dpi=dpi)
    fig.patch.set_alpha(0.0)
    canvas = FigureCanvasAgg(fig)  # noqa: F841 — registers backend
    txt = fig.text(0.0, 0.0, expr, fontsize=fontsize, color=fg, wrap=False)
    fig.canvas.draw()
    bbox = txt.get_window_extent()
    w_in = bbox.width / dpi + 0.15
    h_in = bbox.height / dpi + 0.15
    fig.set_size_inches(max(w_in, 0.3), max(h_in, 0.3))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                pad_inches=0.05, transparent=True)
    return buf.getvalue()


class LatexRenderWorker(QThread):
    """Render off the UI thread. Emits PNG bytes on success or error string."""

    finished_ok = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, content: str, *, is_math: bool = True,
                 fontsize: int = 18, dpi: int = 160, parent=None):
        super().__init__(parent)
        self._content = content
        self._is_math = is_math
        self._fontsize = fontsize
        self._dpi = dpi

    def run(self) -> None:
        try:
            png = render_to_png(self._content, is_math=self._is_math,
                                fontsize=self._fontsize, dpi=self._dpi)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(png)


if __name__ == "__main__":
    # Quick smoke test:
    #   python latex_preview.py math "E=mc^2" out.png
    #   python latex_preview.py md "Hello \$E=mc^2\$ world" out.png
    import sys
    if len(sys.argv) != 4:
        print("usage: python latex_preview.py <math|md> <content> <out.png>")
        sys.exit(2)
    mode, content, out = sys.argv[1], sys.argv[2], sys.argv[3]
    data = render_to_png(content, is_math=(mode == "math"))
    open(out, "wb").write(data)
    print(f"wrote {out} ({len(data)} bytes)")
