"""MediaProbeService: robust ffprobe JSON parsing."""
import json
import pytest
from src.services.transcode.process import ProcResult
from src.services.transcode.probe import MediaProbeService, parse_probe_json

FULL = {
    "format": {"format_name": "mov,mp4,m4a", "duration": "120.5", "size": "10485760"},
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160,
         "avg_frame_rate": "24000/1001", "pix_fmt": "yuv420p10le", "color_transfer": "smpte2084",
         "field_order": "tt", "tags": {"language": "eng"}, "disposition": {"default": 1}},
        {"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6,
         "sample_rate": "48000", "tags": {"language": "ger"}},
        {"index": 2, "codec_type": "subtitle", "codec_name": "subrip",
         "tags": {"language": "eng"}, "disposition": {"forced": 1}},
        {"index": 3, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
    ],
}


def runner_for(payload):
    async def run(args, timeout=None):
        return ProcResult(0, json.dumps(payload) if isinstance(payload, dict) else payload, "")
    return run


@pytest.mark.asyncio
async def test_full_parse():
    svc = MediaProbeService(runner=runner_for(FULL))
    info = await svc.probe("movie.mkv")
    assert info.duration == 120.5 and info.size == 10485760
    assert len(info.video) == 1                       # attached_pic übersprungen
    v = info.primary_video
    assert v.codec == "hevc" and v.width == 3840 and abs(v.fps - 23.976) < 0.01
    assert v.bit_depth == 10 and v.hdr and v.interlaced and v.language == "eng" and v.default
    assert info.audio[0].channels == 6 and info.audio[0].language == "ger"
    assert info.subtitles[0].forced and info.subtitles[0].codec == "subrip"


@pytest.mark.asyncio
async def test_to_hints():
    info = await MediaProbeService(runner=runner_for(FULL)).probe("m.mkv")
    hints = info.to_hints()
    assert hints.hdr and hints.bit_depth == 10 and hints.width == 3840 and hints.source_codec == "hevc"


@pytest.mark.asyncio
async def test_missing_fields_do_not_crash():
    payload = {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}, {}]}
    info = await MediaProbeService(runner=runner_for(payload)).probe("x")
    assert info.primary_video.width == 0 and info.primary_video.bit_depth == 8
    assert info.duration == 0.0 and not info.primary_video.hdr


@pytest.mark.asyncio
async def test_corrupt_json_returns_empty_info():
    info = await MediaProbeService(runner=runner_for("{not json")).probe("x")
    assert info.video == [] and info.audio == [] and info.duration == 0.0   # kein Absturz


@pytest.mark.asyncio
async def test_audio_only_and_video_only():
    audio_only = {"streams": [{"codec_type": "audio", "codec_name": "flac", "channels": 2}]}
    a = await MediaProbeService(runner=runner_for(audio_only)).probe("a.flac")
    assert not a.video and a.audio and a.primary_video is None
    video_only = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 640}]}
    v = await MediaProbeService(runner=runner_for(video_only)).probe("v.mp4")
    assert v.video and not v.audio


def test_parse_bit_depth_variants():
    assert parse_probe_json("x", {"streams": [{"codec_type": "video",
        "pix_fmt": "yuv420p", "bits_per_raw_sample": "8"}]}).primary_video.bit_depth == 8
    assert parse_probe_json("x", {"streams": [{"codec_type": "video",
        "pix_fmt": "p010le"}]}).primary_video.bit_depth == 10
