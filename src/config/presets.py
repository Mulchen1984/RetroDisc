"""RetroDisc Presets - Vordefinierte Konvertierungs-Profile."""

from src.models.media import ConversionPreset

# ─── Video Presets ────────────────────────────────────────────────────

VIDEO_PRESETS = [
    ConversionPreset(
        name="mp4_h264_1080p",
        display_name="MP4 (H.264, 1080p)",
        category="video",
        container="mp4",
        video_codec="libx264",
        audio_codec="aac",
        video_bitrate="5M",
        audio_bitrate="192k",
        resolution="1920:1080",
        extra_args=["-preset", "medium", "-crf", "23"],
        description="Universelles Format, gute Qualität",
    ),
    ConversionPreset(
        name="mp4_h264_720p",
        display_name="MP4 (H.264, 720p)",
        category="video",
        container="mp4",
        video_codec="libx264",
        audio_codec="aac",
        video_bitrate="3M",
        audio_bitrate="192k",
        resolution="1280:720",
        extra_args=["-preset", "medium", "-crf", "23"],
        description="Gutes Verhältnis Qualität/Größe",
    ),
    ConversionPreset(
        name="mp4_h265_4k",
        display_name="MP4 (H.265/HEVC, 4K)",
        category="video",
        container="mp4",
        video_codec="libx265",
        audio_codec="aac",
        video_bitrate="15M",
        audio_bitrate="256k",
        resolution="3840:2160",
        extra_args=["-preset", "medium", "-crf", "22"],
        description="Maximale Qualität, H.265 Kompression",
    ),
    ConversionPreset(
        name="mkv_h265_copy_audio",
        display_name="MKV (H.265, Original-Audio)",
        category="video",
        container="mkv",
        video_codec="libx265",
        audio_codec="copy",
        extra_args=["-preset", "medium", "-crf", "22"],
        description="MKV Container, Audio wird nicht re-encodet",
    ),
    ConversionPreset(
        name="avi_xvid",
        display_name="AVI (XviD) - Retro",
        category="video",
        container="avi",
        video_codec="libxvid",
        audio_codec="libmp3lame",
        video_bitrate="2M",
        audio_bitrate="192k",
        description="Klassisches AVI Format",
    ),
    ConversionPreset(
        name="webm_vp9",
        display_name="WebM (VP9)",
        category="video",
        container="webm",
        video_codec="libvpx-vp9",
        audio_codec="libopus",
        video_bitrate="3M",
        audio_bitrate="128k",
        description="Web-optimiert, gute Kompression",
    ),
]

# ─── Audio Presets ────────────────────────────────────────────────────

AUDIO_PRESETS = [
    ConversionPreset(
        name="mp3_320k",
        display_name="MP3 (320 kbps)",
        category="audio",
        container="mp3",
        audio_codec="libmp3lame",
        audio_bitrate="320k",
        sample_rate=44100,
        extra_args=["-vn"],
        description="Höchste MP3-Qualität",
    ),
    ConversionPreset(
        name="mp3_192k",
        display_name="MP3 (192 kbps)",
        category="audio",
        container="mp3",
        audio_codec="libmp3lame",
        audio_bitrate="192k",
        sample_rate=44100,
        extra_args=["-vn"],
        description="Gute Qualität, kleinere Dateien",
    ),
    ConversionPreset(
        name="flac_lossless",
        display_name="FLAC (Lossless)",
        category="audio",
        container="flac",
        audio_codec="flac",
        sample_rate=44100,
        extra_args=["-vn"],
        description="Verlustfreie Audioqualität",
    ),
    ConversionPreset(
        name="wav_pcm",
        display_name="WAV (PCM, unkomprimiert)",
        category="audio",
        container="wav",
        audio_codec="pcm_s16le",
        sample_rate=44100,
        extra_args=["-vn"],
        description="Unkomprimiertes Audio, CD-Qualität",
    ),
    ConversionPreset(
        name="aac_256k",
        display_name="AAC (256 kbps)",
        category="audio",
        container="m4a",
        audio_codec="aac",
        audio_bitrate="256k",
        sample_rate=44100,
        extra_args=["-vn"],
        description="Apple-kompatibel, gute Qualität",
    ),
    ConversionPreset(
        name="ogg_vorbis",
        display_name="OGG Vorbis",
        category="audio",
        container="ogg",
        audio_codec="libvorbis",
        audio_bitrate="192k",
        extra_args=["-vn"],
        description="Open-Source Audioformat",
    ),
]

# ─── Geräte-Presets ──────────────────────────────────────────────────

DEVICE_PRESETS = [
    ConversionPreset(
        name="iphone",
        display_name="iPhone / iPad",
        category="device",
        container="mp4",
        video_codec="libx264",
        audio_codec="aac",
        video_bitrate="5M",
        audio_bitrate="192k",
        resolution="1920:1080",
        extra_args=["-preset", "medium", "-profile:v", "high", "-level", "4.1"],
        description="Optimiert für Apple-Geräte",
    ),
    ConversionPreset(
        name="android",
        display_name="Android Smartphone",
        category="device",
        container="mp4",
        video_codec="libx264",
        audio_codec="aac",
        video_bitrate="4M",
        audio_bitrate="192k",
        resolution="1920:1080",
        extra_args=["-preset", "medium", "-profile:v", "main"],
        description="Universell für Android",
    ),
    ConversionPreset(
        name="ps5",
        display_name="PlayStation 5",
        category="device",
        container="mp4",
        video_codec="libx264",
        audio_codec="aac",
        video_bitrate="10M",
        audio_bitrate="256k",
        resolution="3840:2160",
        extra_args=["-preset", "medium", "-profile:v", "high"],
        description="4K Gaming-Konsole",
    ),
    ConversionPreset(
        name="smart_tv",
        display_name="Smart TV (Universal)",
        category="device",
        container="mp4",
        video_codec="libx264",
        audio_codec="aac",
        video_bitrate="8M",
        audio_bitrate="256k",
        resolution="3840:2160",
        extra_args=["-preset", "slow", "-profile:v", "high"],
        description="Maximale Kompatibilität",
    ),
]

# ─── Disc-Presets ────────────────────────────────────────────────────

DISC_PRESETS = [
    ConversionPreset(
        name="dvd_pal",
        display_name="DVD (PAL)",
        category="disc",
        container="mpg",
        extra_args=["-target", "pal-dvd", "-aspect", "16:9"],
        description="Standard DVD für Europa",
    ),
    ConversionPreset(
        name="dvd_ntsc",
        display_name="DVD (NTSC)",
        category="disc",
        container="mpg",
        extra_args=["-target", "ntsc-dvd", "-aspect", "16:9"],
        description="Standard DVD für Nordamerika",
    ),
    ConversionPreset(
        name="audio_cd",
        display_name="Audio-CD (CDDA)",
        category="disc",
        container="wav",
        audio_codec="pcm_s16le",
        sample_rate=44100,
        extra_args=["-vn", "-ac", "2"],
        description="CD-Audio Standard (16bit, 44.1kHz, Stereo)",
    ),
]

# ─── Alle Presets ────────────────────────────────────────────────────

ALL_PRESETS = VIDEO_PRESETS + AUDIO_PRESETS + DEVICE_PRESETS + DISC_PRESETS

PRESET_MAP = {p.name: p for p in ALL_PRESETS}


def get_preset(name: str) -> ConversionPreset:
    """Gibt ein Preset anhand des Namens zurück."""
    preset = PRESET_MAP.get(name)
    if preset is None:
        available = ", ".join(PRESET_MAP.keys())
        raise ValueError(f"Preset '{name}' nicht gefunden. Verfügbar: {available}")
    return preset


def get_presets_by_category(category: str) -> list[ConversionPreset]:
    """Gibt alle Presets einer Kategorie zurück."""
    return [p for p in ALL_PRESETS if p.category == category]
