"""MediaAnalysisOrchestrator: coordinates detection/probe/metadata/library."""
import json
import pytest
from src.services.transcode.process import ProcResult
from src.services.transcode.probe import MediaProbeService
from src.services.pipeline.analysis import MediaAnalysisOrchestrator
from src.services.metadata import Metadata
from src.services.library_catalog import LibraryService, LibraryItem

VIDEO_JSON = {"format": {"duration": "5400.0"},
              "streams": [{"codec_type": "video", "codec_name": "h264",
                           "width": 720, "height": 480, "avg_frame_rate": "25/1"}]}


def probe_runner(payload=VIDEO_JSON, fail=False):
    async def run(args, timeout=None):
        if fail:
            raise RuntimeError("ffprobe kaputt")
        return ProcResult(0, json.dumps(payload), "")
    return MediaProbeService(runner=run)


class FakeMeta:
    def __init__(self, result):
        self._r = result
        self.calls = []
    async def lookup(self, query, *, allow_network=False, force_refresh=False):
        self.calls.append((query, allow_network))
        return self._r


@pytest.mark.asyncio
async def test_file_analysis(tmp_path):
    f = tmp_path / "movie.mp4"; f.write_bytes(b"0" * 8000)
    orch = MediaAnalysisOrchestrator(probe=probe_runner())
    r = await orch.analyze(str(f))
    assert r.disc_kind == "file" and r.media_info.duration == 5400.0
    assert r.fingerprint and r.main_movie and r.main_movie["confidence"] >= 80
    assert "transcode" in r.recommended_actions and not r.errors


@pytest.mark.asyncio
async def test_dvd_folder_analysis(tmp_path):
    (tmp_path / "VIDEO_TS").mkdir()
    (tmp_path / "VIDEO_TS" / "VIDEO_TS.IFO").write_bytes(b"x")
    (tmp_path / "VIDEO_TS" / "VTS_01_1.VOB").write_bytes(b"0" * 20000)
    orch = MediaAnalysisOrchestrator(probe=probe_runner())
    r = await orch.analyze(str(tmp_path))
    assert r.disc_kind == "dvd" and r.media_info is not None
    assert r.main_movie is not None and "archive_or_transcode" in r.recommended_actions


@pytest.mark.asyncio
async def test_metadata_hit_and_offline_flag(tmp_path):
    f = tmp_path / "movie.mp4"; f.write_bytes(b"0" * 8000)
    meta = FakeMeta(Metadata(title="Alien", year=1979))
    orch = MediaAnalysisOrchestrator(probe=probe_runner(), metadata=meta)
    r = await orch.analyze(str(f), allow_network=False)
    assert r.metadata["title"] == "Alien" and meta.calls[0][1] is False   # offline durchgereicht


@pytest.mark.asyncio
async def test_library_hit_marks_existing(tmp_path):
    f = tmp_path / "movie.mp4"; f.write_bytes(b"0" * 8000)
    lib = LibraryService(tmp_path / "cat.db", now=lambda: 1.0)
    orch = MediaAnalysisOrchestrator(probe=probe_runner(), library=lib)
    first = await orch.analyze(str(f))
    lib.add_or_update(LibraryItem(fingerprint=first.fingerprint, title="Bekannt"))
    second = await orch.analyze(str(f))
    assert second.library_entry and second.library_entry["title"] == "Bekannt"
    assert "already_in_library" in second.recommended_actions
    lib.close()


@pytest.mark.asyncio
async def test_missing_source_reports_error():
    orch = MediaAnalysisOrchestrator(probe=probe_runner())
    r = await orch.analyze("/nope/missing.mp4")
    assert r.errors and r.media_info is None


@pytest.mark.asyncio
async def test_iso_is_inspect_only(tmp_path):
    iso = tmp_path / "d.iso"; iso.write_bytes(b"0" * 4096)
    r = await MediaAnalysisOrchestrator(probe=probe_runner()).analyze(str(iso))
    assert r.disc_kind == "image" and "iso_inspect_only" in r.recommended_actions
    assert any("Mounting" in w for w in r.warnings)


@pytest.mark.asyncio
async def test_probe_failure_is_not_fatal(tmp_path):
    f = tmp_path / "movie.mp4"; f.write_bytes(b"0" * 8000)
    r = await MediaAnalysisOrchestrator(probe=probe_runner(fail=True)).analyze(str(f))
    assert r.fingerprint and any("Probe" in w for w in r.warnings) and not r.errors
