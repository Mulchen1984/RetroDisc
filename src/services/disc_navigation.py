"""Ehrliche Offenlegung der Disc-*Menü*-Navigationsfähigkeit der aktuellen
Wiedergabe-Engine (mpv, siehe ``player.py``).

Nicht zu verwechseln mit ``drm_capabilities.py`` (CSS/AACS/BD+-Verschlüsselung) -
hier geht es um interaktive Navigation (Hauptmenü, Titelmenü, Pfeiltasten,
Bestätigen), nicht um Entschlüsselung. Ein unverschlüsseltes Medium mit Menü
ist ohne Weiteres lesbar, aber die MENÜ-*Steuerung* ist trotzdem nicht
möglich - das ist genau das Ergebnis dieses Moduls.

## Untersuchung (2026-09-13, mpv 0.41.0, echter Quellcode geprüft)

Ausgangspunkt war die Frage, ob mpv/libdvdnav bzw. libbluray in der
aktuellen, bereits etablierten Engine (siehe ``player.py``) interaktive
Disc-Menüs unterstützen - explizit VOR jeder Eigenentwicklung geprüft
(``stream/stream_dvdnav.c``, ``stream/stream_bluray.c`` aus dem offiziellen
mpv-0.41.0-Quellarchiv, nicht nur Dokumentation):

* **DVD-Menü**: ``stream_dvdnav.c`` wirft für jeden Versuch, ``dvd://menu``
  zu öffnen, einen fatalen Fehler: ``MP_FATAL(stream, "DVD menu support has
  been removed.\\n")`` (Zeile 636, ``ret = STREAM_ERROR``). Das ist
  UNABHÄNGIG davon, ob ``libdvdnav`` überhaupt kompiliert ist - selbst ein
  mpv-Build mit vollständigem ``libdvdnav`` würde an genau dieser Stelle
  denselben Fehler werfen. mpv hat interaktive DVD-Menüs upstream entfernt,
  das ist keine Frage von Abhängigkeiten oder Build-Optionen.
* **Blu-ray HDMV-Menü**: ``stream_bluray.c`` definiert zwar
  ``BLURAY_MENU_TITLE`` (für ``bd://menu``), aber es existiert KEIN
  ``STREAM_CTRL`` für Tasten-/Maus-Eingabe (kein ``bd_user_input``, kein
  ``BD_VK_*``-Mapping, kein ``bd_mouse_select``) - nur Lesezugriffe
  (Kapitel/Titel/Sprache/Disc-Name). Es gibt schlicht keine Schnittstelle,
  über die mpv Navigationseingaben an libbluray weiterreichen könnte.
* **BD-J**: ``libbluray`` (Homebrew, 1.5.0) exportiert zwar die BD-J-API-
  Stubs (``bd_start_bdj``/``bd_stop_bdj``/``bd_read_bdjo``/``bd_free_bdjo``),
  ist aber gegen KEINE Java-Laufzeit gelinkt (``otool -L`` zeigt nur
  fontconfig/freetype/libudfread/libxml2 - keine JVM). Ohne gebundene
  Laufzeit kann BD-J-Code nicht ausgeführt werden.

**Ergebnis**: keine der drei Fähigkeiten ist mit mpv als Engine erreichbar -
nicht wegen dieser Entwicklungsumgebung, sondern weil die etablierte,
bereits integrierte Engine selbst das Feature entweder entfernt hat (DVD)
oder nie eine steuerbare Schnittstelle dafür angeboten hat (Blu-ray HDMV,
BD-J). Ein Wechsel auf eine andere Engine (z. B. VLC/libVLC, die
interaktive Disc-Menüs bekanntermaßen unterstützt) wäre ein vollständiger
Austausch der Wiedergabe-Architektur (andere IPC-Schnittstelle, anderes
Prozess-/Einbettungsmodell) und hätte zwangsläufig Rückwirkungen auf die
bereits stabile, getestete mpv-Integration - das würde "bestehende
Funktionen dürfen nicht regressieren" verletzen und ist nicht Teil dieses
Blocks.
"""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import Optional

from src.utils.subprocesses import create_hidden_subprocess


@dataclass(frozen=True)
class NavigationCapability:
    supported: bool
    reason: str

    def to_dict(self) -> dict:
        return {"supported": self.supported, "reason": self.reason}


_DVD_MENU_REASON = (
    "mpv hat interaktive DVD-Menüs entfernt (Quellcode-Beleg: "
    "stream/stream_dvdnav.c, \"DVD menu support has been removed.\" - "
    "unabhängig davon, ob libdvdnav kompiliert ist)."
)
_BLURAY_HDMV_REASON = (
    "mpv bietet keine steuerbare Schnittstelle für Blu-ray-HDMV-Menüs "
    "(kein STREAM_CTRL für Tasten-/Mauseingabe in stream/stream_bluray.c - "
    "nur lesender Zugriff auf Titel/Kapitel/Sprache)."
)


def dvd_menu_navigation_supported() -> NavigationCapability:
    """Immer False mit der aktuellen Engine - siehe Moduldoku. Kein
    Laufzeit-Check nötig, da die Entfernung im Quellcode selbst liegt, nicht
    an einer fehlenden Abhängigkeit."""
    return NavigationCapability(False, _DVD_MENU_REASON)


def bluray_hdmv_menu_navigation_supported() -> NavigationCapability:
    """Immer False mit der aktuellen Engine - siehe Moduldoku."""
    return NavigationCapability(False, _BLURAY_HDMV_REASON)


async def _run_otool(args: list[str]) -> Optional[str]:
    """otool-Aufruf über denselben versteckten Subprozess-Helfer wie jedes
    andere externe Werkzeug im Projekt (kein Konsolenfenster unter Windows -
    hier zwar irrelevant, da otool macOS-exklusiv ist, aber
    ``tests/test_subprocess_visibility.py`` verlangt den Wrapper für JEDEN
    Subprozessaufruf in ``src/``, unabhängig von Plattform-Erreichbarkeit)."""
    try:
        proc = await create_hidden_subprocess(
            "otool", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except (OSError, asyncio.TimeoutError):
        return None
    return stdout.decode("utf-8", errors="replace")


async def _mpv_libbluray_path(mpv_path: Optional[str]) -> Optional[str]:
    """Ermittelt den von der laufenden mpv-Instanz tatsächlich verlinkten
    libbluray-Pfad (nicht nur irgendeine installierte Version)."""
    mpv_path = mpv_path or shutil.which("mpv")
    if not mpv_path or not shutil.which("otool"):
        return None
    output = await _run_otool(["-L", mpv_path])
    if output is None:
        return None
    for line in output.splitlines():
        line = line.strip()
        if "libbluray" in line.lower():
            return line.split(" ")[0]
    return None


async def bluray_bdj_supported(mpv_path: Optional[str] = None) -> NavigationCapability:
    """Echter Laufzeit-Check (macOS): folgt der tatsächlich von mpv
    verlinkten libbluray-Bibliothek und prüft, ob SIE gegen eine
    Java-Laufzeit gelinkt ist. Ohne ``otool`` (z. B. unter Windows) wird
    NIE stillschweigend Unterstützung angenommen - siehe Rückgabe unten."""
    if not shutil.which("otool"):
        return NavigationCapability(
            False,
            "BD-J-Laufzeitprüfung erfordert 'otool' (macOS) - auf dieser "
            "Plattform nicht verfügbar, daher nicht als unterstützt "
            "ausgewiesen (keine unbelegte Zusage).",
        )
    libbluray_path = await _mpv_libbluray_path(mpv_path)
    if not libbluray_path:
        return NavigationCapability(
            False, "libbluray-Pfad der mpv-Instanz konnte nicht ermittelt werden."
        )
    deps = await _run_otool(["-L", libbluray_path])
    if deps is None:
        return NavigationCapability(
            False, f"libbluray-Abhängigkeiten von {libbluray_path} konnten nicht gelesen werden."
        )
    deps = deps.lower()
    if "jvm" in deps or "libjava" in deps or ".jre" in deps:
        return NavigationCapability(True, f"libbluray ({libbluray_path}) ist gegen eine Java-Laufzeit gelinkt.")
    return NavigationCapability(
        False,
        f"libbluray ({libbluray_path}) exportiert nur BD-J-API-Stubs "
        "(bd_start_bdj/bd_stop_bdj), ist aber gegen keine Java-Laufzeit "
        "gelinkt - BD-J-Inhalte können nicht ausgeführt werden.",
    )


async def describe_disc_navigation_support(mpv_path: Optional[str] = None) -> dict:
    """Strukturierte Momentaufnahme für Bridge/UI - siehe Moduldoku für die
    vollständige Begründung jeder Zeile."""
    return {
        "dvd_menu": dvd_menu_navigation_supported().to_dict(),
        "bluray_hdmv_menu": bluray_hdmv_menu_navigation_supported().to_dict(),
        "bluray_bdj": (await bluray_bdj_supported(mpv_path)).to_dict(),
    }
