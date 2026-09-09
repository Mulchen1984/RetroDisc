"""TranscodingProfile model + EncoderSelectionEngine fallback logic."""
from src.services.transcode.capabilities import EncoderCapability, CapabilityStatus as S, KNOWN_ENCODERS
from src.services.transcode.profiles import BUILTIN_PROFILES, get_profile, TranscodingProfile
from src.services.transcode.selection import (
    EncoderSelectionEngine, SourceHints, SelectionPrefs,
)

_META = {name: (codec, vendor) for codec, vendor, name in KNOWN_ENCODERS}


def caps(available):
    """Build a capability dict; names in `available` are AVAILABLE, rest ABSENT."""
    out = {}
    for codec, vendor, name in KNOWN_ENCODERS:
        out[name] = EncoderCapability(name, codec, vendor,
                                      S.AVAILABLE if name in available else S.ABSENT)
    return out


ENGINE = EncoderSelectionEngine()


def test_profiles_are_declarative_and_serialisable():
    for name, p in BUILTIN_PROFILES.items():
        d = p.to_dict()
        assert d["name"] == name and isinstance(d["codec"], str) and "container" in d
    assert get_profile("uhd_preserve").pixel_format == "yuv420p10le"


def test_nvenc_preferred_for_h264():
    sel = ENGINE.select(get_profile("h264_compatibility"),
                        caps({"h264_nvenc", "libx264"}))
    assert sel.ok and sel.encoder == "h264_nvenc" and sel.hardware and sel.vendor == "nvidia"


def test_qsv_fallback_when_no_nvenc():
    sel = ENGINE.select(get_profile("h264_compatibility"), caps({"h264_qsv", "libx264"}))
    assert sel.encoder == "h264_qsv" and sel.vendor == "intel"


def test_amf_fallback():
    sel = ENGINE.select(get_profile("h264_compatibility"), caps({"h264_amf", "libx264"}))
    assert sel.encoder == "h264_amf" and sel.vendor == "amd"


def test_cpu_fallback_when_no_hardware():
    sel = ENGINE.select(get_profile("h264_compatibility"), caps({"libx264"}))
    assert sel.encoder == "libx264" and not sel.hardware and sel.vendor == "cpu"


def test_av1_downgrades_to_hevc_fallback():
    # av1_archive: codec av1 (keiner nutzbar) -> fallback h265 -> libx265
    sel = ENGINE.select(get_profile("av1_archive"), caps({"libx265"}))
    assert sel.ok and sel.codec == "h265" and sel.encoder == "libx265"


def test_av1_hardware_preferred_if_available():
    sel = ENGINE.select(get_profile("av1_archive"), caps({"av1_nvenc", "libx265"}))
    assert sel.codec == "av1" and sel.encoder == "av1_nvenc"


def test_uhd_hdr_10bit_never_picks_h264():
    hints = SourceHints(width=3840, height=2160, bit_depth=10, hdr=True)
    # nur h264-Encoder nutzbar, aber HDR/10-bit -> h265-Profil hat kein h264-Fallback -> kein Encoder
    sel = ENGINE.select(get_profile("uhd_preserve"), caps({"h264_nvenc", "libx264"}), hints)
    assert not sel.ok                                   # kein ungeeigneter H.264-Fallback
    # mit nutzbarem HEVC -> HEVC gewählt
    sel2 = ENGINE.select(get_profile("uhd_preserve"), caps({"hevc_nvenc"}), hints)
    assert sel2.ok and sel2.encoder == "hevc_nvenc" and sel2.codec == "h265"


def test_h264_profile_on_hdr_prefers_h265_fallback():
    hints = SourceHints(bit_depth=10, hdr=True)
    profile = TranscodingProfile(name="x", codec="h264", fallback_codecs=["h265"])
    sel = ENGINE.select(profile, caps({"libx264", "libx265"}), hints)
    assert sel.codec == "h265" and sel.encoder == "libx265"   # H.264 vermieden


def test_h264_last_resort_on_hdr_warns():
    hints = SourceHints(bit_depth=10, hdr=True)
    profile = TranscodingProfile(name="x", codec="h264")      # kein Fallback
    sel = ENGINE.select(profile, caps({"libx264"}), hints)
    assert sel.ok and sel.encoder == "libx264" and sel.warnings   # Notnagel mit Warnung


def test_prefer_hardware_false_uses_cpu_first():
    sel = ENGINE.select(get_profile("h264_compatibility"),
                        caps({"h264_nvenc", "libx264"}),
                        prefs=SelectionPrefs(prefer_hardware=False))
    assert sel.encoder == "libx264"


def test_disallow_hardware():
    sel = ENGINE.select(get_profile("fast_hardware"), caps({"h264_nvenc", "libx264"}),
                        prefs=SelectionPrefs(allow_hardware=False))
    assert sel.encoder == "libx264" and not sel.hardware


def test_force_encoder():
    sel = ENGINE.select(get_profile("h264_compatibility"), caps({"h264_nvenc"}),
                        prefs=SelectionPrefs(force_encoder="h264_nvenc"))
    assert sel.encoder == "h264_nvenc" and sel.ok
    bad = ENGINE.select(get_profile("h264_compatibility"), caps(set()),
                        prefs=SelectionPrefs(force_encoder="hevc_qsv"))
    assert bad.encoder == "hevc_qsv" and not bad.ok and bad.warnings


def test_no_usable_encoder_returns_not_ok():
    sel = ENGINE.select(get_profile("h264_compatibility"), caps(set()))
    assert not sel.ok and sel.reasons
