"""Media AI: Downloader, Splitter, Prozessoren und der Import-Ablauf.

Die externen Werkzeuge sind durch Doubles ersetzt. Auf diesem Host sind die
Vendor-Binaries ohnehin von Smart App Control blockiert; geprueft werden soll
hier aber auch gar nicht ffmpeg, sondern **womit** es aufgerufen wird - die
Audiovorgabe PCM/16 kHz/mono und das Kopieren der Videospur ohne
Neukodierung sind Zusicherungen der Pipeline, nicht von ffmpeg.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.ffmpeg import FFmpegError
from src.models.media import Job, JobType
from src.services.media_ai import (
    AUDIO_CHANNELS,
    AUDIO_CODEC,
    AUDIO_SAMPLE_RATE,
    AudioProcessor,
    BackendNotConfigured,
    MediaDownloader,
    MediaSplitter,
    ProcessingError,
    SplitError,
    VideoProcessor,
)
from src.services.media_ai.downloader import (
    MediaDownloadError,
    _friendly_download_error,
)
from src.services.media_ai.workflow import MEDIA_AI_STAGES, run_media_ai_import
from src.services.media_ai.workspace import MediaJob, create_workspace


# ══════════════════════════════════════════════════════════════════════
# Doubles
# ══════════════════════════════════════════════════════════════════════

class _RecordingFFmpeg:
    """Merkt sich die Aufrufe und legt die Zieldatei an."""

    ffmpeg_path = "ffmpeg"
    ffprobe_path = "ffprobe"

    def __init__(self):
        self.calls: list[dict] = []

    async def convert(self, input_path, output_path, **kwargs):
        self.calls.append({"input": Path(input_path),
                           "output": Path(output_path), **kwargs})
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"ausgabe")
        return target


class _FailingFFmpeg(_RecordingFFmpeg):
    async def convert(self, input_path, output_path, **kwargs):
        raise FFmpegError("Stream map '0:v' matches no streams")


class _FakeMediaDownloader:
    """Ersetzt yt-dlp: legt original.<ext> in der Mappe ab."""

    def __init__(self, title="Konzert", suffix=".webm", fail=None):
        self.title = title
        self.suffix = suffix
        self.fail = fail

    async def probe(self, url):
        if self.fail:
            raise self.fail
        return {"title": self.title, "id": "vid123", "duration": 42.0,
                "uploader": "Kanal", "extractor": "Youtube"}

    def prepare_workspace(self, base_dir, title):
        return create_workspace(base_dir, title)

    async def fetch(self, url, workspace, quality="best", job=None):
        target = workspace.root / f"original{self.suffix}"
        target.write_bytes(b"quellmedium")
        return target


def _import_job(url="https://example.invalid/v") -> Job:
    return Job(job_type=JobType.MEDIA_AI_IMPORT,
               params={"url": url, "quality": "best", "stage": "",
                       "display_name": "Media AI"})


# ══════════════════════════════════════════════════════════════════════
# MediaSplitter — die Formatzusicherungen
# ══════════════════════════════════════════════════════════════════════

def test_audio_is_extracted_as_pcm_16k_mono(tmp_path):
    """Die Vorgabe fuer Whisper und Voice-Cloning."""
    ffmpeg = _RecordingFFmpeg()
    workspace = create_workspace(tmp_path, "T")
    source = workspace.root / "original.webm"
    source.write_bytes(b"x")

    result = asyncio.run(MediaSplitter(ffmpeg).extract_audio(source, workspace))

    call = ffmpeg.calls[0]
    assert call["audio_codec"] == AUDIO_CODEC == "pcm_s16le"
    assert call["sample_rate"] == AUDIO_SAMPLE_RATE == 16_000
    assert "-ac" in call["extra_args"]
    assert call["extra_args"][call["extra_args"].index("-ac") + 1] == str(AUDIO_CHANNELS)
    assert "-vn" in call["extra_args"], "Ohne -vn landet Video im WAV-Container"
    assert result.name == "audio.wav"


def test_video_is_copied_not_reencoded(tmp_path):
    ffmpeg = _RecordingFFmpeg()
    workspace = create_workspace(tmp_path, "T")
    source = workspace.root / "original.mkv"
    source.write_bytes(b"x")

    result = asyncio.run(MediaSplitter(ffmpeg).extract_video(source, workspace))

    call = ffmpeg.calls[0]
    assert call["video_codec"] == "copy", "Es darf nicht neu kodiert werden"
    assert "-an" in call["extra_args"]
    assert call.get("video_bitrate") is None
    assert result.name == "video.mkv", "Die Endung der Quelle bleibt erhalten"


def test_an_audio_only_source_is_rejected_with_a_clear_reason(tmp_path):
    ffmpeg = _RecordingFFmpeg()
    workspace = create_workspace(tmp_path, "T")
    source = workspace.root / "original.mp3"
    source.write_bytes(b"x")

    with pytest.raises(SplitError, match="nur Ton"):
        asyncio.run(MediaSplitter(ffmpeg).extract_video(source, workspace))
    assert ffmpeg.calls == [], "ffmpeg haette gar nicht laufen duerfen"


def test_a_missing_source_is_reported(tmp_path):
    workspace = create_workspace(tmp_path, "T")

    with pytest.raises(SplitError, match="nicht gefunden"):
        asyncio.run(MediaSplitter(_RecordingFFmpeg()).extract_audio(
            workspace.root / "weg.mp4", workspace))


def test_an_ffmpeg_failure_becomes_a_readable_sentence(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    source = workspace.root / "original.mp4"
    source.write_bytes(b"x")

    with pytest.raises(SplitError) as caught:
        asyncio.run(MediaSplitter(_FailingFFmpeg()).extract_video(source, workspace))

    message = str(caught.value)
    assert "Stream map" not in message, "Rohtext gehoert ins Log, nicht in die UI"
    assert "Protokoll" in message


# ══════════════════════════════════════════════════════════════════════
# MediaDownloader — Fehlerübersetzung und Probe
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw, needle", [
    ("ERROR: unable to download webpage: HTTP Error 403: Forbidden", "403"),
    ("ERROR: HTTP Error 404: Not Found", "404"),
    ("ERROR: Private video. Sign in if you've been granted access", "privat"),
    ("ERROR: Unsupported URL: https://example.invalid", "nicht unterstuetzt"),
    ("OSError: No space left on device", "Platz"),
])
def test_common_download_errors_become_german_sentences(raw, needle):
    message = _friendly_download_error(raw)

    assert needle.lower() in message.lower()
    assert raw not in message, "Der Rohtext darf nicht durchgereicht werden"


def test_an_unknown_error_points_at_the_log():
    message = _friendly_download_error("irgendein voellig neuer Fehler")

    assert "Protokoll" in message


def test_probe_rejects_a_non_http_url():
    downloader = MediaDownloader(ytdlp_path="yt-dlp")

    with pytest.raises(Exception):
        asyncio.run(downloader.probe("file:///C:/Windows/System32"))


def test_a_missing_ytdlp_is_reported_by_name(monkeypatch):
    async def missing(*args, **kwargs):
        raise FileNotFoundError("yt-dlp")

    monkeypatch.setattr(
        "src.services.media_ai.downloader.create_hidden_subprocess", missing)
    downloader = MediaDownloader(ytdlp_path=r"C:\weg\yt-dlp.exe")

    with pytest.raises(MediaDownloadError, match="yt-dlp"):
        asyncio.run(downloader.probe("https://example.invalid/v"))


# ══════════════════════════════════════════════════════════════════════
# KI-Schnittstellen — vorbereitet, nicht integriert
# ══════════════════════════════════════════════════════════════════════

def test_transcription_uses_the_injected_backend(tmp_path):
    seen = {}

    class _Backend:
        async def transcribe(self, audio_path, target_path, language=None, job=None):
            seen.update(audio=audio_path, target=target_path, language=language)
            Path(target_path).write_text("Text", encoding="utf-8")
            return Path(target_path)

    workspace = create_workspace(tmp_path, "T")
    workspace.audio.write_bytes(b"wav")
    processor = AudioProcessor(_RecordingFFmpeg(), transcription=_Backend())

    result = asyncio.run(processor.transcribe(workspace, language="de"))

    assert result.name == "transcript.txt"
    assert seen["audio"] == workspace.audio
    assert seen["language"] == "de"


def test_transcription_without_audio_says_what_to_do_first(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    processor = AudioProcessor(_RecordingFFmpeg())

    with pytest.raises(ProcessingError, match="Audio extrahieren"):
        asyncio.run(processor.transcribe(workspace))


def test_the_default_transcription_backend_is_the_existing_whisper_service():
    """Whisper liegt bereits im Repository - es wird nicht neu gebaut."""
    from src.services.media_ai import WhisperTranscription

    source = inspect.getsource(WhisperTranscription.transcribe)
    assert "from src.services.subtitle import SubtitleGenerator" in source
    assert 'format="txt"' in source


def test_the_whisper_import_stays_out_of_module_scope():
    """faster-whisper zieht Torch nach; das darf kein Startaufwand sein."""
    module = Path(inspect.getfile(AudioProcessor)).read_text(encoding="utf-8")
    header = module.split("class WhisperTranscription")[0]

    assert "from src.services.subtitle import" not in header


def test_voice_cloning_is_prepared_but_not_configured(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    processor = AudioProcessor(_RecordingFFmpeg())

    with pytest.raises(BackendNotConfigured) as caught:
        asyncio.run(processor.synthesize(workspace, "Hallo"))

    assert "kein Modell hinterlegt" in str(caught.value)
    assert "AudioProcessor(voice=" in str(caught.value), \
        "Die Meldung muss sagen, wo ein Backend angeschlossen wird"


def test_a_voice_backend_receives_the_16k_wav_as_reference(tmp_path):
    seen = {}

    class _Voice:
        async def synthesize(self, text, target_path, reference_audio=None, job=None):
            seen.update(text=text, reference=reference_audio)
            Path(target_path).write_bytes(b"wav")
            return Path(target_path)

    workspace = create_workspace(tmp_path, "T")
    workspace.audio.write_bytes(b"stimmprobe")
    processor = AudioProcessor(_RecordingFFmpeg(), voice=_Voice())

    asyncio.run(processor.synthesize(workspace, "Hallo Welt"))

    assert seen["reference"] == workspace.audio


def test_vision_is_prepared_but_not_configured(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    workspace.frames.mkdir()
    (workspace.frames / "frame_000001.png").write_bytes(b"p")
    processor = VideoProcessor(_RecordingFFmpeg())

    with pytest.raises(BackendNotConfigured, match="VideoProcessor\\(vision="):
        asyncio.run(processor.analyse_frames(workspace))


def test_analysing_without_frames_says_what_to_do_first(tmp_path):
    workspace = create_workspace(tmp_path, "T")

    with pytest.raises(ProcessingError, match="zuerst extrahieren"):
        asyncio.run(VideoProcessor(_RecordingFFmpeg()).analyse_frames(workspace))


def test_frame_extraction_needs_a_source(tmp_path):
    workspace = create_workspace(tmp_path, "T")

    with pytest.raises(ProcessingError, match="zuerst importieren"):
        asyncio.run(VideoProcessor(_RecordingFFmpeg()).extract_frames(workspace))


def test_frame_extraction_rejects_a_nonsense_rate(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    (workspace.root / "original.mp4").write_bytes(b"x")

    with pytest.raises(ProcessingError, match="groesser als 0"):
        asyncio.run(VideoProcessor(_RecordingFFmpeg()).extract_frames(
            workspace, fps=0))


# ══════════════════════════════════════════════════════════════════════
# Der Import-Ablauf
# ══════════════════════════════════════════════════════════════════════

def _run_import(tmp_path, downloader=None, ffmpeg=None, **kwargs):
    job = _import_job()
    workspace = asyncio.run(run_media_ai_import(
        job, downloader or _FakeMediaDownloader(),
        MediaSplitter(ffmpeg or _RecordingFFmpeg()),
        tmp_path, **kwargs))
    return job, workspace


def test_the_import_produces_the_promised_layout(tmp_path):
    job, workspace = _run_import(tmp_path)

    assert workspace.root == tmp_path / "Konzert"
    assert workspace.original().name == "original.webm"
    assert workspace.video().name == "video.webm"
    assert workspace.audio.is_file()
    assert workspace.metadata.is_file()


def test_every_stage_is_recorded_in_order(tmp_path):
    job, _ = _run_import(tmp_path)

    steps = job.params["steps"]
    positions = [steps.index(stage) for stage in MEDIA_AI_STAGES]
    assert positions == sorted(positions), steps


def test_the_metadata_records_the_source(tmp_path):
    _, workspace = _run_import(tmp_path)

    stored = json.loads(workspace.metadata.read_text(encoding="utf-8"))
    assert stored["url"] == "https://example.invalid/v"
    assert stored["source_id"] == "vid123"
    assert stored["uploader"] == "Kanal"
    assert stored["duration_seconds"] == 42.0
    assert stored["imported_at"]


def test_the_job_reports_the_workspace_and_the_outputs(tmp_path):
    job, workspace = _run_import(tmp_path)

    assert job.params["workspace"] == str(workspace.root)
    assert job.output_path == workspace.original()
    assert str(workspace.audio) in job.params["outputs"]


def test_the_display_name_becomes_the_real_title(tmp_path):
    job, _ = _run_import(tmp_path)

    assert job.params["display_name"] == "Media AI: Konzert"


def test_an_audio_only_source_still_counts_as_a_successful_import(tmp_path):
    """Eine fehlende Videospur ist eine Eigenschaft der Quelle, kein Fehler."""
    job, workspace = _run_import(
        tmp_path, downloader=_FakeMediaDownloader(suffix=".mp3"))

    assert workspace.original().name == "original.mp3"
    assert workspace.audio.is_file()
    state = workspace.load_job()
    assert any("Videospur" in e for e in state.errors)
    assert "Fertig" in state.stages


def test_a_failing_split_does_not_lose_the_download(tmp_path):
    job, workspace = _run_import(tmp_path, ffmpeg=_FailingFFmpeg())

    assert workspace.original().is_file(), "Das Geladene muss erhalten bleiben"
    state = workspace.load_job()
    assert len(state.errors) == 2
    assert "Fertig" in state.stages


def test_the_steps_can_be_switched_off(tmp_path):
    _, workspace = _run_import(tmp_path, want_video=False, want_audio=False)

    assert workspace.video() is None
    assert not workspace.audio.exists()
    assert workspace.original().is_file()


def test_a_failing_probe_stops_before_a_folder_is_created(tmp_path):
    downloader = _FakeMediaDownloader(fail=MediaDownloadError("Video ist privat."))

    with pytest.raises(MediaDownloadError, match="privat"):
        _run_import(tmp_path, downloader=downloader)

    assert list(tmp_path.iterdir()) == [], "Es darf keine leere Mappe zurueckbleiben"


def test_two_imports_of_the_same_title_keep_both(tmp_path):
    _, first = _run_import(tmp_path)
    (first.root / "original.webm").write_bytes(b"erstes")

    _, second = _run_import(tmp_path)

    assert first.root != second.root
    assert (first.root / "original.webm").read_bytes() == b"erstes"


def test_progress_never_leaves_its_bounds(tmp_path):
    job, _ = _run_import(tmp_path)

    assert 0 <= job.progress <= 100
    assert job.progress == 100
