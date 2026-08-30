@echo off
:: RetroDisc — Windows Portable Build
:: Ergebnis: dist\RetroDisc.exe  (portable, alles drin)
setlocal EnableDelayedExpansion
title RetroDisc Windows Build

echo.
echo  ╔══════════════════════════════════════╗
echo  ║  RetroDisc — Windows Portable Build  ║
echo  ╚══════════════════════════════════════╝
echo.

:: Python prüfen
python --version >nul 2>&1
if errorlevel 1 (
    echo  FEHLER: Python nicht gefunden!
    echo  https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo  OK: %%i

:: Dependencies
echo.
echo  [1/4] Pakete installieren...
pip install pyinstaller pywebview pydantic structlog rich click ^
    httpx yt-dlp sounddevice soundfile certifi ^
    openai-whisper scenedetect librosa --quiet
echo  OK

:: FFmpeg holen
echo.
echo  [2/4] FFmpeg laden...
if exist vendor\ffmpeg.exe (
    echo  OK: ffmpeg.exe bereits vorhanden
) else (
    python prepare_vendor.py
    if errorlevel 1 (
        echo  FEHLER: FFmpeg-Download fehlgeschlagen
        pause & exit /b 1
    )
)

:: PyInstaller
echo.
echo  [3/4] EXE bauen ^(bitte warten...^)
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name RetroDisc ^
    --icon assets\retrodisc.ico ^
    --version-file version_info.txt ^
    --manifest retrodisc.manifest ^
    --add-data "src\ui\app.html;src/ui" ^
    --add-data "src\ui\splash.html;src/ui" ^
    --add-data "assets;assets" ^
    --add-data "vendor\ffmpeg.exe;vendor" ^
    --add-data "vendor\ffprobe.exe;vendor" ^
    --hidden-import "src.core.ffmpeg" ^
    --hidden-import "src.core.pipeline" ^
    --hidden-import "src.core.downloader" ^
    --hidden-import "src.core.disc" ^
    --hidden-import "src.services.converter" ^
    --hidden-import "src.services.search" ^
    --hidden-import "src.services.library" ^
    --hidden-import "src.services.dvd_workflow" ^
    --hidden-import "src.services.smart_edit" ^
    --hidden-import "src.services.subtitle" ^
    --hidden-import "src.services.upscaler" ^
    --hidden-import "src.services.assistant" ^
    --hidden-import "src.services.watch_folder" ^
    --hidden-import "src.config.settings" ^
    --hidden-import "src.config.presets" ^
    --hidden-import "src.models.media" ^
    --hidden-import "src.utils.sound" ^
    --hidden-import "src.bootstrap" ^
    --hidden-import "webview.platforms.winforms" ^
    --hidden-import "webview.platforms.edgechromium" ^
    --hidden-import "pydantic" ^
    --hidden-import "pydantic_core" ^
    --hidden-import "yt_dlp" ^
    --hidden-import "yt_dlp.extractor._extractors" ^
    --collect-data "pydantic" ^
    --collect-data "certifi" ^
    --collect-data "yt_dlp" ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module pytest ^
    --noconfirm ^
    retrodisc_portable.py

if errorlevel 1 (
    echo  FEHLER: Build fehlgeschlagen!
    pause & exit /b 1
)

:: Ergebnis
if exist dist\RetroDisc.exe (
    for %%F in ("dist\RetroDisc.exe") do set SIZE=%%~zF
    set /a SIZE_MB=!SIZE! / 1048576
    echo.
    echo  ╔══════════════════════════════════════╗
    echo  ║  FERTIG!                             ║
    echo  ║                                      ║
    echo  ║  dist\RetroDisc.exe  ^(!SIZE_MB! MB^)        ║
    echo  ║                                      ║
    echo  ║  Portable — einfach doppelklicken    ║
    echo  ╚══════════════════════════════════════╝
    echo.
    set /p GO="Jetzt starten? (j/n): "
    if /i "!GO!"=="j" start "" "dist\RetroDisc.exe"
) else (
    echo  FEHLER: RetroDisc.exe nicht gefunden
)
pause
