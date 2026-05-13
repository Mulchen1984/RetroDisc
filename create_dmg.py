"""
create_dmg.py — Erstellt RetroDisc.dmg für macOS
Ausführen NACH PyInstaller: python3 create_dmg.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
APP  = HERE / "dist" / "RetroDisc"   # PyInstaller --onefile Output
DMG  = HERE / "dist" / "RetroDisc.dmg"

def main():
    # Prüfen ob App existiert
    if not APP.exists():
        print(f"FEHLER: {APP} nicht gefunden.")
        print("Zuerst PyInstaller ausführen (siehe CLAUDE.md Schritt 3B)")
        sys.exit(1)

    print("Erstelle RetroDisc.dmg...")

    # Methode 1: dmgbuild (sauberste Methode)
    try:
        import dmgbuild
        settings = {
            "filename": str(DMG),
            "volume_name": "RetroDisc",
            "format": "UDBZ",
            "compression_level": 9,
            "size": None,
            "files": [str(APP)],
            "symlinks": {"Applications": "/Applications"},
            "icon_locations": {
                "RetroDisc": (150, 180),
                "Applications": (450, 180),
            },
            "background": None,
            "window_rect": ((200, 200), (600, 400)),
            "icon_size": 80,
        }
        dmgbuild.build_dmg(str(DMG), "RetroDisc", settings=settings)
        print(f"✓ DMG erstellt: {DMG}")
        print(f"  Größe: {DMG.stat().st_size / 1024 / 1024:.1f} MB")
        return
    except ImportError:
        print("dmgbuild nicht installiert, versuche hdiutil...")
    except Exception as e:
        print(f"dmgbuild Fehler: {e}, versuche hdiutil...")

    # Methode 2: hdiutil (macOS built-in)
    try:
        # Temporäres Verzeichnis für DMG-Inhalt
        tmp = HERE / "dist" / "_dmg_tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir()

        # App + Applications-Symlink
        shutil.copy2(APP, tmp / "RetroDisc")
        os.symlink("/Applications", tmp / "Applications")

        # DMG erstellen
        subprocess.run([
            "hdiutil", "create",
            "-volname", "RetroDisc",
            "-srcfolder", str(tmp),
            "-ov",
            "-format", "UDBZ",
            str(DMG),
        ], check=True)

        shutil.rmtree(tmp)
        print(f"✓ DMG erstellt: {DMG}")
        print(f"  Größe: {DMG.stat().st_size / 1024 / 1024:.1f} MB")

    except Exception as e:
        print(f"hdiutil Fehler: {e}")
        print()
        print("Manuell:")
        print(f"  1. Finder öffnen")
        print(f"  2. {APP} nach /Applications ziehen")
        print(f"  Oder: Die Binärdatei direkt verwenden: {APP}")
        sys.exit(1)


if __name__ == "__main__":
    main()
