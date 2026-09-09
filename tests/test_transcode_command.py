"""FFmpegCommandBuilder: argument-list construction (never a shell string)."""
import pytest
from src.services.transcode.command import FFmpegCommandBuilder
from src.services.transcode.profiles import (
    get_profile, TranscodingProfile, QualityMode, AudioPolicy, SubtitlePolicy, DeinterlacePolicy,
    ResolutionPolicy,
)
from src.services.transcode.selection import EncoderSelection
from src.services.transcode.probe import SourceMediaInfo, VideoStream

BUILDER = FFmpegCommandBuilder()


def source(*, interlaced=False, width=1920):
    v = VideoStream(codec="mpeg2video", width=width, height=1080,
                    field_order="tt" if interlaced else "progressive")
    return SourceMediaInfo(path="/in.mkv", duration=100.0, video=[v])


def sel(encoder, codec="h264", vendor="cpu", hardware=False):
    return EncoderSelection(encoder=encoder, codec=codec, vendor=vendor, hardware=hardware, ok=True)


def pairs(args, flag):
    return [args[i + 1] for i, a in enumerate(args) if a == flag]


def test_result_is_arg_list_not_shell_string():
    args = BUILDER.build(source(), get_profile("h264_compatibility"), sel("libx264"), "/out.mp4")
    assert isinstance(args, list) and all(isinstance(a, str) for a in args)
    assert args[0].endswith("ffmpeg") and " " not in args[0]


def test_h264_cpu_profile():
    args = BUILDER.build(source(), get_profile("h264_compatibility"), sel("libx264"), "/out.mp4",
                         overwrite=True)
    assert "-y" in args and pairs(args, "-i") == ["/in.mkv"]
    assert pairs(args, "-c:v") == ["libx264"] and pairs(args, "-crf") == ["20"]
    assert pairs(args, "-preset") == ["medium"] and pairs(args, "-pix_fmt") == ["yuv420p"]
    assert "+faststart" in args and args[-1] == "/out.mp4"
    assert "-progress" in args and "pipe:1" in args


def test_overwrite_flag():
    a = BUILDER.build(source(), get_profile("h264_compatibility"), sel("libx264"), "/o.mp4")
    assert "-n" in a and "-y" not in a


def test_nvenc_rate_control():
    args = BUILDER.build(source(), get_profile("fast_hardware"),
                         sel("h264_nvenc", vendor="nvidia", hardware=True), "/o.mp4")
    assert pairs(args, "-c:v") == ["h264_nvenc"] and pairs(args, "-cq") == ["23"] and "-rc" in args


def test_qsv_and_amf_rate_control():
    q = BUILDER.build(source(), get_profile("h264_compatibility"),
                      sel("h264_qsv", vendor="intel", hardware=True), "/o.mp4")
    assert pairs(q, "-global_quality") == ["20"]
    a = BUILDER.build(source(), get_profile("h264_compatibility"),
                      sel("h264_amf", vendor="amd", hardware=True), "/o.mp4")
    assert "cqp" in a and pairs(a, "-qp_i") == ["20"] and pairs(a, "-quality") == ["balanced"]


def test_svtav1_numeric_preset_and_libaom():
    svt = BUILDER.build(source(), TranscodingProfile(name="x", codec="av1", preset="slow",
                        quality_value=30), sel("libsvtav1", codec="av1"), "/o.mkv")
    assert pairs(svt, "-preset") == ["4"] and pairs(svt, "-crf") == ["30"]
    aom = BUILDER.build(source(), TranscodingProfile(name="x", codec="av1", preset="medium"),
                        sel("libaom-av1", codec="av1"), "/o.mkv")
    assert pairs(aom, "-cpu-used") == ["4"] and "-crf" in aom and pairs(aom, "-b:v") == ["0"]


def test_bitrate_mode():
    p = TranscodingProfile(name="x", quality_mode=QualityMode.BITRATE, bitrate="8M",
                           maxrate="10M", bufsize="16M")
    args = BUILDER.build(source(), p, sel("libx264"), "/o.mp4")
    assert pairs(args, "-b:v") == ["8M"] and pairs(args, "-maxrate") == ["10M"]
    assert "-crf" not in args


def test_deinterlace_policies():
    force = BUILDER.build(source(interlaced=False), get_profile("dvd_preserve"), sel("libx264"), "/o.mp4")
    assert any("bwdif" in a for a in force)                    # FORCE -> immer
    auto_on = BUILDER.build(source(interlaced=True), get_profile("h264_compatibility"), sel("libx264"), "/o.mp4")
    assert any("bwdif" in a for a in auto_on)                  # AUTO + interlaced
    auto_off = BUILDER.build(source(interlaced=False), get_profile("h264_compatibility"), sel("libx264"), "/o.mp4")
    assert not any("bwdif" in a for a in auto_off)             # AUTO + progressiv -> nichts


def test_resolution_downscale_filter():
    args = BUILDER.build(source(width=3840), get_profile("bluray_preserve"),
                         sel("libx265", codec="h265"), "/o.mkv")
    assert any("scale='min(iw,1920)'" in a for a in args)


def test_audio_policies():
    stereo = BUILDER.build(source(), get_profile("h264_compatibility"), sel("libx264"), "/o.mp4")
    assert "-ac" in stereo and pairs(stereo, "-c:a") == ["aac"]
    copy = BUILDER.build(source(), get_profile("h265_quality"), sel("libx265", codec="h265"), "/o.mkv")
    assert pairs(copy, "-c:a") == ["copy"]


def test_subtitle_policies():
    drop = BUILDER.build(source(), get_profile("h264_compatibility"), sel("libx264"), "/o.mp4")
    assert "-sn" in drop
    mkv_copy = BUILDER.build(source(), get_profile("h265_quality"), sel("libx265", codec="h265"), "/o.mkv")
    assert "0:s?" in mkv_copy and pairs(mkv_copy, "-c:s") == ["copy"]
    mp4_profile = TranscodingProfile(name="x", subtitle_policy=SubtitlePolicy.COPY, container="mp4")
    mp4 = BUILDER.build(source(), mp4_profile, sel("libx264"), "/o.mp4")
    assert pairs(mp4, "-c:s") == ["mov_text"]


def test_hw_10bit_pixfmt_maps_to_p010():
    args = BUILDER.build(source(), get_profile("uhd_preserve"),
                         sel("hevc_nvenc", codec="h265", vendor="nvidia", hardware=True), "/o.mkv")
    assert pairs(args, "-pix_fmt") == ["p010le"]


def test_unusable_selection_raises():
    with pytest.raises(ValueError):
        BUILDER.build(source(), get_profile("h264_compatibility"),
                      EncoderSelection(ok=False), "/o.mp4")
