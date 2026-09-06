"""Media AI Pipeline - Import über yt-dlp, getrennte Audio- und Videoarbeit.

Die Bausteine sind einzeln verwendbar und kennen einander nur über die
Arbeitsmappe:

- ``MediaDownloader``  yt-dlp-Aufruf, Fortschritt, Fehlerbehandlung
- ``MediaSplitter``    ffmpeg-Steuerung, Audio- und Videoextraktion
- ``AudioProcessor``   WAV-Aufbereitung, Transkription, Sprachausgabe
- ``VideoProcessor``   Frame-Extraktion, später Bildanalyse
- ``MediaJob``         Zustand eines Imports, in ``metadata.json``
- ``MediaWorkspace``   die Mappe je Titel mit festen Dateinamen

Die KI-Schnittstellen sind Protokolle mit einem Vorgabe-Backend. Für die
Transkription ist das der bereits vorhandene ``SubtitleGenerator``; für
Sprachausgabe und Bildanalyse ein Platzhalter, der einen verständlichen Satz
wirft, statt stillschweigend nichts zu tun.
"""

from src.services.media_ai.downloader import MediaDownloader, MediaDownloadError
from src.services.media_ai.processors import (
    AudioProcessor,
    BackendNotConfigured,
    ProcessingError,
    TranscriptionBackend,
    VideoProcessor,
    VisionBackend,
    VoiceBackend,
    WhisperTranscription,
)
from src.services.media_ai.splitter import (
    AUDIO_CHANNELS,
    AUDIO_CODEC,
    AUDIO_SAMPLE_RATE,
    MediaSplitter,
    SplitError,
)
from src.services.media_ai.workflow import MEDIA_AI_STAGES, run_media_ai_import
from src.services.media_ai.workspace import (
    MediaJob,
    MediaWorkspace,
    WorkspaceError,
    create_workspace,
    list_workspaces,
    open_workspace,
    safe_title,
)

__all__ = [
    "AUDIO_CHANNELS",
    "AUDIO_CODEC",
    "AUDIO_SAMPLE_RATE",
    "AudioProcessor",
    "BackendNotConfigured",
    "MEDIA_AI_STAGES",
    "MediaDownloadError",
    "MediaDownloader",
    "MediaJob",
    "MediaSplitter",
    "MediaWorkspace",
    "ProcessingError",
    "SplitError",
    "TranscriptionBackend",
    "VideoProcessor",
    "VisionBackend",
    "VoiceBackend",
    "WhisperTranscription",
    "WorkspaceError",
    "create_workspace",
    "list_workspaces",
    "open_workspace",
    "run_media_ai_import",
    "safe_title",
]
