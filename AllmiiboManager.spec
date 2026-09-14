# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

import PySide6


pyside_directory = Path(PySide6.__file__).parent
runtime_names = (
    "concrt140.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)
qt_runtime_binaries = [
    (str(pyside_directory / name), ".")
    for name in runtime_names
    if (pyside_directory / name).is_file()
]

a = Analysis(
    ['allmiibo_gui.py'],
    pathex=[],
    binaries=qt_runtime_binaries,
    datas=[('assets/amiibo-app-icon-source.png', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AllmiiboManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/amiibo-app-icon.ico'],
)
