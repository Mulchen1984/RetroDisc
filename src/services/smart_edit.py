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
