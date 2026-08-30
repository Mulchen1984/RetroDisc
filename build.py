#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RetroDisc Windows build system.

Creates both deliverables for Windows 11:
  1. Portable one-file app: dist/RetroDisc.exe
  2. Installer EXE:        Output/RetroDisc_Setup_1.0.0.exe

The installer is built with PyInstaller too, so Inno Setup is optional and
not required on the build machine.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST_DIR = HERE / "dist"
BUILD_DIR = HERE / "build"
OUTPUT_DIR = HERE / "Output"
APP_EXE = DIST_DIR / "RetroDisc.exe"
SETUP_EXE = OUTPUT_DIR / "RetroDisc_Setup_1.0.0.exe"
PORTABLE_ZIP = OUTPUT_DIR / "RetroDisc_1.0.0_Portable.zip"

RUNTIME_DEPS = [
    "pyinstaller",
    "pywebview",
    "pydantic",
    "structlog",
    "rich==14.3.3",
    "click",
    "httpx",
    "yt-dlp",
    "sounddevice",
    "soundfile",
    "certifi",
    "faster-whisper",
    "ctranslate2",
    "tokenizers",
    "huggingface-hub",
    "av",
    "numpy",
]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("\n> " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=HERE, check=check)


def clean() -> None:
    for path in [DIST_DIR, BUILD_DIR, OUTPUT_DIR]:
        if path.exists():
            print(f"Loesche {path}")
            shutil.rmtree(path)


def pip_install() -> None:
    print("\n=== Python-Pakete installieren/aktualisieren ===")
    run([sys.executable, "-m", "pip", "install", "--upgrade", *RUNTIME_DEPS])


def check_imports() -> bool:
    print("\n=== Voraussetzungen pruefen ===")
    import_names = {
        "pyinstaller": "PyInstaller",
        "pywebview": "webview",
        "pydantic": "pydantic",
        "structlog": "structlog",
        "rich": "rich",
        "click": "click",
        "httpx": "httpx",
        "yt-dlp": "yt_dlp",
        "sounddevice": "sounddevice",
        "soundfile": "soundfile",
        "certifi": "certifi",
        "faster-whisper": "faster_whisper",
        "ctranslate2": "ctranslate2",
        "tokenizers": "tokenizers",
        "huggingface-hub": "huggingface_hub",
        "av": "av",
        "numpy": "numpy",
    }
    ok = True
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 11):
        print("FEHLER: Python 3.11 oder neuer ist erforderlich.")
        ok = False
    for package, module in import_names.items():
        try:
            __import__(module)
            print(f"OK: {package}")
        except Exception as exc:
            print(f"FEHLT: {package} ({exc})")
            ok = False
    return ok


def prepare_vendor() -> None:
    print("\n=== FFmpeg/FFprobe vorbereiten ===")
    run([sys.executable, "prepare_vendor.py"])


def run_tests(skip_tests: bool) -> None:
    if skip_tests:
        print("\n=== Tests uebersprungen ===")
        return
    print("\n=== Tests ausfuehren ===")
    result = run([sys.executable, "-m", "pytest", "-q", "--tb=short"], check=False)
    if result.returncode != 0:
        raise SystemExit("Tests fehlgeschlagen. Mit --skip-tests kann der Build trotzdem erzwungen werden.")


def build_portable_exe() -> None:
    print("\n=== Portable EXE bauen ===")
    run([sys.executable, "-m", "PyInstaller", "retrodisc_final.spec", "--clean", "--noconfirm"])
    if not APP_EXE.exists():
        raise SystemExit(f"FEHLER: {APP_EXE} wurde nicht erstellt.")
    print(f"OK: {APP_EXE} ({APP_EXE.stat().st_size / 1024 / 1024:.1f} MB)")


def build_portable_zip() -> None:
    print("\n=== Portable ZIP erstellen ===")
    OUTPUT_DIR.mkdir(exist_ok=True)
    if PORTABLE_ZIP.exists():
        PORTABLE_ZIP.unlink()
    with zipfile.ZipFile(PORTABLE_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(APP_EXE, f"RetroDisc/{APP_EXE.name}")
        for extra_name in ["README.md", "START_WINDOWS.txt"]:
            extra = HERE / extra_name
            if extra.exists():
                zf.write(extra, f"RetroDisc/{extra.name}")
    print(f"OK: {PORTABLE_ZIP} ({PORTABLE_ZIP.stat().st_size / 1024 / 1024:.1f} MB)")


def build_setup_exe() -> None:
    print("\n=== Installer EXE bauen ===")
    OUTPUT_DIR.mkdir(exist_ok=True)
    sep = ";" if sys.platform.startswith("win") else ":"
    run([
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--name",
        "RetroDisc_Setup_1.0.0",
        "--icon",
        str(HERE / "assets" / "retrodisc.ico"),
        "--add-binary",
        f"{APP_EXE}{sep}.",
        "--distpath",
        str(OUTPUT_DIR),
        "--workpath",
        str(BUILD_DIR / "installer"),
        "--specpath",
        str(BUILD_DIR / "installer"),
        "--clean",
        "--noconfirm",
        str(HERE / "installer" / "retrodisc_installer.py"),
    ])
    if not SETUP_EXE.exists():
        raise SystemExit(f"FEHLER: {SETUP_EXE} wurde nicht erstellt.")
    print(f"OK: {SETUP_EXE} ({SETUP_EXE.stat().st_size / 1024 / 1024:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RetroDisc for Windows")
    parser.add_argument("--clean", action="store_true", help="Build-Ausgaben vorher loeschen")
    parser.add_argument("--install-deps", action="store_true", help="Python-Pakete vorher installieren/aktualisieren")
    parser.add_argument("--skip-tests", action="store_true", help="Tests ueberspringen")
    parser.add_argument("--skip-installer", action="store_true", help="Nur portable EXE/ZIP bauen")
    parser.add_argument("--skip-zip", action="store_true", help="Portable ZIP nicht erstellen")
    args = parser.parse_args()

    print("RetroDisc Windows Build")
    print("=" * 40)
    if args.clean:
        clean()
    if args.install_deps:
        pip_install()
    if not check_imports():
        print("\nTipp: python build.py --install-deps --skip-tests")
        return 1

    prepare_vendor()
    run_tests(args.skip_tests)
    build_portable_exe()
    if not args.skip_zip:
        build_portable_zip()
    if not args.skip_installer:
        build_setup_exe()

    print("\nFERTIG")
    print(f"Portable EXE: {APP_EXE}")
    if PORTABLE_ZIP.exists():
        print(f"Portable ZIP: {PORTABLE_ZIP}")
    if SETUP_EXE.exists():
        print(f"Installer:    {SETUP_EXE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
