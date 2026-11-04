# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller fast_object_tracker.spec
# Bundles PySide6, OpenCV, torch (CPU) and ultralytics.  Model weights are NOT
# bundled; the base model downloads on first use next to the exe.

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
root = os.path.abspath(".")

datas = [(os.path.join(root, "assets", "icon.png"), "assets")]
datas += collect_data_files("ultralytics", includes=["**/*.yaml"])
hiddenimports = collect_submodules("ultralytics") + ["serial", "serial.tools.list_ports"]

a = Analysis(
    [os.path.join(root, "launcher.py")],
    pathex=[os.path.join(root, "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "scipy", "IPython", "notebook", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia"],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="FASTObjectTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(root, "assets", "icon.ico"),
)
