"""Manual end-to-end verification for the RetroDisc bridge."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retrodisc_launcher import RetroDiscBridge
from src.models.media import JobState


root = ROOT
source = root / "tests" / "fixtures" / "test_video.mp4"
out_dir = Path(tempfile.mkdtemp(prefix="retrodisc_convert_"))
bridge = RetroDiscBridge()
bridge.settings.sound.play_on_complete = False

try:
    probe = json.loads(bridge.probe_file(str(source)))
    if probe.get("error"):
        raise RuntimeError(probe["error"])

    queued = json.loads(bridge.convert_file(
        str(source), "mp3_320k", str(out_dir), True
    ))
    if queued.get("error"):
        raise RuntimeError(queued["error"])

    job_id = queued["job_id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job = bridge.pipeline.get_job(job_id)
        if job and job.state in {JobState.DONE, JobState.FAILED, JobState.CANCELLED}:
            break
        time.sleep(0.1)
    else:
        raise TimeoutError("Konvertierungsjob wurde nicht innerhalb von 120 Sekunden fertig.")

    if job.state is not JobState.DONE:
        raise RuntimeError(job.error_message or f"Jobstatus: {job.state.value}")
    if not job.output_path or not job.output_path.exists():
        raise RuntimeError("Ausgabedatei fehlt.")

    output_probe = json.loads(bridge.probe_file(str(job.output_path)))
    if output_probe.get("error"):
        raise RuntimeError(output_probe["error"])

    print(json.dumps({
        "input": {
            "name": probe["name"],
            "duration": probe["duration_formatted"],
            "resolution": probe["resolution"],
        },
        "job": {"id": job.id, "state": job.state.value, "progress": job.progress},
        "output": {
            "path": str(job.output_path),
            "size_bytes": job.output_path.stat().st_size,
            "audio_codec": output_probe["audio_codec"],
            "video_codec": output_probe["video_codec"],
        },
    }, ensure_ascii=False))
finally:
    bridge._async(bridge.pipeline.stop()).result(timeout=5)
    bridge._async(asyncio.sleep(0.2)).result(timeout=5)
    bridge._loop.call_soon_threadsafe(bridge._loop.stop)
    bridge._thread.join(timeout=5)
