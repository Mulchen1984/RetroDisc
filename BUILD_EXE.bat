@echo off
REM ═══════════════════════════════════════════════════════════════
REM  RetroDisc — EXE Build Script für Windows
REM  Ergebnis: dist\RetroDisc.exe  (eine einzige Datei, ~30-40 MB)
REM ═══════════════════════════════════════════════════════════════

title RetroDisc Build

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   RetroDisc Build — Eine EXE Datei   ║
echo  ╚══════════════════════════════════════╝
echo.

REM ── Python prüfen ──────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  FEHLER: Python nicht gefunden!
    echo  Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do echo  ✓ %%i

REM ── Dependencies installieren ──────────────────────────────────
echo.
echo  [1/4] Dependencies installieren...
pip install pyinstaller pywebview pydantic structlog rich click ^
    httpx yt-dlp sounddevice soundfile certifi --quiet
if errorlevel 1 (
    echo  FEHLER: pip install fehlgeschlagen!
    pause
    exit /b 1
)
echo  ✓ Dependencies OK

REM ── Tests ausführen ────────────────────────────────────────────
echo.
echo  [2/4] Tests ausführen...
python -m pytest tests/test_ffmpeg.py tests/test_pipeline.py -q --tb=short
if errorlevel 1 (
    echo  WARNUNG: Tests fehlgeschlagen - fahre trotzdem fort
)

REM ── PyInstaller ────────────────────────────────────────────────
echo.
echo  [3/4] EXE wird gebaut (dauert 2-5 Minuten)...
python -m PyInstaller retrodisc_onefile.spec --clean --noconfirm
if errorlevel 1 (
    echo  FEHLER: PyInstaller fehlgeschlagen!
    pause
    exit /b 1
)

REM ── Ergebnis prüfen ────────────────────────────────────────────
echo.
echo  [4/4] Ergebnis prüfen...

if exist "dist\RetroDisc.exe" (
    for %%A in ("dist\RetroDisc.exe") do (
        set SIZE=%%~zA
    )
    echo.
    echo  ╔══════════════════════════════════════╗
    echo  ║   BUILD ERFOLGREICH!                 ║
    echo  ╠══════════════════════════════════════╣
    echo  ║   dist\RetroDisc.exe                 ║
    echo  ╚══════════════════════════════════════╝
    echo.
    echo  Die EXE kann direkt ausgeführt werden.
    echo  Beim ersten Start werden FFmpeg und yt-dlp
    echo  automatisch heruntergeladen (~100 MB).
    echo.

    set /p OPEN="RetroDisc.exe jetzt starten? (j/n): "
    if /i "%OPEN%"=="j" start "" "dist\RetroDisc.exe"
) else (
    echo  FEHLER: dist\RetroDisc.exe nicht gefunden!
)

pause
