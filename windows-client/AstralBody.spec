# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AstralBody native Windows client (single-file .exe).

Build (from windows-client/, in the venv):
    .venv/Scripts/pyinstaller --noconfirm AstralBody.spec
Output: dist/AstralBody.exe
"""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("PySide6.QtCharts")
    + collect_submodules("aiohttp")
    + collect_submodules("sigstore")
    + ["PySide6.QtCharts", "websockets", "websockets.legacy", "websockets.legacy.client",
       "win_agent", "win_agent.agent", "win_agent.tools",
       "astral_client.phi_gate", "astral_client.audit_log", "astral_client.integrity",
       "psutil", "pyperclip", "sigstore"]
)

# Trim heavy, unused Qt modules to keep the binary lean.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick3D", "PySide6.QtMultimedia",
    "PySide6.QtPdf", "PySide6.QtPositioning", "PySide6.QtSql", "PySide6.QtTest",
    "tkinter", "PySide6.QtDesigner",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AstralBody",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # GUI app, no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
