# -*- mode: python ; coding: utf-8 -*-
# RetroDisc — PyInstaller Spec File
# Erstellt die retrodisc.exe für Windows
#
# Verwendung:
#   pyinstaller retrodisc.spec
#
# Das erzeugt:
#   dist/RetroDisc/retrodisc.exe   (+ alle DLLs)
#   dist/RetroDisc/src/ui/app.html
#   dist/RetroDisc/tools/           (FFmpeg etc. werden beim ersten Start geladen)

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Pfade ─────────────────────────────────────────────────────────────
HERE = Path(SPECPATH)

# ── Alle src/ui HTML-Dateien einschließen ─────────────────────────────
datas = [
    # HTML UI
    (str(HERE / "src" / "ui" / "app.html"),     "src/ui"),
    (str(HERE / "src" / "ui" / "splash.html"),  "src/ui"),
    # Assets
    (str(HERE / "assets"),                       "assets"),
]

# pydantic Daten
datas += collect_data_files("pydantic")

# ── Hidden Imports ────────────────────────────────────────────────────
# Alle Module die dynamisch importiert werden und PyInstaller
# nicht automatisch erkennt
hiddenimports = [
    # RetroDisc Module
    "src",
    "src.core.ffmpeg",
    "src.core.pipeline",
    "src.core.downloader",
    "src.core.disc",
    "src.services.converter",
    "src.services.search",
    "src.services.library",
    "src.services.dvd_workflow",
    "src.services.smart_edit",
    "src.services.subtitle",
    "src.services.upscaler",
    "src.services.assistant",
    "src.services.watch_folder",
    "src.config.settings",
    "src.config.presets",
    "src.models.media",
    "src.utils.sound",
    "src.utils.mediainfo",
    "src.ui.desktop",
    "src.bootstrap",
    # Externe Libraries
    "pydantic",
    "pydantic.v1",
    "structlog",
    "click",
    "rich",
    "httpx",
    "httpx._transports.default",
    "yt_dlp",
    "yt_dlp.extractor",
    "webview",
    "webview.platforms.winforms",  # Windows-spezifisch
    "webview.platforms.edgechromium",
    "sounddevice",
    "soundfile",
    "sqlite3",
    "wave",
    "asyncio",
]

# ── Analysis ─────────────────────────────────────────────────────────
a = Analysis(
    [str(HERE / "retrodisc.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Nicht benötigte Module ausschließen (kleinere EXE)
        "tkinter",
        "matplotlib",
        "scipy",
        "PIL",
        "cv2",
        "torch",
        "numpy",   # Nur wenn kein AI-Feature genutzt wird
        "pytest",
        "IPython",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── PYZ ───────────────────────────────────────────────────────────────
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# ── EXE ───────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="retrodisc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # UPX-Kompression für kleinere Datei
    console=False,               # Kein Konsolfenster (Windows GUI App)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / "assets" / "retrodisc.ico"),  # App-Icon
    version_file=str(HERE / "version_info.txt"),  # Windows Versioninfo
)

# ── Collect (Ordner-Distribution) ────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RetroDisc",
)
