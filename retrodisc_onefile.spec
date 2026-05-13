# -*- mode: python ; coding: utf-8 -*-
# RetroDisc — ONE FILE EXE Spec
# ================================
# Erzeugt EINE EINZIGE RetroDisc.exe (~30-40 MB)
# Keine DLLs, kein Ordner daneben — nur die EXE.
#
# Auf Windows ausführen:
#   pip install pyinstaller pywebview pydantic structlog rich click httpx yt-dlp sounddevice soundfile
#   pyinstaller retrodisc_onefile.spec
#
# Ergebnis: dist/RetroDisc.exe

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_all

HERE = Path(SPECPATH)

# ── Alle Daten die in die EXE eingebettet werden ──────────────────────
datas = [
    # Die UI HTML-Dateien
    (str(HERE / "src" / "ui" / "app.html"),    "src/ui"),
    (str(HERE / "src" / "ui" / "splash.html"), "src/ui"),
    # Assets (Icon, Sounds)
    (str(HERE / "assets"),                      "assets"),
    # Pydantic braucht seine Daten-Dateien
    *collect_data_files("pydantic"),
]

# certifi für HTTPS (wichtig für Downloads)
try:
    datas += collect_data_files("certifi")
except Exception:
    pass

# ── Hidden Imports ────────────────────────────────────────────────────
hiddenimports = [
    # RetroDisc eigene Module
    "src", "src.core", "src.core.ffmpeg", "src.core.pipeline",
    "src.core.downloader", "src.core.disc",
    "src.services.converter", "src.services.search",
    "src.services.library", "src.services.dvd_workflow",
    "src.services.smart_edit", "src.services.subtitle",
    "src.services.upscaler", "src.services.assistant",
    "src.services.watch_folder",
    "src.config.settings", "src.config.presets",
    "src.models.media", "src.utils.sound",
    "src.utils.mediainfo", "src.bootstrap",
    # PyWebView — Windows-Backends
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "webview.platforms.cef",
    # Pydantic
    "pydantic", "pydantic.v1",
    "pydantic_core",
    # Netzwerk
    "httpx", "httpx._transports.default",
    "httpcore",
    "certifi",
    "charset_normalizer",
    # yt-dlp (viele dynamische Importe)
    "yt_dlp",
    "yt_dlp.extractor",
    "yt_dlp.extractor.youtube",
    "yt_dlp.extractor.generic",
    "yt_dlp.downloader",
    "yt_dlp.postprocessor",
    # Audio
    "sounddevice",
    "soundfile",
    "_soundfile_data",
    # Standard-Library
    "sqlite3", "wave", "asyncio", "threading",
    "zipfile", "urllib.request",
    "email.mime.text",
    "email.mime.multipart",
    "xml.etree.ElementTree",
    # structlog
    "structlog",
    # rich
    "rich", "rich.console", "rich.traceback",
    # click
    "click",
]

# ── Excludes (nicht gebraucht → kleinere EXE) ─────────────────────────
excludes = [
    "tkinter", "matplotlib", "scipy",
    "numpy", "cv2", "torch", "tensorflow",
    "PIL", "Pillow",
    "pytest", "IPython", "jupyter",
    "PyQt5", "PyQt6", "PySide2", "PySide6",
    "wx",
]

# ── Analysis ──────────────────────────────────────────────────────────
a = Analysis(
    [str(HERE / "retrodisc_launcher.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data)

# ── ONEFILE EXE ───────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,     # ← Binaries direkt rein (kein COLLECT)
    a.zipfiles,     # ← ZIPs direkt rein
    a.datas,        # ← Daten direkt rein
    name="RetroDisc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,             # UPX-Kompression
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
    ],
    runtime_tmpdir=None,  # Entpackt in %TEMP%\RetroDisc bei jedem Start
    console=False,        # Kein Konsol-Fenster
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / "assets" / "retrodisc.ico"),
    version_file=str(HERE / "version_info.txt"),
    # Windows-Manifest für High-DPI und UAC
    manifest=str(HERE / "retrodisc.manifest"),
)
