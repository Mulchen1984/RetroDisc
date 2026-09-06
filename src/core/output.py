"""Zielnamen fuer Ausgabedateien atomar reservieren.

Der Downloader machte das als einziger Pfad richtig: er reserviert seinen
Zielnamen mit einem exklusiven ``x``-Open, statt ``exists()`` zu pruefen und
danach zu schreiben. Alle anderen Wege setzten ihren Namen fest zusammen und
ueberschrieben, was schon da war - ``Disc_D_Rip.mkv`` traf die zweite Disc
genauso wie die erste, und ein zweites DVD-Projekt mit dem Vorgabetitel
loeschte das Abbild des ersten.

Dieses Modul zieht die vorhandene Technik aus ``src/core/downloader.py``
heraus, damit sie allen Ausgabepfaden zur Verfuegung steht. Die Semantik ist
unveraendert: ein belegter Name weicht auf ``" (1)"``, ``" (2)"`` usw. aus,
und die Reservierung ist ein einziger atomarer Syscall (``O_CREAT | O_EXCL``),
kein Pruefen-dann-Schreiben.

Die Reservierung legt die Zieldatei als leere Datei an. Wer danach schreibt,
muss deshalb ueberschreiben duerfen - fuer den reservierten, ausschliesslich
eigenen Namen ist das genau richtig und kein Datenverlust.
"""

from __future__ import annotations

import time
from pathlib import Path

import structlog

log = structlog.get_logger()

#: Nach so vielen belegten Namen wird nicht weitergezaehlt.
MAX_COLLISIONS = 10_000


class OutputError(Exception):
    """Ein Zielname konnte nicht reserviert werden."""


def remove_claimed_targets(targets: list[Path]) -> None:
    """Gibt bereits reservierte Namen wieder frei."""
    for target in reversed(targets):
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            # Auch bei einem gesperrten Ziel die uebrigen eigenen Dateien aufraeumen.
            log.warning("Reservierung konnte nicht zurueckgenommen werden",
                        path=str(target), error=str(exc))


def claim_target_group(targets: list[Path], stem: str) -> list[Path]:
    """Reserviert alle Gruppennamen exklusiv mit demselben Kollisionszaehler.

    Eine Gruppe sind zusammengehoerende Dateien mit gemeinsamem Stamm - etwa
    ein Video und sein Untertitel. Sie bekommen denselben Zaehler, damit sie
    zusammen bleiben.
    """
    if not targets:
        return []
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
    for counter in range(MAX_COLLISIONS):
        suffix = f" ({counter})" if counter else ""
        candidates = [
            p.with_name(f"{stem}{suffix}{p.name[len(stem):]}") for p in targets
        ]
        claimed: list[Path] = []
        try:
            for candidate in candidates:
                with open(candidate, "xb"):
                    claimed.append(candidate)
            return claimed
        except FileExistsError:
            remove_claimed_targets(claimed)
        except BaseException:
            remove_claimed_targets(claimed)
            raise
    raise OutputError(f"Zu viele Namenskollisionen fuer {targets[0].name}")


def claim_unique_target(target: Path) -> Path:
    """Reserviert atomar einen freien Zielpfad und weicht Kollisionen aus."""
    return claim_target_group([Path(target)], Path(target).stem)[0]


def timestamped(target: Path) -> Path:
    """Haengt einen Zeitstempel an den Dateinamen - ohne zu reservieren.

    Fuer Ergebnisse, deren Name sonst nur aus dem Laufwerksbuchstaben oder
    einem Vorgabetitel besteht und die dadurch bei jedem Lauf gleich hiessen.
    Der Zeitstempel macht sie schon vor dem Zaehler unterscheidbar.
    """
    target = Path(target)
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    return target.with_name(f"{target.stem}_{stamp}{target.suffix}")
