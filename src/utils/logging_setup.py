"""UTF-8-sichere Standardstroeme fuer Logging und Konsolenausgabe.

Windows gibt einem Prozess Standardstroeme mit der ANSI-Codepage (cp1252).
Jedes Zeichen ausserhalb dieser Codepage - Emoji und Sonderzeichen aus
YouTube-Titeln, CJK, Private-Use-Glyphen - laesst dann schon das blosse
Loggen eines Dateinamens mit
``UnicodeEncodeError: 'charmap' codec can't encode character`` scheitern.

Das ist kein Fehler der Medienpipeline. Es reisst aber bereits erfolgreich
abgeschlossene Arbeit in einen Fehlerzustand, sobald so ein Logaufruf
innerhalb eines ``try`` liegt, dessen ``except`` den Job scheitern laesst:
genau so wurde am 2026-09-05 ein vollstaendig heruntergeladener und korrekt
veroeffentlichter YouTube-Download in der Oberflaeche als FAILED angezeigt.

Deshalb werden die Stroeme hier einmalig auf UTF-8 mit ``errors="replace"``
gestellt. Ein nicht darstellbares Zeichen wird ersetzt, statt eine Ausnahme
auszuloesen. Echte Fehler bleiben davon unberuehrt: unterdrueckt wird nur die
Unfaehigkeit des Ausgabekanals, ein Zeichen darzustellen, nicht ein Fehler
der Anwendung.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Optional, TextIO

#: Nicht darstellbare Zeichen ersetzen statt eine Ausnahme auszuloesen.
ENCODING_ERRORS = "replace"

#: Zielkodierung fuer alle Textausgaben des Prozesses.
ENCODING = "utf-8"


def make_stream_utf8_safe(stream: Optional[TextIO]) -> Optional[TextIO]:
    """Gibt *stream* als UTF-8-Strom mit ``errors='replace'`` zurueck.

    ``None`` bleibt ``None`` - ein PyInstaller-Windowed-Build hat keine
    Standardstroeme. Laesst sich ein Strom weder umstellen noch neu
    umwickeln, wird er unveraendert zurueckgegeben; der Aufrufer darf ihn
    dann weiter benutzen, aber ohne diese Zusicherung.
    """
    if stream is None:
        return None

    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding=ENCODING, errors=ENCODING_ERRORS)
            return stream
        except (AttributeError, OSError, ValueError):
            pass

    # Aeltere oder ersetzte Stroeme (etwa ein von PyInstaller untergeschobener
    # Wrapper) koennen kein reconfigure. Dann den Binaerpuffer neu umwickeln.
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        try:
            return io.TextIOWrapper(
                buffer,
                encoding=ENCODING,
                errors=ENCODING_ERRORS,
                line_buffering=True,
            )
        except (AttributeError, OSError, ValueError):
            pass

    return stream


def open_null_stream() -> TextIO:
    """Ein verwerfender, aber schreibbarer Textstrom."""
    return open(os.devnull, "w", encoding=ENCODING, errors=ENCODING_ERRORS)


def configure_console_encoding() -> tuple[Optional[TextIO], Optional[TextIO]]:
    """Macht ``sys.stdout`` und ``sys.stderr`` prozessweit UTF-8-sicher.

    Muss laufen, bevor Logging-Handler die Stroeme einsammeln.
    """
    sys.stdout = make_stream_utf8_safe(sys.stdout)
    sys.stderr = make_stream_utf8_safe(sys.stderr)
    return sys.stdout, sys.stderr


def configure_structlog(stream: Optional[TextIO] = None) -> TextIO:
    """Bindet structlog explizit an einen UTF-8-sicheren Strom.

    Ohne diesen Aufruf benutzt structlog seine Default-``PrintLoggerFactory``.
    Die sammelt ``sys.stdout`` erst beim ersten Logaufruf ein und damit unter
    Windows den cp1252-Strom. Das Rendering bleibt unveraendert - nur das Ziel
    ist jetzt festgelegt und darstellungssicher.
    """
    import structlog

    target = stream if stream is not None else sys.stdout
    if target is None:
        target = open_null_stream()
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=target))
    return target
