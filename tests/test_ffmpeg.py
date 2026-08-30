"""Tests für den FFmpeg-Wrapper."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.ffmpeg import FFmpeg, FFmpegError, FFmpegNotFoundError
from src.models.media import MediaFile, MediaType


@pytest.fixture
def ffmpeg():
    return FFmpeg(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")


@pytest.fixture
def sample_probe_output():
    return {
        "format": {
            "format_name": "matroska,webm",
            "duration": "7200.000000",
            "size": "1500000000",
            "tags": {"title": "Test Video"},
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "24000/1001",
                "bit_rate": "5000000",
                "disposition": {"attached_pic": 0},
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "sample_rate": "48000",
                "bit_rate": "192000",
                "tags": {"language": "ger"},
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "eng"},
            },
        ],
    }


class TestFFmpegProbe:
    def test_parse_probe_data(self, ffmpeg, sample_probe_output):
        path = Path("/test/video.mkv")
        result = ffmpeg._parse_probe_data(path, sample_probe_output)

        assert isinstance(result, MediaFile)
        assert result.media_type == MediaType.VIDEO
        assert result.container == "matroska,webm"
        assert result.duration_seconds == 7200.0
        assert result.file_size_bytes == 1500000000
        assert result.title == "Test Video"

        # Video
        assert len(result.video_streams) == 1
        assert result.video_streams[0].codec == "h264"
        assert result.video_streams[0].width == 1920
        assert result.video_streams[0].height == 1080

        # Audio
        assert len(result.audio_streams) == 1
        assert result.audio_streams[0].codec == "aac"
        assert result.audio_streams[0].language == "ger"

        # Subtitles
        assert len(result.subtitle_streams) == 1
        assert result.subtitle_streams[0].language == "eng"

    def test_parse_fps(self, ffmpeg):
        assert ffmpeg._parse_fps("30000/1001") == pytest.approx(29.97, rel=0.01)
        assert ffmpeg._parse_fps("25/1") == 25.0
        assert ffmpeg._parse_fps("30") == 30.0
        assert ffmpeg._parse_fps("0/0") == 0.0
        assert ffmpeg._parse_fps("invalid") == 0.0


class TestMediaFile:
    def test_properties(self, ffmpeg, sample_probe_output):
        media = ffmpeg._parse_probe_data(Path("/test.mkv"), sample_probe_output)

        assert media.has_video is True
        assert media.has_audio is True
        assert media.resolution == "1920x1080"
        assert media.duration_formatted == "02:00:00"
        assert "GB" in media.file_size_formatted

    def test_duration_formatting(self):
        media = MediaFile(path=Path("/test.mp3"), duration_seconds=125)
        assert media.duration_formatted == "02:05"

        media.duration_seconds = 3723
        assert media.duration_formatted == "01:02:03"

    def test_file_size_formatting(self):
        media = MediaFile(path=Path("/test.mp4"), file_size_bytes=1024)
        assert media.file_size_formatted == "1.0 KB"

        media.file_size_bytes = 1_500_000_000
        assert "GB" in media.file_size_formatted


class TestPresets:
    def test_get_preset(self):
        from src.config.presets import get_preset, ALL_PRESETS

        preset = get_preset("mp4_h264_1080p")
        assert preset.container == "mp4"
        assert preset.video_codec == "libx264"

    def test_unknown_preset(self):
        from src.config.presets import get_preset

        with pytest.raises(ValueError, match="nicht gefunden"):
            get_preset("nonexistent_preset")

    def test_all_presets_have_names(self):
        from src.config.presets import ALL_PRESETS

        for p in ALL_PRESETS:
            assert p.name
            assert p.display_name
            assert p.category in ("video", "audio", "device", "disc")
