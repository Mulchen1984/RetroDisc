"""Der Import-Ablauf: URL rein, fertige Arbeitsmappe raus.

Die Schritte folgen demselben Muster wie ``download_workflow``: ein Name je
Schritt, gleichzeitig in Jobzeile, Jobhistorie und Logfile. Wer die Kette
aendert, aendert ``MEDIA_AI_STAGES`` mit - der Test prueft dagegen.

Der Ablauf ist bewusst **fehlertolerant an den Raendern**: schlaegt das
Trennen einer Spur fehl, bleibt der Import als Ganzes erfolgreich. Eine
geladene Quelldatei ist ein Ergebnis, das der Nutzer behalten will; ein
fehlendes ``video.mp4`` bei einer reinen Tonquelle ist kein Fehlschlag,
sondern eine Eigenschaft der Quelle. Was schiefging, steht in
``metadata.json`` unter ``errors`` und in der Oberflaeche.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from src.services.media_ai.downloader import MediaDownloader, MediaDownloadError
from src.services.media_ai.splitter import MediaSplitter, SplitError
from src.services.media_ai.workspace import (
    MediaJob,
    MediaWorkspace,
    now_stamp,
)

log = structlog.get_logger()

STAGE_PROBE = "Quelle wird gelesen"
STAGE_WORKSPACE = "Arbeitsmappe angelegt"
STAGE_DOWNLOAD = "Download läuft"
STAGE_DOWNLOAD_DONE = "Download abgeschlossen"
STAGE_VIDEO = "Videospur wird getrennt"
STAGE_AUDIO = "Audiospur wird extrahiert"
STAGE_DONE = "Fertig"

#: Die vollstaendige Kette in ihrer Reihenfolge.
MEDIA_AI_STAGES = (
    STAGE_PROBE,
    STAGE_WORKSPACE,
    STAGE_DOWNLOAD,
    STAGE_DOWNLOAD_DONE,
    STAGE_VIDEO,
    STAGE_AUDIO,
    STAGE_DONE,
)


class _PhaseProgress:
    """Bildet den Fortschritt eines Werkzeugs auf einen Abschnitt ab.

    Gleiche Bauart wie in ``download_workflow``: Abbruch und Prozessbesitz
    bleiben beim echten Job, nur ``update_progress`` wird umgerechnet.
    """

    def __init__(self, job, start: float, span: float):
        object.__setattr__(self, "parent", job)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "span", span)

    def __getattr__(self, key):
        return getattr(self.parent, key)

    def __setattr__(self, key, value):
        setattr(self.parent, key, value)

    def update_progress(self, progress, text=""):
        bounded = min(max(progress, 0), 100)
        stage = self.parent.params.get("stage", "")
        self.parent.update_progress(
            self.start + bounded * self.span / 100,
            f"{stage} | {text}" if text else stage)


async def run_media_ai_import(
    job,
    downloader: MediaDownloader,
    splitter: MediaSplitter,
    base_dir,
    *,
    quality: str = "best",
    want_video: bool = True,
    want_audio: bool = True,
    history=None,
) -> MediaWorkspace:
    """Fuehrt den Import durch und gibt die fertige Arbeitsmappe zurueck."""

    def stage(name: str, progress: Optional[float] = None) -> None:
        job.params["stage"] = name
        job.params.setdefault("steps", []).append(name)
        job.update_progress(job.progress if progress is None else progress, name)
        log.info("Media-AI", job_id=job.id, stage=name)
        if history:
            history.save(job)

    url = job.params["url"]

    # ── 1. Wer ist das? ───────────────────────────────────────────────
    stage(STAGE_PROBE, 0)
    info = await downloader.probe(url)

    # ── 2. Mappe anlegen ──────────────────────────────────────────────
    workspace = downloader.prepare_workspace(base_dir, info["title"])
    state = MediaJob(
        url=url, title=info["title"], source_id=info["id"],
        duration_seconds=info.get("duration"), uploader=info.get("uploader", ""),
        imported_at=now_stamp(),
    )
    state.record(STAGE_PROBE)
    state.record(STAGE_WORKSPACE)
    workspace.save_job(state)
    job.params["workspace"] = str(workspace.root)
    job.params["display_name"] = f"Media AI: {info['title']}"
    stage(STAGE_WORKSPACE, 3)

    # ── 3. Laden ──────────────────────────────────────────────────────
    stage(STAGE_DOWNLOAD, 5)
    original = await downloader.fetch(
        url, workspace, quality=quality, job=_PhaseProgress(job, 5, 55))
    job.output_path = original
    state.record(STAGE_DOWNLOAD)
    workspace.save_job(state)
    stage(STAGE_DOWNLOAD_DONE, 60)
    state.record(STAGE_DOWNLOAD_DONE)

    # ── 4. Spuren trennen ─────────────────────────────────────────────
    # Ab hier ist der Import bereits ein Ergebnis. Ein Fehlschlag beim
    # Trennen wird vermerkt, nicht geworfen.
    if want_video:
        stage(STAGE_VIDEO, 62)
        try:
            await splitter.extract_video(
                original, workspace, job=_PhaseProgress(job, 62, 18))
            state.record(STAGE_VIDEO)
        except SplitError as exc:
            state.errors.append(f"{STAGE_VIDEO}: {exc}")
            log.info("Videospur uebersprungen", reason=str(exc))
        workspace.save_job(state)

    if want_audio:
        stage(STAGE_AUDIO, 80)
        try:
            await splitter.extract_audio(
                original, workspace, job=_PhaseProgress(job, 80, 18))
            state.record(STAGE_AUDIO)
        except SplitError as exc:
            state.errors.append(f"{STAGE_AUDIO}: {exc}")
            log.info("Audiospur uebersprungen", reason=str(exc))
        workspace.save_job(state)

    # ── 5. Abschluss ──────────────────────────────────────────────────
    state.record(STAGE_DONE)
    workspace.save_job(state)
    job.params["outputs"] = sorted(workspace.existing_artefacts().values())
    stage(STAGE_DONE, 100)
    log.info("Media-AI-Import abgeschlossen", workspace=str(workspace.root),
             artefacts=len(state.artefacts))
    return workspace
