"""Tests für den CapacityPlanner (P0 Block 2) und die plan_capacity-Bridge-Methode."""
from __future__ import annotations

import json

import pytest

from src.config.target_media import TARGET_MEDIA, AuthoringFormat, get_target_medium
from src.models.disc_content import DiscAudioTrack, DiscContent, DiscSubtitleTrack, DiscTitle
from src.models.media import DiscType
from src.services.capacity_planner import CapacityPlanner


def _title(index=0, duration=3600.0, size=3_000_000_000, audio=None, subtitles=None) -> DiscTitle:
    return DiscTitle(index=index, duration_seconds=duration, size_bytes=size,
                     audio_tracks=audio or [], subtitle_tracks=subtitles or [])


# ─── Jedes geforderte Zielmedium ─────────────────────────────────────────

@pytest.mark.parametrize("medium_id", [
    "dvd5", "dvd9", "bdmv_on_dvd5", "bdmv_on_dvd9", "bd25", "bd50", "bd100", "bd128",
])
def test_plan_resolves_every_required_target_medium(medium_id):
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=100_000_000)], target_medium_id=medium_id)
    assert plan.error is None
    assert plan.target_medium_id == medium_id
    medium = get_target_medium(medium_id)
    assert plan.target_capacity_bytes == medium.nominal_capacity_bytes
    assert plan.usable_capacity_bytes == medium.usable_capacity_bytes
    assert plan.target_authoring_format == medium.authoring_format.value


def test_plan_accepts_explicit_custom_target_size():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=100_000_000)], target_medium_id="custom",
                        custom_target_bytes=15_000_000_000, custom_authoring_format=AuthoringFormat.BDMV)
    assert plan.error is None
    assert plan.target_medium_id == "custom"
    assert plan.target_capacity_bytes == 15_000_000_000
    assert plan.target_authoring_format == AuthoringFormat.BDMV.value


# ─── Passt / passt nicht ohne Transcoding ────────────────────────────────

def test_content_fits_without_transcoding_on_large_enough_medium():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(duration=3600.0, size=2_000_000_000)], target_medium_id="bd25")
    assert plan.error is None
    assert plan.fits_without_reduction is True
    assert plan.transcoding_required is False


def test_content_requires_transcoding_on_too_small_medium():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(duration=7200.0, size=6_000_000_000)], target_medium_id="dvd5")
    assert plan.fits_without_reduction is False
    assert plan.transcoding_required is True
    assert plan.max_average_video_bitrate_bps is not None
    assert plan.max_average_video_bitrate_bps > 0


# ─── Overhead wird berücksichtigt ────────────────────────────────────────

def test_reserved_overhead_matches_authoring_format_constant():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=100_000_000)], target_medium_id="dvd5")
    medium = get_target_medium("dvd5")
    expected_overhead = CapacityPlanner.AUTHORING_OVERHEAD_BY_FORMAT[AuthoringFormat.DVD_VIDEO]
    assert plan.reserved_overhead_bytes == expected_overhead
    assert plan.available_payload_bytes == medium.usable_capacity_bytes - expected_overhead


def test_bdmv_authoring_format_uses_its_own_overhead_constant():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=100_000_000)], target_medium_id="bd25")
    assert plan.reserved_overhead_bytes == CapacityPlanner.AUTHORING_OVERHEAD_BY_FORMAT[AuthoringFormat.BDMV]


# ─── Video-Bitrate aus Budget und Dauer ───────────────────────────────────

def test_max_average_video_bitrate_is_computed_exactly_from_budget_and_duration():
    planner = CapacityPlanner()
    # Keine Audio-/Untertitelspuren: Video-Budget = available_payload_bytes exakt.
    plan = planner.plan(titles=[_title(duration=1000.0, size=1)], target_medium_id="dvd5")
    expected_bitrate = plan.video_budget_bytes * 8 / 1000.0
    assert plan.max_average_video_bitrate_bps == pytest.approx(expected_bitrate)
    assert plan.video_budget_bytes == plan.available_payload_bytes  # keine Audio-/UT-Spuren


# ─── Mehrere Audiospuren ──────────────────────────────────────────────────

def test_multiple_audio_tracks_sum_into_audio_budget_with_warning_for_unknown_bitrate():
    known = DiscAudioTrack(index=1, codec="ac3", channels=6, bitrate=384_000)
    unknown = DiscAudioTrack(index=2, codec="dts", channels=2, bitrate=None)
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(duration=1000.0, size=1, audio=[known, unknown])],
                        target_medium_id="dvd5")
    expected = int(384_000 * 1000.0 / 8) + int(CapacityPlanner.DEFAULT_AUDIO_BITRATE_STEREO_BPS * 1000.0 / 8)
    assert plan.audio_budget_bytes == expected
    assert any("Audiospur 2" in w and "Schätzung" in w for w in plan.warnings)


def test_surround_default_bitrate_used_for_unknown_multichannel_track():
    unknown_surround = DiscAudioTrack(index=1, codec="ac3", channels=6, bitrate=None)
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(duration=1000.0, size=1, audio=[unknown_surround])],
                        target_medium_id="dvd5")
    expected = int(CapacityPlanner.DEFAULT_AUDIO_BITRATE_SURROUND_BPS * 1000.0 / 8)
    assert plan.audio_budget_bytes == expected


# ─── Mehrere Untertitel ───────────────────────────────────────────────────

def test_multiple_subtitle_tracks_scale_subtitle_overhead_linearly():
    subs = [DiscSubtitleTrack(index=10 + i, language="de") for i in range(3)]
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=1, subtitles=subs)], target_medium_id="dvd5")
    assert plan.subtitle_overhead_bytes == 3 * CapacityPlanner.SUBTITLE_TRACK_RESERVE_BYTES


# ─── Mehrere Titel ────────────────────────────────────────────────────────

def test_multiple_titles_sum_duration_and_size():
    titles = [_title(index=0, duration=1800.0, size=1_500_000_000),
              _title(index=1, duration=2700.0, size=2_500_000_000)]
    planner = CapacityPlanner()
    plan = planner.plan(titles=titles, target_medium_id="bd50")
    assert plan.total_duration_seconds == 1800.0 + 2700.0
    assert plan.estimated_source_size_bytes == 1_500_000_000 + 2_500_000_000


# ─── Sehr lange Laufzeit ──────────────────────────────────────────────────

def test_very_long_duration_computes_without_overflow_or_error():
    ten_hours = 10 * 3600.0
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(duration=ten_hours, size=40_000_000_000)], target_medium_id="bd50")
    assert plan.error is None
    assert plan.max_average_video_bitrate_bps is not None
    assert plan.max_average_video_bitrate_bps > 0


# ─── Laufzeit 0 ───────────────────────────────────────────────────────────

def test_zero_duration_yields_no_bitrate_but_no_crash():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(duration=0.0, size=0)], target_medium_id="dvd5")
    assert plan.max_average_video_bitrate_bps is None
    assert any("0" in w for w in plan.warnings)
    assert plan.fits_without_reduction is True  # 0 Bytes passen trivial


def test_empty_title_list_behaves_like_zero_duration():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[], target_medium_id="dvd5")
    assert plan.total_duration_seconds == 0.0
    assert plan.estimated_source_size_bytes == 0
    assert plan.max_average_video_bitrate_bps is None


# ─── Ungültige Custom-Größe ───────────────────────────────────────────────

@pytest.mark.parametrize("bad_size", [0, -1, None])
def test_invalid_custom_size_produces_error_not_exception(bad_size):
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title()], target_medium_id="custom",
                        custom_target_bytes=bad_size, custom_authoring_format=AuthoringFormat.DVD_VIDEO)
    assert plan.error is not None
    assert "Custom" in plan.error or "custom" in plan.error


def test_custom_without_authoring_format_produces_error():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title()], target_medium_id="custom", custom_target_bytes=10_000_000_000)
    assert plan.error is not None
    assert "Authoring-Format" in plan.error


def test_unknown_target_medium_id_produces_error_not_exception():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title()], target_medium_id="dvd6")
    assert plan.error is not None


# ─── Zielmedium kleiner als notwendiger Mindestbedarf ────────────────────

def test_target_too_small_for_overhead_alone_sets_error():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=1)], target_medium_id="custom",
                        custom_target_bytes=1000, custom_authoring_format=AuthoringFormat.DVD_VIDEO)
    assert plan.error is not None
    assert plan.available_payload_bytes <= 0


def test_target_too_small_for_audio_alone_sets_error():
    huge_audio = [DiscAudioTrack(index=1, codec="ac3", channels=6, bitrate=5_000_000)]
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(duration=36000.0, size=1, audio=huge_audio)],
                        target_medium_id="dvd5")
    assert plan.error is not None
    assert plan.video_budget_bytes <= 0


# ─── BDXL: nie Unterstützung ohne Beleg behaupten ────────────────────────

def test_bdxl_target_without_drive_capabilities_warns_but_does_not_error():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=1_000_000_000)], target_medium_id="bd100")
    assert plan.error is None
    assert any("BDXL" in w for w in plan.warnings)


def test_bdxl_target_with_drive_lacking_bdxl_sets_error():
    from src.services.drive_inspector import DriveCapabilities
    planner = CapacityPlanner()
    # bd_r=True isoliert die BDXL-Prüfung: das Laufwerk KANN Blu-ray
    # schreiben, nur eben kein BDXL - genau das soll hier allein greifen.
    plan = planner.plan(titles=[_title(size=1_000_000_000)], target_medium_id="bd128",
                        drive_capabilities=DriveCapabilities(bd_r=True, bd_xl=False))
    assert plan.error is not None
    assert "BDXL" in plan.error


def test_bdxl_target_with_confirmed_drive_support_has_no_bdxl_error_or_warning():
    from src.services.drive_inspector import DriveCapabilities
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=1_000_000_000)], target_medium_id="bd100",
                        drive_capabilities=DriveCapabilities(bd_r=True, bd_xl=True))
    assert plan.error is None
    assert not any("BDXL" in w for w in plan.warnings)


def test_non_bdxl_target_ignores_drive_capabilities_entirely():
    from src.services.drive_inspector import DriveCapabilities
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(size=1_000_000_000)], target_medium_id="bd25",
                        drive_capabilities=DriveCapabilities(bd_r=True, bd_xl=False))
    assert plan.error is None
    assert not any("BDXL" in w for w in plan.warnings)


# ─── Unbekannte Metadaten -> kontrolliertes Verhalten ────────────────────

def test_unknown_title_size_makes_total_size_unknown_not_zero():
    titles = [_title(index=0, duration=1000.0, size=1_000_000_000),
              _title(index=1, duration=1000.0, size=None)]
    planner = CapacityPlanner()
    plan = planner.plan(titles=titles, target_medium_id="bd50")
    assert plan.estimated_source_size_bytes is None
    assert plan.fits_without_reduction is None
    assert plan.transcoding_required is None
    assert any("Quellgröße" in w for w in plan.warnings)


def test_unknown_title_duration_is_treated_as_partial_sum_with_warning():
    titles = [_title(index=0, duration=1000.0, size=1),
              _title(index=1, duration=None, size=1)]
    planner = CapacityPlanner()
    plan = planner.plan(titles=titles, target_medium_id="bd50")
    assert plan.total_duration_seconds == 1000.0  # nur die bekannte Dauer, keine erfundene Summe
    assert any("Laufzeit" in w for w in plan.warnings)


# ─── Serialisierung ───────────────────────────────────────────────────────

def test_plan_to_dict_round_trips_through_json():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title(duration=3600.0, size=2_000_000_000,
                                       audio=[DiscAudioTrack(index=1, codec="ac3", channels=2, bitrate=192_000)])],
                        target_medium_id="dvd9")
    encoded = json.dumps(plan.to_dict())
    decoded = json.loads(encoded)
    assert decoded["target_medium_id"] == "dvd9"
    assert isinstance(decoded["fits_without_reduction"], bool)
    assert isinstance(decoded["warnings"], list)
    assert decoded["error"] is None


def test_error_plan_serializes_cleanly_with_null_numeric_fields():
    planner = CapacityPlanner()
    plan = planner.plan(titles=[_title()], target_medium_id="not-a-real-medium")
    decoded = json.loads(json.dumps(plan.to_dict()))
    assert decoded["error"] is not None
    assert decoded["estimated_source_size_bytes"] is None
    assert decoded["max_average_video_bitrate_bps"] is None


# ─── Bridge ───────────────────────────────────────────────────────────────

@pytest.fixture
def bare_bridge(tmp_path, monkeypatch):
    """Wie in tests/test_disc_content.py: produktiver Bridge-Konstruktor mit
    echtem Hintergrund-Thread, da plan_capacity über self._async(...).result(...) dispatcht."""
    import retrodisc_launcher as launcher
    from src.config.settings import AppSettings

    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output",
        "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }, library_db_path=tmp_path / ".retrodisc" / "library.db").save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    bridge = launcher.RetroDiscBridge()
    try:
        yield bridge
    finally:
        bridge._loop.call_soon_threadsafe(bridge._loop.stop)
        bridge._thread.join(timeout=5)
        bridge._loop.close()


def _canned_disc_content() -> DiscContent:
    audio = [DiscAudioTrack(index=1, codec="ac3", channels=6, bitrate=384_000)]
    subs = [DiscSubtitleTrack(index=10, language="de")]
    title = DiscTitle(index=0, duration_seconds=5400.0, size_bytes=3_500_000_000,
                      audio_tracks=audio, subtitle_tracks=subs)
    return DiscContent(disc_type=DiscType.DVD, label="TESTDISC", device="D:", titles=[title])


def test_bridge_plan_capacity_requires_a_device(bare_bridge):
    result = json.loads(bare_bridge.plan_capacity("", "dvd5"))
    assert "error" in result


def test_bridge_plan_capacity_returns_serialized_plan_for_all_titles_by_default(bare_bridge, monkeypatch):
    async def fake_analyze(device):
        return _canned_disc_content()

    monkeypatch.setattr(bare_bridge.disc_analyzer, "analyze", fake_analyze)

    result = json.loads(bare_bridge.plan_capacity("D:", "dvd9"))

    assert "error" not in result or result["error"] is None
    assert result["target_medium_id"] == "dvd9"
    assert result["estimated_source_size_bytes"] == 3_500_000_000
    assert result["total_duration_seconds"] == 5400.0


def test_bridge_plan_capacity_supports_custom_target(bare_bridge, monkeypatch):
    async def fake_analyze(device):
        return _canned_disc_content()

    monkeypatch.setattr(bare_bridge.disc_analyzer, "analyze", fake_analyze)

    result = json.loads(bare_bridge.plan_capacity(
        "D:", "custom",
        custom_target_bytes=20_000_000_000, custom_authoring_format="bdmv",
    ))

    assert result["error"] is None
    assert result["target_capacity_bytes"] == 20_000_000_000
    assert result["target_authoring_format"] == "bdmv"


def test_bridge_plan_capacity_respects_selected_title_indices(bare_bridge, monkeypatch):
    two_titles = DiscContent(disc_type=DiscType.DVD, device="D:", titles=[
        DiscTitle(index=0, duration_seconds=600.0, size_bytes=500_000_000),
        DiscTitle(index=1, duration_seconds=5400.0, size_bytes=4_000_000_000),
    ])

    async def fake_analyze(device):
        return two_titles

    monkeypatch.setattr(bare_bridge.disc_analyzer, "analyze", fake_analyze)

    result = json.loads(bare_bridge.plan_capacity(
        "D:", "bd50", selected_title_indices_json=json.dumps([1]),
    ))

    assert result["total_duration_seconds"] == 5400.0
    assert result["estimated_source_size_bytes"] == 4_000_000_000
