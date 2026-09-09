"""Encoder selection: profile + capabilities + source -> a concrete encoder.

Tries the profile's preferred codec on hardware (by vendor priority), then CPU,
then declared fallback codecs, honouring source properties (HDR / 10-bit) so an
unsuitable H.264 path is not chosen when a better codec is available. Every
decision is recorded in ``reasons`` for transparency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.services.transcode.capabilities import EncoderCapability, CapabilityStatus

# codec -> ordered CPU encoders (first usable wins)
_CPU_ENCODERS = {
    "h264": ["libx264"],
    "h265": ["libx265"],
    "av1": ["libsvtav1", "libaom-av1"],
}
# codec -> vendor -> hardware encoder name
_HW_ENCODERS = {
    "h264": {"nvidia": "h264_nvenc", "intel": "h264_qsv", "amd": "h264_amf"},
    "h265": {"nvidia": "hevc_nvenc", "intel": "hevc_qsv", "amd": "hevc_amf"},
    "av1": {"nvidia": "av1_nvenc", "intel": "av1_qsv", "amd": "av1_amf"},
}


@dataclass
class SourceHints:
    width: int = 0
    height: int = 0
    bit_depth: int = 8
    hdr: bool = False
    source_codec: str = ""


@dataclass
class SelectionPrefs:
    allow_hardware: bool = True
    prefer_hardware: bool = True
    force_encoder: str = ""            # exakter Encoder erzwingen (überspringt Auto-Logik)


@dataclass
class EncoderSelection:
    encoder: str = ""
    codec: str = ""
    vendor: str = ""                  # cpu | nvidia | intel | amd
    hardware: bool = False
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = False

    def to_dict(self) -> dict:
        return {"encoder": self.encoder, "codec": self.codec, "vendor": self.vendor,
                "hardware": self.hardware, "ok": self.ok,
                "reasons": list(self.reasons), "warnings": list(self.warnings)}


def _usable(caps: dict, name: str) -> bool:
    cap = caps.get(name)
    return bool(cap and cap.status == CapabilityStatus.AVAILABLE)


def _codec_suitable_for_source(codec: str, hints: SourceHints) -> bool:
    if codec == "h264" and hints.hdr:
        return False                  # H.264 ist für HDR ungeeignet
    if codec == "h264" and hints.bit_depth >= 10:
        return False                  # 10-bit besser mit HEVC/AV1
    return True


class EncoderSelectionEngine:
    def select(self, profile, capabilities: dict, hints: Optional[SourceHints] = None,
               prefs: Optional[SelectionPrefs] = None) -> EncoderSelection:
        hints = hints or SourceHints()
        prefs = prefs or SelectionPrefs()

        if prefs.force_encoder:
            forced_ok = _usable(capabilities, prefs.force_encoder)
            vendor = next((v for c in _HW_ENCODERS.values() for v, n in c.items()
                           if n == prefs.force_encoder), "cpu")
            return EncoderSelection(encoder=prefs.force_encoder, codec=profile.codec, vendor=vendor,
                                    hardware=vendor != "cpu", ok=forced_ok,
                                    reasons=[f"Encoder erzwungen: {prefs.force_encoder}"],
                                    warnings=[] if forced_ok else ["Erzwungener Encoder ist nicht nutzbar"])

        codec_chain = [profile.codec] + [c for c in profile.fallback_codecs if c != profile.codec]
        allow_hw = prefs.allow_hardware and profile.allow_hardware
        reasons: list[str] = []

        # Bevorzugt: geeignete Codecs zuerst; ungeeignete (H.264 bei HDR/10-bit) nur als Notnagel.
        suitable = [c for c in codec_chain if _codec_suitable_for_source(c, hints)]
        unsuitable = [c for c in codec_chain if not _codec_suitable_for_source(c, hints)]
        if unsuitable:
            reasons.append(f"Ungeeignet für Quelle (HDR/10-bit) zurückgestellt: {', '.join(unsuitable)}")

        for codec in suitable + unsuitable:
            downgraded = not _codec_suitable_for_source(codec, hints)
            # 1) Hardware nach Vendor-Priorität
            if allow_hw and prefs.prefer_hardware:
                pick = self._try_hardware(codec, profile, capabilities, reasons)
                if pick:
                    return self._finish(pick, codec, downgraded, reasons, hints)
            # 2) CPU
            for cpu_name in _CPU_ENCODERS.get(codec, []):
                if _usable(capabilities, cpu_name):
                    reasons.append(f"CPU-Encoder {cpu_name} für {codec} gewählt")
                    return self._finish((cpu_name, "cpu", False), codec, downgraded, reasons, hints)
            # 3) Hardware auch ohne prefer_hardware (falls CPU fehlt)
            if allow_hw and not prefs.prefer_hardware:
                pick = self._try_hardware(codec, profile, capabilities, reasons)
                if pick:
                    return self._finish(pick, codec, downgraded, reasons, hints)
            reasons.append(f"Kein nutzbarer Encoder für {codec}")

        return EncoderSelection(ok=False, reasons=reasons + ["Kein nutzbarer Encoder gefunden"])

    def _try_hardware(self, codec, profile, capabilities, reasons):
        for vendor in profile.hardware_priority:
            name = _HW_ENCODERS.get(codec, {}).get(vendor)
            if name and _usable(capabilities, name):
                reasons.append(f"Hardware-Encoder {name} ({vendor}) für {codec} gewählt")
                return (name, vendor, True)
        return None

    def _finish(self, pick, codec, downgraded, reasons, hints):
        name, vendor, hardware = pick
        warnings = []
        if downgraded:
            warnings.append("H.264 für HDR/10-bit gewählt (kein besserer Codec nutzbar) – "
                            "Qualität/HDR wird reduziert.")
        return EncoderSelection(encoder=name, codec=codec, vendor=vendor, hardware=hardware,
                                ok=True, reasons=list(reasons), warnings=warnings)
