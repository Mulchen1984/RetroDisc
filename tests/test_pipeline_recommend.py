"""ProfileRecommendationEngine: goal + source + hardware aware."""
from src.services.pipeline.recommend import ProfileRecommendationEngine, ProfileGoal
from src.services.pipeline.analysis import MediaAnalysisResult
from src.services.pipeline.source import SourceMedia, SourceKind
from src.services.transcode.probe import SourceMediaInfo, VideoStream
from src.services.transcode.capabilities import CapabilityStatus

ENGINE = ProfileRecommendationEngine()


def analysis(kind, *, disc_kind="", width=0, hdr=False, bit_depth=8, interlaced=False):
    v = VideoStream(width=width, height=int(width * 9 / 16) if width else 0, bit_depth=bit_depth,
                    hdr=hdr, field_order="tt" if interlaced else "progressive")
    return MediaAnalysisResult(source=SourceMedia(kind=kind), media_info=SourceMediaInfo(video=[v]),
                               disc_kind=disc_kind)


def test_dvd_preserve_deinterlaces_and_no_upscale():
    r = ENGINE.recommend(analysis(SourceKind.DVD_FOLDER, disc_kind="dvd", width=720, interlaced=True),
                         ProfileGoal.PRESERVE)
    assert r.recommended_profile == "dvd_preserve"
    assert any("Upscale" in x for x in r.reasons) and any("Deinterlac" in x for x in r.reasons)


def test_dvd_compatibility():
    r = ENGINE.recommend(analysis(SourceKind.DVD_FOLDER, disc_kind="dvd", width=720),
                         ProfileGoal.COMPATIBILITY)
    assert r.recommended_profile == "h264_compatibility"


def test_hd_preserve():
    r = ENGINE.recommend(analysis(SourceKind.FILE, width=1920), ProfileGoal.PRESERVE)
    assert r.recommended_profile == "bluray_preserve"


def test_uhd_hdr_preserve_and_compat_warning():
    a = analysis(SourceKind.FILE, width=3840, hdr=True, bit_depth=10)
    preserve = ENGINE.recommend(a, ProfileGoal.PRESERVE)
    assert preserve.recommended_profile == "uhd_preserve" and any("HDR" in x for x in preserve.reasons)
    compat = ENGINE.recommend(a, ProfileGoal.COMPATIBILITY)
    assert compat.recommended_profile == "h264_compatibility"
    assert any("HDR" in w for w in compat.warnings)         # ehrliche Warnung


def test_10bit_without_4k_is_still_uhd_tier():
    r = ENGINE.recommend(analysis(SourceKind.FILE, width=1920, bit_depth=10), ProfileGoal.PRESERVE)
    assert r.recommended_profile == "uhd_preserve"


def test_sd_small_size():
    r = ENGINE.recommend(analysis(SourceKind.FILE, width=640), ProfileGoal.SMALL_SIZE)
    assert r.recommended_profile == "h265_quality"


def test_fast_goal_hardware_awareness():
    a = analysis(SourceKind.FILE, width=1920)
    with_hw = ENGINE.recommend(a, ProfileGoal.FAST,
                               hardware={"h264_nvenc": CapabilityStatus.AVAILABLE.value})
    assert with_hw.recommended_profile == "fast_hardware" and not with_hw.warnings
    no_hw = ENGINE.recommend(a, ProfileGoal.FAST,
                             hardware={"h264_nvenc": CapabilityStatus.HARDWARE_MISSING.value})
    assert any("Hardware" in w for w in no_hw.warnings)     # CPU-Fallback-Warnung


def test_alternatives_are_distinct_and_exclude_recommended():
    r = ENGINE.recommend(analysis(SourceKind.FILE, width=1920), ProfileGoal.PRESERVE)
    assert r.recommended_profile not in r.alternatives
    assert len(r.alternatives) == len(set(r.alternatives))
    assert r.to_dict()["recommended_profile"] == "bluray_preserve"
