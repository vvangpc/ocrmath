# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ocrmath.

Build with:
    python -m PyInstaller build.spec --clean

Produces dist/ocrmath/ocrmath.exe (onedir layout).
The Inno Setup installer (installer.iss) bundles the whole dist/ocrmath/
folder into the user-installable setup .exe.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# `keyboard` registers low-level Windows hooks via _winkeyboard module.
# QtWebEngine ships its own resources/locales that PyInstaller's PyQt6 hook
# already collects, so we don't list it here explicitly.
hiddenimports = (
    collect_submodules("keyboard")
    + collect_submodules("PyQt6.QtWebEngineCore")
    + collect_submodules("PyQt6.QtWebEngineWidgets")
)

datas = []

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
    optimize=0,
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
