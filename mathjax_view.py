"""LaTeX preview rendered by MathJax 3 inside a QWebEngineView.

MathJax produces vector SVG output, which gives crisp formulas at any zoom
level and clean CJK + math mixing (the page's font stack handles the text
parts; SVG handles the math).

On first launch, the widget downloads `tex-svg.js` (~1 MB) from
cdn.jsdelivr.net into `%APPDATA%\\ocrmath\\mathjax\\`. Subsequent launches
load it from disk — fully offline.

Public surface:
    MathJaxView          # QWebEngineView subclass with set_content()
    MathJaxDownloader    # QThread that fetches tex-svg.js
    is_ready() -> bool   # true if the JS bundle is on disk
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl, QThread, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE_OK = True
except ImportError:  # pragma: no cover — caller checks WEBENGINE_AVAILABLE
    QWebEngineView = None  # type: ignore[assignment,misc]
    _WEBENGINE_OK = False

import config

WEBENGINE_AVAILABLE = _WEBENGINE_OK
MATHJAX_URL = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"
MATHJAX_FILENAME = "tex-svg.js"
HTML_FILENAME = "preview.html"
# Anything smaller than this is almost certainly a partial download.
_MIN_BUNDLE_BYTES = 200_000


def cache_dir() -> Path:
    return config.CONFIG_PATH.parent / "mathjax"


def mathjax_path() -> Path:
    return cache_dir() / MATHJAX_FILENAME


def html_path() -> Path:
    return cache_dir() / HTML_FILENAME


def is_ready() -> bool:
    p = mathjax_path()
    try:
        return p.exists() and p.stat().st_size >= _MIN_BUNDLE_BYTES
    except OSError:
        return False


# ---- HTML template ---------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {
  margin: 0; padding: 12px;
  font-family: "Microsoft YaHei", "Microsoft YaHei UI", "PingFang SC",
               "Segoe UI", sans-serif;
  font-size: 16px; color: #222;
  background: white;
  word-wrap: break-word;
}
#content { text-align: center; }
#content.left { text-align: left; }
mjx-container { font-size: 1.05em !important; }
.error {
  color: #b85a00;
  font-size: 13px;
  text-align: center;
  padding: 8px;
}
</style>
<script>
window.MathJax = {
  tex: {
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true
  },
  svg: { fontCache: 'local' },
  startup: {
    typeset: false,
    ready: () => {
      MathJax.startup.defaultReady();
      window._mjx_ready = true;
      if (window._mjx_pending) {
        const p = window._mjx_pending;
        window._mjx_pending = null;
        setContent(p.text, p.isMath);
      }
    }
  }
};
</script>
<script src="__MATHJAX_FILE__"></script>
</head>
<body>
<div id="content"></div>
<script>
function setContent(text, isMath) {
  if (!window._mjx_ready) {
    window._mjx_pending = { text: text, isMath: isMath };
    return;
  }
  const div = document.getElementById('content');
  div.classList.toggle('left', !isMath);
  div.textContent = isMath ? ('$$' + text + '$$') : text;
  if (window.MathJax && MathJax.typesetClear) {
    MathJax.typesetClear([div]);
  }
  if (window.MathJax && MathJax.typesetPromise) {
    MathJax.typesetPromise([div]).catch(function (e) {
      div.innerHTML = '';
      const err = document.createElement('div');
      err.className = 'error';
      err.textContent = '⚠ 渲染失败: ' + (e && e.message ? e.message : e);
      div.appendChild(err);
    });
  }
}
function showMessage(msg) {
  const div = document.getElementById('content');
  div.classList.add('left');
  div.textContent = msg;
}
</script>
</body>
</html>
"""


def _write_html_template() -> Path:
    """Write the HTML to the cache dir and return its path. Skips the write
    when the on-disk copy already matches, so template tweaks still ship
    without manual cache cleanup but unchanged views cost no disk write."""
    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    html = _HTML_TEMPLATE.replace("__MATHJAX_FILE__", MATHJAX_FILENAME)
    p = html_path()
    try:
        if p.read_text(encoding="utf-8") == html:
            return p
    except OSError:
        pass
    p.write_text(html, encoding="utf-8")
    return p


# ---- downloader ------------------------------------------------------------


class MathJaxDownloader(QThread):
    finished_ok = pyqtSignal(str)              # local path to tex-svg.js
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)            # bytes_done, bytes_total

    def run(self) -> None:
        try:
            import requests
            cache_dir().mkdir(parents=True, exist_ok=True)
            target = mathjax_path()
            tmp = target.with_suffix(target.suffix + ".tmp")
            with requests.get(MATHJAX_URL, stream=True, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                done = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if self.isInterruptionRequested():
                            try:
                                tmp.unlink(missing_ok=True)
                            except Exception:
                                pass
                            return
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                        self.progress.emit(done, total)
            if tmp.stat().st_size < _MIN_BUNDLE_BYTES:
                tmp.unlink(missing_ok=True)
                self.failed.emit("下载内容过小，可能不完整")
                return
            tmp.replace(target)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(str(target))


# One downloader for the whole process: several MathJaxViews created during
# the first launch would otherwise each fetch their own 1MB copy in parallel.
_shared_downloader: MathJaxDownloader | None = None


# ---- widget ----------------------------------------------------------------


if WEBENGINE_AVAILABLE:

    class MathJaxView(QWebEngineView):  # type: ignore[misc,valid-type]
        """Renders LaTeX or Mathpix Markdown via MathJax 3 (SVG output)."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumHeight(96)
            self.setMaximumHeight(320)
            self.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Preferred)
            self._page_loaded = False
            self._pending: tuple[str, bool] | None = None
            self._pending_msg: str | None = None
            self._downloader: MathJaxDownloader | None = None
            self.loadFinished.connect(self._on_load_finished)
            self._render_or_download()

        # ---- public ---------------------------------------------------------

        def set_content(self, text: str, is_math: bool = True) -> None:
            """Render `text` as math (when is_math) or as Mathpix Markdown."""
            if not is_ready():
                # Page is showing the placeholder; keep the request for after
                # the download finishes.
                self._pending = (text, is_math)
                return
            if not self._page_loaded:
                self._pending = (text, is_math)
                return
            js = "setContent({}, {});".format(
                json.dumps(text), "true" if is_math else "false")
            self.page().runJavaScript(js)

        def show_message(self, msg: str) -> None:
            if not self._page_loaded:
                self._pending_msg = msg
                return
            self.page().runJavaScript(
                "showMessage({});".format(json.dumps(msg)))

        # ---- internals ------------------------------------------------------

        def _render_or_download(self) -> None:
            if is_ready():
                self._load_page()
                return
            self._load_placeholder("正在下载 MathJax (~1MB)，仅首次需要…")
            self._kick_download()

        def _load_page(self) -> None:
            html_file = _write_html_template()
            self._page_loaded = False
            self.load(QUrl.fromLocalFile(str(html_file)))

        def _load_placeholder(self, msg: str) -> None:
            cache_dir().mkdir(parents=True, exist_ok=True)
            placeholder = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "<style>body{font-family:'Microsoft YaHei',sans-serif;"
                "color:#666;text-align:center;padding:24px;font-size:14px;"
                "background:white;}</style></head><body>"
                f"<div>{msg}</div></body></html>"
            )
            self._page_loaded = True
            self.setHtml(placeholder, QUrl.fromLocalFile(str(cache_dir()) + "/"))

        def _kick_download(self) -> None:
            global _shared_downloader
            d = _shared_downloader
            needs_start = d is None or not d.isRunning()
            if needs_start:
                d = MathJaxDownloader()
                _shared_downloader = d
            d.finished_ok.connect(self._on_download_ok)
            d.failed.connect(self._on_download_fail)
            self._downloader = d
            if needs_start:
                d.start()

        def _on_download_ok(self, _path: str) -> None:
            self._downloader = None
            self._load_page()

        def _on_download_fail(self, msg: str) -> None:
            self._downloader = None
            sys.stderr.write(f"MathJax download failed: {msg}\n")
            self._load_placeholder(f"⚠ MathJax 下载失败: {msg}")

        def _on_load_finished(self, ok: bool) -> None:
            self._page_loaded = bool(ok)
            if not ok:
                return
            if self._pending is not None:
                text, is_math = self._pending
                self._pending = None
                self._pending_msg = None
                self.set_content(text, is_math)
            elif self._pending_msg is not None:
                msg = self._pending_msg
                self._pending_msg = None
                self.show_message(msg)

else:  # pragma: no cover

    class MathJaxView:  # type: ignore[no-redef]
        """Fallback stub that raises on instantiation if WebEngine is missing."""

        def __init__(self, *_a, **_kw):
            raise RuntimeError(
                "PyQt6-WebEngine 未安装，无法显示 LaTeX 预览。"
                "请运行: pip install PyQt6-WebEngine")
