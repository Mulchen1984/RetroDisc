# -*- coding: utf-8 -*-
"""
prepare_vendor.py
=================
Lädt Windows-Binaries (FFmpeg, FFprobe) in den vendor/-Ordner.
Wird von BUILD_STANDALONE.bat vor PyInstaller aufgerufen.

Diese Binaries werden dann direkt in die EXE eingebacken,
sodass der Endnutzer KEIN Internet benötigt.
"""

import os
import sys
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

VENDOR_DIR = Path(__file__).parent / "vendor"
VENDOR_DIR.mkdir(exist_ok=True)

# Offizielle FFmpeg Windows-Builds (statisch kompiliert, keine DLL-Abhängigkeiten)
FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

# yt-dlp als EXE (optional - wir nutzen lieber die Python-Bibliothek)
# YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


def download_with_progress(url: str, dest: Path, label: str) -> None:
    """Lädt eine Datei herunter und zeigt Fortschritt."""
    print(f"  Lade {label}...")
    print(f"  URL: {url}")

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "RetroDisc-Builder/1.0"}
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            chunk_size = 1024 * 256  # 256 KB chunks

            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)

                    if total > 0:
                        pct = done / total * 100
                        bar_len = 40
                        filled = int(bar_len * done / total)
                        bar = "#" * filled + "." * (bar_len - filled)
                        mb = done / 1024 / 1024
                        total_mb = total / 1024 / 1024
                        print(
                            f"\r  [{bar}] {pct:.0f}% ({mb:.1f}/{total_mb:.1f} MB)",
                            end="", flush=True
                        )

            print(f"\r  OK: {label} heruntergeladen ({done/1024/1024:.1f} MB)")

    except urllib.error.URLError as e:
        dest.unlink(missing_ok=True)
        print(f"\n  FEHLER: Download fehlgeschlagen: {e}")
        raise


def extract_ffmpeg(zip_path: Path) -> None:
    """Extrahiert ffmpeg.exe und ffprobe.exe aus dem ZIP."""
    print(f"  Extrahiere aus ZIP...")

    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()

        # Suche nach ffmpeg.exe und ffprobe.exe im ZIP
        for target_name in ("ffmpeg.exe", "ffprobe.exe"):
            # Suche in allen Pfaden im ZIP
            found = None
            for member in members:
                if member.endswith(f"/bin/{target_name}") or member.endswith(f"\\bin\\{target_name}"):
                    found = member
                    break
                elif member.endswith(f"/{target_name}") and "bin" in member:
                    found = member
                    break

            if not found:
                # Fallback: Suche einfach nach dem Dateinamen
                for member in members:
                    if Path(member).name == target_name:
                        found = member
                        break

            if found:
                dest = VENDOR_DIR / target_name
                with zf.open(found) as src, open(dest, "wb") as dst:
                    import shutil
                    shutil.copyfileobj(src, dst)
                size_mb = dest.stat().st_size / 1024 / 1024
                print(f"  OK: {target_name} extrahiert ({size_mb:.1f} MB)")
            else:
                print(f"  FEHLER: {target_name} nicht im ZIP gefunden!")
                print(f"  Verfügbare Dateien: {[m for m in members if m.endswith('.exe')][:10]}")
                raise FileNotFoundError(f"{target_name} nicht im ZIP")


def check_vendor() -> bool:
    """Prüft ob vendor/-Ordner vollständig ist."""
    required = ["ffmpeg.exe", "ffprobe.exe"]
    missing = [f for f in required if not (VENDOR_DIR / f).exists()]

    if missing:
        print(f"  Fehlend: {missing}")
        return False

    # Dateigröße prüfen (mindestens 10 MB = echte Binary, nicht leer)
    for f in required:
        size = (VENDOR_DIR / f).stat().st_size
        if size < 10 * 1024 * 1024:
            print(f"  {f} zu klein ({size} Bytes) - wahrscheinlich beschädigt")
            (VENDOR_DIR / f).unlink()
            return False

    return True


def main():
    print()
    print("  RetroDisc - Vendor-Binaries vorbereiten")
    print("  " + "=" * 40)

    # Bereits vorhanden?
    if check_vendor():
        print("  OK: Alle Binaries bereits vorhanden")
        for f in ["ffmpeg.exe", "ffprobe.exe"]:
            size_mb = (VENDOR_DIR / f).stat().st_size / 1024 / 1024
            print(f"    {f}: {size_mb:.1f} MB")
        return 0

    # FFmpeg-ZIP herunterladen
    zip_path = VENDOR_DIR / "ffmpeg_bundle.zip"

    try:
        print()
        print("  Lade FFmpeg für Windows (ca. 80-90 MB)...")
        print("  Quelle: github.com/BtbN/FFmpeg-Builds")
        print()
        download_with_progress(FFMPEG_URL, zip_path, "FFmpeg-Bundle")

        print()
        extract_ffmpeg(zip_path)

    finally:
        # ZIP nach Extraktion löschen
        if zip_path.exists():
            zip_path.unlink()
            print("  ZIP gelöscht")

    # Ergebnis prüfen
    if check_vendor():
        print()
        print("  OK: Alle Vendor-Binaries bereit!")
        print()
        for f in ["ffmpeg.exe", "ffprobe.exe"]:
            size_mb = (VENDOR_DIR / f).stat().st_size / 1024 / 1024
            print(f"    vendor/{f}: {size_mb:.1f} MB")
        return 0
    else:
        print()
        print("  FEHLER: Vendor-Binaries unvollständig!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
