@echo off
chcp 65001 >nul
title RetroDisc — Portable EXE bauen

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   RetroDisc — Portable Windows App          ║
echo  ║   Eine EXE, kein Installer, kein Internet   ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: Python prüfen
python --version >nul 2>&1
if errorlevel 1 (
    echo  FEHLER: Python nicht gefunden!
    echo  Bitte installieren: https://www.python.org/downloads/windows/
    echo  Wichtig: "Add Python to PATH" ankreuzen!
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo  OK: %%i

:: Dependencies
echo.
echo  [1/4] Python-Pakete installieren...
pip install pyinstaller pywebview pydantic structlog rich click ^
    httpx yt-dlp sounddevice soundfile certifi ^
    openai-whisper scenedetect librosa --quiet --upgrade
if errorlevel 1 ( echo  FEHLER: pip install fehlgeschlagen! & pause & exit /b 1 )
echo  OK: Pakete installiert

:: FFmpeg laden
echo.
echo  [2/4] FFmpeg fuer Windows laden (einmalig ~85 MB)...
if exist "vendor\ffmpeg.exe" (
    echo  OK: FFmpeg bereits vorhanden
) else (
    python prepare_vendor.py
    if errorlevel 1 (
        echo  FEHLER: FFmpeg-Download fehlgeschlagen!
        echo  Manuell: github.com/BtbN/FFmpeg-Builds/releases
        echo  ffmpeg.exe + ffprobe.exe in vendor\ legen
        pause & exit /b 1
    )
)

:: EXE bauen
echo.
echo  [3/4] Portable EXE wird gebaut (5-10 Min.)...
python -m PyInstaller retrodisc_onefile.spec --clean --noconfirm
if errorlevel 1 ( echo  FEHLER: Build fehlgeschlagen! & pause & exit /b 1 )

:: Prüfen
echo.
echo  [4/4] Ergebnis prüfen...
if exist "dist\RetroDisc.exe" (
    for %%F in ("dist\RetroDisc.exe") do set SIZE=%%~zF
    echo.
    echo  ╔══════════════════════════════════════════════╗
    echo  ║   FERTIG!  dist\RetroDisc.exe               ║
    echo  ║   Portable — kein Installer nötig            ║
    echo  ╚══════════════════════════════════════════════╝
    echo.
    set /p RUN="Jetzt starten? (j/n): "
    if /i "%RUN%"=="j" start "" "dist\RetroDisc.exe"
) else (
    echo  FEHLER: dist\RetroDisc.exe nicht erstellt!
)
pause
