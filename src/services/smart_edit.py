"""RetroDisc Smart Edit — KI-gestütztes Auto-Editing & Highlight-Generierung.

Analysiert Videos automatisch und erstellt Highlight-Zusammenschnitte:
- Szenenerkennung (PySceneDetect)
- Audio-Analyse für Energie-Peaks (Librosa)
- Gesichtserkennung (MediaPipe/OpenCV)
- Bewegungsanalyse (OpenCV Optical Flow)
- LLM als "Regisseur" für die finale Auswahl (Ollama)
"""

from __future__ import annotations

import asyncio
import structlog
from pathlib import Path
from typing import Optional

from src.models.media import HighlightConfig, Job, SceneScore

log = structlog.get_logger()


class SmartEditError(Exception):
    pass


class SmartEdit:
    """
    KI Auto-Edit Engine — analysiert Videos und erstellt automatische Highlights.

    Workflow:
    1. Szenen erkennen (PySceneDetect)
    2. Audio-Energie pro Szene berechnen (Librosa)
    3. Gesichter & Bewegung pro Szene analysieren (OpenCV/MediaPipe)
    4. Szenen bewerten und ranken
    5. Beste Szenen auswählen und zusammenschneiden (FFmpeg)

    Beispiel:
        editor = SmartEdit(ffmpeg=ffmpeg_instance)
        config = HighlightConfig(target_duration_seconds=300)
        result = await editor.create_highlights(
            input_path="konzert.mp4",
            output_path="konzert_highlights.mp4",
            config=config,
        )
    """

    def __init__(self, ffmpeg=None):
        self.ffmpeg = ffmpeg  # FFmpeg-Instanz für den finalen Schnitt

    async def detect_scenes(self, video_path: Path) -> list[tuple[float, float]]:
        """
        Erkennt Szenenwechsel im Video via PySceneDetect.

        Returns:
            Liste von (start_time, end_time) Tupeln in Sekunden
        """
        from scenedetect import detect, ContentDetector

        log.info("Szenenerkennung gestartet", path=str(video_path))

        # PySceneDetect ist synchron, daher in Thread auslagern
        def _detect():
            scene_list = detect(str(video_path), ContentDetector(threshold=27.0))
            return [
                (scene[0].get_seconds(), scene[1].get_seconds())
                for scene in scene_list
            ]

        scenes = await asyncio.to_thread(_detect)
        log.info("Szenen erkannt", count=len(scenes))
        return scenes

    async def analyze_audio_energy(
        self,
        video_path: Path,
        scenes: list[tuple[float, float]],
    ) -> list[float]:
        """
        Berechnet die Audio-Energie für jede Szene.

        Hohe Energie = laute/energiereiche Passage (Refrain, Applaus, Solo).

        Returns:
            Liste von Energie-Werten (0.0 - 1.0) pro Szene
        """
        import librosa
        import numpy as np

        log.info("Audio-Analyse gestartet")

        def _analyze():
            # Audio laden
            y, sr = librosa.load(str(video_path), sr=22050, mono=True)

            energies = []
            for start, end in scenes:
                start_sample = int(start * sr)
                end_sample = int(end * sr)
                segment = y[start_sample:end_sample]

                if len(segment) == 0:
                    energies.append(0.0)
                    continue

                # RMS-Energie berechnen
                rms = np.sqrt(np.mean(segment ** 2))
                energies.append(float(rms))

            # Normalisieren auf 0-1
            if energies:
                max_e = max(energies) or 1.0
                energies = [e / max_e for e in energies]

            return energies

        energies = await asyncio.to_thread(_analyze)
        log.info("Audio-Analyse abgeschlossen", scenes=len(energies))
        return energies

    async def analyze_motion(
        self,
        video_path: Path,
        scenes: list[tuple[float, float]],
        sample_frames: int = 5,
    ) -> list[float]:
        """
        Analysiert die Bewegungsintensität pro Szene via Optical Flow.

        Returns:
            Liste von Bewegungs-Scores (0.0 - 1.0) pro Szene
        """
        import cv2
        import numpy as np

        log.info("Bewegungsanalyse gestartet")

        def _analyze():
            cap = cv2.VideoCapture(str(video_path))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            motion_scores = []

            for start, end in scenes:
                scene_motion = []
                duration = end - start
                step = max(duration / sample_frames, 1 / fps)

                prev_gray = None
                for t in [start + i * step for i in range(sample_frames)]:
                    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                    ret, frame = cap.read()
                    if not ret:
                        break

                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    gray = cv2.resize(gray, (320, 180))

                    if prev_gray is not None:
                        flow = cv2.calcOpticalFlowFarneback(
                            prev_gray, gray, None,
                            0.5, 3, 15, 3, 5, 1.2, 0
                        )
                        magnitude = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
                        scene_motion.append(float(np.mean(magnitude)))

                    prev_gray = gray

                motion_scores.append(np.mean(scene_motion) if scene_motion else 0.0)

            cap.release()

            # Normalisieren
            if motion_scores:
                max_m = max(motion_scores) or 1.0
                motion_scores = [m / max_m for m in motion_scores]

            return motion_scores

        scores = await asyncio.to_thread(_analyze)
        log.info("Bewegungsanalyse abgeschlossen", scenes=len(scores))
        return scores

    async def detect_faces(
        self,
        video_path: Path,
        scenes: list[tuple[float, float]],
    ) -> list[int]:
        """
        Zählt Gesichter pro Szene via MediaPipe.

        Returns:
            Liste von Gesichter-Counts pro Szene
        """
        import cv2

        log.info("Gesichtserkennung gestartet")

        def _detect():
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            cap = cv2.VideoCapture(str(video_path))
            face_counts = []

            for start, end in scenes:
                mid_time = (start + end) / 2
                cap.set(cv2.CAP_PROP_POS_MSEC, mid_time * 1000)
                ret, frame = cap.read()

                if not ret:
                    face_counts.append(0)
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                face_counts.append(len(faces))

            cap.release()
            return face_counts

        counts = await asyncio.to_thread(_detect)
        log.info("Gesichtserkennung abgeschlossen", scenes=len(counts))
        return counts

    async def score_scenes(
        self,
        scenes: list[tuple[float, float]],
        audio_energies: list[float],
        motion_scores: list[float],
        face_counts: list[int],
        config: HighlightConfig,
    ) -> list[SceneScore]:
        """
        Bewertet jede Szene mit einem kombinierten Score.

        Gewichtung:
        - Audio-Energie: 40% (wichtigster Faktor bei Konzerten)
        - Bewegung: 30%
        - Gesichter: 30%
        """
        scored = []
        max_faces = max(face_counts) if face_counts else 1

        for i, (start, end) in enumerate(scenes):
            audio = audio_energies[i] if i < len(audio_energies) else 0.0
            motion = motion_scores[i] if i < len(motion_scores) else 0.0
            faces = (face_counts[i] / max_faces) if i < len(face_counts) and max_faces > 0 else 0.0

            # Gewichteter Score
            weights = {
                "audio": 0.4 if config.prefer_audio_peaks else 0.2,
                "motion": 0.3 if config.prefer_motion else 0.15,
                "faces": 0.3 if config.prefer_faces else 0.15,
            }
            combined = (
                audio * weights["audio"]
                + motion * weights["motion"]
                + faces * weights["faces"]
            )

            scored.append(SceneScore(
                start_time=start,
                end_time=end,
                audio_energy=audio,
                motion_score=motion,
                face_count=face_counts[i] if i < len(face_counts) else 0,
                combined_score=combined,
            ))

        # Nach Score sortieren (beste zuerst)
        scored.sort(key=lambda s: s.combined_score, reverse=True)
        return scored

    async def select_highlights(
        self,
        scored_scenes: list[SceneScore],
        config: HighlightConfig,
    ) -> list[SceneScore]:
        """Wählt die besten Szenen aus, bis die Zieldauer erreicht ist."""
        selected = []
        total_duration = 0.0

        for scene in scored_scenes:
            if total_duration >= config.target_duration_seconds:
                break

            # Zu kurze oder zu lange Szenen filtern
            if scene.duration < config.min_clip_duration:
                continue
            if scene.duration > config.max_clip_duration:
                # Szene kürzen (Mitte nehmen)
                mid = (scene.start_time + scene.end_time) / 2
                half = config.max_clip_duration / 2
                scene.start_time = mid - half
                scene.end_time = mid + half

            selected.append(scene)
            total_duration += scene.duration

        # Chronologisch sortieren für natürlichen Flow
        selected.sort(key=lambda s: s.start_time)

        log.info("Highlights ausgewählt",
                 clips=len(selected),
                 total_duration=f"{total_duration:.1f}s")
        return selected

    async def create_highlights(
        self,
        input_path: Path | str,
        output_path: Path | str,
        config: Optional[HighlightConfig] = None,
        job: Optional[Job] = None,
    ) -> Path:
        """
        Erstellt ein Highlight-Video aus dem Input.

        Der komplette Workflow:
        1. Szenen erkennen
        2. Audio, Bewegung, Gesichter analysieren
        3. Szenen bewerten und auswählen
        4. Zusammenschneiden

        Args:
            input_path: Quell-Video
            output_path: Ziel-Video
            config: Highlight-Konfiguration
            job: Job für Progress-Updates

        Returns:
            Pfad zum fertigen Highlight-Video
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        config = config or HighlightConfig()

        if job:
            job.update_progress(5, "Szenen werden erkannt...")

        # 1. Szenen erkennen; ohne optionale Analysepakete bleibt ein
        # deterministischer FFmpeg-Fallback voll funktionsfähig.
        try:
            scenes = await self.detect_scenes(input_path)
        except (ImportError, ModuleNotFoundError):
            if self.ffmpeg is None:
                from src.core.ffmpeg import FFmpeg
                self.ffmpeg = FFmpeg()
            media = await self.ffmpeg.probe(input_path)
            duration = media.duration_seconds
            if duration <= 0:
                raise SmartEditError("Videodauer konnte nicht ermittelt werden")
            step = max(config.min_clip_duration, min(config.max_clip_duration, 30.0))
            scenes = [(start, min(start + step, duration))
                      for start in [i * step for i in range(max(1, int((duration + step - 1) // step)))]
                      if start < duration]
            log.info("Szenenerkennungs-Fallback", count=len(scenes))
        if not scenes:
            raise SmartEditError("Keine Szenen erkannt")

        if job:
            job.update_progress(20, f"{len(scenes)} Szenen erkannt, Audio wird analysiert...")

        # 2. Analysieren. Fehlende optionale KI/Computer-Vision-Pakete
        # führen nicht zum Job-Abbruch, sondern zu neutraler Gewichtung.
        try:
            audio_energies = await self.analyze_audio_energy(input_path, scenes)
        except (ImportError, ModuleNotFoundError):
            audio_energies = [1.0 for _ in scenes]
            log.info("Audioanalyse-Fallback aktiv")

        if job:
            job.update_progress(40, "Bewegung wird analysiert...")

        try:
            motion_scores = await self.analyze_motion(input_path, scenes)
        except (ImportError, ModuleNotFoundError):
            motion_scores = [0.5 for _ in scenes]
            log.info("Bewegungsanalyse-Fallback aktiv")

        if job:
            job.update_progress(55, "Gesichter werden erkannt...")

        try:
            face_counts = await self.detect_faces(input_path, scenes)
        except (ImportError, ModuleNotFoundError):
            face_counts = [0 for _ in scenes]
            log.info("Gesichtserkennungs-Fallback aktiv")

        if job:
            job.update_progress(65, "Szenen werden bewertet...")

        # 3. Bewerten & Auswählen
        scored = await self.score_scenes(
            scenes, audio_energies, motion_scores, face_counts, config
        )
        highlights = await self.select_highlights(scored, config)

        if not highlights:
            raise SmartEditError("Keine Highlight-Szenen gefunden")

        if job:
            job.update_progress(75, f"{len(highlights)} Clips werden zusammengeschnitten...")

        # 4. Clips extrahieren und zusammenfügen
        if self.ffmpeg is None:
            from src.core.ffmpeg import FFmpeg
            self.ffmpeg = FFmpeg()

        temp_dir = output_path.parent / f"_temp_highlights_{output_path.stem}"
        temp_dir.mkdir(exist_ok=True)

        try:
            clip_paths = []
            for i, scene in enumerate(highlights):
                clip_path = temp_dir / f"clip_{i:04d}.mp4"
                await self.ffmpeg.trim(
                    input_path=input_path,
                    output_path=clip_path,
                    start_seconds=scene.start_time,
                    end_seconds=scene.end_time,
                )
                clip_paths.append(clip_path)

                if job:
                    clip_progress = 75 + (i / len(highlights)) * 20
                    job.update_progress(clip_progress, f"Clip {i+1}/{len(highlights)}")

            # Zusammenfügen
            await self.ffmpeg.merge(clip_paths, output_path)

            if job:
                job.update_progress(98, "Highlight-Video erstellt!")

        finally:
            # Temp-Dateien aufräumen
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        log.info("Highlights erstellt",
                 input=str(input_path),
                 output=str(output_path),
                 clips=len(highlights))

        return output_path


# ── Smart Edit / "Mach mir ein Short" (Missionen 9–19) ───────────────────────
# Deterministischer, FFmpeg-basierter Kern. Reine Helfer sind ohne FFmpeg
# testbar; der Director-LLM wird nur für die Highlight-Auswahl wiederverwendet.

import asyncio as _asyncio
import json as _json
import re as _re
import tempfile as _tempfile
import uuid as _uuid
from dataclasses import replace as _replace
from pathlib import Path as _Path

from src.models.smart_edit import (
    ASPECTS, CaptionStyle, ReframeSettings, SilenceSettings, SmartEditProject,
    TimeRange, VoiceEnhanceSettings,
)

_VOICE_AF = {
    'off': '',
    'natural': 'highpass=f=80,acompressor=threshold=-18dB:ratio=2:attack=20:release=200,'
               'loudnorm=I=-16:TP=-1.5:LRA=11',
    'clear': 'highpass=f=100,afftdn=nr=10:nf=-25,acompressor=threshold=-20dB:ratio=3:attack=15:release=180,'
             'loudnorm=I=-16:TP=-1.5:LRA=11',
    'strong': 'highpass=f=120,afftdn=nr=18:nf=-25,acompressor=threshold=-22dB:ratio=4:attack=10:release=150,'
              'loudnorm=I=-14:TP=-1.5:LRA=11',
}

# Unambiguous German/English filler words only (Mission 13). No "also/so/like".
_FILLERS = {'äh', 'ähm', 'öhm', 'ähem', 'uh', 'um', 'uhm', 'erm', 'hmm'}

_SOCIAL_PROFILES = {
    'youtube':          {'aspect': '16:9', 'video_codec': 'libx264', 'audio_codec': 'aac',
                         'video_bitrate': '8M', 'audio_bitrate': '192k', 'container': 'mp4'},
    'youtube_shorts':   {'aspect': '9:16', 'video_codec': 'libx264', 'audio_codec': 'aac',
                         'video_bitrate': '8M', 'audio_bitrate': '192k', 'container': 'mp4'},
    'tiktok':           {'aspect': '9:16', 'video_codec': 'libx264', 'audio_codec': 'aac',
                         'video_bitrate': '8M', 'audio_bitrate': '192k', 'container': 'mp4'},
    'instagram_reels':  {'aspect': '9:16', 'video_codec': 'libx264', 'audio_codec': 'aac',
                         'video_bitrate': '8M', 'audio_bitrate': '192k', 'container': 'mp4'},
    'tv_original':      {'aspect': None, 'video_codec': 'libx264', 'audio_codec': 'aac',
                         'video_bitrate': '6M', 'audio_bitrate': '192k', 'container': 'mp4'},
    'archive':          {'aspect': None, 'video_codec': 'ffv1', 'audio_codec': 'pcm_s24le',
                         'video_bitrate': None, 'audio_bitrate': None, 'container': 'mkv'},
}


class SmartEditor:
    """Short-/Smart-Edit orchestrator reusing FFmpeg, the Director LLM and the library."""

    def __init__(self, library, ffmpeg, output_dir, temp_dir):
        self.library, self.ffmpeg = library, ffmpeg
        self.output_dir, self.temp_dir = _Path(output_dir), _Path(temp_dir)
        self.projects_dir = library.db_path.parent / 'smart-edit-projects'

    # ── Capabilities ────────────────────────────────────────────────────
    @staticmethod
    def subject_tracker_capability():
        """Mission 15: architecture only. No CV runtime is installed, so never advanced."""
        return {'level': 'unavailable',
                'note': 'Kein Subject-Tracking-Provider installiert; Reframe nutzt stabilen Center-Crop.'}

    async def capabilities(self):
        text, _ = await self._run(['-hide_banner', '-filters'])
        names = set(_re.findall(r'^\s*[.A-Z|]{2,3}\s+(\w+)\s', text, _re.M))
        encoders = await self.ffmpeg.available_video_encoders()
        return {
            'filters': sorted(names),
            'silence_detection': 'silencedetect' in names,
            'captions': 'subtitles' in names,        # libass burn-in
            'voice_enhance': {'afftdn': 'afftdn' in names, 'loudnorm': 'loudnorm' in names,
                              'acompressor': 'acompressor' in names},
            'reframe': {'level': 'basic', 'subject_tracker': self.subject_tracker_capability()},
            'hardware_encode': sorted(e for e in encoders if 'videotoolbox' in e or 'nvenc' in e or 'qsv' in e),
            'export_profiles': sorted(_SOCIAL_PROFILES),
        }

    async def _run(self, args, job=None, cwd=None):
        from src.utils.subprocesses import create_hidden_subprocess, communicate_with_job
        proc = await create_hidden_subprocess(self.ffmpeg.ffmpeg_path, *args, cwd=cwd,
            stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE)
        out, err = await communicate_with_job(proc, job, max_output_bytes=2 * 1024 * 1024)
        if proc.returncode:
            raise RuntimeError(err.decode('utf-8', errors='replace')[-3000:])
        return out.decode('utf-8', errors='replace'), err.decode('utf-8', errors='replace')

    # ── Pure planning helpers (Missionen 11–17) ─────────────────────────
    @staticmethod
    def plan_silence_segments(duration, silences, settings: SilenceSettings):
        """Keep-segments after trimming only qualifying silences; speech is never clipped."""
        if settings.preset == 'off' or duration <= 0:
            return [TimeRange(start=0.0, end=duration)] if duration > 0 else []
        pad, minimum = settings.keep_padding, settings.min_silence
        cuts = []
        for start, end in silences:
            start, end = max(0.0, start), min(duration, end)
            if end - start < minimum:
                continue
            inner_start, inner_end = start + pad, end - pad
            if inner_end - inner_start > 0.05:
                cuts.append((inner_start, inner_end))
        keep, position = [], 0.0
        for cut_start, cut_end in sorted(cuts):
            if cut_start - position > 0.1:
                keep.append(TimeRange(start=round(position, 3), end=round(cut_start, 3)))
            position = max(position, cut_end)
        if duration - position > 0.1:
            keep.append(TimeRange(start=round(position, 3), end=round(duration, 3)))
        return keep or [TimeRange(start=0.0, end=duration)]

    @staticmethod
    def reframe_filter(aspect):
        """Center-crop to the target aspect, then scale to the canonical size (Mission 14 V1)."""
        tw, th = ASPECTS[aspect]
        crop = (f"crop=w='trunc(min(iw\\,ih*{tw}/{th})/2)*2':"
                f"h='trunc(min(ih\\,iw*{th}/{tw})/2)*2'")
        return f"{crop},scale={tw}:{th}:flags=lanczos,setsar=1", (tw, th)

    @staticmethod
    def voice_enhance_af(settings: VoiceEnhanceSettings):
        return _VOICE_AF[settings.preset]

    @staticmethod
    def strip_fillers(caption_segments):
        """Mission 13: drop segments that are ONLY an unambiguous filler word."""
        kept = []
        for start, end, text in caption_segments:
            words = _re.findall(r"[\wäöüÄÖÜß']+", text.lower())
            if words and all(w in _FILLERS for w in words):
                continue
            kept.append((start, end, text))
        return kept

    @staticmethod
    def retime_segments(caption_segments, keep_segments):
        """Map source-time captions onto the concatenated cut timeline; drop what was cut."""
        keeps = [(k.start, k.end) for k in keep_segments]
        offsets, running = [], 0.0
        for start, end in keeps:
            offsets.append(running)
            running += end - start
        out = []
        for seg_start, seg_end, text in caption_segments:
            for (k_start, k_end), base in zip(keeps, offsets):
                lo, hi = max(seg_start, k_start), min(seg_end, k_end)
                if hi - lo > 0.05:
                    out.append((round(base + (lo - k_start), 3), round(base + (hi - k_start), 3), text))
        return out

    @staticmethod
    def highlight_fallback(caption_segments, target, duration):
        """Deterministic highlight: contiguous span around the middle, clamped to media."""
        target = min(target, duration)
        if not caption_segments:
            return [TimeRange(start=0.0, end=round(target, 3))]
        mid = duration / 2
        start = max(0.0, min(mid - target / 2, duration - target))
        return [TimeRange(start=round(start, 3), end=round(start + target, 3))]

    @staticmethod
    def validate_ranges(ranges, duration):
        """Clamp/reject LLM ranges so nothing points outside the real media duration."""
        clean = []
        for start, end in ranges:
            start, end = max(0.0, float(start)), min(float(duration), float(end))
            if end - start > 0.05:
                clean.append(TimeRange(start=round(start, 3), end=round(end, 3)))
        return clean

    @staticmethod
    def build_ass(caption_segments, style: CaptionStyle, size):
        """Render a libass ASS document. Segment-level captions; no faked word timing."""
        width, height = size
        align = {'bottom': 2, 'center': 5, 'lower_third': 2}[style.position]
        margin_v = int(style.safe_margin * height)
        if style.position == 'lower_third':
            margin_v = int(height * 0.25)
        border_style = 3 if style.background else 1
        header = [
            '[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {width}', f'PlayResY: {height}',
            'WrapStyle: 2', '', '[V4+ Styles]',
            'Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, '
            'BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV',
            f'Style: Default,Arial,{style.font_size},&H00FFFFFF,&H00000000,&H96000000,'
            f'{1 if style.style == "modern" else 0},{border_style},{style.outline},0,{align},'
            f'{int(width * 0.06)},{int(width * 0.06)},{margin_v}',
            '', '[Events]',
            'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
        ]

        def stamp(t):
            hours = int(t // 3600); minutes = int((t % 3600) // 60)
            seconds = t % 60
            return f'{hours}:{minutes:02d}:{seconds:05.2f}'

        events = []
        for start, end, text in caption_segments:
            text = text.strip()
            if not text:
                continue
            words = text.split()
            chunks = [words[i:i + style.max_words] for i in range(0, len(words), style.max_words)] or [[]]
            span = max(end - start, 0.2) / len(chunks)
            for index, chunk in enumerate(chunks):
                phrase = ' '.join(chunk)
                if style.capitalization == 'upper':
                    phrase = phrase.upper()
                phrase = phrase.replace('\\', '').replace('{', '(').replace('}', ')').replace('\n', ' ')
                c_start, c_end = start + index * span, start + (index + 1) * span
                events.append(f'Dialogue: 0,{stamp(c_start)},{stamp(c_end)},Default,,0,0,0,,{phrase}')
        return '\n'.join(header + events) + '\n'

    @staticmethod
    def export_preset(name, size):
        """Build a ConversionPreset from a social profile; size overrides for reframed shorts."""
        from src.config.presets import get_preset
        profile = _SOCIAL_PROFILES[name]
        base = get_preset('mp4_h264_1080p')
        resolution = f'{size[0]}:{size[1]}' if size else None
        return _replace(base, name=f'social_{name}', display_name=f'Social: {name}',
            container=profile['container'], video_codec=profile['video_codec'],
            audio_codec=profile['audio_codec'], video_bitrate=profile['video_bitrate'],
            audio_bitrate=profile['audio_bitrate'], resolution=resolution, fps=None,
            extra_args=['-preset', 'medium', '-crf', '20'] if profile['video_codec'] == 'libx264' else [])

    # ── Persistence (Mission 22) ────────────────────────────────────────
    def save(self, project: SmartEditProject):
        project = SmartEditProject.model_validate(project.model_dump())
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        target = self.projects_dir / (project.id + '.json')
        with _tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.projects_dir, delete=False) as handle:
            temp = _Path(handle.name); handle.write(project.model_dump_json(indent=2))
        try:
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
        return target

    def load(self, project_id):
        if not _re.fullmatch('[a-f0-9]{32}', project_id):
            raise ValueError('Ungültige Projekt-ID.')
        return SmartEditProject.model_validate_json(
            (self.projects_dir / (project_id + '.json')).read_text(encoding='utf-8'))

    # ── Highlight selection (Missionen 10/11) ───────────────────────────
    def _transcript_segments(self, asset):
        transcript = asset.transcript or {}
        segments = transcript.get('segments') or []
        result = []
        for seg in segments:
            try:
                start, end = float(seg['start']), float(seg['end'])
            except (KeyError, TypeError, ValueError):
                continue
            if end > start:
                result.append((start, end, str(seg.get('text', '')).strip()))
        return result

    async def select_highlights(self, project: SmartEditProject, director=None, wish='', model=''):
        """Reuse the Director LLM if available; otherwise a deterministic, validated fallback."""
        asset = project.source_assets[0]
        segments = self._transcript_segments(asset)
        if project.planner == 'ollama' and director is not None and segments:
            try:
                ranges = await director.select_time_ranges(asset, segments, project.target_duration, wish, model)
                validated = self.validate_ranges(ranges, asset.duration)
                if validated:
                    return validated
            except Exception:
                pass  # deterministic fallback below; LLM offline/invalid is not fatal
        return self.highlight_fallback(segments, project.target_duration, asset.duration)

    # ── Render (Mission 10) ─────────────────────────────────────────────
    @staticmethod
    def _select_expr(segments):
        return '+'.join(f'between(t,{r.start},{r.end})' for r in segments)

    async def render_short(self, project: SmartEditProject, director=None, wish='', encoder='auto', job=None):
        project = SmartEditProject.model_validate(project.model_dump())
        asset = project.source_assets[0]
        source = _Path(asset.path)
        if not source.is_file():
            raise FileNotFoundError(f'Quelle fehlt: {source}')
        actual = await self.library.asset(source)
        duration = actual.duration
        if duration <= 0:
            raise ValueError('Quelle ohne gültige Dauer.')

        # 1. Which parts to keep: explicit cuts > highlights > LLM/fallback.
        keep = list(project.cuts) or list(project.highlight_selection)
        if not keep:
            keep = await self.select_highlights(project, director=director, wish=wish)
        keep = self.validate_ranges([(r.start, r.end) for r in keep], duration)
        if not keep:
            keep = [TimeRange(start=0.0, end=min(project.target_duration, duration))]

        # 2. Trim qualifying silences inside the kept span (single detection pass).
        if project.silence.preset != 'off':
            _, err = await self._run(['-hide_banner', '-nostdin', '-i', str(source), '-map', '0:a?',
                '-af', f'silencedetect=n={project.silence.threshold_db}dB:d={project.silence.min_silence}',
                '-f', 'null', '-'], job)
            starts = [float(x) for x in _re.findall(r'silence_start:\s*([\d.]+)', err)]
            ends = [float(x) for x in _re.findall(r'silence_end:\s*([\d.]+)', err)]
            silences = list(zip(starts, ends))
            trimmed = []
            for seg in keep:
                local = [(max(s, seg.start), min(e, seg.end)) for s, e in silences]
                for piece in self.plan_silence_segments(seg.end, local, project.silence):
                    lo, hi = max(piece.start, seg.start), min(piece.end, seg.end)
                    if hi - lo > 0.1:
                        trimmed.append(TimeRange(start=lo, end=hi))
            keep = trimmed or keep

        reframe_vf, size = self.reframe_filter(project.aspect_ratio)
        has_audio = bool(actual.audio_codec) and project.audio_mode != 'mute'
        af = self.voice_enhance_af(project.voice_enhance)

        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output = self.output_dir / f'Short_{project.id[:8]}_{_uuid.uuid4().hex[:8]}.mp4'
        if output.resolve() == source.resolve():
            raise ValueError('Original darf nicht überschrieben werden.')
        if output.exists():
            raise FileExistsError('Ausgabename existiert bereits.')

        select_expr = self._select_expr(keep)
        try:
            with _tempfile.TemporaryDirectory(prefix='short-', dir=self.temp_dir) as work:
                work = _Path(work)
                stage = work / 'cut.mp4'
                video_chain = f"[0:v]select='{select_expr}',setpts=N/FRAME_RATE/TB,{reframe_vf}[v]"
                maps = ['-map', '[v]']
                filters = [video_chain]
                if has_audio:
                    audio_chain = f"[0:a]aselect='{select_expr}',asetpts=N/SR/TB"
                    if af:
                        audio_chain += ',' + af
                    audio_chain += '[a]'
                    filters.append(audio_chain)
                    maps += ['-map', '[a]']
                args = ['-hide_banner', '-nostdin', '-i', str(source), '-filter_complex', ';'.join(filters),
                        *maps, '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p']
                if has_audio:
                    args += ['-c:a', 'aac', '-b:a', '192k']
                args += [str(stage)]
                await self._run(args, job)

                final = stage
                captions_burned = False
                if project.captions.style != 'off':
                    segments = self.retime_segments(self._transcript_segments(asset), keep)
                    if project.remove_fillers:
                        segments = self.strip_fillers(segments)
                    caps = await self.capabilities()
                    if segments and caps['captions']:
                        ass = work / 'captions.ass'
                        ass.write_text(self.build_ass(segments, project.captions, size), encoding='utf-8')
                        final = work / 'captioned.mp4'
                        escaped = str(ass).replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'")
                        cap_args = ['-hide_banner', '-nostdin', '-i', str(stage), '-vf', f"subtitles='{escaped}'",
                                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p']
                        if has_audio:
                            cap_args += ['-c:a', 'copy']
                        cap_args += [str(final)]
                        await self._run(cap_args, job)
                        captions_burned = True
                    elif not caps['captions']:
                        project.notes.append('Captions übersprungen: FFmpeg ohne subtitles/libass-Filter.')

                # Commit atomically.
                import shutil as _shutil
                _shutil.move(str(final), str(output))

                info = await self.ffmpeg.probe(output)
                video = info.video_streams[0] if info.video_streams else None
                expected = sum(r.duration for r in keep)
                if not video or abs(info.duration_seconds - expected) > max(0.6, expected * 0.1):
                    raise ValueError(f'Short-Dauer unerwartet: {info.duration_seconds:.2f}s statt ~{expected:.2f}s.')
                if bool(info.audio_streams) != has_audio:
                    raise ValueError('Short-Audiospur weicht von der Erwartung ab.')

                await self.library.asset(output)
                project.outputs.append(str(output))
                project.report = {
                    'source': {'filename': source.name, 'duration': duration,
                               'video_codec': actual.video_codec, 'audio_codec': actual.audio_codec},
                    'edit': {'aspect_ratio': project.aspect_ratio, 'resolution': list(size),
                             'kept_segments': [[r.start, r.end] for r in keep],
                             'kept_duration': round(expected, 3), 'silence_preset': project.silence.preset,
                             'reframe_mode': project.reframe.mode, 'captions': project.captions.style,
                             'captions_burned': captions_burned, 'remove_fillers': project.remove_fillers,
                             'voice_enhance': project.voice_enhance.preset, 'audio_mode': project.audio_mode,
                             'export_preset': project.export_preset},
                    'result': {'path': str(output), 'duration': info.duration_seconds,
                               'resolution': [video.width, video.height], 'video_codec': video.codec,
                               'audio_codec': info.audio_streams[0].codec if info.audio_streams else None,
                               'filesize': output.stat().st_size},
                }
                self.save(project)
                if job:
                    job.output_path = output
                    job.params['output_paths'] = [str(output)]
                return project
        except BaseException:
            output.unlink(missing_ok=True)
            raise
