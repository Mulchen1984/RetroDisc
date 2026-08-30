"""RetroDisc Sound — Der legendäre Fertig-Sound und Notifications."""

from __future__ import annotations

import math
import struct
import wave
import tempfile
import structlog
from pathlib import Path
from typing import Optional

log = structlog.get_logger()

# Globaler Pfad für Custom-Sounds
_custom_sound_path: Optional[Path] = None


def set_custom_sound(path: Path) -> None:
    """Setzt einen eigenen Fertig-Sound (WAV-Datei)."""
    global _custom_sound_path
    if path.exists() and path.suffix.lower() == ".wav":
        _custom_sound_path = path
        log.info("Custom Sound gesetzt", path=str(path))
    else:
        log.warning("Ungültige Sound-Datei", path=str(path))


def generate_completion_wav() -> Path:
    """
    Generiert den RetroDisc Fertig-Sound als WAV-Datei.

    Der Sound ist inspiriert vom CloneCD-Jingle:
    Aufsteigende Tonfolge mit kurzem Nachhall — sofort erkennbar.
    """
    sample_rate = 44100
    duration_total = 1.2  # Sekunden

    # Noten: aufsteigende Quinte + Oktave (wie CloneCD)
    notes = [
        {"freq": 880, "start": 0.0, "dur": 0.18, "vol": 0.5},    # A5
        {"freq": 1108, "start": 0.14, "dur": 0.18, "vol": 0.45},  # C#6
        {"freq": 1318, "start": 0.28, "dur": 0.18, "vol": 0.4},   # E6
        {"freq": 1760, "start": 0.42, "dur": 0.55, "vol": 0.5},   # A6 (lang)
    ]

    num_samples = int(sample_rate * duration_total)
    samples = [0.0] * num_samples

    for note in notes:
        start_sample = int(note["start"] * sample_rate)
        num_note_samples = int(note["dur"] * sample_rate)

        for i in range(num_note_samples):
            if start_sample + i >= num_samples:
                break

            t = i / sample_rate

            # Sinus mit leichtem Oberton für wärmeren Klang
            value = (
                math.sin(2 * math.pi * note["freq"] * t) * 0.7
                + math.sin(2 * math.pi * note["freq"] * 2 * t) * 0.2
                + math.sin(2 * math.pi * note["freq"] * 3 * t) * 0.1
            )

            # Hüllkurve: Attack + Decay
            attack = min(t / 0.02, 1.0)  # 20ms Attack
            decay = max(0, 1.0 - (t / note["dur"]) ** 1.5)
            envelope = attack * decay * note["vol"]

            samples[start_sample + i] += value * envelope

    # Normalisieren und zu 16-bit konvertieren
    max_val = max(abs(s) for s in samples) or 1.0
    int_samples = [int(max(-1, min(1, s / max_val)) * 32000) for s in samples]

    # WAV-Datei schreiben
    wav_path = Path(tempfile.gettempdir()) / "retrodisc_complete.wav"
    with wave.open(str(wav_path), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack(f"<{len(int_samples)}h", *int_samples))

    return wav_path


def play_completion_sound() -> None:
    """
    Spielt den RetroDisc Fertig-Sound ab.

    Verwendet entweder einen Custom-Sound oder generiert den
    Standard-Jingle on-the-fly.
    """
    try:
        sound_path = _custom_sound_path

        if sound_path is None or not sound_path.exists():
            sound_path = generate_completion_wav()

        # Versuche sounddevice/soundfile
        try:
            import soundfile as sf
            import sounddevice as sd

            data, samplerate = sf.read(str(sound_path))
            sd.play(data, samplerate)
            # Non-blocking — Sound spielt im Hintergrund
            log.debug("Fertig-Sound abgespielt", path=str(sound_path))
            return
        except ImportError:
            pass

        # Fallback: winsound (Windows only)
        try:
            import winsound
            winsound.PlaySound(str(sound_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            log.debug("Fertig-Sound abgespielt (winsound)", path=str(sound_path))
            return
        except (ImportError, RuntimeError):
            pass

        # Fallback: System-Beep
        print("\a")  # Terminal bell
        log.debug("Fertig-Sound: System-Beep (Fallback)")

    except Exception as e:
        log.warning("Sound konnte nicht abgespielt werden", error=str(e))


def play_error_sound() -> None:
    """Spielt einen Fehler-Sound ab."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONHAND)
    except (ImportError, RuntimeError):
        print("\a")
