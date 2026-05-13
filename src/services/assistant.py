"""RetroDisc KI-Assistent - Natürliche Spracheingabe via Ollama."""

from __future__ import annotations

import json
import structlog
from typing import Optional

from src.models.media import JobType

log = structlog.get_logger()


class AssistantError(Exception):
    pass


class Assistant:
    """
    Lokaler KI-Assistent powered by Ollama.

    Versteht natürliche Sprache und übersetzt sie in RetroDisc-Aktionen:
    - "Lad den letzten Tatort runter und brenn ihn auf DVD"
    - "Konvertier alle MKVs im Ordner zu MP4"
    - "Mach mir ein 5-Minuten-Highlight aus dem Konzertvideo"
    - "Was ist das beste Format für mein iPhone?"

    Beispiel:
        assistant = Assistant()
        action = await assistant.parse_command(
            "Lad mir den Tatort von gestern und brenn ihn auf DVD"
        )
        # -> {"action": "workflow", "steps": [
        #       {"type": "search", "query": "Tatort", "source": "mediathek"},
        #       {"type": "download", ...},
        #       {"type": "convert", "preset": "dvd_pal"},
        #       {"type": "burn", "disc_type": "dvd"}
        #   ]}
    """

    SYSTEM_PROMPT = """Du bist der RetroDisc KI-Assistent. Du hilfst dem Benutzer,
Medien zu konvertieren, herunterzuladen und auf Disc zu brennen.

Deine Aufgabe: Analysiere die Eingabe des Benutzers und erstelle einen strukturierten
Aktionsplan als JSON.

Verfügbare Aktionen:
- search: Mediensuche (query, source: "youtube"|"mediathek"|"all")
- download: Download (url, format: "best"|"720p"|"1080p"|"mp3", audio_only: bool)
- convert: Konvertierung (preset: siehe unten, input_path, output_path)
- burn: Disc brennen (disc_type: "dvd"|"bluray"|"cd", iso_path)
- dvd_author: DVD erstellen (input_files, title, standard: "PAL"|"NTSC")
- create_iso: ISO erstellen (source_dir, output_path)
- subtitle: Untertitel generieren (input_path, language)
- upscale: Video hochskalieren (input_path, scale: 2|4)
- interpolate: Framerate erhöhen (input_path, target_fps)
- highlight: KI-Highlights erstellen (input_path, duration_seconds)
- trim: Video schneiden (input_path, start, end)
- merge: Videos zusammenfügen (input_files)
- extract_audio: Audio extrahieren (input_path, format: "mp3"|"flac"|"wav")
- info: Dateiinfo anzeigen (input_path)

Verfügbare Presets:
- Video: mp4_h264_1080p, mp4_h264_720p, mp4_h265_4k, mkv_h265_copy_audio, avi_xvid, webm_vp9
- Audio: mp3_320k, mp3_192k, flac_lossless, wav_pcm, aac_256k, ogg_vorbis
- Geräte: iphone, android, ps5, smart_tv
- Disc: dvd_pal, dvd_ntsc, audio_cd

Antworte NUR mit validem JSON. Keine Erklärungen, kein Markdown.

Format:
{
    "action": "single"|"workflow"|"question"|"info",
    "steps": [{"type": "...", ...}],
    "message": "Optionale Nachricht an den User"
}

Für Fragen oder wenn du mehr Info brauchst:
{"action": "question", "message": "Welches Video möchtest du konvertieren?"}
"""

    def __init__(
        self,
        model: str = "phi3:mini",
        host: str = "http://localhost:11434",
    ):
        self.model = model
        self.host = host.rstrip("/")

    async def check_available(self) -> bool:
        """Prüft ob Ollama läuft und das Modell verfügbar ist."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.host}/api/tags", timeout=5.0)
                if resp.status_code != 200:
                    return False
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                if self.model not in models and self.model.split(":")[0] not in [m.split(":")[0] for m in models]:
                    log.warning("Ollama Modell nicht gefunden",
                                model=self.model, available=models)
                    return False
                return True
        except Exception as e:
            log.warning("Ollama nicht erreichbar", error=str(e))
            return False

    async def parse_command(self, user_input: str) -> dict:
        """
        Parst natürliche Spracheingabe in einen strukturierten Aktionsplan.

        Args:
            user_input: Benutzereingabe in natürlicher Sprache

        Returns:
            Aktionsplan als Dictionary
        """
        import httpx

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,  # Niedrig für konsistente Ausgaben
                "num_predict": 512,
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.host}/api/chat",
                    json=payload,
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()

            content = data.get("message", {}).get("content", "{}")
            result = json.loads(content)

            log.info("KI-Assistent Aktion",
                     input=user_input[:50],
                     action=result.get("action"),
                     steps=len(result.get("steps", [])))

            return result

        except json.JSONDecodeError:
            return {
                "action": "question",
                "message": "Entschuldigung, ich konnte die Anfrage nicht verarbeiten. Kannst du das anders formulieren?",
            }
        except Exception as e:
            log.error("KI-Assistent Fehler", error=str(e))
            return {
                "action": "error",
                "message": f"Verbindung zum KI-Assistenten fehlgeschlagen: {str(e)}",
            }

    async def suggest_preset(self, file_info: dict, target: str) -> str:
        """
        Lässt die KI das beste Preset für eine Konvertierung vorschlagen.

        Args:
            file_info: MediaInfo der Quelldatei
            target: Beschreibung des Ziels (z.B. "iPhone", "DVD", "klein für WhatsApp")

        Returns:
            Preset-Name
        """
        prompt = f"""Welches RetroDisc-Preset ist am besten für diese Konvertierung?

Quelldatei:
{json.dumps(file_info, indent=2, default=str)}

Ziel: {target}

Antworte NUR mit dem Preset-Namen als JSON:
{{"preset": "preset_name", "reason": "kurze Begründung"}}
"""
        result = await self.parse_command(prompt)
        return result.get("preset", "mp4_h264_1080p")

    async def generate_dvd_menu_description(self, titles: list[str]) -> dict:
        """
        Generiert einen DVD-Menü-Vorschlag basierend auf den Titeln.

        Args:
            titles: Liste der Video-Titel auf der DVD

        Returns:
            Menü-Beschreibung mit Layout-Vorschlag
        """
        prompt = f"""Erstelle einen DVD-Menü-Vorschlag für diese Videos:
{json.dumps(titles)}

Antworte als JSON:
{{
    "menu_title": "Haupttitel",
    "background_suggestion": "Beschreibung des Hintergrunds",
    "chapters": [{{"title": "...", "thumbnail_time": 5.0}}],
    "layout": "grid|list|carousel"
}}
"""
        return await self.parse_command(prompt)
