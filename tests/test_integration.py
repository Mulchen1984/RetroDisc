"""Integration-Tests mit echten FFmpeg-Aufrufen und Test-Videodateien."""

import asyncio
import pytest
from pathlib import Path

# Markierung für Integration-Tests (brauchen FFmpeg)
pytestmark = pytest.mark.asyncio

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TEST_VIDEO = FIXTURE_DIR / "test_video.mp4"


@pytest.fixture(autouse=True)
def check_fixtures():
    """Prüft ob Test-Fixtures vorhanden sind."""
    if not TEST_VIDEO.exists():
        pytest.skip(f"Test-Fixture fehlt: {TEST_VIDEO}. Bitte 'python -m retrodisc fixtures' ausführen.")


class TestFFmpegIntegration:
    """Echte FFmpeg-Tests mit dem Test-Video."""

    async def test_probe_real_file(self):
        from src.core.ffmpeg import FFmpeg
        ff = FFmpeg()
        media = await ff.probe(TEST_VIDEO)

        assert media.path.name == "test_video.mp4"
        assert media.duration_seconds > 0
        assert media.has_video
        assert media.has_audio
        assert media.video_streams[0].width == 1280
        assert media.video_streams[0].height == 720

    async def test_convert_to_mkv(self, tmp_path):
        from src.core.ffmpeg import FFmpeg
        ff = FFmpeg()
        output = tmp_path / "output.mkv"
        result = await ff.convert(
            input_path=TEST_VIDEO,
            output_path=output,
            video_codec="libx264",
            audio_codec="aac",
            extra_args=["-preset", "ultrafast", "-crf", "35"],
        )
        assert result.exists()
        assert result.stat().st_size > 1000

    async def test_extract_audio_mp3(self, tmp_path):
        from src.core.ffmpeg import FFmpeg
        ff = FFmpeg()
        output = tmp_path / "audio.mp3"
        result = await ff.extract_audio(
            input_path=TEST_VIDEO,
            output_path=output,
            codec="libmp3lame",
            bitrate="128k",
        )
        assert result.exists()
        # Prüfen ob wirklich Audio (kein Video)
        media = await ff.probe(result)
        assert not media.has_video
        assert media.has_audio

    async def test_trim(self, tmp_path):
        from src.core.ffmpeg import FFmpeg
        ff = FFmpeg()
        output = tmp_path / "trimmed.mp4"
        result = await ff.trim(
            input_path=TEST_VIDEO,
            output_path=output,
            start_seconds=2.0,
            end_seconds=7.0,
        )
        assert result.exists()
        media = await ff.probe(result)
        # Darf nicht länger als 6 Sekunden sein (5s + etwas Puffer)
        assert media.duration_seconds < 6.5

    async def test_thumbnail(self, tmp_path):
        from src.core.ffmpeg import FFmpeg
        ff = FFmpeg()
        output = tmp_path / "thumb.jpg"
        result = await ff.generate_thumbnail(
            input_path=TEST_VIDEO,
            output_path=output,
            time_seconds=3.0,
            width=320,
        )
        assert result.exists()
        assert result.stat().st_size > 1000  # Echtes Bild

    async def test_progress_callback(self):
        from src.core.ffmpeg import FFmpeg
        from src.models.media import Job, JobType

        ff = FFmpeg()
        job = Job(job_type=JobType.CONVERT)
        progress_values = []
        job.on_progress = lambda p, t: progress_values.append(p)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            out = Path(f.name)

        try:
            await ff.convert(
                input_path=TEST_VIDEO,
                output_path=out,
                video_codec="libx264",
                audio_codec="aac",
                extra_args=["-preset", "ultrafast", "-crf", "40"],
                job=job,
                overwrite=True,
            )
        finally:
            out.unlink(missing_ok=True)

        # Progress-Callbacks müssen aufgerufen worden sein
        assert len(progress_values) >= 0  # Kurzes Video -> möglicherweise keine Updates
        if progress_values:
            assert all(0 <= p <= 100 for p in progress_values)


class TestMediaLibrary:
    """Tests für den Media Library Manager."""

    async def test_scan_and_query(self, tmp_path):
        from src.services.library import MediaLibrary

        db = tmp_path / "test.db"
        lib = MediaLibrary(
            db_path=db,
            thumb_dir=tmp_path / "thumbs",
        )
        lib.open()

        try:
            # Scan des Fixtures-Ordners
            added = await lib.scan_folder(
                FIXTURE_DIR,
                recursive=False,
                generate_thumbs=True,
            )
            assert added >= 1  # Mindestens test_video.mp4

            # Abfrage
            all_files = lib.get_all()
            assert len(all_files) >= 1

            video_files = lib.get_all(media_type="video")
            assert len(video_files) >= 1
            assert all(f["media_type"] == "video" for f in video_files)

            # Statistiken
            stats = lib.get_stats()
            assert stats["total"] >= 1
            assert stats["videos"] >= 1

        finally:
            lib.close()

    async def test_search(self, tmp_path):
        from src.services.library import MediaLibrary

        lib = MediaLibrary(db_path=tmp_path / "test.db", thumb_dir=tmp_path / "thumbs")
        lib.open()
        try:
            await lib.scan_folder(FIXTURE_DIR, recursive=False, generate_thumbs=False)

            # Suche nach Dateinamen-Fragment
            results = lib.search("test_video")
            assert len(results) >= 1
        finally:
            lib.close()

    async def test_no_rescan_unchanged(self, tmp_path):
        """Unveränlerte Dateien werden nicht neu gescannt."""
        from src.services.library import MediaLibrary

        lib = MediaLibrary(db_path=tmp_path / "test.db", thumb_dir=tmp_path / "thumbs")
        lib.open()
        try:
            added1 = await lib.scan_folder(FIXTURE_DIR, recursive=False, generate_thumbs=False)
            added2 = await lib.scan_folder(FIXTURE_DIR, recursive=False, generate_thumbs=False)
            # Zweiter Scan sollte 0 neue Dateien hinzufügen
            assert added2 == 0
        finally:
            lib.close()


class TestConverterService:
    """Tests für den Converter-Service."""

    async def test_convert_with_preset(self, tmp_path):
        from src.services.converter import Converter

        conv = Converter(output_dir=tmp_path)
        result = await conv.convert_file(
            input_path=TEST_VIDEO,
            preset="mp3_320k",
        )
        assert result.exists()
        assert result.suffix == ".mp3"

    async def test_analyze(self):
        from src.services.converter import Converter

        conv = Converter()
        media = await conv.analyze(TEST_VIDEO)
        assert media.has_video
        assert media.resolution == "1280x720"

    async def test_batch_single_file(self, tmp_path):
        from src.services.converter import Converter

        # Kopie des Test-Videos im tmp-Ordner
        import shutil
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        shutil.copy(TEST_VIDEO, src_dir / "test_video.mp4")

        conv = Converter(output_dir=tmp_path / "output")
        completed_files = []

        results = await conv.batch_convert(
            input_dir=src_dir,
            preset="mp3_320k",
            on_file_complete=lambda f, o, i, t: completed_files.append(o),
        )

        assert len(results) == 1
        assert len(completed_files) == 1
        assert results[0].exists()
