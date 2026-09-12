"""Zentrale, medienunabhängige Definition der RetroDisc-Zielmedien.

Eine einzige Quelle für alle Zielgrößen (DVD-5/9, BDMV-auf-DVD-5/9, echte
Blu-ray-Medien BD-25/50/100/128) statt über mehrere Dateien verstreuter
Magic Numbers. Wird vom ``CapacityPlanner`` (``src/services/capacity_planner.py``)
genutzt und ist so angelegt, dass ein späterer Authoring-/Brennweg dieselbe
Quelle verwenden kann.

## Dezimale Herstellerangabe vs. binäre Größe

``nominal_capacity_bytes`` ist die dezimale (SI, 10^9) Herstellerangabe, wie
sie auf der Verpackung steht - z. B. 4,7 GB = 4.700.000.000 Bytes bei DVD-5.
Das ist NICHT dasselbe wie 4,7 GiB (2^30-Einheiten): ein Werkzeug, das dieselbe
Byte-Zahl fälschlich durch 1024^3 statt 1000^3 teilt, zeigt für dieselbe Disc
"4,38 GB" an - ein in Consumer-Software verbreiteter Verwechslungsfehler.
Dieses Modul vermeidet ihn, indem sämtliche Kapazitäten ausschließlich in
Bytes geführt werden; jede GB/GiB-Anzeige ist Sache der aufrufenden Schicht.

``usable_capacity_bytes`` ist die nominelle Kapazität abzüglich einer
konservativen, klar benannten Sicherheitsmarge für Dateisystem-/
Formatierungs-Overhead (UDF-Bridge-Format bei DVD, UDF 2.50 bei Blu-ray).
Das ist eine bewusst gewählte Ingenieurs-Sicherheitsmarge, KEINE aus
Sektortabellen exakt gemessene Größe - siehe P0_CAPACITY_PLANNING.md,
Abschnitt "Kapazitäten", für die vollständige Begründung.

## Physische Blu-ray-Zielmedien vs. BDMV-auf-DVD-Rohling

**Korrektur (2026-09-11):** Die vorherige Fassung führte "BD-5"/"BD-9" als
eigene Zielmedien - das war irreführend bzw. fachlich falsch. BD-5/BD-9 sind
KEINE physischen Blu-ray-Formfaktoren; es gibt keinen 4,7-GB- oder
8,5-GB-Blu-ray-Rohling. Echte physische Blu-ray-Zielmedien sind ausschließlich
``bd25``/``bd50`` (Standard-BD) und ``bd100``/``bd128`` (BDXL).

Was vorher "BD-5"/"BD-9" hieß, beschreibt tatsächlich eine BDMV-Struktur
(Blu-ray-*Authoring*), die auf einem gewöhnlichen DVD-5- bzw. DVD-9-Rohling
gebrannt wird (damit auch günstige DVD-Rohlinge auf einem Blu-ray-Player
abspielbar sind) - ein in der Blu-ray-Hobby-Szene verbreitetes, aber nicht
mit einem physischen Blu-ray-Medium zu verwechselndes Vorgehen. Dieses Profil
bleibt erhalten, heißt jetzt aber eindeutig ``bdmv_on_dvd5``/``bdmv_on_dvd9``
mit einem Anzeigenamen, der die DVD-Kapazität und die fehlende physische
BD-Eigenschaft explizit nennt ("BDMV auf DVD-5 ... kein physisches
Blu-ray-Medium"). ``authoring_format=AuthoringFormat.BDMV`` bei gleichzeitig
DVD-5/DVD-9-Kapazität bleibt architektonisch bestehen (Disc-*Struktur* und
physisches Speichervermögen sind zwei unabhängige Achsen), nur die
Benennung wurde korrigiert.

## BDXL (BD-100/BD-128)

BDXL-Medien (Triple-/Quad-Layer, 100/128 GB) benötigen ein BDXL-fähiges
Laufwerk UND Brennbackend. Dieses Modul definiert ihre Kapazität als reine
Dateninformation (``requires_bdxl=True``) - es behauptet an keiner Stelle,
dass BDXL tatsächlich unterstützt wird. Die Prüfung erfolgt über
``bdxl_capability_warning()`` gegen die bereits vorhandene
``DriveCapabilities.bd_xl``-Erkennung (``src/services/drive_inspector.py``,
liest reale ``dvd+rw-mediainfo``-INQUIRY-Daten). Ohne bekannte
Laufwerksdaten wird BDXL nie stillschweigend als unterstützt angenommen.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.services.drive_inspector import DriveCapabilities


class AuthoringFormat(Enum):
    """Die Disc-*Struktur* (Authoring-Format), unabhängig von der physischen Kapazität."""
    DVD_VIDEO = "dvd_video"   # VIDEO_TS-Struktur
    BDMV = "bdmv"             # BDMV-Struktur


@dataclass(frozen=True)
class TargetMedium:
    id: str
    display_name: str
    authoring_format: AuthoringFormat
    nominal_capacity_bytes: int
    usable_capacity_bytes: int
    authoring_overhead_bytes: int = 0   # optionale zusätzliche, medienspezifische Reserve; Standard 0
    is_physical_bluray: bool = False     # echtes BD-Medium (BD-25/50/100/128), nicht BDMV-auf-DVD
    requires_bdxl: bool = False           # nur mit BDXL-fähigem Laufwerk/Backend real erreichbar


# 2 % konservative Sicherheitsmarge für Dateisystem-/Formatierungs-Overhead,
# einheitlich auf alle Medien angewendet - siehe Moduldoku oben.
_FILESYSTEM_OVERHEAD_RATIO = 0.02


def _usable(nominal_bytes: int) -> int:
    return round(nominal_bytes * (1 - _FILESYSTEM_OVERHEAD_RATIO))


TARGET_MEDIA: dict[str, TargetMedium] = {
    "dvd5": TargetMedium(
        id="dvd5", display_name="DVD-5 (Single Layer, 4,7 GB)",
        authoring_format=AuthoringFormat.DVD_VIDEO,
        nominal_capacity_bytes=4_700_000_000, usable_capacity_bytes=_usable(4_700_000_000),
    ),
    "dvd9": TargetMedium(
        id="dvd9", display_name="DVD-9 (Dual Layer, 8,5 GB)",
        authoring_format=AuthoringFormat.DVD_VIDEO,
        nominal_capacity_bytes=8_500_000_000, usable_capacity_bytes=_usable(8_500_000_000),
    ),
    "bdmv_on_dvd5": TargetMedium(
        id="bdmv_on_dvd5",
        display_name="BDMV auf DVD-5 (Blu-ray-Struktur auf 4,7-GB-Rohling, kein physisches Blu-ray-Medium)",
        authoring_format=AuthoringFormat.BDMV,
        nominal_capacity_bytes=4_700_000_000, usable_capacity_bytes=_usable(4_700_000_000),
    ),
    "bdmv_on_dvd9": TargetMedium(
        id="bdmv_on_dvd9",
        display_name="BDMV auf DVD-9 (Blu-ray-Struktur auf 8,5-GB-Rohling, kein physisches Blu-ray-Medium)",
        authoring_format=AuthoringFormat.BDMV,
        nominal_capacity_bytes=8_500_000_000, usable_capacity_bytes=_usable(8_500_000_000),
    ),
    "bd25": TargetMedium(
        id="bd25", display_name="BD-25 (Single Layer, 25 GB, physisches Blu-ray-Medium)",
        authoring_format=AuthoringFormat.BDMV,
        nominal_capacity_bytes=25_000_000_000, usable_capacity_bytes=_usable(25_000_000_000),
        is_physical_bluray=True,
    ),
    "bd50": TargetMedium(
        id="bd50", display_name="BD-50 (Dual Layer, 50 GB, physisches Blu-ray-Medium)",
        authoring_format=AuthoringFormat.BDMV,
        nominal_capacity_bytes=50_000_000_000, usable_capacity_bytes=_usable(50_000_000_000),
        is_physical_bluray=True,
    ),
    "bd100": TargetMedium(
        id="bd100", display_name="BD-100 / BDXL (Triple Layer, 100 GB, physisches Blu-ray-Medium)",
        authoring_format=AuthoringFormat.BDMV,
        nominal_capacity_bytes=100_000_000_000, usable_capacity_bytes=_usable(100_000_000_000),
        is_physical_bluray=True, requires_bdxl=True,
    ),
    "bd128": TargetMedium(
        id="bd128", display_name="BD-128 / BDXL (Quad Layer, 128 GB, physisches Blu-ray-Medium)",
        authoring_format=AuthoringFormat.BDMV,
        nominal_capacity_bytes=128_000_000_000, usable_capacity_bytes=_usable(128_000_000_000),
        is_physical_bluray=True, requires_bdxl=True,
    ),
}


def get_target_medium(medium_id: str) -> TargetMedium:
    """Wirft ValueError bei unbekannter ID - vom Aufrufer (CapacityPlanner)
    bewusst abgefangen und in ein CapacityPlan.error umgewandelt, damit
    ungültige Nutzereingaben nie zu einer Exception bis zur Bridge durchschlagen."""
    try:
        return TARGET_MEDIA[medium_id]
    except KeyError:
        raise ValueError(
            f"Unbekanntes Zielmedium: {medium_id!r}. Bekannt: {sorted(TARGET_MEDIA)} oder 'custom'."
        ) from None


def custom_target_medium(size_bytes: int, authoring_format: AuthoringFormat) -> TargetMedium:
    """Baut ein TargetMedium für eine benutzerdefinierte Zielgröße.

    Wirft ValueError bei nicht-positiver Größe - vom Aufrufer bewusst
    abgefangen, siehe get_target_medium()."""
    if size_bytes <= 0:
        raise ValueError("Custom-Zielgröße muss eine positive Byte-Anzahl sein.")
    return TargetMedium(
        id="custom", display_name=f"Benutzerdefiniert ({size_bytes:,} Bytes)".replace(",", "."),
        authoring_format=authoring_format,
        nominal_capacity_bytes=size_bytes, usable_capacity_bytes=_usable(size_bytes),
    )


def bdxl_capability_warning(medium: TargetMedium, drive_capabilities: Optional["DriveCapabilities"]) -> Optional[str]:
    """Prüft, ob ein BDXL-Zielmedium durch bekannte Laufwerks-/Backend-Daten
    gedeckt ist. Behauptet NIE Unterstützung ohne Beleg:

    - kein BDXL-Ziel -> ``None`` (nichts zu prüfen)
    - BDXL-Ziel, keine Laufwerksdaten übergeben -> Warnung "unbekannt"
    - BDXL-Ziel, Laufwerk meldet kein BDXL -> Warnung "nicht unterstützt"
    - BDXL-Ziel, Laufwerk meldet BDXL -> ``None`` (bestätigt unterstützt)
    """
    if not medium.requires_bdxl:
        return None
    if drive_capabilities is None:
        return ("BDXL-Fähigkeit des Laufwerks ist nicht bekannt (keine Laufwerksdaten "
                "übergeben) - vor dem Brennen mit einer echten Laufwerksprüfung bestätigen.")
    if not drive_capabilities.bd_xl:
        return "Dieses Laufwerk/Backend meldet keine BDXL-Unterstützung."
    return None


def target_medium_capability_issue(
    medium: TargetMedium,
    drive_capabilities: Optional["DriveCapabilities"],
    *,
    bdmv_authoring_available: bool = True,
) -> Optional[str]:
    """Grund, warum ``medium`` gerade NICHT erzeugt/gebrannt werden kann, oder
    ``None`` wenn nichts dagegen spricht. Schichtet die Prüfungen von der
    grundsätzlichsten zur speziellsten - die erste zutreffende Sperre
    gewinnt, es wird nie mehr behauptet als tatsächlich geprüft wurde:

    1. Software/Authoring: kann RetroDisc diese Struktur überhaupt bauen?
    2. Hardware-Schreibfähigkeit der physischen Medienfamilie (BD- vs.
       DVD-Rohling - unabhängig vom Authoring-Format, denn ``bdmv_on_dvd5``/
       ``bdmv_on_dvd9`` werden auf einem gewöhnlichen DVD-Rohling gebrannt).
    3. BDXL (delegiert an :func:`bdxl_capability_warning`).

    Ohne bekannte Laufwerksdaten (``drive_capabilities is None``) wird wie
    bei ``bdxl_capability_warning`` nie stillschweigend Unterstützung
    angenommen, aber auch kein Fehler erzwungen - der Aufrufer entscheidet
    (Warnung vs. harte Sperre), ob eine Prüfung ohne Laufwerksdaten möglich
    sein muss.
    """
    if medium.authoring_format is AuthoringFormat.BDMV and not bdmv_authoring_available:
        return "BDMV-Authoring-Backend ist nicht verfügbar (FFmpeg fehlt)."
    if drive_capabilities is not None:
        if medium.is_physical_bluray and not (drive_capabilities.bd_r or drive_capabilities.bd_re):
            return "Dieses Laufwerk kann keine Blu-ray-Rohlinge beschreiben."
        if not medium.is_physical_bluray and not drive_capabilities.dvd_write:
            return "Dieses Laufwerk kann keine DVD-Rohlinge beschreiben."
    return bdxl_capability_warning(medium, drive_capabilities)
