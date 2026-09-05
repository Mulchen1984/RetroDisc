"""Minimaler macOS-Bootstrap fuer die Vendor-Runtime.

Bewusst klein gehalten. Er ergaenzt **nur** das, was auf macOS anders ist, und
erfindet nichts:

* Der Whisper-Baum ist plattformneutral (CTranslate2-Gewichte, reine Daten).
  Er wird ueber die bestehende, gepinnte ``prepare_vendor.prepare_whisper()``
  geholt - derselbe Code, dieselbe Revision, dieselben SHA-256-Pruefungen.
* FFmpeg, FFprobe und yt-dlp sind Maschinencode und muessen als macOS-Build
  neu beschafft werden.
* Die DVD-Werkzeuge kommen unter Windows aus dem DVDStyler-Installer. Diesen
  Weg gibt es auf macOS nicht; dort liefert Homebrew die Gegenstuecke.

**Warum hier keine Pins fuer die macOS-Binaries stehen:** Dieses Projekt bindet
jede Aussage ueber ein Artefakt an dessen gemessenen SHA-256. Ein Pin, den
niemand verifiziert hat, waere genau die unbelegte Aussage, die
``RELEASE_AUDIT_STATUS.md`` verbietet. Die Pins werden deshalb auf dem Mac
**einmal gemessen und dann fest eingetragen** - dieses Skript hilft dabei
(``--pin <url>``), setzt sie aber nicht selbsttaetig als vertrauenswuerdig.

Aufruf auf dem Mac:

    python3 prepare_vendor_macos.py            # Bestandsaufnahme + Whisper
    python3 prepare_vendor_macos.py --pin URL  # SHA-256 einer Quelle messen

Exitcode 0 = alles vorhanden. 1 = es fehlt etwas (mit genauer Liste).
"""

from __future__ import annotations

import platform
import shutil
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from prepare_vendor import (  # noqa: E402
    VENDOR_DIR,
    WHISPER_REPO,
    WHISPER_REVISION,
    prepare_whisper,
    sha256_file,
    whisper_is_ready,
)

#: Werkzeuge, die als macOS-Build vorliegen muessen, mit ihrer Herkunft.
MACOS_TOOLS = {
    "ffmpeg": (
        "FFmpeg (macOS-Build)",
        "Homebrew: brew install ffmpeg — oder ein gepinnter Build von evermeet.cx",
    ),
    "ffprobe": (
        "FFprobe (macOS-Build)",
        "kommt mit demselben FFmpeg-Paket",
    ),
    "yt-dlp": (
        "yt-dlp (macOS)",
        "yt-dlp_macos derselben Version wie der Windows-Pin — ein aelterer Pin "
        "bricht den Download still mit HTTP 403",
    ),
    "dvdauthor": ("dvdauthor", "brew install dvdauthor"),
    "mkisofs": ("mkisofs", "brew install cdrtools"),
    "growisofs": ("growisofs", "brew install dvd+rw-tools"),
}

#: Python-Pakete, die nur macOS braucht (pywebview laeuft dort ueber WebKit).
MACOS_PYTHON_DEPS = ("pywebview", "pyobjc-core", "pyobjc-framework-Cocoa")


def measure_pin(url: str) -> int:
    """Laedt *url* und gibt den SHA-256 aus, damit er fest eingetragen wird."""
    target = Path(f"./.pin-{Path(url).name}")
    print(f"  Lade zum Messen: {url}")
    try:
        with urllib.request.urlopen(url) as response, open(target, "wb") as handle:
            shutil.copyfileobj(response, handle)
        digest = sha256_file(target)
        print(f"\n  Datei   : {target.name} ({target.stat().st_size} Bytes)")
        print(f"  SHA-256 : {digest}")
        print("\n  Diesen Wert fest in den macOS-Vendor-Pin eintragen.")
        return 0
    except OSError as exc:
        print(f"  FEHLER: {exc}")
        return 1
    finally:
        target.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    if "--pin" in argv:
        return measure_pin(argv[argv.index("--pin") + 1])

    print("\n  RetroDisc - macOS-Vendor-Bootstrap")
    print("  " + "=" * 52)
    if platform.system() != "Darwin":
        print(f"  HINWEIS: laeuft gerade auf {platform.system()}, nicht auf macOS.")
        print("  Die Bestandsaufnahme ist trotzdem aussagekraeftig.\n")

    VENDOR_DIR.mkdir(exist_ok=True)
    missing: list[str] = []

    # 1. Plattformneutral: derselbe Code wie unter Windows, keine Kopie.
    print("\n  [1] Whisper-Modell (plattformneutral)")
    print(f"      Repo     : {WHISPER_REPO}")
    print(f"      Revision : {WHISPER_REVISION}")
    if whisper_is_ready():
        print("      OK: bereits vorhanden und per SHA-256 verifiziert.")
    else:
        try:
            prepare_whisper()
            print("      OK: geholt und verifiziert.")
        except Exception as exc:  # noqa: BLE001 - Bestandsaufnahme, kein Abbruch
            missing.append(f"Whisper-Modell: {exc}")
            print(f"      FEHLT: {exc}")

    # 2. Maschinencode: muss als macOS-Build vorliegen.
    #
    # Auf einem Nicht-Darwin-Host findet `which` zwar ein gleichnamiges
    # Werkzeug, aber das ist dann ein Windows- oder Linux-Build. Ein "OK" waere
    # dort eine unbelegte Aussage - also wird es ausdruecklich nicht gegeben.
    on_macos = platform.system() == "Darwin"
    print("\n  [2] macOS-Binaries")
    for tool, (label, hint) in MACOS_TOOLS.items():
        location = shutil.which(tool)
        if location is None and (VENDOR_DIR / tool).is_file():
            location = str(VENDOR_DIR / tool)

        if location is None:
            missing.append(f"{label} - {hint}")
            print(f"      FEHLT {label}")
            print(f"            {hint}")
        elif on_macos:
            print(f"      OK    {label}: {location}")
        else:
            missing.append(f"{label} - auf macOS neu beschaffen: {hint}")
            print(f"      OFFEN {label}: gefunden unter")
            print(f"            {location},")
            print("            aber das ist kein macOS-Build.")

    # 3. Python-Pakete, die nur macOS braucht.
    print("\n  [3] macOS-Python-Pakete")
    for package in MACOS_PYTHON_DEPS:
        module = package.replace("-", "_").replace("pyobjc_framework_", "")
        try:
            __import__("webview" if package == "pywebview" else module)
            print(f"      OK    {package}")
        except ImportError:
            missing.append(f"{package} - pip install {package}")
            print(f"      FEHLT {package}  (pip install {package})")

    print("\n  " + "=" * 52)
    if missing:
        print(f"  UNVOLLSTAENDIG - {len(missing)} Punkt(e) offen:\n")
        for item in missing:
            print(f"    - {item}")
        print(
            "\n  Danach dieselben Pruefungen wie unter Windows fahren:\n"
            "    python3 -m pytest -q\n"
            "    python3 scripts/run_acceptance.py --source-only\n"
            "  Es gibt bewusst KEINE eigene macOS-Testlogik."
        )
        return 1

    print("  OK: macOS-Vendor-Runtime ist vollstaendig.")
    print(
        "\n  Naechster Schritt — derselbe Harness wie unter Windows:\n"
        "    python3 -m pytest -q\n"
        "    python3 scripts/run_acceptance.py --source-only"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
