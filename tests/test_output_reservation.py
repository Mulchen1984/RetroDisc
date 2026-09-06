"""RD-03: Kein Ausgabeweg darf eine vorhandene Datei stillschweigend loeschen.

Der Downloader machte das immer richtig, alle anderen Wege nicht: Rip-Namen
kamen allein aus dem Laufwerksbuchstaben, der DVD-ISO-Name aus einem
Vorgabetitel, und die Werkzeugausgaben aus dem Namen der Quelldatei. Zweimal
derselbe Auftrag traf denselben Namen - je nach Weg mit hartem Abbruch oder
mit stillem Ueberschreiben.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from src.core.output import (
    OutputError,
    claim_target_group,
    claim_unique_target,
    remove_claimed_targets,
    timestamped,
)
from retrodisc_launcher import RetroDiscBridge


# ── Die Reservierung selbst ───────────────────────────────────────────

def test_a_free_name_is_claimed_unchanged(tmp_path):
    claimed = claim_unique_target(tmp_path / "Disc_D_Rip.mkv")

    assert claimed == tmp_path / "Disc_D_Rip.mkv"
    assert claimed.is_file(), "Die Reservierung muss die Datei wirklich belegen"


def test_a_taken_name_never_touches_the_existing_file(tmp_path):
    """Der Kern des Tickets: Disc zwei darf Disc eins nicht loeschen."""
    first = tmp_path / "Disc_D_Rip.mkv"
    first.write_bytes(b"erste disc")

    second = claim_unique_target(tmp_path / "Disc_D_Rip.mkv")

    assert second == tmp_path / "Disc_D_Rip (1).mkv"
    assert first.read_bytes() == b"erste disc", "Die erste Disc wurde ueberschrieben"


def test_the_counter_keeps_climbing(tmp_path):
    names = [claim_unique_target(tmp_path / "Rip.iso").name for _ in range(3)]

    assert names == ["Rip.iso", "Rip (1).iso", "Rip (2).iso"]


def test_the_parent_folder_is_created(tmp_path):
    claimed = claim_unique_target(tmp_path / "neu" / "tief" / "a.mkv")

    assert claimed.is_file()


def test_a_group_shares_one_counter(tmp_path):
    """Video und Untertitel duerfen nicht auseinanderlaufen."""
    (tmp_path / "Film.mp4").write_bytes(b"x")
    targets = [tmp_path / "Film.mp4", tmp_path / "Film.de.srt"]

    claimed = claim_target_group(targets, "Film")

    assert [p.name for p in claimed] == ["Film (1).mp4", "Film (1).de.srt"]


def test_remove_claimed_targets_frees_the_names(tmp_path):
    claimed = claim_target_group([tmp_path / "a.mkv", tmp_path / "a.srt"], "a")

    remove_claimed_targets(claimed)

    assert not any(p.exists() for p in claimed)


def test_timestamp_makes_a_fixed_name_distinguishable():
    stamped = timestamped(Path("C:/out/Disc_D_Rip.mkv"))

    assert stamped.suffix == ".mkv"
    assert stamped.name.startswith("Disc_D_Rip_")
    assert stamped.parent == Path("C:/out")


def test_a_hopeless_collision_raises_output_error(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.output.MAX_COLLISIONS", 2)
    for name in ("a.mkv", "a (1).mkv"):
        (tmp_path / name).write_bytes(b"x")

    with pytest.raises(OutputError):
        claim_unique_target(tmp_path / "a.mkv")


# ── Der Downloader benutzt jetzt dieselbe Technik ─────────────────────

def test_downloader_delegates_to_the_shared_reservation(tmp_path):
    """Kein zweiter Reservierungsmechanismus - sonst driften sie auseinander."""
    from src.core.downloader import Downloader

    (tmp_path / "Video.mp4").write_bytes(b"alt")
    claimed = Downloader._claim_unique_target(tmp_path / "Video.mp4")

    assert claimed.name == "Video (1).mp4"
    assert (tmp_path / "Video.mp4").read_bytes() == b"alt"


def test_downloader_still_raises_its_own_error_type(tmp_path, monkeypatch):
    """Bestehende Aufrufer fangen DownloadError; das darf sich nicht aendern."""
    from src.core.downloader import Downloader, DownloadError

    monkeypatch.setattr("src.core.output.MAX_COLLISIONS", 1)
    (tmp_path / "a.mp4").write_bytes(b"x")

    with pytest.raises(DownloadError):
        Downloader._claim_unique_target(tmp_path / "a.mp4")


# ── Der Wrapper der Bridge ────────────────────────────────────────────

class _Job:
    def __init__(self, output_path):
        self.output_path = output_path


def test_wrapper_reserves_before_the_handler_runs(tmp_path):
    seen = {}

    async def handler(job):
        seen["path"] = job.output_path
        assert job.output_path.is_file(), "Beim Start muss das Ziel belegt sein"
        job.output_path.write_bytes(b"ergebnis")

    (tmp_path / "film_4x.mp4").write_bytes(b"aelterer lauf")
    job = _Job(tmp_path / "film_4x.mp4")

    asyncio.run(RetroDiscBridge._with_reserved_output(handler)(job))

    assert seen["path"].name == "film_4x (1).mp4"
    assert (tmp_path / "film_4x.mp4").read_bytes() == b"aelterer lauf"


def test_wrapper_releases_the_name_when_the_handler_fails(tmp_path):
    async def handler(job):
        raise RuntimeError("FFmpeg abgebrochen")

    job = _Job(tmp_path / "film_4x.mp4")

    with pytest.raises(RuntimeError):
        asyncio.run(RetroDiscBridge._with_reserved_output(handler)(job))

    assert not (tmp_path / "film_4x.mp4").exists(), \
        "Ein gescheiterter Job darf keine leere Datei hinterlassen"


def test_wrapper_removes_the_ghost_when_the_handler_writes_elsewhere(tmp_path):
    other = tmp_path / "woanders.mp4"

    async def handler(job):
        other.write_bytes(b"x")
        job.output_path = other

    job = _Job(tmp_path / "film_4x.mp4")

    asyncio.run(RetroDiscBridge._with_reserved_output(handler)(job))

    assert not (tmp_path / "film_4x.mp4").exists()
    assert other.is_file()


def test_wrapper_keeps_a_real_result_that_moved(tmp_path):
    """Eine nicht leere Datei am reservierten Namen wird nie geloescht."""
    async def handler(job):
        job.output_path.write_bytes(b"echtes ergebnis")
        job.output_path = tmp_path / "film_4x.mp4"

    job = _Job(tmp_path / "film_4x.mp4")
    asyncio.run(RetroDiscBridge._with_reserved_output(handler)(job))

    assert (tmp_path / "film_4x.mp4").read_bytes() == b"echtes ergebnis"


# ── Verdrahtung: die betroffenen Wege gehen wirklich darueber ─────────

@pytest.mark.parametrize("method", [
    "create_highlights", "generate_subtitles", "upscale_video",
    "interpolate_video", "trim_video", "merge_videos",
])
def test_deterministic_paths_submit_through_the_wrapper(method):
    source = inspect.getsource(getattr(RetroDiscBridge, method))
    assert "self._with_reserved_output(_handler)" in source, \
        f"{method} reserviert seinen Zielnamen nicht"


def test_rip_disc_stamps_and_reserves():
    source = inspect.getsource(RetroDiscBridge.rip_disc)
    assert "timestamped(" in source, "Der Rip-Name bleibt sonst bei jedem Lauf gleich"
    assert "claim_unique_target(j.output_path)" in source


def test_copy_disc_uses_the_shared_reservation():
    source = inspect.getsource(RetroDiscBridge.copy_disc)
    assert "claim_unique_target(j.output_path)" in source
    assert 'with candidate.open("xb")' not in source, \
        "Die eigene Reservierungsschleife wurde nicht abgeloest"


def test_dvd_workflow_reserves_its_iso():
    from src.services import dvd_workflow

    source = inspect.getsource(dvd_workflow.DVDWorkflow.run)
    assert "claim_unique_target(out_dir" in source


def test_trim_can_be_told_the_target_is_already_reserved():
    from src.core.ffmpeg import FFmpeg

    assert "overwrite" in inspect.signature(FFmpeg.trim).parameters
    assert "overwrite=True" in inspect.getsource(RetroDiscBridge.trim_video)
