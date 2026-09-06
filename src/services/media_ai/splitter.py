"""MediaSplitter - trennt Video- und Audiospur eines Imports.

Steuert ``src.core.ffmpeg.FFmpeg.convert``. Dadurch gelten hier unveraendert
das Schreiben ueber eine Staging-Datei, das atomare Veroeffentlichen und der
Fortschritt am Job.

Zwei Zielvorgaben, die den Aufruf bestimmen:

- **Video:** kein Grund, neu zu kodieren. ``-c:v copy`` behaelt die
  Originalqualitaet und ist um Groessenordnungen schneller. Die Tonspur faellt
  mit ``-an`` weg, sie liegt danach separat vor.
- **Audio:** ``pcm_s16le``, 16 kHz, mono. Das ist genau das Format, das
  Whisper intern erwartet und das gaengige Voice-Cloning-Modelle als Eingabe
  nehmen. Ein spaeteres Umrechnen entfaellt damit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import structlog

from src.core.ffmpeg import FFmpeg, FFmpegError
from src.services.media_ai.workspace import AUDIO_NAME, VIDEO_STEM, MediaWorkspace

log = structlog.get_logger()

#: Zielformat der Audiospur. Bewusst Konstanten: die Werte stehen in mehreren
#: Tests und in der Oberflaechenbeschreibung und duerfen nicht auseinanderlaufen.
AUDIO_SAMPLE_RATE = 16_000
AUDIO_CHANNELS = 1
AUDIO_CODEC = "pcm_s16le"

#: Containerlose Tonformate koennen keine Videospur tragen; ein Video daraus
#: zu erwarten ist ein Bedienfehler, kein Programmfehler.
AUDIO_ONLY_SUFFIXES = frozenset({".mp3", ".m4a", ".opus", ".ogg", ".flac",
                                 ".wav", ".aac", ".wma"})


class SplitError(Exception):
    """Eine Spur konnte nicht getrennt werden - mit Text fuer den Nutzer."""


class MediaSplitter:
    """Trennt die Spuren einer geladenen Datei in die Arbeitsmappe."""

    def __init__(self, ffmpeg: FFmpeg):
        self.ffmpeg = ffmpeg

    async def extract_audio(
        self,
        source: Path,
        workspace: MediaWorkspace,
        job: Optional[Any] = None,
    ) -> Path:
        """Schreibt ``audio.wav``: PCM, 16 kHz, mono."""
        source = Path(source)
        if not source.is_file():
            raise SplitError(f"Quelldatei nicht gefunden: {source}")
        target = workspace.root / AUDIO_NAME
        log.info("Audiospur wird extrahiert", source=str(source),
                 target=str(target))
        try:
            return await self.ffmpeg.convert(
                input_path=source,
                output_path=target,
                audio_codec=AUDIO_CODEC,
                sample_rate=AUDIO_SAMPLE_RATE,
                # -vn muss vor die Ausgabe: ohne das versucht ffmpeg, eine
                # Videospur in einen WAV-Container zu schreiben.
                extra_args=["-ac", str(AUDIO_CHANNELS), "-vn"],
                job=job,
                overwrite=True,
            )
        except FFmpegError as exc:
            log.error("Audioextraktion fehlgeschlagen", error=str(exc))
            raise SplitError(
                "Die Tonspur konnte nicht extrahiert werden. Einzelheiten "
                "stehen im Protokoll (Einstellungen -> Logordner oeffnen)."
            ) from exc

    async def extract_video(
        self,
        source: Path,
        workspace: MediaWorkspace,
        job: Optional[Any] = None,
    ) -> Path:
        """Schreibt ``video.<ext>`` ohne Neukodierung."""
        source = Path(source)
        if not source.is_file():
            raise SplitError(f"Quelldatei nicht gefunden: {source}")
        if source.suffix.lower() in AUDIO_ONLY_SUFFIXES:
            raise SplitError(
                f"Diese Quelle enthaelt nur Ton ({source.suffix}); "
                "es gibt keine Videospur zum Trennen.")
        target = workspace.root / f"{VIDEO_STEM}{source.suffix}"
        log.info("Videospur wird extrahiert", source=str(source),
                 target=str(target))
        try:
            return await self.ffmpeg.convert(
                input_path=source,
                output_path=target,
                video_codec="copy",
                extra_args=["-an"],
                job=job,
                overwrite=True,
            )
        except FFmpegError as exc:
            log.error("Videoextraktion fehlgeschlagen", error=str(exc))
            raise SplitError(
                "Die Videospur konnte nicht getrennt werden. Moeglicherweise "
                "enthaelt die Quelle kein Video. Einzelheiten stehen im "
                "Protokoll (Einstellungen -> Logordner oeffnen)."
            ) from exc
