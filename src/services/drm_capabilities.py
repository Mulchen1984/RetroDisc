"""Ehrliche Offenlegung der DRM-/Kopierschutz-Grenzen der Wiedergabe.

Keine Unterstützung behaupten, die technisch nicht vorhanden ist. Deckt sich
bewusst mit der bereits bestehenden Haltung aus ``src/services/ripper.py``
("Encrypted commercial DVD/Blu-ray media require an external decryption
backend (for example MakeMKV) and fail with an explicit message.") - hier
nur für den Player als strukturierte, prüfbare Aussage statt Freitext.

## Tatsächlicher Stand (Stand dieses Blocks)

* **Unverschlüsselte DVD/Blu-ray**: UNTERSTÜTZT. Reine Wiedergabe von
  VIDEO_TS/BDMV-Inhalten über mpv/FFmpeg-Decoder - keine Verschlüsselung
  im Weg.
* **CSS-verschlüsselte DVD**: NICHT unterstützt. Es existiert kein
  ``libdvdcss``-Einbindung in RetroDiscs Wiedergabepfad - selbst wenn
  ``libdvdcss`` als System-/Homebrew-Paket vorhanden sein sollte (z. B.
  als Abhängigkeit eines anderen Werkzeugs), ist es weder in
  ``prepare_vendor.py`` vendort noch von der hier verwendeten mpv-
  Wiedergabe-Engine genutzt (dieser mpv-Build hat laut ``--list-protocols``
  kein ``dvd://``/``dvdnav://`` - nur reine Dateisystem-Wiedergabe der
  VOB-Dateien). Verschlüsselte Discs schlagen mit einer klaren Fehlermeldung
  fehl, nicht mit einem stillen Blackscreen oder einer vorgetäuschten
  Wiedergabe.
* **AACS-verschlüsseltes Blu-ray**: NICHT unterstützt. Keine AACS-
  Schlüsseldatenbank, kein ``libaacs`` eingebunden.
* **BD+**: NICHT unterstützt. Keine Implementierung vorhanden (BD+ ist
  proprietär und hat praktisch keine quelloffene Umsetzung).

Für kopiergeschützte Medien bleibt die bereits etablierte Antwort: ein
externes, spezialisiertes Werkzeug (z. B. MakeMKV) wird vom Nutzer separat
benötigt - RetroDisc versucht keine eigene Umgehung.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DrmCapability:
    supported: bool
    detail: str

    def to_dict(self) -> dict:
        return {"supported": self.supported, "detail": self.detail}


def describe_drm_support() -> dict:
    """Strukturierte, für die UI/Bridge geeignete Momentaufnahme - siehe
    Moduldoku für die vollständige Begründung jeder Zeile."""
    return {
        "unencrypted_dvd": DrmCapability(
            True, "Unterstützt: reine VIDEO_TS-Wiedergabe über mpv/FFmpeg.",
        ).to_dict(),
        "unencrypted_bluray": DrmCapability(
            True, "Unterstützt: reine BDMV-Wiedergabe über mpv/FFmpeg.",
        ).to_dict(),
        "css_encrypted_dvd": DrmCapability(
            False,
            "Nicht unterstützt: kein libdvdcss im Wiedergabepfad eingebunden. "
            "Kopiergeschützte DVDs benötigen ein externes Werkzeug (z. B. MakeMKV).",
        ).to_dict(),
        "aacs_bluray": DrmCapability(
            False,
            "Nicht unterstützt: keine AACS-Schlüsseldatenbank/libaacs vorhanden.",
        ).to_dict(),
        "bdplus_bluray": DrmCapability(
            False, "Nicht unterstützt: keine BD+-Implementierung vorhanden.",
        ).to_dict(),
    }
