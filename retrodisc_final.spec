# -*- mode: python ; coding: utf-8 -*-
# RetroDisc — FINAL STANDALONE SPEC
# ====================================
# Erzeugt dist\RetroDisc.exe
# Enthält: Python + Code + UI + FFmpeg.exe + FFprobe.exe + yt-dlp
# Kein Internet beim Endnutzer nötig.
# Größe: ~120-150 MB

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_all

HERE = Path(SPECPATH)
VENDOR = HERE / "vendor"

# Sicherstellen dass vendor/ existiert
if not (VENDOR / "ffmpeg.exe").exists():
    print("=" * 60)
    print("FEHLER: vendor/ffmpeg.exe nicht gefunden!")
    print("Bitte zuerst ausführen: python prepare_vendor.py")
    print("=" * 60)
    import sys; sys.exit(1)

# ── Einzubettende Dateien/Pakete ──────────────────────────────────────
ai_datas = []
ai_binaries = []
ai_hiddenimports = []
for package in ("faster_whisper", "ctranslate2", "tokenizers", "huggingface_hub", "av", "numpy"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
        ai_datas.extend(package_datas)
        ai_binaries.extend(package_binaries)
        ai_hiddenimports.extend(package_hidden)
    except Exception as exc:
        print(f"WARNUNG: {package} konnte nicht gesammelt werden: {exc}")

datas = [
    # ── UI ──
    (str(HERE / "src" / "ui" / "app.html"),    "src/ui"),
    (str(HERE / "src" / "ui" / "splash.html"), "src/ui"),

    # ── Assets ──
    (str(HERE / "assets"),                      "assets"),

    # ── FFmpeg Windows-Binaries (das Herzstück!) ──
    (str(VENDOR / "ffmpeg.exe"),   "vendor"),
    (str(VENDOR / "ffprobe.exe"),  "vendor"),
    (str(VENDOR / "yt-dlp.exe"),   "vendor"),
    (str(VENDOR / "dvdtools"),      "vendor/dvdtools"),
    (str(VENDOR / "whisper-base"),  "vendor/whisper-base"),

    # ── Python-Pakete die Datendateien brauchen ──
    *collect_data_files("pydantic"),
    *collect_data_files("certifi"),
    *collect_data_files("yt_dlp"),          # yt-dlp Extractor-Daten
] + ai_datas

# ── Hidden Imports ────────────────────────────────────────────────────
hiddenimports = [
    # RetroDisc
    "src", "src.core", "src.core.ffmpeg", "src.core.pipeline",
    "src.core.downloader", "src.core.disc",
    "src.services.converter", "src.services.search",
    "src.services.library", "src.services.dvd_workflow",
    "src.services.smart_edit", "src.services.subtitle",
    "src.services.upscaler", "src.services.assistant",
    "src.services.watch_folder", "src.services.ripper",
    "src.config.settings", "src.config.presets",
    "src.models.media", "src.utils.sound", "src.utils.mediainfo",
    "src.ui.desktop", "src.bootstrap",

    # PyWebView — Windows-Backends
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",

    # pydantic
    "pydantic", "pydantic.v1", "pydantic_core",

    # Netzwerk
    "httpx", "httpx._transports.default",
    "httpcore", "certifi", "charset_normalizer",

    # yt-dlp — alle Extraktoren
    "yt_dlp",
    "yt_dlp.extractor",
    "yt_dlp.extractor._extractors",
    "yt_dlp.extractor.youtube",
    "yt_dlp.extractor.ard",
    "yt_dlp.extractor.zdf",
    "yt_dlp.extractor.arte",
    "yt_dlp.extractor.generic",
    "yt_dlp.downloader",
    "yt_dlp.postprocessor",
    "yt_dlp.utils",

    # Audio
    "sounddevice", "soundfile", "_soundfile_data",

    # Standard
    "sqlite3", "wave", "asyncio", "threading",
    "zipfile", "urllib.request", "email.mime.text",
    "xml.etree.ElementTree",

    # structlog, rich, click
    "structlog", "rich", "rich.console", "click",
] + ai_hiddenimports

# ── Nicht benötigte Module ausschließen ───────────────────────────────
excludes = [
    "tkinter", "matplotlib", "scipy",
    "cv2", "torch", "tensorflow",
    "PIL", "Pillow",
    "pytest", "IPython", "jupyter",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "test", "unittest",
]

# ── Analysis ──────────────────────────────────────────────────────────
a = Analysis(
    [str(HERE / "retrodisc_launcher.py")],
    pathex=[str(HERE)],
    binaries=ai_binaries,
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

# ── EINE EINZIGE EXE ─────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,    # ← Alle Binaries direkt rein
    a.zipfiles,
    a.datas,       # ← Alle Daten direkt rein (inkl. ffmpeg.exe!)
    name="RetroDisc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,              # UPX-Kompression → 30-40% kleiner
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
        "ffmpeg.exe",      # ffmpeg nicht komprimieren (schadet Performance)
        "ffprobe.exe",
    ],
    runtime_tmpdir=None,
    console=False,         # Kein schwarzes Konsol-Fenster
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / "assets" / "retrodisc.ico"),
    version_file=str(HERE / "version_info.txt"),
    manifest=str(HERE / "retrodisc.manifest"),
)
