"""Local copy of MathJax 3 for the web UI's formula rendering.

MathJax produces vector SVG output, which gives crisp formulas at any zoom
level and clean CJK + math mixing.

Installer builds bundle a pinned `tex-svg.js` (build.spec vendors it); on
first use it is copied into `%APPDATA%\\ocrmath\\mathjax\\`. Source runs
without a vendored copy download it once from cdn.jsdelivr.net instead,
verified against MATHJAX_SHA256. Either way later launches are offline.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from ocrmath.core import config

# Pinned: this script runs inside the preview page, so an unpinned "@3" tag
# would execute whatever the CDN serves next. Bump version + hash together.
MATHJAX_VERSION = "3.2.2"
MATHJAX_URL = (f"https://cdn.jsdelivr.net/npm/mathjax@{MATHJAX_VERSION}"
               f"/es5/tex-svg.js")
MATHJAX_SHA256 = (
    "d4295dc33744836935c1399feece5159577b34c5c8ffb9f1c6324cd82e03a882")
MATHJAX_FILENAME = "tex-svg.js"
# Anything smaller than this is almost certainly a partial download.
_MIN_BUNDLE_BYTES = 200_000


def cache_dir() -> Path:
    return config.CONFIG_PATH.parent / "mathjax"


def mathjax_path() -> Path:
    return cache_dir() / MATHJAX_FILENAME


def bundled_path() -> Path | None:
    """The tex-svg.js shipped with the app: PyInstaller's data dir in frozen
    builds, the vendor/ dir build.spec fills when running from source."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / "mathjax" / MATHJAX_FILENAME
    else:
        p = Path(__file__).resolve().parents[2] / "vendor" / MATHJAX_FILENAME
    return p if p.is_file() else None


def is_ready() -> bool:
    p = mathjax_path()
    try:
        return p.exists() and p.stat().st_size >= _MIN_BUNDLE_BYTES
    except OSError:
        return False


def install_bundled() -> bool:
    """Copy the bundled tex-svg.js into the cache dir. True on success."""
    src = bundled_path()
    if src is None:
        return False
    try:
        cache_dir().mkdir(parents=True, exist_ok=True)
        tmp = mathjax_path().with_suffix(".js.tmp")
        shutil.copyfile(src, tmp)
        tmp.replace(mathjax_path())
    except OSError as exc:
        sys.stderr.write(f"MathJax bundle copy failed: {exc}\n")
        return False
    return is_ready()


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
            digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
            if digest != MATHJAX_SHA256:
                tmp.unlink(missing_ok=True)
                self.failed.emit("下载内容校验失败 (SHA-256 不匹配)")
                return
            tmp.replace(target)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(str(target))


# One downloader for the whole process: several MathJaxViews created during
# the first launch would otherwise each fetch their own 1MB copy in parallel.
_shared_downloader: MathJaxDownloader | None = None


def downloader_running() -> bool:
    d = _shared_downloader
    return d is not None and d.isRunning()


def ensure_available(on_ready=None, on_failed=None) -> bool:
    """True if the script is on disk. Otherwise start the one shared download
    and report through the callbacks."""
    global _shared_downloader
    if is_ready() or install_bundled():
        return True
    d = _shared_downloader
    needs_start = d is None or not d.isRunning()
    if needs_start:
        d = MathJaxDownloader()
        _shared_downloader = d
    if on_ready:
        d.finished_ok.connect(on_ready)
    if on_failed:
        d.failed.connect(on_failed)
    if needs_start:
        d.start()
    return False
