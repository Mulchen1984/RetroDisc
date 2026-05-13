#!/usr/bin/env python3
"""
RetroDisc Build Script
======================
Ein Befehl → fertige Windows EXE + Installer

Verwendung:
    python build.py                  # Vollständiger Build
    python build.py --skip-installer # Nur EXE (ohne Inno Setup)
    python build.py --clean          # Build-Ordner löschen und neu bauen

Voraussetzungen:
    pip install pyinstaller
    Inno Setup 6.x (für den Installer): https://jrsoftware.org/isinfo.php
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
DIST_DIR = HERE / "dist"
BUILD_DIR = HERE / "build"
OUTPUT_DIR = HERE / "Output"


def run(cmd: list, cwd: Path = None, check: bool = True) -> subprocess.CompletedProcess:
    """Führt einen Befehl aus und gibt das Ergebnis zurück."""
    print(f"\n→ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd or HERE, check=check)
    return result


def clean():
    """Löscht alle Build-Artefakte."""
    for d in [DIST_DIR, BUILD_DIR, OUTPUT_DIR]:
        if d.exists():
            print(f"  Lösche {d}...")
            shutil.rmtree(d)
    print("  Clean abgeschlossen.")


def check_prerequisites():
    """Prüft ob alle nötigen Tools vorhanden sind."""
    print("\n=== Voraussetzungen prüfen ===")
    ok = True

    # Python
    version = sys.version_info
    if version < (3, 11):
        print(f"  ✗ Python {version.major}.{version.minor} — Mindestens 3.11 nötig!")
        ok = False
    else:
        print(f"  ✓ Python {version.major}.{version.minor}.{version.micro}")

    # PyInstaller
    try:
        import PyInstaller
        print(f"  ✓ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  ✗ PyInstaller nicht gefunden → pip install pyinstaller")
        ok = False

    # Pydantic, structlog, etc.
    for lib in ["pydantic", "structlog", "rich", "click", "httpx"]:
        try:
            __import__(lib)
            print(f"  ✓ {lib}")
        except ImportError:
            print(f"  ✗ {lib} nicht gefunden → pip install {lib}")
            ok = False

    return ok


def create_assets():
    """Erstellt fehlende Assets (Platzhalter-Icon etc.)."""
    assets_dir = HERE / "assets"
    assets_dir.mkdir(exist_ok=True)

    ico_path = assets_dir / "retrodisc.ico"
    if not ico_path.exists():
        print("  Erstelle Platzhalter-Icon...")
        _create_placeholder_ico(ico_path)

    tools_dir = HERE / "tools"
    tools_dir.mkdir(exist_ok=True)
    keep = tools_dir / ".gitkeep"
    if not keep.exists():
        keep.write_text("")

    print("  Assets OK")


def _create_placeholder_ico(path: Path):
    """Erstellt ein minimales ICO-Icon als Platzhalter."""
    # 16x16 ICO mit einfarbigem Inhalt (navy blau)
    # Echtes Icon sollte mit einem Image-Editor erstellt werden
    import struct

    def make_bmp_16x16(color_rgb):
        """Erstellt ein minimales 16x16 BMP."""
        w, h = 16, 16
        r, g, b = color_rgb
        # BMP Header
        row_size = ((w * 3 + 3) & ~3)
        pixel_data_size = row_size * h
        file_size = 54 + pixel_data_size

        header = struct.pack('<HIII', 0x4D42, file_size, 0, 54)
        dib = struct.pack('<IIIHHIIIIII', 40, w, h, 1, 24, 0,
                          pixel_data_size, 2835, 2835, 0, 0)
        pixels = b''
        for _ in range(h):
            row = bytes([b, g, r] * w)
            padding = bytes(row_size - len(row))
            pixels += row + padding

        return header + dib + pixels

    bmp_data = make_bmp_16x16((0, 0, 128))  # Navy blau
    bmp_size = len(bmp_data)

    # ICO Header + Directory Entry
    ico_header = struct.pack('<HHH', 0, 1, 1)  # Reserved, Type=1(ICO), Count=1
    dir_entry = struct.pack('<BBBBHHII',
                            16, 16,  # Width, Height
                            0, 0,    # Color count, Reserved
                            1, 24,   # Planes, Bit count
                            bmp_size,
                            6 + 16   # Offset to image data
                            )

    path.write_bytes(ico_header + dir_entry + bmp_data)


def run_tests():
    """Führt die Unit-Tests aus."""
    print("\n=== Tests ausführen ===")
    result = run([sys.executable, "-m", "pytest", "tests/test_ffmpeg.py",
                  "tests/test_pipeline.py", "-v", "--tb=short"], check=False)
    if result.returncode != 0:
        print("\n  ✗ Tests fehlgeschlagen!")
        return False
    print("  ✓ Alle Tests bestanden")
    return True


def build_exe():
    """Baut die EXE mit PyInstaller."""
    print("\n=== PyInstaller: EXE erstellen ===")
    run([
        sys.executable, "-m", "PyInstaller",
        "retrodisc.spec",
        "--clean",
        "--noconfirm",
    ])

    exe = DIST_DIR / "RetroDisc" / "retrodisc.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / 1024 / 1024
        print(f"\n  ✓ EXE erstellt: {exe}")
        print(f"    Größe: {size_mb:.1f} MB")
    else:
        print("  ✗ EXE wurde nicht erstellt!")
        return False

    return True


def build_portable():
    """Erstellt eine portable ZIP-Version."""
    print("\n=== Portable ZIP erstellen ===")
    OUTPUT_DIR.mkdir(exist_ok=True)

    zip_path = OUTPUT_DIR / "RetroDisc_1.0.0_Portable.zip"
    source_dir = DIST_DIR / "RetroDisc"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file in source_dir.rglob("*"):
            if file.is_file():
                arcname = "RetroDisc/" + str(file.relative_to(source_dir))
                zf.write(file, arcname)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  ✓ Portable ZIP: {zip_path}")
    print(f"    Größe: {size_mb:.1f} MB")
    return True


def build_installer():
    """Erstellt den Installer mit Inno Setup."""
    print("\n=== Inno Setup: Installer erstellen ===")

    # Inno Setup suchen
    inno_paths = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        shutil.which("ISCC"),
    ]
    iscc = next((p for p in inno_paths if p and Path(p).exists()), None)

    if not iscc:
        print("  ⚠ Inno Setup nicht gefunden — Installer wird übersprungen")
        print("    Download: https://jrsoftware.org/isinfo.php")
        return False

    run([str(iscc), str(HERE / "installer" / "retrodisc_setup.iss")])

    setup_exe = OUTPUT_DIR / "RetroDisc_Setup_1.0.0.exe"
    if setup_exe.exists():
        size_mb = setup_exe.stat().st_size / 1024 / 1024
        print(f"  ✓ Setup.exe: {setup_exe}")
        print(f"    Größe: {size_mb:.1f} MB")
    else:
        print("  ✗ Setup.exe wurde nicht erstellt")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="RetroDisc Build System")
    parser.add_argument("--clean", action="store_true", help="Build-Ordner vorher löschen")
    parser.add_argument("--skip-tests", action="store_true", help="Tests überspringen")
    parser.add_argument("--skip-installer", action="store_true", help="Inno Setup überspringen")
    parser.add_argument("--portable-only", action="store_true", help="Nur portable ZIP")
    args = parser.parse_args()

    print("╔══════════════════════════════════════╗")
    print("║   RetroDisc Build System v1.0        ║")
    print("╚══════════════════════════════════════╝")

    if args.clean:
        print("\n=== Clean ===")
        clean()

    # Voraussetzungen
    if not check_prerequisites():
        print("\n✗ Build abgebrochen — Voraussetzungen nicht erfüllt")
        sys.exit(1)

    # Assets
    print("\n=== Assets vorbereiten ===")
    create_assets()

    # Tests
    if not args.skip_tests:
        if not run_tests():
            print("\n✗ Build abgebrochen wegen Test-Fehlern")
            sys.exit(1)

    # EXE bauen
    if not build_exe():
        sys.exit(1)

    # Portable ZIP
    build_portable()

    # Installer
    if not args.skip_installer:
        build_installer()

    # Zusammenfassung
    print("\n╔══════════════════════════════════════╗")
    print("║   BUILD ERFOLGREICH!                 ║")
    print("╠══════════════════════════════════════╣")
    print(f"║   EXE:       dist/RetroDisc/         ║")
    print(f"║   Portable:  Output/RetroDisc_...zip ║")
    if not args.skip_installer:
        print(f"║   Installer: Output/RetroDisc_...exe ║")
    print("╚══════════════════════════════════════╝")


if __name__ == "__main__":
    main()
