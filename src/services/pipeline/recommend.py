"""Profile recommendation from analysis + goal + available hardware.

Not a static table: derives resolution tier, HDR/10-bit and interlacing from the
analysis, respects the goal, and warns honestly (e.g. HDR loss with H.264, no
hardware detected). Never recommends upscaling SD to 4K.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.services.pipeline.analysis import MediaAnalysisResult
from src.services.pipeline.source import SourceKind
from src.services.transcode.capabilities import CapabilityStatus

_HW_ENCODERS = {"h264_nvenc", "hevc_nvenc", "av1_nvenc", "h264_qsv", "hevc_qsv",
                "av1_qsv", "h264_amf", "hevc_amf", "av1_amf"}


class ProfileGoal(str, Enum):
    PRESERVE = "preserve"
    COMPATIBILITY = "compatibility"
    SMALL_SIZE = "small_size"
    FAST = "fast"
    ARCHIVE = "archive"


# tier -> goal -> builtin profile name
_TABLE = {
    "dvd": {ProfileGoal.PRESERVE: "dvd_preserve", ProfileGoal.COMPATIBILITY: "h264_compatibility",
            ProfileGoal.SMALL_SIZE: "h265_quality", ProfileGoal.FAST: "fast_hardware",
            ProfileGoal.ARCHIVE: "dvd_preserve"},
    "uhd": {ProfileGoal.PRESERVE: "uhd_preserve", ProfileGoal.COMPATIBILITY: "h264_compatibility",
            ProfileGoal.SMALL_SIZE: "h265_quality", ProfileGoal.FAST: "fast_hardware",
            ProfileGoal.ARCHIVE: "uhd_preserve"},
    "hd": {ProfileGoal.PRESERVE: "bluray_preserve", ProfileGoal.COMPATIBILITY: "h264_compatibility",
           ProfileGoal.SMALL_SIZE: "h265_quality", ProfileGoal.FAST: "fast_hardware",
           ProfileGoal.ARCHIVE: "av1_archive"},
    "sd": {ProfileGoal.PRESERVE: "h265_quality", ProfileGoal.COMPATIBILITY: "h264_compatibility",
           ProfileGoal.SMALL_SIZE: "h265_quality", ProfileGoal.FAST: "fast_hardware",
           ProfileGoal.ARCHIVE: "av1_archive"},
}


@dataclass
class Recommendation:
    goal: str
    recommended_profile: str
    alternatives: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"goal": self.goal, "recommended_profile": self.recommended_profile,
                "alternatives": list(self.alternatives), "reasons": list(self.reasons),
                "warnings": list(self.warnings)}


def _tier(analysis: MediaAnalysisResult) -> str:
    if analysis.disc_kind == "dvd" or analysis.source.kind == SourceKind.DVD_FOLDER:
        return "dvd"
    v = analysis.media_info.primary_video if analysis.media_info else None
    width = v.width if v else 0
    if width >= 3840 or (v and (v.hdr or v.bit_depth >= 10)):
        return "uhd"
    if width >= 1920:
        return "hd"
    return "sd"


class ProfileRecommendationEngine:
    def recommend(self, analysis: MediaAnalysisResult, goal: ProfileGoal = ProfileGoal.PRESERVE,
                  *, hardware: Optional[dict] = None) -> Recommendation:
        tier = _tier(analysis)
        table = _TABLE[tier]
        profile = table[goal]
        alternatives = [p for g, p in table.items() if p != profile]
        # eindeutige Alternativen, Reihenfolge erhalten
        seen, alts = set(), []
        for p in alternatives:
            if p not in seen:
                seen.add(p); alts.append(p)

        rec = Recommendation(goal=goal.value, recommended_profile=profile, alternatives=alts)
        v = analysis.media_info.primary_video if analysis.media_info else None

        if tier == "dvd":
            rec.reasons.append("DVD-Quelle: SD erhalten, kein Upscale auf HD/4K.")
            if v and v.interlaced:
                rec.reasons.append("Interlaced erkannt: Deinterlacing im Profil.")
        elif tier == "uhd":
            rec.reasons.append("4K/HDR/10-bit erkannt: HDR-/10-bit-fähiger Codec bevorzugt.")
            if goal == ProfileGoal.COMPATIBILITY:
                rec.warnings.append("H.264-Kompatibilitätsprofil reduziert HDR/10-bit zu SDR/8-bit.")
        elif tier == "hd":
            rec.reasons.append("1080p-Quelle: hochwertig erhalten.")
        else:
            rec.reasons.append("SD-/Standardquelle.")

        if goal == ProfileGoal.FAST:
            hw_ok = bool(hardware) and any(
                hardware.get(n) in (CapabilityStatus.AVAILABLE, CapabilityStatus.AVAILABLE.value)
                for n in _HW_ENCODERS)
            if not hw_ok:
                rec.warnings.append("Keine nutzbare Hardware erkannt: Fast-Profil fällt auf CPU zurück.")
            else:
                rec.reasons.append("Hardware-Encoder verfügbar: schnelles Encoding.")
        return rec
