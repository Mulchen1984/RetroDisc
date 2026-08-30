# CLAUDE.md — RetroDisc Build-Anweisungen

## Auftrag
Baue eine fertige portable App:
- Windows: dist/RetroDisc.exe
- macOS:   dist/RetroDisc.dmg

## Schritt 1: Dependencies
pip install pyinstaller pywebview pydantic structlog rich click httpx yt-dlp sounddevice soundfile certifi openai-whisper scenedetect librosa

## Schritt 2: FFmpeg laden
python prepare_vendor.py

## Schritt 3A: Windows EXE
python -m PyInstaller --onefile --windowed --name "RetroDisc" --icon "assets/retrodisc.ico" --version-file "version_info.txt" --manifest "retrodisc.manifest" --add-data "src/ui/app.html;src/ui" --add-data "src/ui/splash.html;src/ui" --add-data "assets;assets" --add-data "vendor/ffmpeg.exe;vendor" --add-data "vendor/ffprobe.exe;vendor" --collect-data "pydantic" --collect-data "certifi" --collect-data "yt_dlp" --collect-submodules "yt_dlp" --hidden-import "src.core.ffmpeg" --hidden-import "src.core.pipeline" --hidden-import "src.core.downloader" --hidden-import "src.core.disc" --hidden-import "src.services.converter" --hidden-import "src.services.search" --hidden-import "src.services.library" --hidden-import "src.services.dvd_workflow" --hidden-import "src.services.smart_edit" --hidden-import "src.services.subtitle" --hidden-import "src.services.upscaler" --hidden-import "src.services.assistant" --hidden-import "src.services.watch_folder" --hidden-import "src.config.settings" --hidden-import "src.config.presets" --hidden-import "src.models.media" --hidden-import "src.utils.sound" --hidden-import "src.bootstrap" --hidden-import "webview.platforms.winforms" --hidden-import "webview.platforms.edgechromium" --hidden-import "pydantic_core" --hidden-import "sqlite3" --noconfirm retrodisc_portable.py

## Schritt 3B: macOS DMG
python3 -m PyInstaller --onefile --windowed --name "RetroDisc" --icon "assets/retrodisc.icns" --add-data "src/ui/app.html:src/ui" --add-data "src/ui/splash.html:src/ui" --add-data "assets:assets" --add-data "vendor/ffmpeg:vendor" --add-data "vendor/ffprobe:vendor" --collect-data "pydantic" --collect-data "certifi" --collect-data "yt_dlp" --collect-submodules "yt_dlp" --hidden-import "src.core.ffmpeg" --hidden-import "src.core.pipeline" --hidden-import "src.core.downloader" --hidden-import "src.services.converter" --hidden-import "src.services.search" --hidden-import "src.services.library" --hidden-import "src.services.smart_edit" --hidden-import "src.services.subtitle" --hidden-import "src.services.upscaler" --hidden-import "src.services.assistant" --hidden-import "src.config.settings" --hidden-import "src.config.presets" --hidden-import "src.models.media" --hidden-import "src.bootstrap" --hidden-import "webview.platforms.cocoa" --hidden-import "pydantic_core" --hidden-import "sqlite3" --noconfirm retrodisc_portable.py
pip install dmgbuild
python3 create_dmg.py
