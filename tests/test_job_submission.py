"""Every bridge method that queues work must produce a usable job.

``Job`` is a dataclass whose **first** field is ``id``, not ``job_type``. A
positional ``Job(JobType.TRIM, ...)`` therefore silently assigns the enum to
``id`` and leaves ``job_type`` at its ``CONVERT`` default. The damage is not
cosmetic:

* ``_submit_job`` ends with ``json.dumps({"job_id": job.id, ...})`` and an enum
  is not JSON serialisable, so the call raises out of the bridge and the UI
  action does nothing at all;
* every job of that kind shares one id, so ``Pipeline._tasks`` and
  ``_job_handlers`` collide as soon as two run together;
* the queue and the burn animation key on ``job_type`` and would see the wrong
  one.

Seven flows shipped that way — rip, highlights, subtitles, upscale,
interpolate, trim and merge. The tests below check the real product methods
through the real constructor, and an AST rule keeps the shape from returning
anywhere in the product code.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import retrodisc_launcher as launcher
from retrodisc_launcher import RetroDiscBridge
from src.config.settings import AppSettings
from src.models.media import JobType

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def queued_bridge(tmp_path, monkeypatch):
    """The production bridge with a live loop, but a queue that never drains.

    ``_submit_job`` only starts the pipeline when it is not already running.
    Marking it running without a worker keeps submitted jobs parked in the
    queue, so the submission itself can be inspected without needing FFmpeg,
    yt-dlp or an optical drive.
    """
    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(
        AppSettings, "_default_config_path", staticmethod(lambda: config_path)
    )
    AppSettings(directories={
        "output_dir": tmp_path / "output",
        "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }).save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    bridge = RetroDiscBridge()
    bridge.pipeline._is_running = True
    try:
        yield bridge
    finally:
        bridge._loop.call_soon_threadsafe(bridge._loop.stop)
        bridge._thread.join(timeout=5)
        bridge._loop.close()


def _media(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"placeholder; only its existence is checked")
    return path


def submissions(bridge, tmp_path) -> list[tuple[str, JobType, object]]:
    """(label, expected job type, call) for every queueing bridge method."""
    first = _media(tmp_path, "clip.mp4")
    second = _media(tmp_path, "clip2.mp4")
    pair = json.dumps([str(first), str(second)])
    return [
        ("convert_file", JobType.CONVERT,
         lambda: bridge.convert_file(str(first), "mp4_h264_1080p")),
        ("download_url", JobType.DOWNLOAD,
         lambda: bridge.download_url("https://www.youtube.com/watch?v=9bZkp7q19f0")),
        ("create_dvd", JobType.BURN_DVD,
         lambda: bridge.create_dvd(pair, "Testtitel")),
        ("copy_disc", JobType.RIP_DVD,
         lambda: bridge.copy_disc("E:", "F:")),
        ("rip_disc", JobType.RIP_DVD,
         lambda: bridge.rip_disc("E:", "iso")),
        ("create_highlights", JobType.SMART_EDIT,
         lambda: bridge.create_highlights(str(first), 60)),
        ("generate_subtitles", JobType.SUBTITLE_GENERATE,
         lambda: bridge.generate_subtitles(str(first))),
        ("upscale_video", JobType.UPSCALE,
         lambda: bridge.upscale_video(str(first), 2)),
        ("interpolate_video", JobType.INTERPOLATE,
         lambda: bridge.interpolate_video(str(first), 50)),
        ("trim_video", JobType.TRIM,
         lambda: bridge.trim_video(str(first), 0.0, 1.0)),
        ("merge_videos", JobType.MERGE,
         lambda: bridge.merge_videos(pair)),
    ]


def test_every_queueing_bridge_method_returns_a_usable_job(queued_bridge, tmp_path):
    """Before the fix seven of these raised instead of returning a job id."""
    seen: dict[str, str] = {}

    for label, expected_type, call in submissions(queued_bridge, tmp_path):
        answer = json.loads(call())
        assert "error" not in answer, f"{label} was rejected: {answer}"
        job_id = answer["job_id"]
        assert isinstance(job_id, str) and job_id, f"{label} returned {job_id!r}"
        assert answer["status"] == "queued"

        job = queued_bridge.pipeline.get_job(job_id)
        assert job is not None, f"{label} did not park a job under {job_id}"
        assert job.job_type is expected_type, (
            f"{label} queued {job.job_type} instead of {expected_type}"
        )
        assert job.id == job_id
        seen[label] = job_id

    assert len(set(seen.values())) == len(seen), f"ids collided: {seen}"


def test_two_jobs_of_the_same_kind_get_distinct_ids(queued_bridge, tmp_path):
    """A shared id would let the second submission overwrite the first handler."""
    clip = _media(tmp_path, "clip.mp4")

    first = json.loads(queued_bridge.trim_video(str(clip), 0.0, 1.0))["job_id"]
    second = json.loads(queued_bridge.trim_video(str(clip), 1.0, 2.0))["job_id"]

    assert first != second
    assert queued_bridge.pipeline.queue_size == 2
    handlers = queued_bridge.pipeline._job_handlers
    assert {first, second} <= set(handlers)
    assert handlers[first] is not handlers[second]


def test_no_product_code_passes_the_job_type_positionally():
    """The dataclass field order makes a positional job type a silent id."""
    offenders: list[str] = []
    sources = [ROOT / "retrodisc_launcher.py", *sorted((ROOT / "src").rglob("*.py"))]

    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name != "Job" or not node.args:
                continue
            offenders.append(
                f"{source.relative_to(ROOT).as_posix()}:{node.lineno}"
            )

    assert offenders == [], (
        "Job() must always be built with keywords; these pass the first field "
        f"positionally and would set 'id' instead of 'job_type': {offenders}"
    )
