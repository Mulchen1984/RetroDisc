"""Real cached audio waveform peaks (Mission 35). No dummy/constant peaks allowed."""
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from src.core.ffmpeg import FFmpeg
from src.services.waveform import Waveform

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg erforderlich")


def _run(*args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    if not FFMPEG:
        return {}
    base = tmp_path_factory.mktemp("wf")
    # Audio mit lauter/leiser Hälfte -> Peaks MÜSSEN variieren (Anti-Dummy).
    env = base / "env.wav"
    _run("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
         "-af", "volume='if(lt(t,3),0.1,0.9)':eval=frame", "-c:a", "pcm_s16le", str(env))
    with_audio = base / "with audio ä ß.mp4"      # Leerzeichen + Umlaute (Mission-Fall 8)
    _run("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25", "-i", str(env),
         "-map", "0:v", "-map", "1:a", "-t", "6", "-pix_fmt", "yuv420p",
         "-c:v", "libx264", "-crf", "28", "-c:a", "aac", "-shortest", str(with_audio))
    no_audio = base / "no_audio.mp4"
    _run("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25", "-t", "4", "-pix_fmt", "yuv420p",
         "-c:v", "libx264", "-crf", "28", str(no_audio))
    audio_only = base / "audio_only.mp3"
    _run("-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100:duration=5",
         "-c:a", "libmp3lame", str(audio_only))
    return {"base": base, "with_audio": with_audio, "no_audio": no_audio, "audio_only": audio_only}


def test_slice_window_maps_clip_range_to_peaks():
    peaks = list(range(100))
    # Trim/Split: Fenster [2.5,5] von 10s -> Indizes 25..50
    seg = Waveform.slice_window(peaks, duration=10, start=2.5, end=5.0)
    assert seg == list(range(25, 50))
    assert Waveform.slice_window(peaks, 10, 0, 0) == []      # leeres Fenster
    assert Waveform.slice_window([], 10, 0, 5) == []          # keine Peaks
    assert Waveform.slice_window(peaks, 0, 0, 5) == []        # keine Dauer


def test_bucketize_is_real_not_constant():
    import struct
    # Rampe 0..30000: die Bucket-Peaks müssen monoton steigen, nicht konstant.
    samples = struct.pack("<%dh" % 8000, *[int(i / 8000 * 30000) for i in range(8000)])
    peaks = Waveform._bucketize(samples, buckets=8)
    assert len(peaks) == 8
    assert len(set(peaks)) > 1                       # NICHT konstant
    assert peaks == sorted(peaks) and peaks[-1] > peaks[0]
    assert Waveform._bucketize(b"", 8) == []


@needs_ffmpeg
@pytest.mark.asyncio
async def test_video_with_audio_has_varying_peaks(media, tmp_path):
    wf = Waveform(FFmpeg(), tmp_path / "cache")
    result = await wf.peaks(media["with_audio"], buckets=200)
    assert result["has_audio"] and result["peaks"]
    peaks = result["peaks"]
    # Anti-Dummy: echte Peaks variieren; die laute Hälfte übertrifft die leise deutlich.
    assert len(set(peaks)) > 5, "Peaks sind konstant -> Dummy-Daten"
    half = len(peaks) // 2
    quiet = sum(peaks[:half]) / half
    loud = sum(peaks[half:]) / (len(peaks) - half)
    assert loud > quiet * 2, f"Hüllkurve nicht abgebildet (leise={quiet:.4f} laut={loud:.4f})"


@needs_ffmpeg
@pytest.mark.asyncio
async def test_video_without_audio_is_clean_no_error(media, tmp_path):
    wf = Waveform(FFmpeg(), tmp_path / "cache")
    result = await wf.peaks(media["no_audio"])
    assert result["has_audio"] is False and result["peaks"] == []
    assert result["duration"] > 0                    # kein Fehler, saubere Meldung


@needs_ffmpeg
@pytest.mark.asyncio
async def test_audio_only_file_produces_peaks(media, tmp_path):
    wf = Waveform(FFmpeg(), tmp_path / "cache")
    result = await wf.peaks(media["audio_only"], buckets=300)
    assert result["has_audio"] and 0 < len(result["peaks"]) <= 300


@needs_ffmpeg
@pytest.mark.asyncio
async def test_cache_is_reused_without_reanalysis(media, tmp_path):
    cache = tmp_path / "cache"
    wf = Waveform(FFmpeg(), cache)
    first = await wf.peaks(media["with_audio"], buckets=128)
    assert list(cache.glob("*.json")), "kein Cache geschrieben"
    # ffmpeg unbrauchbar machen: ein zweiter Aufruf darf ihn NICHT mehr aufrufen.
    wf.ffmpeg = SimpleNamespace(ffmpeg_path="/nonexistent",
                                probe=lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-analysiert!")))
    second = await wf.peaks(media["with_audio"], buckets=128)
    assert second == first


@needs_ffmpeg
@pytest.mark.asyncio
async def test_peak_count_bounded_by_buckets(media, tmp_path):
    wf = Waveform(FFmpeg(), tmp_path / "cache")
    result = await wf.peaks(media["audio_only"], buckets=64)
    assert len(result["peaks"]) <= 64                # Downsampling-/Peak-Limit greift
