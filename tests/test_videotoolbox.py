"""VideoToolbox selection, quality mapping and lossless CPU fallback of options."""
import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config.presets import get_preset
from src.core.ffmpeg import FFmpeg, FFmpegError
from src.models.media import Job, JobType
from src.services.converter import Converter
from retrodisc_launcher import RetroDiscBridge


@pytest.mark.asyncio
@pytest.mark.parametrize('preset,encoder', [('mp4_h264_720p', 'h264_videotoolbox'), ('mp4_h265_4k', 'hevc_videotoolbox'), ('iphone', 'h264_videotoolbox')])
@pytest.mark.parametrize('mode', [None, 'auto', 'videotoolbox'])
async def test_hardware_reuses_preset_bitrate_without_cpu_flags(tmp_path, monkeypatch, preset, encoder, mode):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    source = tmp_path / 'source.mp4'
    source.touch()
    ffmpeg = SimpleNamespace(available_video_encoders=AsyncMock(return_value={encoder}), convert=AsyncMock())
    job = Job(job_type=JobType.CONVERT)
    p = get_preset(preset)
    original = list(p.extra_args)
    await Converter(ffmpeg).convert_file(source, p, job=job, hwaccel=mode)
    args = ffmpeg.convert.call_args.kwargs
    assert args['video_codec'] == encoder
    assert args['video_bitrate'] == p.video_bitrate
    assert args['hwaccel'] is None
    assert '-crf' not in args['extra_args'] and '-preset' not in args['extra_args']
    assert args['extra_args'][args['extra_args'].index('-allow_sw') + 1] == '0'
    if preset == 'iphone':
        assert args['extra_args'][args['extra_args'].index('-level') + 1] == '41'
    assert p.extra_args == original
    assert job.params['encoder'] == encoder


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,platform,available,fails', [
    ('cpu', 'darwin', True, False), ('none', 'darwin', True, False),
    ('auto', 'win32', True, False), ('auto', 'darwin', False, False),
    ('videotoolbox', 'darwin', True, True),
])
async def test_cpu_and_fallback_preserve_preset(tmp_path, monkeypatch, mode, platform, available, fails):
    monkeypatch.setattr(sys, 'platform', platform)
    source = tmp_path / 'source.mp4'
    source.touch()
    ffmpeg = SimpleNamespace(available_video_encoders=AsyncMock(return_value={'h264_videotoolbox'} if available else set()),
                             convert=AsyncMock(side_effect=[FFmpegError('unavailable'), tmp_path / 'out.mp4'] if fails else None))
    p = get_preset('mp4_h264_720p')
    await Converter(ffmpeg).convert_file(source, p, hwaccel=mode)
    args = ffmpeg.convert.call_args.kwargs
    assert args['video_codec'] == p.video_codec
    assert args['extra_args'] == p.extra_args
    assert args['video_bitrate'] == p.video_bitrate
    assert ffmpeg.convert.await_count == (2 if fails else 1)
    if platform == 'win32' or mode in ('cpu', 'none'):
        ffmpeg.available_video_encoders.assert_not_called()


@pytest.mark.asyncio
async def test_original_size_hevc_scales_existing_reference_bitrate(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    source = tmp_path / 'source.mp4'
    source.touch()
    ffmpeg = SimpleNamespace(available_video_encoders=AsyncMock(return_value={'hevc_videotoolbox'}),
        probe=AsyncMock(return_value=SimpleNamespace(video_streams=[SimpleNamespace(width=1920,height=1080)])), convert=AsyncMock())
    await Converter(ffmpeg).convert_file(source, 'mkv_h265_copy_audio')
    assert ffmpeg.convert.call_args.kwargs['video_bitrate'] == '3750000'
    assert ffmpeg.convert.call_args.kwargs['audio_codec'] == 'copy'


@pytest.mark.asyncio
async def test_cancel_never_retries_on_cpu(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    source = tmp_path / 'source.mp4'
    source.touch()
    ffmpeg = SimpleNamespace(available_video_encoders=AsyncMock(return_value={'h264_videotoolbox'}),
                             convert=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await Converter(ffmpeg).convert_file(source, 'mp4_h264_720p')
    assert ffmpeg.convert.await_count == 1


@pytest.mark.asyncio
async def test_encoder_detection_cache_follows_configured_binary(monkeypatch):
    launch = AsyncMock(return_value=SimpleNamespace(returncode=0))
    communicate = AsyncMock(return_value=(b' V....D h264_videotoolbox Hardware\n V....D hevc_videotoolbox Hardware\n A..... aac Audio', b''))
    monkeypatch.setattr('src.core.ffmpeg.create_hidden_subprocess', launch)
    monkeypatch.setattr('src.core.ffmpeg.communicate_with_job', communicate)
    ffmpeg = FFmpeg(ffmpeg_path='first-ffmpeg')
    assert await ffmpeg.available_video_encoders() == {'h264_videotoolbox', 'hevc_videotoolbox'}
    await ffmpeg.available_video_encoders()
    assert launch.await_count == 1
    ffmpeg.ffmpeg_path = 'second-ffmpeg'
    await ffmpeg.available_video_encoders()
    assert launch.await_count == 2


@pytest.mark.parametrize('platform,count', [('darwin',3),('win32',0)])
def test_encoder_options_are_macos_only(monkeypatch, platform, count):
    monkeypatch.setattr(sys, 'platform', platform)
    bridge = object.__new__(RetroDiscBridge)
    options = json.loads(bridge.get_encoder_options())
    assert len(options) == count
    if count:
        assert [o['id'] for o in options] == ['auto','videotoolbox','cpu']


@pytest.mark.asyncio
async def test_bridge_passes_encoder_choice_to_converter(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    source = tmp_path / 'video.mp4'
    source.touch()
    bridge = object.__new__(RetroDiscBridge)
    bridge.converter = SimpleNamespace(convert_file=AsyncMock(return_value=tmp_path / 'out.mp4'))
    captured = []
    bridge._submit_job = lambda job, handler: (captured.append((job,handler)) or '{}')
    bridge.convert_file(str(source), 'mp4_h264_720p', encoder='cpu')
    job, handler = captured[0]
    await handler(job)
    assert bridge.converter.convert_file.call_args.kwargs['hwaccel'] == 'cpu'
    assert job.output_path == tmp_path / 'out.mp4'
