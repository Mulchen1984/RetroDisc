@echo off
REM ═══════════════════════════════════════════════════════════════════
REM  RetroDisc — Vollständige Standalone EXE bauen
REM
REM  Ergebnis: dist\RetroDisc.exe
REM  Enthält: Python + Code + UI + FFmpeg + FFprobe + yt-dlp
REM  Kein Internet beim Endnutzer nötig.
REM  Größe: ~120-150 MB
REM ═══════════════════════════════════════════════════════════════════
setlocal EnableDelayedExpansion

title RetroDisc — Standalone EXE Build

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   RetroDisc — Standalone EXE Builder     ║
echo  ║   Alles inklusive, kein Internet nötig   ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Python prüfen ──────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [FEHLER] Python nicht gefunden!
    echo  Download: https://www.python.org/downloads/
    echo  Wichtig: "Add Python to PATH" ankreuzen!
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo  OK: %%i

REM ── pip Dependencies ───────────────────────────────────────────────
echo.
echo  [1/5] Python-Pakete installieren...
pip install pyinstaller pywebview pydantic structlog rich click ^
    httpx yt-dlp sounddevice soundfile certifi --quiet --upgrade
if errorlevel 1 (
    echo  [FEHLER] pip install fehlgeschlagen!
    pause & exit /b 1
)
echo  OK: Python-Pakete installiert

REM ── FFmpeg Windows-Binaries herunterladen ──────────────────────────
echo.
echo  [2/5] FFmpeg fuer Windows herunterladen...
echo  (Einmalig ~85 MB von github.com/BtbN/FFmpeg-Builds)

if exist "vendor\ffmpeg.exe" (
    echo  OK: FFmpeg bereits vorhanden, ueberspringe Download
) else (
    mkdir vendor 2>nul
    python prepare_vendor.py
    if errorlevel 1 (
        echo  [FEHLER] FFmpeg-Download fehlgeschlagen!
        echo  Bitte manuell herunterladen:
        echo  https://github.com/BtbN/FFmpeg-Builds/releases
        echo  ZIP entpacken, ffmpeg.exe + ffprobe.exe in vendor\ legen
        pause & exit /b 1
    )
)

if not exist "vendor\ffmpeg.exe" (
    echo  [FEHLER] vendor\ffmpeg.exe nicht gefunden!
    pause & exit /b 1
)
if not exist "vendor\ffprobe.exe" (
    echo  [FEHLER] vendor\ffprobe.exe nicht gefunden!
    pause & exit /b 1
)

for %%F in ("vendor\ffmpeg.exe") do echo  OK: ffmpeg.exe ^(%%~zF Bytes^)
for %%F in ("vendor\ffprobe.exe") do echo  OK: ffprobe.exe ^(%%~zF Bytes^)

REM ── Tests ──────────────────────────────────────────────────────────
echo.
echo  [3/5] Tests ausfuehren...
python -m pytest tests\test_ffmpeg.py tests\test_pipeline.py -q --tb=short 2>nul
if errorlevel 1 (
    echo  Warnung: Tests fehlgeschlagen - fahre fort
) else (
    echo  OK: Alle Tests bestanden
)

REM ── PyInstaller ────────────────────────────────────────────────────
echo.
echo  [4/5] EXE wird gebaut (3-8 Minuten)...
echo  Bitte warten...

python -m PyInstaller retrodisc_final.spec --clean --noconfirm
if errorlevel 1 (
    echo  [FEHLER] PyInstaller fehlgeschlagen!
    echo  Log: build\retrodisc_final\warn-retrodisc_final.txt
    pause & exit /b 1
)

REM ── Ergebnis ───────────────────────────────────────────────────────
echo.
echo  [5/5] Pruefe Ergebnis...

if not exist "dist\RetroDisc.exe" (
    echo  [FEHLER] dist\RetroDisc.exe nicht gefunden!
    pause & exit /b 1
)

for %%F in ("dist\RetroDisc.exe") do (
    set /a SIZE_MB=%%~zF / 1048576
)

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   BUILD ERFOLGREICH!                     ║
echo  ╠══════════════════════════════════════════╣
echo  ║                                          ║
echo  ║   dist\RetroDisc.exe  (!SIZE_MB! MB)          ║
echo  ║                                          ║
echo  ║   Enthält:                               ║
echo  ║   ✓ Python Runtime                       ║
echo  ║   ✓ RetroDisc UI + Backend               ║
echo  ║   ✓ FFmpeg + FFprobe (Video/Audio)       ║
echo  ║   ✓ yt-dlp (Downloads)                   ║
echo  ║   ✓ Alle Bibliotheken                    ║
echo  ║                                          ║
echo  ║   Kein Internet beim Start nötig!        ║
echo  ╚══════════════════════════════════════════╝
echo.

set /p START="RetroDisc.exe jetzt starten? (j/n): "
if /i "!START!"=="j" (
    start "" "dist\RetroDisc.exe"
)

pause
