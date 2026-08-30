# RetroDisc — Portable App bauen mit Qwen

## Für Qwen: Das ist dein Auftrag

Baue aus diesem Python-Quellcode eine portable Standalone-App:
- **Windows**: `dist/RetroDisc.exe`  (~120-150 MB, portable)
- **macOS M1/M2**: `dist/RetroDisc`  (~100-130 MB, portable)

Beide laufen ohne Installation, ohne Python, ohne Internet.

---

## Projektstruktur

```
retrodisc/
├── retrodisc_portable.py     ← HAUPTDATEI (Entry Point für PyInstaller)
├── BUILD_WINDOWS.bat         ← Windows Build-Script
├── BUILD_MACOS.sh            ← macOS Build-Script
├── prepare_vendor.py         ← Lädt FFmpeg herunter
├── src/
│   ├── core/
│   │   ├── ffmpeg.py         ← FFmpeg-Wrapper (Konvertierung)
│   │   ├── pipeline.py       ← Job-Queue
│   │   ├── downloader.py     ← yt-dlp Downloads
│   │   └── disc.py           ← DVD/Blu-ray Authoring
│   ├── services/
│   │   ├── converter.py      ← Konvertierungs-Service
│   │   ├── search.py         ← Mediensuche
│   │   ├── library.py        ← Media-Bibliothek
│   │   ├── dvd_workflow.py   ← DVD-Erstellungs-Workflow
│   │   ├── smart_edit.py     ← KI Auto-Edit
│   │   ├── subtitle.py       ← Whisper Untertitel
│   │   ├── upscaler.py       ← Real-ESRGAN Upscaling
│   │   └── assistant.py      ← Ollama KI-Assistent
│   ├── ui/
│   │   ├── app.html          ← Komplette UI (Windows XP Style, 2700 Zeilen)
│   │   └── splash.html       ← Startbildschirm
│   ├── config/
│   │   ├── settings.py       ← App-Einstellungen (Pydantic)
│   │   └── presets.py        ← 19 Konvertierungs-Presets
│   └── models/
│       └── media.py          ← Datenmodelle
├── assets/
│   └── retrodisc.ico         ← App-Icon
└── vendor/                   ← FFmpeg kommt hierher (prepare_vendor.py)
```

---

## Schritt 1: Projekt entpacken

```bash
# TAR entpacken
tar -xzf retrodisc-portable.tar.gz
cd retrodisc
```

---

## Schritt 2: Auf Windows bauen

```cmd
# Doppelklick auf:
BUILD_WINDOWS.bat

# Oder manuell:
pip install pyinstaller pywebview pydantic structlog rich click httpx yt-dlp sounddevice soundfile certifi
python prepare_vendor.py
python -m PyInstaller --onefile --windowed --name RetroDisc --add-data "src/ui/app.html;src/ui" --add-data "vendor/ffmpeg.exe;vendor" --add-data "vendor/ffprobe.exe;vendor" --hidden-import "src.core.ffmpeg" --hidden-import "yt_dlp" --hidden-import "yt_dlp.extractor._extractors" --hidden-import "pydantic" --hidden-import "webview.platforms.winforms" --collect-data "yt_dlp" --noconfirm retrodisc_portable.py
```

Ergebnis: `dist\RetroDisc.exe`

---

## Schritt 3: Auf macOS M1/M2 bauen

```bash
chmod +x BUILD_MACOS.sh
./BUILD_MACOS.sh

# Oder manuell:
pip3 install pyinstaller pywebview pydantic structlog rich click httpx yt-dlp sounddevice soundfile certifi
# FFmpeg laden:
curl -L "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip" -o /tmp/ffmpeg.zip
cd vendor && unzip /tmp/ffmpeg.zip && chmod +x ffmpeg && cd ..

python3 -m PyInstaller --onefile --windowed --name RetroDisc \
    --add-data "src/ui/app.html:src/ui" \
    --add-data "vendor/ffmpeg:vendor" \
    --hidden-import "src.core.ffmpeg" \
    --hidden-import "yt_dlp" \
    --hidden-import "webview.platforms.cocoa" \
    --collect-data "yt_dlp" \
    --noconfirm retrodisc_portable.py
```

Ergebnis: `dist/RetroDisc`

---

## Was ist in der fertigen App?

| Feature | Status |
|---------|--------|
| Konvertierung (25 Formate) | ✓ FFmpeg eingebettet |
| DVD/Blu-ray brennen | ✓ dvdauthor (muss installiert sein) |
| Download YouTube/Mediathek | ✓ yt-dlp eingebettet |
| Mediensuche (ARD/ZDF/Arte) | ✓ |
| KI Auto-Edit (Highlights) | ✓ PySceneDetect + Librosa |
| Whisper Untertitel | ✓ Modell wird beim 1. Aufruf geladen |
| Video Trim/Merge | ✓ |
| DVD-Menü Designer | ✓ |
| Media Library | ✓ SQLite |
| Watch Folder | ✓ |
| Windows XP UI | ✓ |
| Schaf-Maskottchen | ✓ |
| Fertig-Sound (Jingle) | ✓ |

## Portable-Verhalten

Beim ersten Start wird in einem `RetroDisc_Data/`-Ordner
neben der EXE folgendes angelegt:
```
RetroDisc_Data/
├── settings.json
├── library.db
├── logs/retrodisc.log
├── Output/       ← Konvertierte Dateien
├── Downloads/    ← Heruntergeladene Dateien
└── Temp/         ← Temporäre Dateien
```
→ Komplett portable: App + Data-Ordner auf USB-Stick kopieren, fertig.

## Troubleshooting für Qwen

**ImportError: No module named 'src'**
→ `retrodisc_portable.py` muss im Projektordner ausgeführt werden

**WebView2 nicht gefunden (Windows)**
→ https://developer.microsoft.com/microsoft-edge/webview2/

**Blank window / weiße UI**
→ `RETRODISC_DEBUG=1 RetroDisc.exe` für DevTools

**ffmpeg not found**
→ `python prepare_vendor.py` ausführen

**macOS: "nicht verifizierter Entwickler"**
→ `xattr -cr dist/RetroDisc` dann nochmal öffnen
