"""P1 #2 und das Abnahmeszenario: kein Schritt bleibt unsichtbar.

Gefordert ist die vollstaendige Kette von der erkannten Quelle bis zur
fertigen Datei, und zwar an drei Orten gleichzeitig: in der Jobzeile, in der
dauerhaften Jobhistorie und im Logfile. Zusaetzlich das Szenario aus dem
Auftrag - Disc rippen, Download, Verarbeitung, Datei oeffnen - inklusive der
Zusicherung, dass eine zweite Disc die erste nicht ueberschreibt.

Die Medienwerkzeuge werden hier bewusst durch Doubles ersetzt. Die echten
Vendor-Binaries sind auf diesem Host von Smart App Control blockiert; die
Ablauf- und Pfadlogik ist davon unabhaengig und genau das, was hier geprueft
werden soll.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.media import Job, JobType
from src.services.download_workflow import (
    STAGE_CONVERTING,
    STAGE_DONE,
    STAGE_DOWNLOAD_DONE,
    STAGE_DOWNLOAD_STARTED,
    STAGE_FILE_READY,
    STAGE_PROCESSING_STARTED,
    STAGE_SOURCE,
    WORKFLOW_STAGES,
    run_download_workflow,
)
from src.services.job_history import JobHistory, job_record

UI = (Path(__file__).parents[1] / "src" / "ui" / "app.html").read_text(encoding="utf-8")


class _FakeDownloader:
    """Legt eine Quelldatei ab, wie yt-dlp es tun wuerde."""

    def __init__(self, output_dir: Path, name: str = "Konzert.webm"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.name = name

    async def download(self, **kwargs):
        target = self.output_dir / self.name
        target.write_bytes(b"quellvideo")
        return target


class _FakeConverter:
    """Schreibt eine Zieldatei an genau den Pfad, den er bekommt."""

    VIDEO_EXTENSIONS = {".webm", ".mp4", ".mkv"}

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seen: list[Path] = []

    async def convert_file(self, item, preset=None, output_path=None,
                           overwrite=False, job=None):
        target = Path(output_path)
        self.seen.append(target)
        target.write_bytes(b"fertiges video")
        return target


def _download_job(job_id="job-1") -> Job:
    job = Job(job_type=JobType.DOWNLOAD,
              params={"url": "https://example.invalid/v", "format": "best",
                      "audio_only": False, "audio_format": "mp3",
                      "subtitles": False, "display_name": "Download: Konzert"})
    job.id = job_id
    return job


def _run(job, downloader, converter, history=None):
    asyncio.run(run_download_workflow(job, downloader, converter, history))
    return job


# ── Die Kette ─────────────────────────────────────────────────────────

def test_every_required_stage_is_recorded(tmp_path):
    job = _run(_download_job(),
               _FakeDownloader(tmp_path / "dl"),
               _FakeConverter(tmp_path / "out"))

    steps = job.params["steps"]
    for stage in WORKFLOW_STAGES:
        assert any(step.startswith(stage) for step in steps), \
            f"Schritt fehlt in der Anzeige: {stage}"


def test_the_stages_keep_their_order(tmp_path):
    job = _run(_download_job(),
               _FakeDownloader(tmp_path / "dl"),
               _FakeConverter(tmp_path / "out"))

    positions = [
        next(i for i, step in enumerate(job.params["steps"]) if step.startswith(stage))
        for stage in WORKFLOW_STAGES
    ]

    assert positions == sorted(positions), f"Reihenfolge stimmt nicht: {job.params['steps']}"


def test_the_stage_names_are_the_ones_that_were_asked_for():
    assert WORKFLOW_STAGES == (
        "Quelle erkannt",
        "Download gestartet",
        "Download abgeschlossen",
        "Verarbeitung gestartet",
        "Konvertierung läuft",
        "Datei erstellt",
        "Fertig",
    )


def test_the_conversion_stage_names_the_file_being_written(tmp_path):
    job = _run(_download_job(),
               _FakeDownloader(tmp_path / "dl"),
               _FakeConverter(tmp_path / "out"))

    converting = [s for s in job.params["steps"] if s.startswith(STAGE_CONVERTING)]

    assert converting, "Der Konvertierungsschritt fehlt"
    assert ".mp4" in converting[0], "Der Nutzer sieht nicht, welche Datei entsteht"


def test_the_conversion_stage_does_not_reset_the_progress_bar(tmp_path):
    """progress=None heisst 'nur beschriften'."""
    job = _download_job()
    job.update_progress(72.0, "irgendwas")
    seen: list[float] = []
    original = job.update_progress

    def spy(progress, text=""):
        seen.append(progress)
        original(progress, text)

    job.update_progress = spy
    _run(job, _FakeDownloader(tmp_path / "dl"), _FakeConverter(tmp_path / "out"))

    assert all(value is not None for value in seen)


def test_an_audio_only_download_still_reports_a_finished_file(tmp_path):
    job = _download_job()
    job.params["audio_only"] = True

    _run(job, _FakeDownloader(tmp_path / "dl", "Lied.mp3"),
         _FakeConverter(tmp_path / "out"))

    assert job.params["steps"][-1] == STAGE_DONE
    assert STAGE_FILE_READY in job.params["steps"]
    assert job.output_path is not None


def test_the_stages_reach_the_durable_history(tmp_path):
    history = JobHistory(tmp_path / "jobs.sqlite3")

    job = _run(_download_job(), _FakeDownloader(tmp_path / "dl"),
               _FakeConverter(tmp_path / "out"), history)
    # Den Abschluss setzt in Produktion die Pipeline in ihrem finally-Zweig,
    # nicht der Workflow. Ohne diesen Schritt liest die Historie den Job zu
    # Recht als unterbrochen - das ist die Absicht, kein Fehler.
    job.mark_done()
    history.save(job)

    row = next(r for r in history.recent() if r["id"] == job.id)
    assert row["status"] == STAGE_DONE
    assert STAGE_DOWNLOAD_DONE in row["steps"]
    assert row["output"] == str(job.output_path)


def test_an_unfinished_job_is_reported_as_interrupted(tmp_path):
    """Die Kehrseite: was die Pipeline nie abgeschlossen hat, bleibt sichtbar."""
    history = JobHistory(tmp_path / "jobs.sqlite3")

    job = _run(_download_job(), _FakeDownloader(tmp_path / "dl"),
               _FakeConverter(tmp_path / "out"), history)

    row = next(r for r in history.recent() if r["id"] == job.id)
    assert row["state"] == "interrupted"
    assert row["output"] == str(job.output_path), \
        "Auch ein unterbrochener Auftrag muss sagen, was schon entstanden ist"


def test_the_stages_reach_the_log(tmp_path, capsys):
    """Ein Supportfall muss ohne laufende Oberflaeche lesbar sein."""
    import structlog

    # structlog haelt seine Schreibsperre in einer WeakKeyDictionary; ein
    # SimpleNamespace laesst sich nicht referenzieren. Ein echter Strom schon.
    import io

    sink = io.StringIO()
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sink))
    try:
        _run(_download_job(), _FakeDownloader(tmp_path / "dl"),
             _FakeConverter(tmp_path / "out"))
    finally:
        structlog.reset_defaults()

    joined = sink.getvalue()
    assert "Download-Workflow" in joined
    assert STAGE_DOWNLOAD_STARTED in joined
    assert STAGE_PROCESSING_STARTED in joined


def test_the_ui_renders_the_step_chain():
    assert "j.steps?.length" in UI
    assert "j.steps.map(escHtml).join(' → ')" in UI


# ── Ausgabe: eindeutig, kein stilles Ueberschreiben ───────────────────

def test_a_second_run_never_replaces_the_first_video(tmp_path):
    download = tmp_path / "dl"
    out = tmp_path / "out"

    first = _run(_download_job("job-1"), _FakeDownloader(download), _FakeConverter(out))
    first_bytes = Path(first.output_path).read_bytes()
    Path(first.output_path).write_bytes(b"nicht anfassen")

    second = _run(_download_job("job-2"), _FakeDownloader(download), _FakeConverter(out))

    assert first.output_path != second.output_path
    assert Path(first.output_path).read_bytes() == b"nicht anfassen"
    assert Path(second.output_path).is_file()
    assert first_bytes  # der erste Lauf hat wirklich geschrieben


def test_the_same_job_id_twice_still_yields_two_files(tmp_path):
    """Der Zaehler greift auch, wenn die Job-Id kein Unterscheidungsmerkmal ist."""
    download = tmp_path / "dl"
    out = tmp_path / "out"

    first = _run(_download_job("gleich"), _FakeDownloader(download), _FakeConverter(out))
    second = _run(_download_job("gleich"), _FakeDownloader(download), _FakeConverter(out))

    assert first.output_path != second.output_path
    assert Path(first.output_path).is_file()
    assert Path(second.output_path).is_file()


def test_a_failed_conversion_leaves_no_empty_reservation(tmp_path):
    class _Failing(_FakeConverter):
        async def convert_file(self, *a, **k):
            raise RuntimeError("FFmpeg abgebrochen")

    out = tmp_path / "out"
    with pytest.raises(RuntimeError):
        _run(_download_job(), _FakeDownloader(tmp_path / "dl"), _Failing(out))

    assert list(out.glob("*.mp4")) == []


# ── Das Abnahmeszenario ───────────────────────────────────────────────

def test_scenario_disc_download_processing_open(tmp_path, monkeypatch):
    """Disc rippen -> Download -> Verarbeitung -> Datei oeffnen.

    Geprueft wird die Kette so, wie ein Nutzer sie erlebt: es entstehen
    wirklich Dateien, ihre Pfade stimmen mit dem ueberein, was die
    Oberflaeche anzeigt, ein Log ist vorhanden, und eine zweite Disc laesst
    die erste unangetastet.
    """
    import retrodisc_launcher
    from retrodisc_launcher import RetroDiscBridge
    from src.core.output import claim_unique_target, timestamped

    videos = tmp_path / "Medien" / "Videos"
    videos.mkdir(parents=True)

    # ── Schritt 1+2: zwei Discs rippen, Namen wie rip_disc sie bildet ──
    def rip(device="D:"):
        safe = device.replace(":", "")
        planned = timestamped(videos / f"Disc_{safe}_Rip.mkv")
        claimed = claim_unique_target(planned)
        claimed.write_bytes(b"rip " + device.encode())
        return claimed

    first_disc = rip()
    first_disc.write_bytes(b"disc eins")
    second_disc = rip()

    assert first_disc != second_disc, "Die zweite Disc bekam denselben Namen"
    assert first_disc.read_bytes() == b"disc eins", "Die erste Disc wurde ueberschrieben"

    # ── Schritt 3+4: Download und Verarbeitung ────────────────────────
    history = JobHistory(tmp_path / "jobs.sqlite3")
    job = _run(_download_job("szenario"),
               _FakeDownloader(tmp_path / "Medien" / "Downloads"),
               _FakeConverter(videos), history)

    result = Path(job.output_path)
    assert result.is_file(), "Die fertige Videodatei fehlt"
    assert result.parent == videos, "Die Datei liegt nicht im Ausgabeordner"
    assert result.stat().st_size > 0

    # ── Schritt 5: die Oberflaeche zeigt genau diesen Pfad ────────────
    row = job_record(job)
    assert row["output"] == str(result)
    assert row["status"] == STAGE_DONE

    # ── Schritt 6: Datei und Ordner lassen sich oeffnen ───────────────
    opened: list[str] = []
    monkeypatch.setattr(retrodisc_launcher.os, "startfile", opened.append)
    bridge = object.__new__(RetroDiscBridge)
    bridge.get_queue = lambda: json.dumps([row])
    bridge.settings = SimpleNamespace(directories=SimpleNamespace(output_dir=videos))

    assert json.loads(bridge.open_job_file(job.id)) == {"ok": True}
    assert opened == [str(result)]

    opened.clear()
    assert json.loads(bridge.open_output_folder())["ok"] is True
    assert opened == [str(videos)]

    # ── Schritt 7: das Protokoll ist da ───────────────────────────────
    stored = next(r for r in history.recent() if r["id"] == job.id)
    assert stored["steps"], "Kein Verlauf protokolliert"
    assert stored["output"] == str(result)
