#!/bin/bash
# RetroDisc — macOS Build (Intel + Apple Silicon M1/M2/M3)
# Ergebnis: dist/RetroDisc  (portable, alles drin)

set -e
echo ""
echo "╔══════════════════════════════════════╗"
echo "║  RetroDisc — macOS Build             ║"
echo "║  Intel + Apple Silicon M1/M2/M3      ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Architektur erkennen
ARCH=$(uname -m)
echo "  Architektur: $ARCH"

# Python prüfen (Homebrew oder System)
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/dev/null; then
    PYTHON=python
else
    echo "  FEHLER: Python nicht gefunden!"
    echo "  brew install python3"
    exit 1
fi
echo "  OK: $($PYTHON --version)"

# 1. Dependencies
echo ""
echo "[1/4] Pakete installieren..."
$PYTHON -m pip install pyinstaller pywebview pydantic structlog rich \
    click httpx yt-dlp sounddevice soundfile certifi \
    openai-whisper scenedetect librosa --quiet
echo "  OK"

# 2. FFmpeg für macOS
echo ""
echo "[2/4] FFmpeg laden..."
mkdir -p vendor

if [ ! -f "vendor/ffmpeg" ]; then
    echo "  Lade ffmpeg von evermeet.cx..."
    curl -L "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip" \
         -o /tmp/ffmpeg.zip --progress-bar
    cd vendor && unzip -o /tmp/ffmpeg.zip ffmpeg
    chmod +x ffmpeg; cd ..
    echo "  OK: $(du -sh vendor/ffmpeg | cut -f1)"
else
    echo "  OK: ffmpeg bereits vorhanden"
fi

if [ ! -f "vendor/ffprobe" ]; then
    echo "  Lade ffprobe..."
    curl -L "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip" \
         -o /tmp/ffprobe.zip --progress-bar
    cd vendor && unzip -o /tmp/ffprobe.zip ffprobe
    chmod +x ffprobe; cd ..
    echo "  OK: $(du -sh vendor/ffprobe | cut -f1)"
else
    echo "  OK: ffprobe bereits vorhanden"
fi

# 3. PyInstaller
echo ""
echo "[3/4] App bauen (bitte warten)..."

$PYTHON -m PyInstaller \
    --onefile \
    --windowed \
    --name RetroDisc \
    --icon "assets/retrodisc.icns" \
    --add-data "src/ui/app.html:src/ui" \
    --add-data "src/ui/splash.html:src/ui" \
    --add-data "assets:assets" \
    --add-data "vendor/ffmpeg:vendor" \
    --add-data "vendor/ffprobe:vendor" \
    --hidden-import "src.core.ffmpeg" \
    --hidden-import "src.core.pipeline" \
    --hidden-import "src.core.downloader" \
    --hidden-import "src.core.disc" \
    --hidden-import "src.services.converter" \
    --hidden-import "src.services.search" \
    --hidden-import "src.services.library" \
    --hidden-import "src.services.dvd_workflow" \
    --hidden-import "src.services.smart_edit" \
    --hidden-import "src.services.subtitle" \
    --hidden-import "src.services.upscaler" \
    --hidden-import "src.services.assistant" \
    --hidden-import "src.services.watch_folder" \
    --hidden-import "src.config.settings" \
    --hidden-import "src.config.presets" \
    --hidden-import "src.models.media" \
    --hidden-import "src.utils.sound" \
    --hidden-import "src.bootstrap" \
    --hidden-import "webview.platforms.cocoa" \
    --hidden-import "pydantic" \
    --hidden-import "pydantic_core" \
    --hidden-import "yt_dlp" \
    --hidden-import "yt_dlp.extractor._extractors" \
    --collect-data "pydantic" \
    --collect-data "certifi" \
    --collect-data "yt_dlp" \
    --exclude-module tkinter \
    --exclude-module matplotlib \
    --exclude-module pytest \
    --noconfirm \
    retrodisc_portable.py

# 4. Ergebnis
echo ""
if [ -f "dist/RetroDisc" ]; then
    SIZE=$(du -sh dist/RetroDisc | cut -f1)
    echo "╔══════════════════════════════════════╗"
    echo "║  FERTIG!                             ║"
    echo "║                                      ║"
    echo "║  dist/RetroDisc  ($SIZE)             ║"
    echo "║                                      ║"
    echo "║  Portable — einfach doppelklicken    ║"
    echo "║  Oder: ./dist/RetroDisc              ║"
    echo "╚══════════════════════════════════════╝"
    echo ""
    read -p "Jetzt starten? (j/n): " GO
    if [ "$GO" = "j" ]; then
        open dist/RetroDisc 2>/dev/null || ./dist/RetroDisc
    fi
else
    echo "FEHLER: dist/RetroDisc nicht gefunden!"
    exit 1
fi
