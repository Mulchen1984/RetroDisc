"""Tests für das DiscContent-Modell, den DiscAnalyzer und die Bridge-Methode.

Stub-Objekte statt echter DiscTools/MediaProbeService: DiscAnalyzer greift nur
auf ``disc_tools.get_disc_info(device)`` und ``probe.probe(path)`` zu, beides
async - ein schlankes Duck-Typing-Double reicht, genau wie die vorhandenen
Tests FFmpeg-Methoden statt eines echten FFmpeg-Prozesses monkeypatchen.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.disc_content import (
    DiscAudioTrack,
    DiscChapter,
    DiscContent,
    DiscContentError,
    DiscSubtitleTrack,
    DiscTitle,
    DiscVideoInfo,
)
from src.models.media import DiscType
from src.services.disc_analyzer import DiscAnalyzer
from src.services.transcode.probe import AudioStream, SourceMediaInfo
from src.services.transcode.probe import SubtitleStream as ProbedSubtitle
from src.services.transcode.probe import VideoStream as ProbedVideo

_SECTOR_SIZE = 2048
_TT_SRPT_POINTER_OFFSET = 0xC4
_ENTRY_MARK = 1


# ─── Stubs ──────────────────────────────────────────────────────────────

class _FakeDiscTools:
    def __init__(self, info: dict):
        self._info = info

    async def get_disc_info(self, device: str) -> dict:
        return self._info


class _FakeProbe:
    def __init__(self, by_filename: dict[str, SourceMediaInfo]):
        self._by_filename = by_filename

    async def probe(self, path: str) -> SourceMediaInfo:
        return self._by_filename.get(Path(path).name, SourceMediaInfo())


def _dvd_layout(codec="mpeg2video", audio_langs=("de",), sub_langs=(), duration=0.0) -> SourceMediaInfo:
    info = SourceMediaInfo(duration=duration)
    info.video.append(ProbedVideo(index=0, codec=codec, width=720, height=576, fps=25.0))
    for i, lang in enumerate(audio_langs):
        info.audio.append(AudioStream(index=1 + i, codec="ac3", channels=2, sample_rate=48000,
                                       language=lang, default=(i == 0)))
    for i, lang in enumerate(sub_langs):
        info.subtitles.append(ProbedSubtitle(index=10 + i, codec="dvd_subtitle",
                                             language=lang, forced=False, default=(i == 0)))
    return info


# ─── Binär-Fixtures: VIDEO_TS.IFO (TT_SRPT) und *.mpls ──────────────────
# Duplizierte, absichtlich schlanke Kopien der Builder aus test_dvd_ifo.py /
# test_bluray_mpls.py - dort wird der Parser isoliert getestet, hier wird
# derselbe Byte-Aufbau verwendet, um DiscAnalyzer end-to-end zu prüfen.

def _build_video_ts_ifo(entries: list[tuple[int, int, int, int]], tt_srpt_sector: int = 1) -> bytes:
    header = bytearray(_SECTOR_SIZE)
    header[0:12] = b"DVDVIDEO-VMG"
    header[_TT_SRPT_POINTER_OFFSET:_TT_SRPT_POINTER_OFFSET + 4] = tt_srpt_sector.to_bytes(4, "big")
    table = bytearray()
    table += len(entries).to_bytes(2, "big")
    table += b"\x00\x00\x00\x00\x00\x00"
    for vts_number, vts_ttn, chapter_count, angle_count in entries:
        entry = bytearray(12)
        entry[1] = angle_count
        entry[2:4] = chapter_count.to_bytes(2, "big")
        entry[6] = vts_number
        entry[7] = vts_ttn
        table += entry
    return bytes(header) + b"\x00" * (tt_srpt_sector * _SECTOR_SIZE - len(header)) + bytes(table)


def _play_item(clip_id: str, in_time: int, out_time: int) -> bytes:
    body = bytearray()
    body += clip_id.encode("ascii").ljust(5, b"0")
    body += b"M2TS" + b"\x00\x00"
    body += in_time.to_bytes(4, "big")
    body += out_time.to_bytes(4, "big")
    return len(body).to_bytes(2, "big") + bytes(body)


def _mark(mark_type: int, ref_play_item_id: int, mark_timestamp: int) -> bytes:
    entry = bytearray()
    entry += b"\x00" + mark_type.to_bytes(1, "big") + ref_play_item_id.to_bytes(2, "big")
    entry += mark_timestamp.to_bytes(4, "big") + b"\x00\x00" + (0xFFFFFFFF).to_bytes(4, "big")
    return bytes(entry)


def _build_mpls(items: list[tuple[str, int, int]], marks: list[tuple[int, int, int]] = ()) -> bytes:
    playlist_start = 40
    playlist_body = bytearray()
    playlist_body += (0).to_bytes(4, "big") + b"\x00\x00"
    playlist_body += len(items).to_bytes(2, "big") + (0).to_bytes(2, "big")
    for clip_id, in_time, out_time in items:
        playlist_body += _play_item(clip_id, in_time, out_time)

    marks_start = playlist_start + len(playlist_body)
    marks_body = bytearray()
    marks_body += (0).to_bytes(4, "big") + len(marks).to_bytes(2, "big")
    for mark_type, ref_id, ts in marks:
        marks_body += _mark(mark_type, ref_id, ts)

    header = bytearray(playlist_start)
    header[0:4] = b"MPLS"
    header[4:8] = b"0200"
    header[8:12] = playlist_start.to_bytes(4, "big")
    header[12:16] = marks_start.to_bytes(4, "big")
    return bytes(header) + bytes(playlist_body) + bytes(marks_body)


# ─── Modell: leere Struktur, ein Titel, mehrere Titel ────────────────────

def test_empty_disc_content_has_no_titles_and_no_main_movie():
    disc = DiscContent()
    assert disc.titles == []
    assert disc.main_movie is None
    assert disc.disc_type == DiscType.DVD  # Default, unverändert bis Analyse etwas anderes liefert


def test_disc_content_with_single_title():
    title = DiscTitle(index=0, name=None, duration_seconds=5400.0, size_bytes=4_000_000_000)
    disc = DiscContent(disc_type=DiscType.DVD, label="MEIN_FILM", device="D:", titles=[title])
    assert len(disc.titles) == 1
    assert disc.titles[0].index == 0
    assert disc.main_movie is None  # is_main_movie wurde nicht gesetzt


def test_disc_content_with_multiple_titles_preserves_order():
    titles = [DiscTitle(index=i, duration_seconds=100.0 * (i + 1)) for i in range(4)]
    disc = DiscContent(titles=titles)
    assert [t.index for t in disc.titles] == [0, 1, 2, 3]


# ─── Kapitel ──────────────────────────────────────────────────────────

def test_chapters_are_stored_and_serialized_in_order():
    chapters = [
        DiscChapter(index=0, start_seconds=0.0, duration_seconds=600.0),
        DiscChapter(index=1, start_seconds=600.0, duration_seconds=450.0),
        DiscChapter(index=2, start_seconds=1050.0, duration_seconds=300.0),
    ]
    title = DiscTitle(index=0, duration_seconds=1350.0, chapters=chapters)
    data = title.to_dict()
    assert [c["index"] for c in data["chapters"]] == [0, 1, 2]
    assert data["chapters"][1]["start_seconds"] == 600.0


# ─── Audiospuren ──────────────────────────────────────────────────────

def test_multiple_audio_tracks_keep_distinct_fields():
    tracks = [
        DiscAudioTrack(index=1, codec="ac3", language="de", channels=6, bitrate=448000, default=True),
        DiscAudioTrack(index=2, codec="ac3", language="en", channels=2, bitrate=192000, default=False),
        DiscAudioTrack(index=3, codec="dts", language=None, channels=6, bitrate=None, default=False),
    ]
    title = DiscTitle(index=0, audio_tracks=tracks)
    data = title.to_dict()["audio_tracks"]
    assert len(data) == 3
    assert data[0]["default"] is True and data[0]["language"] == "de"
    assert data[2]["language"] is None and data[2]["bitrate"] is None


# ─── Untertitelspuren ──────────────────────────────────────────────────

def test_multiple_subtitle_tracks_keep_forced_and_default_flags():
    tracks = [
        DiscSubtitleTrack(index=10, language="de", format="dvd_subtitle", forced=False, default=True),
        DiscSubtitleTrack(index=11, language="de", format="dvd_subtitle", forced=True, default=False),
        DiscSubtitleTrack(index=12, language="en", format="dvd_subtitle", forced=False, default=False),
    ]
    title = DiscTitle(index=0, subtitle_tracks=tracks)
    data = title.to_dict()["subtitle_tracks"]
    assert len(data) == 3
    assert data[1]["forced"] is True
    assert data[0]["default"] is True


# ─── Main-Movie-Markierung ──────────────────────────────────────────────

def test_main_movie_flagging_picks_longest_title_with_confidence():
    titles = [
        DiscTitle(index=0, duration_seconds=300.0, size_bytes=300_000_000,
                  chapters=[DiscChapter(0, 0.0, 300.0)]),
        DiscTitle(index=1, duration_seconds=5700.0, size_bytes=6_500_000_000,
                  chapters=[DiscChapter(i, i * 600.0, 600.0) for i in range(9)]),
        DiscTitle(index=2, duration_seconds=180.0, size_bytes=150_000_000,
                  chapters=[DiscChapter(0, 0.0, 180.0)]),
    ]
    DiscAnalyzer._apply_main_movie(titles)
    flagged = [t for t in titles if t.is_main_movie]
    assert len(flagged) == 1
    assert flagged[0].index == 1
    assert isinstance(flagged[0].main_movie_confidence, int)
    disc = DiscContent(titles=titles)
    assert disc.main_movie is flagged[0]


def test_main_movie_flagging_handles_empty_title_list_without_error():
    titles: list[DiscTitle] = []
    DiscAnalyzer._apply_main_movie(titles)  # darf nicht werfen
    assert titles == []


# ─── Serialisierung für UI/Bridge ──────────────────────────────────────

def test_disc_content_to_dict_round_trips_through_json():
    title = DiscTitle(
        index=0, name=None, duration_seconds=5400.0, size_bytes=4_000_000_000,
        chapters=[DiscChapter(0, 0.0, 5400.0)],
        video=DiscVideoInfo(codec="mpeg2video", width=720, height=576, fps=25.0),
        audio_tracks=[DiscAudioTrack(index=1, codec="ac3", language="de", channels=6, default=True)],
        subtitle_tracks=[DiscSubtitleTrack(index=10, language="de", format="dvd_subtitle", default=True)],
        is_main_movie=True, main_movie_confidence=90,
    )
    disc = DiscContent(disc_type=DiscType.DVD, label="TESTDISC", device="D:",
                       capacity_bytes=4_700_000_000, titles=[title])
    encoded = json.dumps(disc.to_dict())
    decoded = json.loads(encoded)
    assert decoded["disc_type"] == "dvd"
    assert decoded["titles"][0]["is_main_movie"] is True
    assert decoded["titles"][0]["video"]["width"] == 720
    assert decoded["titles"][0]["audio_tracks"][0]["language"] == "de"


# ─── DiscAnalyzer: DVD - echte Titel aus TT_SRPT, nicht aus VOB-Dateien ──

@pytest.mark.asyncio
async def test_analyze_dvd_regression_5_multiple_vobs_form_one_logical_title(tmp_path):
    """Regressionstest 5: mehrere VOB-Dateien, die zu EINEM logischen Titel
    gehören, dürfen nicht als mehrere Titel gezählt werden - und ein
    einzelner VOB-Titelsatz ist nicht automatisch ein Titel, sondern wird
    erst durch einen Eintrag in TT_SRPT zu einem."""
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    (video_ts / "VIDEO_TS.IFO").write_bytes(_build_video_ts_ifo([(1, 1, 8, 1)]))
    (video_ts / "VTS_01_1.VOB").write_bytes(b"x" * 2000)
    (video_ts / "VTS_01_2.VOB").write_bytes(b"x" * 3000)

    probe = _FakeProbe({
        "VTS_01_1.VOB": _dvd_layout(audio_langs=("de", "en"), sub_langs=("de",), duration=90.0),
        "VTS_01_2.VOB": SourceMediaInfo(duration=5310.0),
    })
    disc_tools = _FakeDiscTools({"present": True, "label": "MEIN_FILM", "capacity_bytes": 4_700_000_000})
    analyzer = DiscAnalyzer(disc_tools, probe)

    content = await analyzer.analyze(str(tmp_path))

    assert content.disc_type == DiscType.DVD
    assert len(content.titles) == 1                       # EIN logischer Titel, nicht zwei VOBs
    title = content.titles[0]
    assert title.duration_seconds == 90.0 + 5310.0         # beide VOB-Teile zusammengerechnet
    assert title.size_bytes == 2000 + 3000
    assert title.video is not None and title.video.width == 720
    assert len(title.audio_tracks) == 2
    assert len(title.subtitle_tracks) == 1
    assert len(title.chapters) == 8                        # echte nr_of_ptts aus TT_SRPT
    assert all(c.start_seconds is None for c in title.chapters)  # Zeitposition NICHT erfunden
    assert title.is_main_movie is True


@pytest.mark.asyncio
async def test_analyze_dvd_multiple_titles_across_different_vts(tmp_path):
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    (video_ts / "VIDEO_TS.IFO").write_bytes(_build_video_ts_ifo([(1, 1, 2, 1), (2, 1, 12, 1)]))
    (video_ts / "VTS_01_1.VOB").write_bytes(b"x" * 500)
    (video_ts / "VTS_02_1.VOB").write_bytes(b"x" * 9000)

    probe = _FakeProbe({
        "VTS_01_1.VOB": SourceMediaInfo(duration=180.0),
        "VTS_02_1.VOB": _dvd_layout(duration=5400.0),
    })
    disc_tools = _FakeDiscTools({"present": True, "label": "MEIN_FILM", "capacity_bytes": 4_700_000_000})
    analyzer = DiscAnalyzer(disc_tools, probe)

    content = await analyzer.analyze(str(tmp_path))

    assert len(content.titles) == 2
    short_title, main_title = content.titles
    assert short_title.duration_seconds == 180.0 and len(short_title.chapters) == 2
    assert main_title.duration_seconds == 5400.0 and len(main_title.chapters) == 12
    assert main_title.is_main_movie is True
    assert short_title.is_main_movie is False


@pytest.mark.asyncio
async def test_analyze_dvd_titles_sharing_one_vts_have_unknown_duration_and_size(tmp_path):
    """Zwei TT_SRPT-Titel teilen sich denselben Titelsatz: ohne Zell-/PGC-
    Parsing ist nicht bekannt, welcher VOB-Abschnitt zu welchem Titel gehört.
    Das muss als unbekannt (None) und NICHT als geschätzter Wert erscheinen."""
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    (video_ts / "VIDEO_TS.IFO").write_bytes(_build_video_ts_ifo([(1, 1, 3, 1), (1, 2, 4, 1)]))
    (video_ts / "VTS_01_1.VOB").write_bytes(b"x" * 5000)

    disc_tools = _FakeDiscTools({"present": True, "label": "SAMMEL_DVD", "capacity_bytes": 4_700_000_000})
    analyzer = DiscAnalyzer(disc_tools, _FakeProbe({}))

    content = await analyzer.analyze(str(tmp_path))

    assert len(content.titles) == 2
    for title in content.titles:
        assert title.duration_seconds is None
        assert title.size_bytes is None
    assert len(content.titles[0].chapters) == 3
    assert len(content.titles[1].chapters) == 4


@pytest.mark.asyncio
async def test_analyze_dvd_without_video_ts_ifo_raises_instead_of_guessing(tmp_path):
    """Kein VIDEO_TS.IFO -> keine verlässliche Titelquelle. Es darf NICHT
    stillschweigend auf eine VOB-Dateigruppierung zurückgefallen werden."""
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    (video_ts / "VTS_01_1.VOB").write_bytes(b"x" * 500)   # keine VIDEO_TS.IFO!

    disc_tools = _FakeDiscTools({"present": True, "label": "KAPUTT", "capacity_bytes": 4_700_000_000})
    analyzer = DiscAnalyzer(disc_tools, _FakeProbe({}))

    with pytest.raises(DiscContentError, match="VIDEO_TS.IFO"):
        await analyzer.analyze(str(tmp_path))


# ─── DiscAnalyzer: Blu-ray - echte Titel aus Playlists, nicht aus M2TS ───

@pytest.mark.asyncio
async def test_analyze_bluray_regression_1_playlist_with_one_clip(tmp_path):
    bdmv = tmp_path / "BDMV"
    (bdmv / "PLAYLIST").mkdir(parents=True)
    (bdmv / "STREAM").mkdir(parents=True)
    (bdmv / "PLAYLIST" / "00800.mpls").write_bytes(_build_mpls([("00001", 0, 45000 * 3600)]))
    (bdmv / "STREAM" / "00001.m2ts").write_bytes(b"x" * 1_000_000)

    probe = _FakeProbe({"00001.m2ts": SourceMediaInfo(
        duration=3600.0, video=[ProbedVideo(index=0, codec="h264", width=1920, height=1080, fps=23.976)])})
    disc_tools = _FakeDiscTools({"present": True, "label": "BD_EINZELCLIP", "capacity_bytes": 25_025_314_816})
    analyzer = DiscAnalyzer(disc_tools, probe)

    content = await analyzer.analyze(str(tmp_path))

    assert content.disc_type == DiscType.BLURAY
    assert len(content.titles) == 1
    assert content.titles[0].duration_seconds == pytest.approx(3600.0)
    assert content.titles[0].video.width == 1920


@pytest.mark.asyncio
async def test_analyze_bluray_regression_2_playlist_with_multiple_clips(tmp_path):
    """Regressionstest 2: ein Titel besteht aus mehreren M2TS-Clips - das
    muss EIN Titel mit summierter Laufzeit/Größe sein, nicht mehrere."""
    bdmv = tmp_path / "BDMV"
    (bdmv / "PLAYLIST").mkdir(parents=True)
    (bdmv / "STREAM").mkdir(parents=True)
    (bdmv / "PLAYLIST" / "00800.mpls").write_bytes(_build_mpls([
        ("00001", 0, 45000 * 1800), ("00002", 0, 45000 * 1800),
    ]))
    (bdmv / "STREAM" / "00001.m2ts").write_bytes(b"x" * 4000)
    (bdmv / "STREAM" / "00002.m2ts").write_bytes(b"x" * 6000)

    probe = _FakeProbe({"00001.m2ts": SourceMediaInfo(
        duration=1800.0, video=[ProbedVideo(index=0, codec="h264", width=1920, height=1080, fps=23.976)])})
    disc_tools = _FakeDiscTools({"present": True, "label": "BD_MEHRTEILIG", "capacity_bytes": 25_025_314_816})
    analyzer = DiscAnalyzer(disc_tools, probe)

    content = await analyzer.analyze(str(tmp_path))

    assert len(content.titles) == 1
    title = content.titles[0]
    assert title.duration_seconds == pytest.approx(3600.0)
    assert title.size_bytes == 4000 + 6000


@pytest.mark.asyncio
async def test_analyze_bluray_regression_3_multiple_playlists(tmp_path):
    """Regressionstest 3: mehrere Playlists = mehrere Titel."""
    bdmv = tmp_path / "BDMV"
    (bdmv / "PLAYLIST").mkdir(parents=True)
    (bdmv / "STREAM").mkdir(parents=True)
    (bdmv / "PLAYLIST" / "00000.mpls").write_bytes(_build_mpls([("00001", 0, 45000 * 60)]))       # Menü/Trailer
    (bdmv / "PLAYLIST" / "00800.mpls").write_bytes(_build_mpls([("00002", 0, 45000 * 6300)]))      # Hauptfilm
    (bdmv / "STREAM" / "00001.m2ts").write_bytes(b"x" * 1000)
    (bdmv / "STREAM" / "00002.m2ts").write_bytes(b"x" * 9_000_000)

    probe = _FakeProbe({
        "00001.m2ts": SourceMediaInfo(duration=60.0),
        "00002.m2ts": SourceMediaInfo(duration=6300.0, video=[ProbedVideo(index=0, codec="h264", width=1920, height=1080, fps=23.976)]),
    })
    disc_tools = _FakeDiscTools({"present": True, "label": "BD_FILM", "capacity_bytes": 25_025_314_816})
    analyzer = DiscAnalyzer(disc_tools, probe)

    content = await analyzer.analyze(str(tmp_path))

    assert len(content.titles) == 2
    main = next(t for t in content.titles if t.is_main_movie)
    assert main.duration_seconds == pytest.approx(6300.0)
    assert main.video.width == 1920


@pytest.mark.asyncio
async def test_analyze_bluray_regression_4_same_clip_referenced_by_multiple_playlists(tmp_path):
    """Regressionstest 4: derselbe Clip wird von zwei Playlists referenziert
    (z. B. Hauptfilm-Playlist und eine kurze Vorschau-Playlist auf denselben
    Clip). Beide sind eigenständige, gültige Titel - der Clip darf nicht
    dazu führen, dass nur einer davon gezählt wird."""
    bdmv = tmp_path / "BDMV"
    (bdmv / "PLAYLIST").mkdir(parents=True)
    (bdmv / "STREAM").mkdir(parents=True)
    (bdmv / "PLAYLIST" / "00000.mpls").write_bytes(_build_mpls([("00001", 0, 45000 * 90)]))         # Vorschau: erste 90s
    (bdmv / "PLAYLIST" / "00800.mpls").write_bytes(_build_mpls([("00001", 0, 45000 * 6000)]))        # Hauptfilm: ganzer Clip
    (bdmv / "STREAM" / "00001.m2ts").write_bytes(b"x" * 8_000_000)

    probe = _FakeProbe({"00001.m2ts": SourceMediaInfo(
        duration=6000.0, video=[ProbedVideo(index=0, codec="h264", width=1920, height=1080, fps=23.976)])})
    disc_tools = _FakeDiscTools({"present": True, "label": "BD_GETEILTER_CLIP", "capacity_bytes": 25_025_314_816})
    analyzer = DiscAnalyzer(disc_tools, probe)

    content = await analyzer.analyze(str(tmp_path))

    assert len(content.titles) == 2
    durations = sorted(t.duration_seconds for t in content.titles)
    assert durations == pytest.approx([90.0, 6000.0])
    # Beide Titel referenzieren real denselben Clip - beide bekommen dasselbe Stream-Layout.
    assert all(t.size_bytes == 8_000_000 for t in content.titles)
    assert next(t for t in content.titles if t.duration_seconds == pytest.approx(6000.0)).is_main_movie is True


@pytest.mark.asyncio
async def test_analyze_bluray_regression_6_no_marks_means_no_fabricated_chapters(tmp_path):
    """Regressionstest 6: eine Playlist ohne PlayListMark-Einträge bekommt
    eine LEERE Kapitelliste, kein erfundenes Platzhalter-Kapitel."""
    bdmv = tmp_path / "BDMV"
    (bdmv / "PLAYLIST").mkdir(parents=True)
    (bdmv / "STREAM").mkdir(parents=True)
    (bdmv / "PLAYLIST" / "00800.mpls").write_bytes(_build_mpls([("00001", 0, 45000 * 6000)], marks=[]))
    (bdmv / "STREAM" / "00001.m2ts").write_bytes(b"x" * 100)

    disc_tools = _FakeDiscTools({"present": True, "label": "BD_OHNE_KAPITEL", "capacity_bytes": 25_025_314_816})
    analyzer = DiscAnalyzer(disc_tools, _FakeProbe({}))

    content = await analyzer.analyze(str(tmp_path))

    assert content.titles[0].chapters == []


@pytest.mark.asyncio
async def test_analyze_bluray_playlist_marks_become_real_chapters(tmp_path):
    bdmv = tmp_path / "BDMV"
    (bdmv / "PLAYLIST").mkdir(parents=True)
    (bdmv / "STREAM").mkdir(parents=True)
    (bdmv / "PLAYLIST" / "00800.mpls").write_bytes(_build_mpls(
        [("00001", 0, 45000 * 6000)],
        marks=[(_ENTRY_MARK, 0, 0), (_ENTRY_MARK, 0, 45000 * 2400)],
    ))
    (bdmv / "STREAM" / "00001.m2ts").write_bytes(b"x" * 100)

    disc_tools = _FakeDiscTools({"present": True, "label": "BD_MIT_KAPITELN", "capacity_bytes": 25_025_314_816})
    analyzer = DiscAnalyzer(disc_tools, _FakeProbe({}))

    content = await analyzer.analyze(str(tmp_path))

    chapters = content.titles[0].chapters
    assert len(chapters) == 2
    assert chapters[0].start_seconds == pytest.approx(0.0)
    assert chapters[0].duration_seconds == pytest.approx(2400.0)
    assert chapters[1].start_seconds == pytest.approx(2400.0)
    assert chapters[1].duration_seconds == pytest.approx(6000.0 - 2400.0)


@pytest.mark.asyncio
async def test_analyze_bluray_without_playlist_folder_returns_no_titles(tmp_path):
    bdmv = tmp_path / "BDMV"
    (bdmv / "STREAM").mkdir(parents=True)          # kein PLAYLIST-Ordner
    (bdmv / "STREAM" / "00001.m2ts").write_bytes(b"x" * 100)

    disc_tools = _FakeDiscTools({"present": True, "label": "BD_KAPUTT", "capacity_bytes": 25_025_314_816})
    analyzer = DiscAnalyzer(disc_tools, _FakeProbe({}))

    content = await analyzer.analyze(str(tmp_path))

    assert content.disc_type == DiscType.BLURAY
    assert content.titles == []


# ─── Fehlerfall: nicht analysierbare Disc ────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_raises_disc_content_error_when_no_medium_present(tmp_path):
    disc_tools = _FakeDiscTools({"present": False, "error": "kein Medium erkannt"})
    analyzer = DiscAnalyzer(disc_tools, _FakeProbe({}))

    with pytest.raises(DiscContentError, match="D:"):
        await analyzer.analyze("D:")


@pytest.mark.asyncio
async def test_analyze_returns_empty_titles_for_data_or_audio_disc(tmp_path):
    # Lesbares Medium ohne VIDEO_TS/BDMV (z. B. Audio-CD oder Datenträger).
    disc_tools = _FakeDiscTools({"present": True, "label": "DATA", "capacity_bytes": 700_000_000})
    analyzer = DiscAnalyzer(disc_tools, _FakeProbe({}))

    content = await analyzer.analyze(str(tmp_path))

    assert content.disc_type == DiscType.CD
    assert content.titles == []
    assert content.main_movie is None


# ─── Bridge ──────────────────────────────────────────────────────────────

@pytest.fixture
def bare_bridge(tmp_path, monkeypatch):
    """Produktiver RetroDiscBridge mit isolierten Settings und echtem
    Hintergrund-Thread (analog zur ``queued_bridge``-Fixture in
    test_job_submission.py).

    ``get_disc_content`` dispatcht über ``self._async(...).result(timeout=...)``
    auf ``self._loop`` - ohne einen wirklich laufenden Hintergrund-Thread würde
    jeder Aufruf deterministisch in einen Timeout laufen (dieselbe Klasse von
    Fehler wie in STABILITY_QUEUE_INIT.md dokumentiert). Die No-Op-Thread-
    Attrappe aus ``disc_bridge`` (test_disc_flows.py) ist hier deshalb bewusst
    NICHT verwendet.
    """
    import retrodisc_launcher as launcher
    from src.config.settings import AppSettings

    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output",
        "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }).save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    bridge = launcher.RetroDiscBridge()
    try:
        yield bridge
    finally:
        bridge._loop.call_soon_threadsafe(bridge._loop.stop)
        bridge._thread.join(timeout=5)
        bridge._loop.close()


def test_bridge_get_disc_content_requires_a_device(bare_bridge):
    result = json.loads(bare_bridge.get_disc_content(""))
    assert "error" in result


def test_bridge_get_disc_content_returns_serialized_model_on_success(bare_bridge, monkeypatch):
    canned = DiscContent(
        disc_type=DiscType.DVD, label="TESTDISC", device="D:",
        titles=[DiscTitle(index=0, duration_seconds=5400.0, is_main_movie=True, main_movie_confidence=90)],
    )

    async def fake_analyze(device):
        return canned

    monkeypatch.setattr(bare_bridge.disc_analyzer, "analyze", fake_analyze)

    result = json.loads(bare_bridge.get_disc_content("D:"))

    assert "error" not in result
    assert result["label"] == "TESTDISC"
    assert result["titles"][0]["is_main_movie"] is True


def test_bridge_get_disc_content_returns_error_json_when_not_analyzable(bare_bridge, monkeypatch):
    async def fake_analyze(device):
        raise DiscContentError(f"Kein lesbares Medium in Laufwerk {device}.")

    monkeypatch.setattr(bare_bridge.disc_analyzer, "analyze", fake_analyze)

    result = json.loads(bare_bridge.get_disc_content("D:"))

    assert "error" in result
    assert "D:" in result["error"]
    assert result["device"] == "D:"
