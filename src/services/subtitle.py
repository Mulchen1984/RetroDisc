"""RetroDisc Subtitle — Automatische Untertitel-Generierung mit OpenAI Whisper."""

from __future__ import annotations

import asyncio
import structlog
from pathlib import Path
from typing import Optional

from src.models.media import Job

log = structlog.get_logger()


class SubtitleError(Exception):
    pass


class SubtitleGenerator:
    """
    Automatische Untertitel-Generierung via OpenAI Whisper.

    Unterstützt 57+ Sprachen, automatische Spracherkennung,
    und verschiedene Output-Formate (SRT, VTT, ASS, TSV, JSON).

    Beispiel:
        gen = SubtitleGenerator(model="base")
        srt_path = await gen.generate(
            input_path="video.mp4",
            output_path="video.srt",
            language="de",
        )
    """

    MODELS = ["tiny", "base", "small", "medium", "large", "large-v3"]

    def __init__(self, model: str = "base", device: Optional[str] = None):
        """
        Args:
            model: Whisper-Modell ("tiny", "base", "small", "medium", "large")
                   Größer = genauer aber langsamer
            device: "cuda", "cpu", oder None (auto)
        """
        self.model_name = model
        self.device = device
        self._model = None
        self._backend = None

    async def _load_model(self):
        """Lädt das Whisper-Modell (lazy loading)."""
        if self._model is not None:
            return

        def _load():
            try:
                import whisper
                device = self.device or ("cuda" if self._cuda_available() else "cpu")
                log.info("OpenAI-Whisper-Modell wird geladen",
                         model=self.model_name, device=device)
                self._backend = "openai"
                return whisper.load_model(self.model_name, device=device)
            except ImportError:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise SubtitleError(
                        "Whisper-Engine fehlt. Installieren: pip install faster-whisper"
                    ) from exc
                device = self.device or "cpu"
                compute_type = "float16" if device == "cuda" else "int8"
                model_name = "large-v3" if self.model_name == "large" else self.model_name
                # Das Base-Modell wird im Windows-Build mitgeliefert, damit die
                # Standard-Transkription vollständig offline funktioniert.
                if model_name == "base":
                    import sys
                    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "vendor" / "whisper-base"
                    if bundled.is_dir():
                        model_name = str(bundled)
                log.info("Faster-Whisper-Modell wird geladen",
                         model=model_name, device=device, compute_type=compute_type)
                self._backend = "faster"
                return WhisperModel(model_name, device=device, compute_type=compute_type)

        self._model = await asyncio.to_thread(_load)
        log.info("Whisper-Modell geladen", model=self.model_name)

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    async def generate(
        self,
        input_path: Path | str,
        output_path: Optional[Path | str] = None,
        language: Optional[str] = None,
        format: str = "srt",
        word_timestamps: bool = False,
        job: Optional[Job] = None,
    ) -> Path:
        """
        Generiert Untertitel aus einer Audio-/Videodatei.

        Args:
            input_path: Quell-Datei (Video oder Audio)
            output_path: Ziel-Pfad für die Untertitel-Datei
            language: Sprache (z.B. "de", "en", None=Auto-Detect)
            format: Output-Format ("srt", "vtt", "ass", "tsv", "json", "txt")
            word_timestamps: Wort-genaue Timestamps
            job: Job für Progress-Updates

        Returns:
            Pfad zur Untertitel-Datei
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise SubtitleError(f"Datei nicht gefunden: {input_path}")

        if output_path is None:
            output_path = input_path.with_suffix(f".{format}")
        output_path = Path(output_path)

        if job:
            job.update_progress(5, "Whisper-Modell wird geladen...")

        await self._load_model()

        if job:
            job.update_progress(15, "Audio wird transkribiert...")

        # Transkription in Thread ausführen (CPU-intensiv)
        def _transcribe():
            if self._backend == "faster":
                segments_iter, info = self._model.transcribe(
                    str(input_path), language=language or None,
                    word_timestamps=word_timestamps, vad_filter=True)
                segments = []
                for i, seg in enumerate(segments_iter):
                    item = {"id": i, "start": float(seg.start),
                            "end": float(seg.end), "text": seg.text}
                    if word_timestamps and seg.words:
                        item["words"] = [
                            {"start": float(w.start), "end": float(w.end),
                             "word": w.word, "probability": float(w.probability)}
                            for w in seg.words]
                    segments.append(item)
                return {"language": info.language, "segments": segments,
                        "text": "".join(s["text"] for s in segments)}

            options = {
                "word_timestamps": word_timestamps,
                "verbose": False,
            }
            if language:
                options["language"] = language
            return self._model.transcribe(str(input_path), **options)

        result = await asyncio.to_thread(_transcribe)

        if job:
            job.update_progress(85, "Untertitel werden formatiert...")

        # Erkannte Sprache loggen
        detected_lang = result.get("language", "unknown")
        log.info("Sprache erkannt", language=detected_lang)

        # In gewünschtes Format konvertieren
        content = self._format_output(result, format)

        # Datei schreiben
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

        if job:
            job.update_progress(98, f"Untertitel erstellt ({detected_lang})")

        segment_count = len(result.get("segments", []))
        log.info("Untertitel generiert",
                 output=str(output_path),
                 language=detected_lang,
                 segments=segment_count,
                 format=format)

        return output_path

    def _format_output(self, result: dict, format: str) -> str:
        """Formatiert Whisper-Output in das gewünschte Format."""
        segments = result.get("segments", [])

        if format == "srt":
            return self._to_srt(segments)
        elif format == "vtt":
            return self._to_vtt(segments)
        elif format == "ass":
            return self._to_ass(segments)
        elif format == "txt":
            return self._to_txt(segments)
        elif format == "tsv":
            return self._to_tsv(segments)
        elif format == "json":
            import json
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            raise SubtitleError(f"Unbekanntes Format: {format}")

    @staticmethod
    def _format_timestamp_srt(seconds: float) -> str:
        """Formatiert Sekunden als SRT-Timestamp (HH:MM:SS,mmm)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _format_timestamp_vtt(seconds: float) -> str:
        """Formatiert Sekunden als VTT-Timestamp (HH:MM:SS.mmm)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    def _to_srt(self, segments: list[dict]) -> str:
        """Konvertiert zu SRT-Format."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = self._format_timestamp_srt(seg["start"])
            end = self._format_timestamp_srt(seg["end"])
            text = seg["text"].strip()
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _to_vtt(self, segments: list[dict]) -> str:
        """Konvertiert zu WebVTT-Format."""
        lines = ["WEBVTT\n"]
        for i, seg in enumerate(segments, 1):
            start = self._format_timestamp_vtt(seg["start"])
            end = self._format_timestamp_vtt(seg["end"])
            text = seg["text"].strip()
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _to_ass(self, segments: list[dict]) -> str:
        """Konvertiert zu ASS/SSA-Format."""
        header = """[Script Info]
Title: RetroDisc Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [header]
        for seg in segments:
            start = self._format_timestamp_ass(seg["start"])
            end = self._format_timestamp_ass(seg["end"])
            text = seg["text"].strip().replace("\n", "\\N")
            lines.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_timestamp_ass(seconds: float) -> str:
        """ASS-Timestamp: H:MM:SS.cc"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    @staticmethod
    def _to_txt(segments: list[dict]) -> str:
        """Nur Text, ohne Timestamps."""
        return "\n".join(seg["text"].strip() for seg in segments)

    @staticmethod
    def _to_tsv(segments: list[dict]) -> str:
        """Tab-separiertes Format."""
        lines = ["start\tend\ttext"]
        for seg in segments:
            lines.append(f"{seg['start']:.3f}\t{seg['end']:.3f}\t{seg['text'].strip()}")
        return "\n".join(lines)

    async def detect_language(self, input_path: Path | str) -> str:
        """Erkennt die Sprache einer Audio-/Videodatei."""
        await self._load_model()

        def _detect():
            import whisper
            audio = whisper.load_audio(str(input_path))
            audio = whisper.pad_or_trim(audio)
            mel = whisper.log_mel_spectrogram(audio).to(self._model.device)
            _, probs = self._model.detect_language(mel)
            return max(probs, key=probs.get)

        lang = await asyncio.to_thread(_detect)
        log.info("Sprache erkannt", language=lang, path=str(input_path))
        return lang
