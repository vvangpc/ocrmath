# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ocrmath.

Build with:
    python -m PyInstaller build.spec --clean

Produces dist/ocrmath/ocrmath.exe (onedir layout).
The Inno Setup installer (installer.iss) bundles the whole dist/ocrmath/
folder into the user-installable setup .exe.

Side outputs (both gitignored):
  vendor/tex-svg.js      pinned MathJax, bundled so first launch is offline
  installer/version.iss  AppVersion from pyproject.toml for installer.iss
"""
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT))
from mathjax_view import MATHJAX_FILENAME, MATHJAX_SHA256, MATHJAX_URL  # noqa: E402

block_cipher = None


def _project_version() -> str:
    """pyproject.toml is the single source of the release version."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("build.spec: no version in pyproject.toml")
    return m.group(1)


def _write_installer_version() -> None:
    (ROOT / "installer" / "version.iss").write_text(
        f'#define AppVersion "{_project_version()}"\n', encoding="utf-8")


def _vendored_mathjax() -> Path:
    """Download the pinned MathJax once into vendor/, verified by SHA-256."""
    dest = ROOT / "vendor" / MATHJAX_FILENAME
    if dest.is_file() and \
            hashlib.sha256(dest.read_bytes()).hexdigest() == MATHJAX_SHA256:
        return dest
    print(f"build.spec: fetching {MATHJAX_URL}")
    with urllib.request.urlopen(MATHJAX_URL, timeout=60) as resp:
        data = resp.read()
    if hashlib.sha256(data).hexdigest() != MATHJAX_SHA256:
        raise SystemExit("build.spec: MathJax download failed its SHA-256 "
                         "check; not bundling an unverified script")
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(data)
    return dest


_write_installer_version()

# `keyboard` registers low-level Windows hooks via _winkeyboard module.
# QtWebEngine ships its own resources/locales that PyInstaller's PyQt6 hook
# already collects, so we don't list it here explicitly.
hiddenimports = (
    collect_submodules("keyboard")
    + collect_submodules("PyQt6.QtWebEngineCore")
    + collect_submodules("PyQt6.QtWebEngineWidgets")
)

# mathjax_view.bundled_path() looks for it under <_MEIPASS>/mathjax/.
datas = [(str(_vendored_mathjax()), "mathjax")]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Trim heavy unused libs that PyInstaller might over-include.
    excludes=[
        "tkinter", "test", "unittest", "pdb", "doctest",
        "PyQt5", "PySide2", "PySide6",
        "scipy", "numpy.f2py", "IPython",
    ],
    noarchive=False,
    # -OO bytecode (drops docstrings) — smaller PYZ. Keep strip/upx off:
    # both are known to corrupt Qt6 DLLs on Windows and trip AV heuristics.
    optimize=2,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ocrmath",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # windowed app, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ocrmath",
)
