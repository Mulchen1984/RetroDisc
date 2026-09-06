"""RD-05: Der Konvertieren-Tab zeigt reale Konfiguration, keinen Platzhalter.

Das Feld ``#outdir`` trug einen fest im Markup stehenden Platzhalter
``C:\\Videos\\RetroDisc``. Dieser Pfad existiert auf keinem Rechner - der
Standard liegt unter dem Benutzerprofil. Das Feld wurde ausserdem nie aus den
Einstellungen befuellt, sodass der Nutzer einen erfundenen Zielordner las und
seine Datei anschliessend am falschen Ort suchte.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

UI = (Path(__file__).parents[1] / "src" / "ui" / "app.html").read_text(encoding="utf-8")


def _outdir_input() -> str:
    match = re.search(r"<input[^>]*id=\"outdir\"[^>]*>", UI)
    if match:
        return match.group(0)
    # Attributreihenfolge ist nicht garantiert; zweiter Versuch ueber das Ende.
    match = re.search(r"<input[^>]*\bid=\"outdir\"[\s\S]{0,200}?>", UI)
    assert match, "Das Feld #outdir wurde nicht gefunden"
    return match.group(0)


def test_the_invented_placeholder_path_is_gone():
    assert "C:\\Videos\\RetroDisc" not in UI, \
        "Der erfundene Platzhalterpfad steht wieder im Markup"


def test_the_field_carries_no_placeholder_at_all():
    assert "placeholder=" not in _outdir_input(), \
        "Ein Platzhalter im Ausgabeordner ist immer ein erfundener Pfad"


def test_the_field_is_filled_from_the_real_settings():
    assert "outdir.value=s.directories.output_dir" in UI, \
        "loadSettingsIntoForm befuellt den Ausgabeordner nicht"


def test_the_field_is_refreshed_when_the_convert_flow_opens():
    assert "if(name==='convert'){ refreshOutputDirField(); }" in UI
    assert "async function refreshOutputDirField()" in UI
    assert "s.directories?.output_dir" in UI


def test_an_own_entry_is_not_overwritten_by_the_settings():
    """Wer selbst einen Ordner waehlt, behaelt ihn."""
    assert "outdir.dataset.userEdited" in UI
    assert "oninput=\"this.dataset.userEdited='1'\"" in _outdir_input()
    assert "!outdir.dataset.userEdited" in UI, \
        "Die Einstellung darf eine eigene Eingabe nicht ueberschreiben"


def test_the_browse_dialog_marks_the_field_as_chosen():
    match = re.search(
        r"async function openOutputFolderDialog\(\)\{[\s\S]*?\n\}", UI)
    assert match, "openOutputFolderDialog wurde nicht gefunden"
    assert "userEdited='1'" in match.group(0)


def test_go_convert_still_falls_back_to_the_backend_default():
    """Ein leeres Feld muss weiterhin 'nimm die Einstellung' bedeuten."""
    match = re.search(r"async function goConvert\(\)\{[\s\S]*?\n\}", UI)
    assert match, "goConvert wurde nicht gefunden"
    assert "outputDir||null" in match.group(0)
