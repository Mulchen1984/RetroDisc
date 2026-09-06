"""Media AI: die Anbindung an Bridge und Oberflaeche.

Geprueft wird hier nicht die Medienarbeit, sondern die Verdrahtung: dass die
Auftraege durch die **bestehende** Pipeline gehen statt an ihr vorbei, dass
eine Mappe ausserhalb des Downloadordners abgewiesen wird, und dass jede
Bridge-Methode ihren Proxy hat - ohne den ist der Knopf in der Oberflaeche
tot.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from retrodisc_launcher import RetroDiscApi, RetroDiscBridge
from src.models.media import JobType
from src.services.media_ai.workspace import MediaJob, create_workspace

UI = (Path(__file__).parents[1] / "src" / "ui" / "app.html").read_text(encoding="utf-8")

MEDIA_AI_METHODS = [
    "media_ai_import",
    "media_ai_extract_audio",
    "media_ai_extract_video",
    "media_ai_transcribe",
    "media_ai_extract_frames",
    "media_ai_list",
    "media_ai_open",
]


def _bridge(download_dir: Path) -> RetroDiscBridge:
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = SimpleNamespace(
        directories=SimpleNamespace(download_dir=download_dir),
        tools=SimpleNamespace(ytdlp="yt-dlp", ffmpeg="ffmpeg"),
        ai=SimpleNamespace(whisper_model="base"),
    )
    bridge.ffmpeg = SimpleNamespace(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
    bridge.job_history = None
    bridge.submitted = []

    def _submit(job, handler):
        bridge.submitted.append((job, handler))
        return json.dumps({"job_id": job.id, "status": "queued"})

    bridge._submit_job = _submit
    return bridge


# ── Verdrahtung ───────────────────────────────────────────────────────

@pytest.mark.parametrize("method", MEDIA_AI_METHODS)
def test_every_bridge_method_has_its_proxy(method):
    assert hasattr(RetroDiscBridge, method), f"Bridge kennt {method} nicht"
    assert hasattr(RetroDiscApi, method), f"Ohne Proxy ist der Knopf tot: {method}"


@pytest.mark.parametrize("method", MEDIA_AI_METHODS)
def test_the_proxy_accepts_what_the_bridge_accepts(method):
    bridge_args = inspect.signature(getattr(RetroDiscBridge, method)).parameters
    proxy_args = inspect.signature(getattr(RetroDiscApi, method)).parameters

    assert len(proxy_args) == len(bridge_args), \
        f"Arity-Unterschied bei {method}: {list(proxy_args)} vs {list(bridge_args)}"


def test_the_work_goes_through_the_existing_pipeline():
    """Keine zweite Queue - Fortschritt, Abbruch und Historie sollen gelten."""
    for method in ("media_ai_import", "media_ai_extract_audio",
                   "media_ai_extract_video", "media_ai_transcribe",
                   "media_ai_extract_frames"):
        source = inspect.getsource(getattr(RetroDiscBridge, method))
        assert "self._submit_job(job, _handler)" in source, \
            f"{method} laeuft an der Pipeline vorbei"


def test_import_uses_its_own_job_type(tmp_path):
    bridge = _bridge(tmp_path)

    bridge.media_ai_import("https://example.invalid/v")

    job, _ = bridge.submitted[0]
    assert job.job_type is JobType.MEDIA_AI_IMPORT


# ── Eingaben ──────────────────────────────────────────────────────────

def test_import_rejects_a_non_http_url(tmp_path):
    bridge = _bridge(tmp_path)

    answer = json.loads(bridge.media_ai_import("nicht-mal-eine-url"))

    assert "error" in answer
    assert bridge.submitted == []


def test_import_carries_the_chosen_options(tmp_path):
    bridge = _bridge(tmp_path)

    bridge.media_ai_import("https://example.invalid/v", "720p", False, True)

    job, _ = bridge.submitted[0]
    assert job.params["quality"] == "720p"


def test_a_workspace_outside_the_download_folder_is_refused(tmp_path):
    """Sonst liesse sich ueber die Bridge ein beliebiger Ordner oeffnen."""
    bridge = _bridge(tmp_path / "Downloads")
    (tmp_path / "Downloads").mkdir()
    outside = tmp_path / "woanders"
    outside.mkdir()

    for method in ("media_ai_extract_audio", "media_ai_extract_video",
                   "media_ai_transcribe", "media_ai_open"):
        answer = json.loads(getattr(bridge, method)(str(outside)))
        assert "error" in answer, f"{method} liess einen fremden Ordner zu"
        assert "ausserhalb" in answer["error"]


def test_a_traversal_attempt_is_refused(tmp_path):
    base = tmp_path / "Downloads"
    base.mkdir()
    bridge = _bridge(base)

    answer = json.loads(bridge.media_ai_open(str(base / ".." / "geheim")))

    assert "error" in answer


def test_extracting_without_a_source_file_is_reported(tmp_path):
    base = tmp_path / "Downloads"
    workspace = create_workspace(base, "Leer")
    workspace.save_job(MediaJob(title="Leer"))
    bridge = _bridge(base)

    answer = json.loads(bridge.media_ai_extract_audio(str(workspace.root)))

    assert "error" in answer
    assert "keine Quelldatei" in answer["error"]


def test_a_nonsense_frame_rate_is_refused(tmp_path):
    base = tmp_path / "Downloads"
    workspace = create_workspace(base, "T")
    workspace.save_job(MediaJob(title="T"))
    bridge = _bridge(base)

    answer = json.loads(bridge.media_ai_extract_frames(str(workspace.root), 0))

    assert "error" in answer
    assert bridge.submitted == []


# ── Auflisten ─────────────────────────────────────────────────────────

def test_list_reports_the_workspaces_and_their_base(tmp_path):
    base = tmp_path / "Downloads"
    workspace = create_workspace(base, "Konzert")
    (workspace.root / "original.mp4").write_bytes(b"x")
    workspace.save_job(MediaJob(title="Konzert", url="https://example.invalid/v"))
    bridge = _bridge(base)

    answer = json.loads(bridge.media_ai_list())

    assert answer["base"] == str(base)
    assert len(answer["workspaces"]) == 1
    assert answer["workspaces"][0]["title"] == "Konzert"
    assert "original" in answer["workspaces"][0]["artefacts"]


def test_list_is_empty_before_the_first_import(tmp_path):
    answer = json.loads(_bridge(tmp_path / "Downloads").media_ai_list())

    assert answer["workspaces"] == []


# ── Oberflaeche ───────────────────────────────────────────────────────

def test_the_ui_has_a_media_ai_area():
    assert 'id="tab-mediaai"' in UI
    assert 'id="tbtn-mediaai"' in UI
    assert "mediaai:['Media AI'" in UI


@pytest.mark.parametrize("control", [
    "maiUrl", "maiQuality", "maiVideo", "maiAudio", "maiList",
])
def test_the_area_offers_the_required_controls(control):
    assert f'id="{control}"' in UI


def test_the_area_wires_every_action():
    for call in ("a.media_ai_import(", "a.media_ai_list()",
                 "a.media_ai_extract_frames(", "a.media_ai_open("):
        assert call in UI, f"Nicht verdrahtet: {call}"
    assert "media_ai_extract_audio" in UI
    assert "media_ai_extract_video" in UI
    assert "media_ai_transcribe" in UI


def test_the_audio_target_is_named_where_the_user_chooses_it():
    """Die Vorgabe soll nicht erst im Handbuch stehen."""
    assert "16 kHz" in UI and "mono" in UI


def test_the_workspace_list_is_reloaded_when_the_area_opens():
    assert "if(name==='mediaai'){ loadMediaAiWorkspaces(); }" in UI


def test_folder_arguments_reach_the_bridge_through_data_attributes():
    """Pfade mit Anfuehrungszeichen wuerden ein inline-Argument sprengen."""
    assert "onclick=\"mediaAiOpen(this.dataset.f)\"" in UI
    assert "data-f=\"${folder}\"" in UI
