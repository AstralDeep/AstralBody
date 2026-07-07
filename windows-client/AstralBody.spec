# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AstralBody native Windows client (single-file .exe).

Build (from windows-client/, in the venv):
    .venv/Scripts/pyinstaller --noconfirm AstralBody.spec
Output: dist/AstralBody.exe
"""
import pathlib
import re

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
    VarStruct, VSVersionInfo,
)

# Single version source: astral_client/__init__.py. Read textually (SPECPATH
# is the spec's directory, injected by PyInstaller) — the spec is exec'd, so
# the package is not necessarily importable here.
__version__ = re.search(
    r'__version__\s*=\s*"([^"]+)"',
    (pathlib.Path(SPECPATH) / "astral_client" / "__init__.py").read_text(encoding="utf-8"),
).group(1)

# Windows VERSIONINFO resource derived from the single version constant, so
# the shipped exe's file properties (FileVersion/ProductVersion) always match
# astral_client.__version__ — the same constant the launch integrity check
# compares against the latest GitHub release tag.
_ver_tuple = tuple(int(p) for p in __version__.split(".")[:3]) + (0,)
version_res = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_ver_tuple, prodvers=_ver_tuple),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("ProductName", "AstralBody"),
            StringStruct("FileDescription", "AstralBody native Windows client"),
            StringStruct("FileVersion", __version__),
            StringStruct("ProductVersion", __version__),
            StringStruct("CompanyName", "AstralDeep"),
            StringStruct("OriginalFilename", "AstralBody.exe"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

hiddenimports = (
    collect_submodules("PySide6.QtCharts")
    + collect_submodules("aiohttp")
    + collect_submodules("sigstore")
    + ["PySide6.QtCharts", "websockets",
       "win_agent", "win_agent.agent", "win_agent.tools",
       "astral_client.phi_gate", "astral_client.audit_log", "astral_client.integrity",
       "astral_client.confirm",
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
    version=version_res,  # VERSIONINFO stamped from astral_client.__version__
)
