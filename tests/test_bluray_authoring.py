"""Tests für das neue BDMV-Authoring (src/services/bluray_authoring.py).

MPLS wird gegen den bereits produktiven, unabhängig getesteten Leser
(``src/services/bluray_mpls.py``) im echten Round-Trip geprüft - keine
Annahme über das eigene Schreiben, sondern dieselbe Prüfung, die
``DiscAnalyzer``/``get_disc_content`` für echte Discs verwendet.

CLPI/index.bdmv/MovieObject.bdmv haben in diesem Projekt (noch) keinen
Leser zum Gegenprüfen - hier wird deshalb nur strukturelle Konsistenz
(Magic, Längen-Nesting, in sich passende Start-Adressen, PID-
Übereinstimmung mit FFmpeg.to_bluray_stream) getestet, nicht Bit-für-Bit-
Spec-Konformität. Das ist eine bewusste, im Modul dokumentierte Grenze.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.core.ffmpeg import FFmpeg
from src.services.bluray_authoring import (
    BlurayAuthoringError,
    author_bdmv,
    build_clip_info,
    build_index_bdmv,
    build_movie_object_bdmv,
    build_mpls,
)
from src.services.bluray_mpls import parse_mpls


# ─── MPLS: echter Round-Trip gegen den produktiven Leser ──────────────────

def test_single_clip_round_trips_through_the_real_reader():
    data = build_mpls([("00000", 12.5)])
    playlist = parse_mpls(data)
    assert playlist.clip_ids == ["00000"]
    assert playlist.duration_seconds == pytest.approx(12.5, abs=0.01)
    assert playlist.chapter_seconds == []


def test_multi_clip_playlist_sums_durations_in_order():
    data = build_mpls([("00000", 10.0), ("00001", 20.0), ("00002", 5.0)])
    playlist = parse_mpls(data)
    assert playlist.clip_ids == ["00000", "00001", "00002"]
    assert playlist.duration_seconds == pytest.approx(35.0, abs=0.01)


def test_chapters_land_on_the_correct_clip_and_absolute_timeline():
    data = build_mpls(
        [("00000", 10.0), ("00001", 10.0)],
        chapter_seconds=[0.0, 4.0, 12.0],
    )
    playlist = parse_mpls(data)
    assert playlist.chapter_seconds == pytest.approx([0.0, 4.0, 12.0], abs=0.05)


def test_no_chapters_yields_no_fabricated_marks():
    data = build_mpls([("00000", 10.0)])
    playlist = parse_mpls(data)
    assert playlist.chapter_seconds == []


def test_empty_clip_list_is_rejected():
    with pytest.raises(BlurayAuthoringError):
        build_mpls([])


# ─── CLPI: strukturelle Konsistenz + PID-Übereinstimmung ──────────────────

def test_clip_info_starts_with_correct_magic_and_version():
    data = build_clip_info(45000 * 10, video_pid=0x1011, audio_pid=0x1100)
    assert data[0:4] == b"HDMV"
    assert data[4:8] == b"0200"


def test_clip_info_declares_the_same_pids_ffmpeg_actually_writes():
    """Die konkret testbare Eigenschaft: CLIPINF und STREAM stimmen überein."""
    data = build_clip_info(45000 * 10, video_pid=FFmpeg.BLURAY_VIDEO_PID, audio_pid=FFmpeg.BLURAY_AUDIO_PID)
    assert FFmpeg.BLURAY_VIDEO_PID.to_bytes(2, "big") in data
    assert FFmpeg.BLURAY_AUDIO_PID.to_bytes(2, "big") in data
    # 0x1B = H.264/AVC, 0x81 = AC-3 (die von to_bluray_stream erzeugten Codecs).
    assert b"\x1b" in data
    assert b"\x81" in data


def test_clip_info_start_addresses_are_within_bounds_and_monotonic():
    data = build_clip_info(45000 * 10, video_pid=0x1011, audio_pid=0x1100)
    addresses = [int.from_bytes(data[8 + i * 4:12 + i * 4], "big") for i in range(5)]
    assert all(0 < addr < len(data) for addr in addresses)
    assert addresses == sorted(addresses)


# ─── index.bdmv / MovieObject.bdmv: strukturelle Konsistenz ───────────────

def test_index_bdmv_starts_with_correct_magic_and_points_within_bounds():
    data = build_index_bdmv()
    assert data[0:4] == b"INDX"
    indexes_start = int.from_bytes(data[8:12], "big")
    assert 0 < indexes_start < len(data)


def test_movie_object_bdmv_starts_with_correct_magic_and_declares_one_object():
    data = build_movie_object_bdmv()
    assert data[0:4] == b"MOBJ"
    # Aufbau: "MOBJ"(4)+version(4)+ExtensionData_addr(4)=12, dann der
    # MovieObjects()-Block: length(4)+reserved(2)+number_of_mobjs(2)+... .
    number_of_mobjs = int.from_bytes(data[18:20], "big")
    assert number_of_mobjs == 1


# ─── author_bdmv(): Orchestrierung mit gefakter FFmpeg-Schicht ────────────

class _FakeMediaFile:
    def __init__(self, duration_seconds: float):
        self.duration_seconds = duration_seconds


class _FakeFFmpeg:
    """Fakt nur die Subprozess-Schicht (to_bluray_stream/probe) - der reale
    Vertrag von FFmpeg.to_bluray_stream (PIDs, Codec) wird separat gegen
    das echte FFmpeg getestet, nicht hier (siehe Modul-Docstring)."""

    BLURAY_VIDEO_PID = FFmpeg.BLURAY_VIDEO_PID
    BLURAY_AUDIO_PID = FFmpeg.BLURAY_AUDIO_PID

    def __init__(self, durations: dict[str, float]):
        self._durations = durations

    async def to_bluray_stream(self, input_path, output_path, video_bitrate_bps=None, job=None):
        Path(output_path).write_bytes(b"fake-m2ts-bytes")
        return Path(output_path)

    async def probe(self, path):
        return _FakeMediaFile(self._durations[Path(path).stem])


@pytest.mark.asyncio
async def test_author_bdmv_writes_the_complete_expected_directory_tree(tmp_path):
    src_a = tmp_path / "a.mp4"
    src_b = tmp_path / "b.mp4"
    src_a.write_bytes(b"a")
    src_b.write_bytes(b"b")
    ffmpeg = _FakeFFmpeg({"00000": 10.0, "00001": 5.0})

    bd_root = await author_bdmv(ffmpeg, [src_a, src_b], tmp_path / "out")

    bdmv = bd_root / "BDMV"
    assert (bdmv / "index.bdmv").is_file()
    assert (bdmv / "MovieObject.bdmv").is_file()
    assert (bdmv / "PLAYLIST" / "00000.mpls").is_file()
    assert (bdmv / "STREAM" / "00000.m2ts").is_file()
    assert (bdmv / "STREAM" / "00001.m2ts").is_file()
    assert (bdmv / "CLIPINF" / "00000.clpi").is_file()
    assert (bdmv / "CLIPINF" / "00001.clpi").is_file()


@pytest.mark.asyncio
async def test_author_bdmv_output_is_readable_by_retrodiscs_own_bluray_reader(tmp_path):
    """Der stärkste verfügbare Validitätsnachweis: die bereits produktive,
    unabhängig getestete Leseseite (DiscAnalyzer) erkennt genau die Titel/
    Kapitel, die tatsächlich geschrieben wurden."""
    from src.core.disc import DiscTools
    from src.services.disc_analyzer import DiscAnalyzer
    from src.services.transcode.probe import MediaProbeService

    src = tmp_path / "movie.mp4"
    src.write_bytes(b"source")
    ffmpeg = _FakeFFmpeg({"00000": 42.0})

    bd_root = await author_bdmv(ffmpeg, [src], tmp_path / "out")

    async def fake_probe(path):
        from src.services.transcode.probe import SourceMediaInfo
        return SourceMediaInfo(duration=42.0)

    analyzer = DiscAnalyzer(DiscTools(), MediaProbeService())
    analyzer.probe.probe = fake_probe

    titles = await analyzer._bluray_titles(bd_root / "BDMV")
    assert len(titles) == 1
    assert titles[0].duration_seconds == pytest.approx(42.0, abs=0.01)
    assert titles[0].size_bytes == len(b"fake-m2ts-bytes")


@pytest.mark.asyncio
async def test_author_bdmv_rejects_empty_input_list(tmp_path):
    with pytest.raises(BlurayAuthoringError):
        await author_bdmv(_FakeFFmpeg({}), [], tmp_path / "out")
