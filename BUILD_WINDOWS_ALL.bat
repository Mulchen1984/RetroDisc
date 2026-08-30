@echo off
setlocal
cd /d "%~dp0"
title RetroDisc Windows Build

echo.
echo ========================================
echo RetroDisc bauen: Portable EXE + Installer
echo ========================================
echo.

python build.py --install-deps --skip-tests
if errorlevel 1 (
    echo.
    echo Build fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo Fertig.
echo Portable EXE: dist\RetroDisc.exe
echo Portable ZIP: Output\RetroDisc_1.0.0_Portable.zip
echo Installer:    Output\RetroDisc_Setup_1.0.0.exe
echo.
pause
