"""Behavioral checks for isolated downloads and coherent, exclusive publication."""

from __future__ import annotations

import asyncio
import builtins
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.core.downloader import DownloadError, Downloader


def _stage(work: Path, files: dict[str, bytes]) -> None:
    for name, content in files.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


@pytest.mark.asyncio
@pytest.mark.parametrize("template", [
    "../escaped.%(ext)s",
    "nested/../../escaped.%(ext)s",
    r"..\escaped.%(ext)s",
    r"C:\escaped.%(ext)s",
    r"C:escaped.%(ext)s",
    r"\escaped.%(ext)s",
    r"\\server\share\escaped.%(ext)s",
    "/escaped.%(ext)s",
])
async def test_download_rejects_escaping_template_before_launch(tmp_path, monkeypatch, template):
    output = tmp_path / "out"
    downloader = Downloader(output_dir=output)
    launch = AsyncMock()
    monkeypatch.setattr("src.core.downloader.create_hidden_subprocess", launch)

    with pytest.raises(DownloadError, match="Template"):
        await downloader.download("https://example.invalid/video", output_template=template)

    launch.assert_not_called()
    assert list(output.iterdir()) == []


def test_relative_nested_template_stays_in_private_work_area(tmp_path):
    downloader = Downloader(output_dir=tmp_path / "out")
    work = tmp_path / "work"
    command = downloader._build_download_command(
        url="https://example.invalid/video", format="best",
        output_template="Series/%(title)s.%(ext)s", extract_audio=False,
        audio_format="mp3", audio_quality="320k", subtitles=True,
        subtitle_langs="de,en", dest_dir=work,
    )
    assert Path(command[command.index("-o") + 1]) == work / "Series/%(title)s.%(ext)s"


@pytest.mark.parametrize("collision", ["Clip.mp4", "Clip.de.srt", "Clip.info.json"])
def test_collision_renames_the_whole_media_and_sidecar_group(tmp_path, collision):
    output = tmp_path / "out"
    downloader = Downloader(output_dir=output)
    work = tmp_path / "work"
    files = {"Clip.mp4": b"new-media", "Clip.de.srt": b"german",
             "Clip.en.vtt": b"english", "Clip.info.json": b"{}"}
    _stage(work, files)
    existing = output / collision
    existing.write_bytes(b"previous-file")

    result = downloader._publish_downloads(work, work / "Clip.mp4")

    assert result == output / "Clip (1).mp4"
    assert existing.read_bytes() == b"previous-file"
    assert {p.name for p in output.iterdir()} == {
        collision, "Clip (1).mp4", "Clip (1).de.srt", "Clip (1).en.vtt", "Clip (1).info.json"
    }
    for name, content in files.items():
        assert (output / name.replace("Clip", "Clip (1)", 1)).read_bytes() == content


def test_playlist_sidecars_follow_their_own_longest_matching_media_stem(tmp_path):
    output = tmp_path / "out"
    downloader = Downloader(output_dir=output)
    work = tmp_path / "work"
    _stage(work, {"series/Clip.mp4": b"one", "series/Clip.en.srt": b"one-sub",
                  "series/Clip.Part2.mp4": b"two", "series/Clip.Part2.en.srt": b"two-sub"})
    _stage(output, {"series/Clip.Part2.mp4": b"old"})

    result = downloader._publish_downloads(work, work / "series/Clip.Part2.mp4")

    assert result == output / "series/Clip.Part2 (1).mp4"
    assert (output / "series/Clip.Part2 (1).en.srt").read_bytes() == b"two-sub"
    assert (output / "series/Clip.en.srt").read_bytes() == b"one-sub"
    assert (output / "series/Clip.Part2.mp4").read_bytes() == b"old"


@pytest.mark.parametrize("extension", ["srt", "vtt", "ttml", "srv3", "json", "jpg"])
@pytest.mark.parametrize("reported", [False, True])
def test_sidecar_only_results_are_never_published_as_media(tmp_path, extension, reported):
    output = tmp_path / "out"
    downloader = Downloader(output_dir=output)
    work = tmp_path / "work"
    source = work / f"Clip.de.{extension}"
    _stage(work, {source.name: b"only-a-sidecar"})

    assert downloader._publish_downloads(work, source if reported else None) is None
    assert list(output.iterdir()) == []
    assert source.is_file()


@pytest.mark.asyncio
async def test_download_with_only_subtitles_fails_and_removes_private_work(tmp_path, monkeypatch):
    output = tmp_path / "out"
    downloader = Downloader(output_dir=output)

    async def launch(*command, **_kwargs):
        work = Path(command[command.index("-o") + 1]).parent
        (work / "Clip.de.srt").write_bytes(b"subtitles-only")
        stream = asyncio.StreamReader()
        stream.feed_eof()
        process = AsyncMock()
        process.stdout = stream
        process.returncode = 0
        return process

    monkeypatch.setattr("src.core.downloader.create_hidden_subprocess", launch)
    with pytest.raises(DownloadError, match="nicht gefunden"):
        await downloader.download("https://example.invalid/video")
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("failure_at", [1, 2, 4])
def test_move_failure_rolls_back_all_files_owned_by_this_call(tmp_path, monkeypatch, failure_at):
    output = tmp_path / "out"
    downloader = Downloader(output_dir=output)
    work = tmp_path / "work"
    files = {"A.mp4": b"a", "A.de.srt": b"a-sub", "B.mp4": b"b", "B.de.srt": b"b-sub"}
    _stage(work, files)
    previous = {"A.mp4": b"previous-media", "B.de.srt": b"previous-sub",
                "parallel.mp4": b"independent-publication"}
    _stage(output, previous)
    real_replace = os.replace
    count = 0

    def failing_replace(source, target):
        nonlocal count
        count += 1
        if count == failure_at:
            raise OSError("simulated publication failure")
        real_replace(source, target)

    monkeypatch.setattr("src.core.downloader.os.replace", failing_replace)
    with pytest.raises(OSError, match="simulated publication"):
        downloader._publish_downloads(work, work / "B.mp4")

    assert {p.name: p.read_bytes() for p in output.iterdir()} == previous


def test_reservation_failure_releases_current_and_previous_groups(tmp_path, monkeypatch):
    output = tmp_path / "out"
    downloader = Downloader(output_dir=output)
    work = tmp_path / "work"
    _stage(work, {"A.mp4": b"a", "A.de.srt": b"a-sub", "B.mp4": b"b", "B.de.srt": b"b-sub"})
    real_open = builtins.open

    def failing_open(path, mode):
        if Path(path).name == "B.de.srt":
            raise OSError("simulated reservation failure")
        return real_open(path, mode)

    # Die Reservierung selbst wohnt seit RD-03 in src/core/output.py; der
    # Downloader leitet nur noch dorthin weiter. Geprueft wird unveraendert,
    # dass ein Fehlschlag die eigene *und* die zuvor belegte Gruppe freigibt.
    monkeypatch.setattr("src.core.output.open", failing_open, raising=False)
    with pytest.raises(OSError, match="simulated reservation"):
        downloader._publish_downloads(work, work / "B.mp4")

    assert list(output.iterdir()) == []
    assert len(list(work.iterdir())) == 4


def test_simultaneous_independent_publishers_keep_media_and_subtitles_paired(tmp_path):
    output = tmp_path / "out"
    count = 8
    ready = threading.Barrier(count)

    def publish(index):
        downloader = Downloader(output_dir=output)
        work = tmp_path / f"work-{index}"
        payload = str(index).encode()
        _stage(work, {"Clip.mp4": payload, "Clip.de.srt": payload + b"-de",
                      "Clip.en.srt": payload + b"-en"})
        ready.wait(timeout=10)
        result = downloader._publish_downloads(work, work / "Clip.mp4")
        return result, payload

    with ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(publish, range(count)))

    assert len({result for result, _ in results}) == count
    assert len(list(output.iterdir())) == count * 3
    for result, payload in results:
        assert result.read_bytes() == payload
        assert result.with_name(result.stem + ".de.srt").read_bytes() == payload + b"-de"
        assert result.with_name(result.stem + ".en.srt").read_bytes() == payload + b"-en"
