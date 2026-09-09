"""Post-transcode verification."""
import json
import pytest
from src.services.transcode.process import ProcResult
from src.services.transcode.probe import MediaProbeService
from src.services.transcode.verify import verify_transcode
from src.services.verify import PASS, FAIL, PASS_WITH_WARNINGS


def probe_returning(payload):
    async def run(args, timeout=None):
        return ProcResult(0, json.dumps(payload), "")
    return MediaProbeService(runner=run)


def _ok_payload(duration=100.0, codec="hevc"):
    return {"format": {"duration": str(duration)},
            "streams": [{"codec_type": "video", "codec_name": codec, "width": 1920, "height": 1080}]}


@pytest.mark.asyncio
async def test_missing_output_fails(tmp_path):
    r = await verify_transcode(tmp_path / "nope.mkv", probe_returning(_ok_payload()))
    assert r.status == FAIL and r.checks[0].name == "exists"


@pytest.mark.asyncio
async def test_too_small_output_fails(tmp_path):
    out = tmp_path / "o.mkv"; out.write_bytes(b"0" * 10)
    r = await verify_transcode(out, probe_returning(_ok_payload()), min_bytes=4096)
    assert r.status == FAIL and any(c.name == "size" and not c.ok for c in r.checks)


@pytest.mark.asyncio
async def test_good_output_passes(tmp_path):
    out = tmp_path / "o.mkv"; out.write_bytes(b"0" * 100000)
    r = await verify_transcode(out, probe_returning(_ok_payload(duration=100.0, codec="hevc")),
                               expected_duration=100.0, expected_codec="h265")
    assert r.status == PASS


@pytest.mark.asyncio
async def test_wrong_codec_fails(tmp_path):
    out = tmp_path / "o.mkv"; out.write_bytes(b"0" * 100000)
    r = await verify_transcode(out, probe_returning(_ok_payload(codec="h264")),
                               expected_codec="h265")
    assert r.status == FAIL and any(c.name == "codec" and not c.ok for c in r.checks)


@pytest.mark.asyncio
async def test_duration_mismatch_is_warning(tmp_path):
    out = tmp_path / "o.mkv"; out.write_bytes(b"0" * 100000)
    r = await verify_transcode(out, probe_returning(_ok_payload(duration=50.0, codec="hevc")),
                               expected_duration=100.0, expected_codec="h265")
    assert r.status == PASS_WITH_WARNINGS       # nur Warnung, Datei ist valide


@pytest.mark.asyncio
async def test_no_video_stream_fails(tmp_path):
    out = tmp_path / "o.mkv"; out.write_bytes(b"0" * 100000)
    payload = {"format": {"duration": "10"}, "streams": [{"codec_type": "audio", "codec_name": "aac"}]}
    r = await verify_transcode(out, probe_returning(payload))
    assert r.status == FAIL and any(c.name == "video_stream" and not c.ok for c in r.checks)


@pytest.mark.asyncio
async def test_codec_family_normalisation(tmp_path):
    out = tmp_path / "o.mp4"; out.write_bytes(b"0" * 100000)
    # ffprobe meldet 'hevc', erwartet wurde der Encodername 'hevc_nvenc' -> gleiche Familie
    r = await verify_transcode(out, probe_returning(_ok_payload(codec="hevc")),
                               expected_codec="hevc_nvenc")
    assert r.status == PASS
