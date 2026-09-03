"""Tests für Pipeline, Converter, Presets und Sound."""

import asyncio
import sys
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.pipeline import Pipeline
from src.models.media import Job, JobType, JobState, ConversionPreset, HighlightConfig, SceneScore
from src.config.presets import get_preset, get_presets_by_category, ALL_PRESETS
from src.config.settings import AppSettings
from src.utils.sound import generate_completion_wav


class TestPipeline:
    @pytest.mark.asyncio
    async def test_submit_job(self):
        pipeline = Pipeline(play_sound=False)
        job = Job(job_type=JobType.CONVERT)
        job_id = await pipeline.submit(job)
        assert job_id == job.id
        assert pipeline.queue_size == 1

    @pytest.mark.asyncio
    async def test_job_executes(self):
        pipeline = Pipeline(play_sound=False)
        executed = []

        async def handler(job):
            executed.append(job.id)
            job.update_progress(100, "Done")

        pipeline.register_handler(JobType.CONVERT.value, handler)
        job = Job(job_type=JobType.CONVERT)
        await pipeline.submit(job)

        # Run pipeline with timeout
        try:
            await asyncio.wait_for(pipeline.start(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        assert job.id in executed
        assert job.state == JobState.DONE

    @pytest.mark.asyncio
    async def test_failed_job(self):
        pipeline = Pipeline(play_sound=False)
        failures = []
        pipeline.on_job_failed = lambda j: failures.append(j.id)

        async def failing_handler(job):
            raise ValueError("Test-Fehler")

        pipeline.register_handler(JobType.CONVERT.value, failing_handler)
        job = Job(job_type=JobType.CONVERT)
        await pipeline.submit(job)

        try:
            await asyncio.wait_for(pipeline.start(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        assert job.state == JobState.FAILED
        assert job.error_message == "Test-Fehler"
        assert job.id in failures

    @pytest.mark.asyncio
    async def test_completion_observer_cannot_turn_done_job_into_failure(self):
        pipeline = Pipeline(play_sound=False)

        async def successful_handler(job):
            job.update_progress(50, "arbeitet")

        def broken_observer(_job):
            raise RuntimeError("UI ist bereits geschlossen")

        pipeline.register_handler(JobType.CONVERT.value, successful_handler)
        pipeline.on_job_complete = broken_observer
        job = Job(job_type=JobType.CONVERT)

        await pipeline._execute_job(job)

        assert job.state == JobState.DONE
        assert job.error_message is None
        assert job in pipeline.completed_jobs

    @pytest.mark.asyncio
    async def test_job_completion_observer_cannot_turn_done_job_into_failure(self):
        pipeline = Pipeline(play_sound=False)

        async def successful_handler(job):
            job.update_progress(50, "arbeitet")

        def broken_job_observer(_job):
            raise RuntimeError("Job-Observer ist bereits geschlossen")

        pipeline.register_handler(JobType.CONVERT.value, successful_handler)
        job = Job(job_type=JobType.CONVERT, on_complete=broken_job_observer)

        await pipeline._execute_job(job)

        assert job.state == JobState.DONE
        assert job.error_message is None
        assert job in pipeline.completed_jobs

    @pytest.mark.asyncio
    async def test_failure_observer_cannot_escape_or_replace_original_failure(self):
        pipeline = Pipeline(play_sound=False)

        async def failing_handler(_job):
            raise ValueError("ursprünglicher Fehler")

        def broken_observer(_job):
            raise RuntimeError("UI ist bereits geschlossen")

        pipeline.register_handler(JobType.CONVERT.value, failing_handler)
        pipeline.on_job_failed = broken_observer
        job = Job(job_type=JobType.CONVERT)

        await pipeline._execute_job(job)

        assert job.state == JobState.FAILED
        assert job.error_message == "ursprünglicher Fehler"
        assert job in pipeline.completed_jobs

    @pytest.mark.asyncio
    async def test_cancel_queued_job(self):
        pipeline = Pipeline(play_sound=False)
        job = Job(job_type=JobType.CONVERT)
        await pipeline.submit(job)
        cancelled = await pipeline.cancel_job(job.id)
        assert cancelled is True
        assert pipeline.queue_size == 0

    @pytest.mark.asyncio
    async def test_per_job_handlers_do_not_overwrite_each_other(self):
        """Queued jobs of the same type must retain their own closure/inputs."""
        pipeline = Pipeline(play_sound=False)
        executed = []

        async def first_handler(job):
            executed.append((job.id, "first"))

        async def second_handler(job):
            executed.append((job.id, "second"))

        first = Job(job_type=JobType.MERGE)
        second = Job(job_type=JobType.MERGE)
        await pipeline.submit(first, handler=first_handler)
        await pipeline.submit(second, handler=second_handler)

        runner = asyncio.create_task(pipeline.start())
        try:
            for _ in range(100):
                if first.state == JobState.DONE and second.state == JobState.DONE:
                    break
                await asyncio.sleep(0.01)
        finally:
            await pipeline.stop()
            await asyncio.wait_for(runner, timeout=1)

        assert executed == [(first.id, "first"), (second.id, "second")]

    @pytest.mark.asyncio
    async def test_cancel_running_job_terminates_attached_process(self):
        pipeline = Pipeline(play_sound=False)

        async def process_handler(job):
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", "import time; time.sleep(30)"
            )
            job._process = proc
            try:
                await proc.wait()
            finally:
                job._process = None

        job = Job(job_type=JobType.CONVERT)
        await pipeline.submit(job, handler=process_handler)
        runner = asyncio.create_task(pipeline.start())
        proc = None
        try:
            for _ in range(200):
                proc = getattr(job, "_process", None)
                if job.state == JobState.RUNNING and proc is not None:
                    break
                await asyncio.sleep(0.01)
            assert proc is not None and proc.returncode is None
            assert await pipeline.cancel_job(job.id) is True
            await asyncio.wait_for(proc.wait(), timeout=2)
            assert job.state == JobState.CANCELLED
            assert proc.returncode is not None
        finally:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            await pipeline.stop()
            await asyncio.wait_for(runner, timeout=1)

    @pytest.mark.asyncio
    async def test_shutdown_cancels_queued_and_running_jobs(self):
        pipeline = Pipeline(play_sound=False)

        async def process_handler(job):
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", "import time; time.sleep(30)"
            )
            job._process = proc
            try:
                await proc.wait()
            finally:
                job._process = None

        running = Job(job_type=JobType.CONVERT)
        queued = Job(job_type=JobType.CONVERT)
        await pipeline.submit(running, handler=process_handler)
        await pipeline.submit(queued, handler=process_handler)
        runner = asyncio.create_task(pipeline.start())
        proc = None
        try:
            for _ in range(200):
                proc = getattr(running, "_process", None)
                if proc is not None:
                    break
                await asyncio.sleep(0.01)
            assert proc is not None and proc.returncode is None
            await pipeline.shutdown()
            await asyncio.wait_for(runner, timeout=1)
            await asyncio.wait_for(proc.wait(), timeout=2)
            assert running.state == JobState.CANCELLED
            assert queued.state == JobState.CANCELLED
            assert pipeline.queue_size == 0
            assert pipeline.running_count == 0
        finally:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            await pipeline.stop()


class TestJob:
    def test_initial_state(self):
        job = Job()
        assert job.state == JobState.PENDING
        assert job.progress == 0.0
        assert job.started_at is None

    def test_mark_running(self):
        job = Job()
        job.mark_running()
        assert job.state == JobState.RUNNING
        assert job.started_at is not None

    def test_mark_done(self):
        complete_called = []
        job = Job()
        job.on_complete = lambda j: complete_called.append(j.id)
        job.mark_running()
        job.mark_done()
        assert job.state == JobState.DONE
        assert job.progress == 100.0
        assert job.id in complete_called

    def test_mark_failed(self):
        job = Job()
        job.mark_running()
        job.mark_failed("Fehler!")
        assert job.state == JobState.FAILED
        assert job.error_message == "Fehler!"

    def test_progress_callback(self):
        updates = []
        job = Job()
        job.on_progress = lambda p, t: updates.append((p, t))
        job.update_progress(50.0, "Halbzeit")
        assert updates == [(50.0, "Halbzeit")]

    def test_progress_observer_failure_does_not_escape(self):
        job = Job()
        job.on_progress = lambda *_args: (_ for _ in ()).throw(
            RuntimeError("UI geschlossen")
        )

        job.update_progress(50.0, "Halbzeit")

        assert job.progress == 50.0
        assert job.progress_text == "Halbzeit"

    def test_progress_capped_at_100(self):
        job = Job()
        job.update_progress(150.0, "Über 100")
        assert job.progress == 100.0

    def test_elapsed_seconds(self):
        import time
        job = Job()
        job.mark_running()
        time.sleep(0.05)
        assert job.elapsed_seconds >= 0.04


class TestHighlightConfig:
    def test_defaults(self):
        config = HighlightConfig()
        assert config.target_duration_seconds == 300.0
        assert config.prefer_faces is True
        assert config.prefer_audio_peaks is True
        assert config.min_clip_duration == 3.0

    def test_scene_score_duration(self):
        scene = SceneScore(start_time=10.0, end_time=25.0)
        assert scene.duration == 15.0


class TestPresets:
    def test_get_all_presets(self):
        assert len(ALL_PRESETS) >= 18

    def test_category_filtering(self):
        video = get_presets_by_category('video')
        audio = get_presets_by_category('audio')
        device = get_presets_by_category('device')
        disc = get_presets_by_category('disc')
        assert all(p.category == 'video' for p in video)
        assert all(p.category == 'audio' for p in audio)
        assert all(p.category == 'device' for p in device)
        assert all(p.category == 'disc' for p in disc)

    def test_dvd_presets_have_extra_args(self):
        dvd = get_preset('dvd_pal')
        assert '-target' in dvd.extra_args
        assert 'pal-dvd' in dvd.extra_args

    def test_audio_cd_preset(self):
        cd = get_preset('audio_cd')
        assert cd.audio_codec == 'pcm_s16le'
        assert cd.sample_rate == 44100
        assert cd.container == 'wav'

    def test_all_presets_valid(self):
        for p in ALL_PRESETS:
            assert p.name, f"Preset {p} hat keinen Namen"
            assert p.display_name, f"Preset {p.name} hat keinen Display-Namen"
            assert p.container, f"Preset {p.name} hat keinen Container"
            assert p.category in ('video', 'audio', 'device', 'disc')


class TestSettings:
    def test_default_settings(self):
        s = AppSettings()
        assert s.conversion.dvd_standard == 'PAL'
        assert s.sound.play_on_complete is True
        assert s.ai.whisper_model == 'base'

    def test_settings_serialization(self):
        s = AppSettings()
        json_str = s.model_dump_json()
        s2 = AppSettings.model_validate_json(json_str)
        assert s2.conversion.dvd_standard == s.conversion.dvd_standard

    def test_ensure_directories(self, tmp_path):
        s = AppSettings()
        s.directories.output_dir = tmp_path / 'output'
        s.directories.temp_dir = tmp_path / 'temp'
        s.directories.download_dir = tmp_path / 'downloads'
        s.ensure_directories()
        assert s.directories.output_dir.exists()
        assert s.directories.temp_dir.exists()
        assert s.directories.download_dir.exists()


class TestSound:
    def test_generate_completion_wav(self):
        wav_path = generate_completion_wav()
        assert wav_path.exists()
        assert wav_path.stat().st_size > 1000
        assert wav_path.suffix == '.wav'
        wav_path.unlink()
