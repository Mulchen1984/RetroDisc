# -*- coding: utf-8 -*-
"""RetroDisc Windows installer.

This is a small PyInstaller-built installer that embeds the portable
RetroDisc.exe and installs it into a user-writable location by default.
It avoids requiring Inno Setup on the build machine.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "RetroDisc"
APP_VERSION = "1.0.0"
EXE_NAME = "RetroDisc.exe"


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def default_install_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Programs" / APP_NAME
    return Path.home() / "AppData" / "Local" / "Programs" / APP_NAME


def desktop_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"


def start_menu_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME


def create_shortcut(link_path: Path, target: Path, working_dir: Path, description: str) -> bool:
    """Create a Windows .lnk file through PowerShell COM automation."""
    link_path.parent.mkdir(parents=True, exist_ok=True)
    ps = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{str(link_path).replace("'", "''")}')
$Shortcut.TargetPath = '{str(target).replace("'", "''")}'
$Shortcut.WorkingDirectory = '{str(working_dir).replace("'", "''")}'
$Shortcut.IconLocation = '{str(target).replace("'", "''")},0'
$Shortcut.Description = '{description.replace("'", "''")}'
$Shortcut.Save()
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def write_uninstaller(install_dir: Path) -> None:
    uninstaller = install_dir / "Uninstall RetroDisc.cmd"
    script = f"""@echo off
setlocal
cd /d "%~dp0"
echo RetroDisc wird deinstalliert...
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\RetroDisc\RetroDisc.lnk" 2>nul
rmdir "%APPDATA%\Microsoft\Windows\Start Menu\Programs\RetroDisc" 2>nul
del "%USERPROFILE%\Desktop\RetroDisc.lnk" 2>nul
cd /d "%TEMP%"
rmdir /s /q "{install_dir}" 2>nul
echo Fertig.
pause
"""
    uninstaller.write_text(script, encoding="utf-8")


def install(install_dir: Path, desktop_shortcut: bool, start_menu_shortcut: bool, launch: bool) -> int:
    source_exe = resource_path(EXE_NAME)
    if not source_exe.exists():
        print(f"FEHLER: Eingebettete {EXE_NAME} nicht gefunden: {source_exe}")
        return 1

    print(f"Installiere {APP_NAME} {APP_VERSION} nach:")
    print(f"  {install_dir}")
    install_dir.mkdir(parents=True, exist_ok=True)

    target_exe = install_dir / EXE_NAME
    shutil.copy2(source_exe, target_exe)
    write_uninstaller(install_dir)

    if start_menu_shortcut:
        create_shortcut(start_menu_dir() / f"{APP_NAME}.lnk", target_exe, install_dir, "RetroDisc starten")
        create_shortcut(start_menu_dir() / f"{APP_NAME} deinstallieren.lnk", install_dir / "Uninstall RetroDisc.cmd", install_dir, "RetroDisc deinstallieren")

    if desktop_shortcut:
        create_shortcut(desktop_dir() / f"{APP_NAME}.lnk", target_exe, install_dir, "RetroDisc starten")

    print("Installation abgeschlossen.")
    print(f"Programm: {target_exe}")

    if launch:
        subprocess.Popen([str(target_exe)], cwd=str(install_dir))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="RetroDisc Windows Installer")
    parser.add_argument("--dir", dest="install_dir", default=str(default_install_dir()), help="Installationsordner")
    parser.add_argument("--no-desktop", action="store_true", help="Keine Desktop-Verknüpfung erstellen")
    parser.add_argument("--no-start-menu", action="store_true", help="Keine Startmenü-Verknüpfung erstellen")
    parser.add_argument("--launch", action="store_true", help="RetroDisc nach Installation starten")
    parser.add_argument("--silent", action="store_true", help="Ohne Rückfragen installieren")
    args = parser.parse_args()

    install_dir = Path(args.install_dir).expanduser()

    if not args.silent:
        print(f"{APP_NAME} {APP_VERSION} Setup")
        print("=" * 40)
        print(f"Zielordner: {install_dir}")
        answer = input("Installieren? [J/n] ").strip().lower()
        if answer not in ("", "j", "ja", "y", "yes"):
            print("Abgebrochen.")
            return 1

    return install(
        install_dir=install_dir,
        desktop_shortcut=not args.no_desktop,
        start_menu_shortcut=not args.no_start_menu,
        launch=args.launch,
    )


if __name__ == "__main__":
    raise SystemExit(main())
