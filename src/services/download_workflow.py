"""One visible job from URL to retained source and finished MP4.

Die Schrittnamen stehen hier als Konstanten, weil sie an drei Stellen
zusammenpassen muessen: in der Jobzeile der Oberflaeche, in der dauerhaften
Jobhistorie und im Logfile. Kein Schritt der Kette darf fuer den Nutzer
unsichtbar bleiben - genau daran war die Downloadstrecke vorher schwer zu
beurteilen.
"""
from dataclasses import replace

import structlog

from src.config.presets import get_preset
from src.config.settings import ensure_writable_directory
from src.core.output import claim_unique_target, remove_claimed_targets
from src.services.converter import Converter

log = structlog.get_logger()

STAGE_SOURCE = "Quelle erkannt"
STAGE_DOWNLOAD_STARTED = "Download gestartet"
STAGE_DOWNLOAD_DONE = "Download abgeschlossen"
STAGE_PROCESSING_STARTED = "Verarbeitung gestartet"
STAGE_CONVERTING = "Konvertierung läuft"
STAGE_FILE_READY = "Datei erstellt"
STAGE_DONE = "Fertig"

#: Die vollstaendige Kette in ihrer Reihenfolge - Grundlage der Pruefung.
WORKFLOW_STAGES = (
    STAGE_SOURCE,
    STAGE_DOWNLOAD_STARTED,
    STAGE_DOWNLOAD_DONE,
    STAGE_PROCESSING_STARTED,
    STAGE_CONVERTING,
    STAGE_FILE_READY,
    STAGE_DONE,
)


class _PhaseProgress:
    """Delegate cancellation/process ownership while mapping tool progress."""
    def __init__(self, job, start, span):
        object.__setattr__(self, "parent", job)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "span", span)

    def __getattr__(self, key):
        return getattr(self.parent, key)

    def __setattr__(self, key, value):
        setattr(self.parent, key, value)

    def update_progress(self, progress, text=""):
        self.parent.update_progress(self.start + min(max(progress, 0), 100) * self.span / 100,
                                    f"{self.parent.params['stage']} | {text}")


async def run_download_workflow(job, downloader, converter, history=None):
    def stage(name, progress):
        """Haelt einen Schritt fest: sichtbar, protokolliert, dauerhaft.

        ``progress=None`` heisst "nur beschriften": beim Konvertieren liefert
        FFmpeg den Fortschritt selbst, und ein fester Wert wuerde den Balken
        zurueckspringen lassen.
        """
        job.params["stage"] = name
        job.params.setdefault("steps", []).append(name)
        job.update_progress(job.progress if progress is None else progress, name)
        # Der Schritt gehoert auch ins Logfile: ein Supportfall muss ohne die
        # laufende Oberflaeche nachvollziehbar sein.
        log.info("Download-Workflow", job_id=job.id, stage=name)
        if history:
            history.save(job)

    stage(STAGE_SOURCE, 0)
    stage(STAGE_DOWNLOAD_STARTED, 1)
    source = await downloader.download(
        url=job.params["url"], format=job.params["format"],
        extract_audio=job.params["audio_only"], audio_format=job.params["audio_format"],
        subtitles=job.params["subtitles"], job=_PhaseProgress(job, 1, 43))
    job.output_path = None
    stage(STAGE_DOWNLOAD_DONE, 45)
    if job.params["audio_only"]:
        job.output_path = source
        job.params["outputs"] = [str(source)]
        stage(STAGE_FILE_READY, 99)
        stage(STAGE_DONE, 100)
        return
    # A playlist remains one job; every downloaded video gets a final MP4.
    sources = sorted(p for p in downloader.output_dir.rglob("*")
                     if p.is_file() and p.suffix.lower() in Converter.VIDEO_EXTENSIONS)
    if not sources:
        raise ValueError(f"Kein Video zur Verarbeitung gefunden: {downloader.output_dir}")
    ensure_writable_directory(converter.output_dir)
    job.params["outputs"] = []
    stage(STAGE_PROCESSING_STARTED, 50)
    for index, item in enumerate(sources, 1):
        # Der Zielname traegt bereits Job-Id und laufende Nummer; die
        # Reservierung faengt darueber hinaus alles ab, was zwischen zwei
        # Laeufen im Ausgabeordner entstanden ist.
        target = claim_unique_target(
            converter.output_dir / f"{item.stem[:100]}_{job.id}_{index}.mp4")
        stage(f"{STAGE_CONVERTING} ({index}/{len(sources)}): {target.name}", None)
        preset = replace(get_preset("mp4_h264_1080p"), resolution=None)
        try:
            result = await converter.convert_file(
                item, preset=preset, output_path=target, overwrite=True,
                job=_PhaseProgress(job, 50 + (index - 1) * 48 / len(sources), 48 / len(sources)))
        except BaseException:
            remove_claimed_targets([target])
            raise
        if not result.is_file() or result.stat().st_size == 0:
            raise ValueError(f"Videoausgabe fehlt oder ist leer: {result}")
        job.output_path = result
        job.params["outputs"].append(str(result))
        if history:
            history.save(job)
    stage(STAGE_FILE_READY, 99)
    stage(STAGE_DONE, 100)
