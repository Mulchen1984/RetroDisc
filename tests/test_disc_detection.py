# -*- coding: utf-8 -*-
"""Regressionstests fuer die Medienerkennung in ``DiscTools.get_disc_info``.

Zwei echte Fehler, beide am 2026-09-03 mit einem virtuell eingebundenen
DVD-Abbild reproduziert:

1. ``present`` folgte aus der *Abwesenheit* dreier englischer Fehlermuster.
   Auf einem deutschen Windows meldet ``dvd+rw-mediainfo`` fuer einen nicht
   vorhandenen Laufwerksbuchstaben aber "Z:: unable to open: Ein oder mehrere
   Argumente sind ungueltig." -- RetroDisc behauptete daraufhin ein Medium in
   einem Laufwerk, das es gar nicht gibt.
2. Fuer ein virtuell eingebundenes Abbild meldet dasselbe Werkzeug "unable to
   TEST UNIT READY". Die Erkennung gab daraufhin "kein Medium" zurueck,
   obwohl ``VIDEO_TS`` lesbar war und der Rip-Workflow einwandfrei lief.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from src.core import disc as disc_module
from src.core.disc import DiscTools

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows-Laufwerkslogik")

MEDIAINFO_UNABLE_TO_OPEN = (
    "\nZ:: unable to open: Ein oder mehrere Argumente sind ung�ltig.\r\r\n"
)
MEDIAINFO_NO_MEDIA = (
    "INQUIRY:\t\t[PIONEER ][BD-RW   BDR-209M][1.34]\n"
    "H:: unable to TEST UNIT READY: Das Ger�t ist nicht bereit.\n"
)
MEDIAINFO_REAL_DVD = (
    'Mounted Media:         11h, DVD-R Sequential\n'
    "Disc status:           complete\n"
    "READ CAPACITY:          2296512*2048=4703256576\n"
)


def _fake_mediainfo(output: str):
    """Ersetzt den Werkzeugaufruf durch eine feste Ausgabe."""

    class _Proc:
        returncode = 0

        async def communicate(self):
            return output.encode("utf-8"), b""

    async def _spawn(*_cmd, **_kwargs):
        return _Proc()

    return _spawn


@pytest.fixture
def mediainfo_available(monkeypatch):
    monkeypatch.setattr(disc_module.shutil, "which", lambda _path: _path)


@WINDOWS_ONLY
def test_volume_info_recognises_dvd_video(tmp_path):
    (tmp_path / "VIDEO_TS").mkdir()
    info = DiscTools._windows_volume_info(str(tmp_path), {"present": False, "readable": False})

    assert info["present"] is True
    assert info["readable"] is True
    assert info["type"] == "DVD-Video"


@WINDOWS_ONLY
def test_volume_info_recognises_bluray(tmp_path):
    (tmp_path / "BDMV").mkdir()
    info = DiscTools._windows_volume_info(str(tmp_path), {"present": False, "readable": False})

    assert info["type"] == "Blu-ray"


@WINDOWS_ONLY
def test_volume_info_reports_empty_volume_as_blank(tmp_path):
    info = DiscTools._windows_volume_info(
        str(tmp_path), {"present": False, "readable": False, "blank": False, "type": "unknown"}
    )

    assert info["present"] is True
    assert info["blank"] is True
    assert info["readable"] is False
    assert info["type"] == "blank"


@WINDOWS_ONLY
def test_volume_info_reports_missing_volume_as_absent(tmp_path):
    info = DiscTools._windows_volume_info(
        str(tmp_path / "gibt-es-nicht"), {"present": False, "readable": False}
    )

    assert info["present"] is False


@WINDOWS_ONLY
def test_missing_drive_is_not_reported_as_media(monkeypatch, mediainfo_available, tmp_path):
    """Der lokalisierte Oeffnen-Fehler darf kein Medium vortaeuschen."""
    monkeypatch.setattr(
        disc_module, "create_hidden_subprocess", _fake_mediainfo(MEDIAINFO_UNABLE_TO_OPEN)
    )
    tools = DiscTools(mediainfo_path="dvd+rw-mediainfo")

    info = asyncio.run(tools.get_disc_info(str(tmp_path / "gibt-es-nicht")))

    assert info["present"] is False
    assert info["readable"] is False


@WINDOWS_ONLY
def test_readable_volume_wins_over_tool_reporting_no_media(
    monkeypatch, mediainfo_available, tmp_path
):
    """Ein lesbares Medium zaehlt, auch wenn das Werkzeug schweigt."""
    (tmp_path / "VIDEO_TS").mkdir()
    monkeypatch.setattr(
        disc_module, "create_hidden_subprocess", _fake_mediainfo(MEDIAINFO_NO_MEDIA)
    )
    tools = DiscTools(mediainfo_path="dvd+rw-mediainfo")

    info = asyncio.run(tools.get_disc_info(str(tmp_path)))

    assert info["present"] is True
    assert info["readable"] is True
    assert info["type"] == "DVD-Video"


@WINDOWS_ONLY
def test_empty_drive_stays_absent_when_tool_reports_no_media(
    monkeypatch, mediainfo_available, tmp_path
):
    """Der Fallback darf ein wirklich leeres Laufwerk nicht erfinden."""
    monkeypatch.setattr(
        disc_module, "create_hidden_subprocess", _fake_mediainfo(MEDIAINFO_NO_MEDIA)
    )
    tools = DiscTools(mediainfo_path="dvd+rw-mediainfo")

    info = asyncio.run(tools.get_disc_info(str(tmp_path / "kein-laufwerk")))

    assert info["present"] is False


@WINDOWS_ONLY
def test_positive_tool_evidence_is_still_used(monkeypatch, mediainfo_available, tmp_path):
    """Meldet das Werkzeug ein Profil, bleibt dessen Auswertung massgeblich."""
    monkeypatch.setattr(
        disc_module, "create_hidden_subprocess", _fake_mediainfo(MEDIAINFO_REAL_DVD)
    )
    tools = DiscTools(mediainfo_path="dvd+rw-mediainfo")

    info = asyncio.run(tools.get_disc_info("D:"))

    assert info["present"] is True
    assert info["profile"] == "DVD-R Sequential"
    assert info["blank"] is False
    assert info["readable"] is True
    assert info["capacity_bytes"] == 4703256576


@WINDOWS_ONLY
@pytest.mark.parametrize(
    ("line", "expected", "rewritable"),
    [
        ("Mounted Media:         11h, DVD-R Sequential", "DVD-R Sequential", False),
        ('Mounted Media:         1Ah, "DVD+RW"', "DVD+RW", True),
        ("Mounted Media:         1Ah, DVD+RW", "DVD+RW", True),
        ("Mounted Media:         41h, BD-R SRM", "BD-R SRM", False),
    ],
)
def test_media_profile_is_parsed_quoted_and_unquoted(
    monkeypatch, mediainfo_available, line, expected, rewritable
):
    """Beide Schreibweisen des Profils muessen ausgewertet werden."""
    output = f"{line}\nDisc status:           complete\n"
    monkeypatch.setattr(disc_module, "create_hidden_subprocess", _fake_mediainfo(output))
    tools = DiscTools(mediainfo_path="dvd+rw-mediainfo")

    info = asyncio.run(tools.get_disc_info("D:"))

    assert info["profile"] == expected
    assert info["type"] == expected
    assert info["rewritable"] is rewritable
