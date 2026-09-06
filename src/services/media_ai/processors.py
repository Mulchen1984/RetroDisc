"""AudioProcessor und VideoProcessor - die KI-Schnittstellen.

Hier wird **kein** Modell integriert. Was hier steht, sind die Nahtstellen,
an denen spaeter eines angeschlossen wird, und zwar so, dass der Anschluss
weder die Oberflaeche noch die Bridge noch die Pipeline anfasst.

Das Muster ist dreiteilig:

1. Ein ``Protocol`` beschreibt, was ein Backend koennen muss.
2. Ein ``_NotConfigured``-Backend ist die Vorgabe. Es wirft einen Satz, den
   ein Nutzer versteht, statt ``AttributeError`` oder stiller Untaetigkeit.
3. Der Prozessor kennt nur das Protokoll. Ein Backend wird im Konstruktor
   uebergeben - keine Importe von Modellbibliotheken auf Modulebene, sonst
   waechst die gepackte EXE um Abhaengigkeiten, die niemand benutzt.

Die Transkription ist der Beleg, dass das Muster traegt: Whisper liegt mit
``src/services/subtitle.SubtitleGenerator`` bereits im Repository und wird
hier als Vorgabe-Backend angeschlossen, nicht neu geschrieben.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

import structlog

from src.core.ffmpeg import FFmpeg, FFmpegError
from src.services.media_ai.workspace import (
    FRAMES_DIRNAME,
    TRANSCRIPT_NAME,
    MediaWorkspace,
)

log = structlog.get_logger()

#: Vorgabe fuer die Frame-Extraktion: ein Bild je Sekunde reicht fuer eine
#: inhaltliche Analyse und laesst eine Stunde Video bei 3600 Bildern.
DEFAULT_FRAME_FPS = 1.0
#: Obergrenze, damit ein langes Video nicht unbemerkt die Platte fuellt.
DEFAULT_MAX_FRAMES = 3_000


class ProcessingError(Exception):
    """Ein Verarbeitungsschritt ist gescheitert - mit Text fuer den Nutzer."""


class BackendNotConfigured(ProcessingError):
    """Fuer diesen Schritt ist noch kein Modell hinterlegt."""


# ══════════════════════════════════════════════════════════════════════
# Audio
# ══════════════════════════════════════════════════════════════════════

@runtime_checkable
class TranscriptionBackend(Protocol):
    """Wandelt eine Audiodatei in Text."""

    async def transcribe(
        self,
        audio_path: Path,
        target_path: Path,
        language: Optional[str] = None,
        job: Optional[Any] = None,
    ) -> Path:
        ...


@runtime_checkable
class VoiceBackend(Protocol):
    """Erzeugt Sprache - Voice-Cloning oder TTS.

    ``reference_audio`` ist die Stimmprobe, die eine Arbeitsmappe als
    ``audio.wav`` bereits im richtigen Format vorhaelt: PCM, 16 kHz, mono.
    """

    async def synthesize(
        self,
        text: str,
        target_path: Path,
        reference_audio: Optional[Path] = None,
        job: Optional[Any] = None,
    ) -> Path:
        ...


class WhisperTranscription:
    """Vorgabe-Backend: der bereits vorhandene ``SubtitleGenerator``.

    Der Import steht absichtlich in der Methode. ``faster-whisper`` zieht beim
    Laden Torch-Abhaengigkeiten nach; ein Nutzer, der nur herunterlaedt und
    schneidet, soll das nicht bezahlen.
    """

    def __init__(self, model: str = "base"):
        self.model = model

    async def transcribe(
        self,
        audio_path: Path,
        target_path: Path,
        language: Optional[str] = None,
        job: Optional[Any] = None,
    ) -> Path:
        from src.services.subtitle import SubtitleGenerator

        generator = SubtitleGenerator(model=self.model)
        return await generator.generate(
            input_path=audio_path,
            output_path=target_path,
            language=language,
            format="txt",
            job=job,
        )


class _NoVoiceBackend:
    """Vorgabe, solange kein Sprachmodell hinterlegt ist."""

    async def synthesize(self, text, target_path, reference_audio=None, job=None):
        raise BackendNotConfigured(
            "Fuer die Sprachausgabe ist noch kein Modell hinterlegt. Die "
            "Schnittstelle ist vorbereitet; ein Backend (etwa XTTS oder "
            "OpenVoice) wird ueber AudioProcessor(voice=...) angeschlossen.")


class AudioProcessor:
    """Audioseite: WAV-Aufbereitung, Transkription, Sprachausgabe."""

    def __init__(
        self,
        ffmpeg: FFmpeg,
        transcription: Optional[TranscriptionBackend] = None,
        voice: Optional[VoiceBackend] = None,
    ):
        self.ffmpeg = ffmpeg
        self.transcription = transcription or WhisperTranscription()
        self.voice = voice or _NoVoiceBackend()

    async def transcribe(
        self,
        workspace: MediaWorkspace,
        language: Optional[str] = None,
        job: Optional[Any] = None,
    ) -> Path:
        """Schreibt ``transcript.txt`` aus ``audio.wav``."""
        audio = workspace.audio
        if not audio.is_file():
            raise ProcessingError(
                "Es gibt noch keine Tonspur. Bitte zuerst 'Audio extrahieren'.")
        target = workspace.root / TRANSCRIPT_NAME
        log.info("Transkription gestartet", audio=str(audio), model=
                 getattr(self.transcription, "model", "?"))
        try:
            return await self.transcription.transcribe(
                audio_path=audio, target_path=target,
                language=language or None, job=job)
        except BackendNotConfigured:
            raise
        except Exception as exc:
            log.error("Transkription fehlgeschlagen", error=str(exc))
            raise ProcessingError(
                "Die Transkription ist fehlgeschlagen. Einzelheiten stehen im "
                "Protokoll (Einstellungen -> Logordner oeffnen)."
            ) from exc

    async def synthesize(
        self,
        workspace: MediaWorkspace,
        text: str,
        target_name: str = "speech.wav",
        job: Optional[Any] = None,
    ) -> Path:
        """Erzeugt Sprache; nutzt ``audio.wav`` als Stimmprobe, wenn vorhanden."""
        reference = workspace.audio if workspace.audio.is_file() else None
        return await self.voice.synthesize(
            text=text, target_path=workspace.root / target_name,
            reference_audio=reference, job=job)


# ══════════════════════════════════════════════════════════════════════
# Video
# ══════════════════════════════════════════════════════════════════════

@runtime_checkable
class VisionBackend(Protocol):
    """Beschreibt oder klassifiziert Einzelbilder."""

    async def analyse(
        self,
        frames: list[Path],
        prompt: str = "",
        job: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        ...


class _NoVisionBackend:
    """Vorgabe, solange kein Bildmodell hinterlegt ist."""

    async def analyse(self, frames, prompt="", job=None):
        raise BackendNotConfigured(
            "Fuer die Bildanalyse ist noch kein Modell hinterlegt. Die "
            "Schnittstelle ist vorbereitet; ein Backend wird ueber "
            "VideoProcessor(vision=...) angeschlossen.")


class VideoProcessor:
    """Videoseite: Frame-Extraktion und - spaeter - Bildanalyse."""

    def __init__(self, ffmpeg: FFmpeg, vision: Optional[VisionBackend] = None):
        self.ffmpeg = ffmpeg
        self.vision = vision or _NoVisionBackend()

    async def extract_frames(
        self,
        workspace: MediaWorkspace,
        fps: float = DEFAULT_FRAME_FPS,
        max_frames: int = DEFAULT_MAX_FRAMES,
        job: Optional[Any] = None,
    ) -> list[Path]:
        """Schreibt Einzelbilder nach ``frames/``.

        Quelle ist die getrennte Videospur, sonst das Original. Ein
        vorhandener Ordner wird geleert: zwei Laeufe mit verschiedener
        Bildrate wuerden sich sonst zu einer unbrauchbaren Mischung addieren.
        """
        source = workspace.video() or workspace.original()
        if source is None:
            raise ProcessingError(
                "Es gibt noch keine Videodatei. Bitte zuerst importieren.")
        if fps <= 0:
            raise ProcessingError("Die Bildrate muss groesser als 0 sein.")

        target_dir = workspace.root / FRAMES_DIRNAME
        _clear_frames(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        from src.utils.subprocesses import (
            communicate_with_job,
            create_hidden_subprocess,
        )

        cmd = [
            self.ffmpeg.ffmpeg_path, "-y", "-i", str(source),
            "-vf", f"fps={fps}",
            "-frames:v", str(int(max_frames)),
            str(target_dir / "frame_%06d.png"),
        ]
        log.info("Frame-Extraktion gestartet", source=str(source), fps=fps)
        proc = None
        try:
            import asyncio

            proc = await create_hidden_subprocess(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await communicate_with_job(proc, job)
            if proc.returncode != 0:
                detail = (stderr or b"")[-600:]
                raise FFmpegError(detail.decode("utf-8", errors="replace"))
        except FFmpegError as exc:
            log.error("Frame-Extraktion fehlgeschlagen", error=str(exc))
            raise ProcessingError(
                "Die Einzelbilder konnten nicht erzeugt werden. Einzelheiten "
                "stehen im Protokoll (Einstellungen -> Logordner oeffnen)."
            ) from exc

        frames = sorted(target_dir.glob("frame_*.png"))
        if not frames:
            raise ProcessingError(
                "Es wurden keine Einzelbilder erzeugt. Enthaelt die Quelle "
                "ueberhaupt Video?")
        log.info("Frames erzeugt", count=len(frames))
        return frames

    async def analyse_frames(
        self,
        workspace: MediaWorkspace,
        prompt: str = "",
        job: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        frames = sorted((workspace.root / FRAMES_DIRNAME).glob("frame_*.png"))
        if not frames:
            raise ProcessingError(
                "Es gibt noch keine Einzelbilder. Bitte zuerst extrahieren.")
        return await self.vision.analyse(frames, prompt=prompt, job=job)


def _clear_frames(target_dir: Path) -> None:
    """Entfernt nur die eigenen Bilder, nie fremde Dateien."""
    if not target_dir.is_dir():
        return
    for path in target_dir.glob("frame_*.png"):
        try:
            path.unlink()
        except OSError as exc:
            log.warning("Altes Einzelbild blieb liegen", path=str(path),
                        error=str(exc))
