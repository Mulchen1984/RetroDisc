"""Tests für die zentrale Zielmedien-Definition (src/config/target_media.py)."""
from __future__ import annotations

import pytest

from src.config.target_media import (
    TARGET_MEDIA,
    AuthoringFormat,
    bdxl_capability_warning,
    custom_target_medium,
    get_target_medium,
    target_medium_capability_issue,
)
from src.services.drive_inspector import DriveCapabilities


def test_all_required_target_media_are_registered():
    assert set(TARGET_MEDIA) == {
        "dvd5", "dvd9", "bdmv_on_dvd5", "bdmv_on_dvd9", "bd25", "bd50", "bd100", "bd128",
    }


def test_dvd5_and_dvd9_use_dvd_video_authoring_format():
    assert get_target_medium("dvd5").authoring_format == AuthoringFormat.DVD_VIDEO
    assert get_target_medium("dvd9").authoring_format == AuthoringFormat.DVD_VIDEO


def test_bd25_and_bd50_use_bdmv_authoring_format_and_are_physical_bluray():
    for medium_id in ("bd25", "bd50"):
        medium = get_target_medium(medium_id)
        assert medium.authoring_format == AuthoringFormat.BDMV
        assert medium.is_physical_bluray is True
        assert medium.requires_bdxl is False


def test_bd100_and_bd128_are_physical_bluray_and_require_bdxl():
    for medium_id in ("bd100", "bd128"):
        medium = get_target_medium(medium_id)
        assert medium.authoring_format == AuthoringFormat.BDMV
        assert medium.is_physical_bluray is True
        assert medium.requires_bdxl is True


def test_bd128_is_larger_than_bd100_which_is_larger_than_bd50():
    assert get_target_medium("bd50").nominal_capacity_bytes < get_target_medium("bd100").nominal_capacity_bytes
    assert get_target_medium("bd100").nominal_capacity_bytes < get_target_medium("bd128").nominal_capacity_bytes


def test_bdmv_on_dvd_profiles_use_bdmv_structure_but_dvd_sized_capacity_and_are_not_physical_bluray():
    """BDMV auf DVD-5/DVD-9: Blu-ray-*Struktur* auf einem DVD-Rohling - kein
    physisches Blu-ray-Medium. Disc-Struktur und physisches Speichervermögen
    sind unabhängige Achsen."""
    on_dvd5, dvd5 = get_target_medium("bdmv_on_dvd5"), get_target_medium("dvd5")
    on_dvd9, dvd9 = get_target_medium("bdmv_on_dvd9"), get_target_medium("dvd9")
    assert on_dvd5.authoring_format == AuthoringFormat.BDMV
    assert on_dvd5.nominal_capacity_bytes == dvd5.nominal_capacity_bytes
    assert on_dvd5.is_physical_bluray is False
    assert on_dvd9.authoring_format == AuthoringFormat.BDMV
    assert on_dvd9.nominal_capacity_bytes == dvd9.nominal_capacity_bytes
    assert on_dvd9.is_physical_bluray is False


def test_bdmv_on_dvd_display_names_are_unambiguous_not_plain_bd_labels():
    on_dvd5 = get_target_medium("bdmv_on_dvd5")
    on_dvd9 = get_target_medium("bdmv_on_dvd9")
    assert "BDMV" in on_dvd5.display_name and "DVD-5" in on_dvd5.display_name
    assert "kein physisches Blu-ray-Medium" in on_dvd5.display_name
    assert "BDMV" in on_dvd9.display_name and "DVD-9" in on_dvd9.display_name
    # Darf nicht wie ein eigenständiges physisches "BD-5"/"BD-9"-Medium aussehen.
    assert not on_dvd5.display_name.startswith("BD-5")
    assert not on_dvd9.display_name.startswith("BD-9")


def test_nominal_capacities_match_documented_decimal_marketing_values():
    assert get_target_medium("dvd5").nominal_capacity_bytes == 4_700_000_000
    assert get_target_medium("dvd9").nominal_capacity_bytes == 8_500_000_000
    assert get_target_medium("bd25").nominal_capacity_bytes == 25_000_000_000
    assert get_target_medium("bd50").nominal_capacity_bytes == 50_000_000_000
    assert get_target_medium("bd100").nominal_capacity_bytes == 100_000_000_000
    assert get_target_medium("bd128").nominal_capacity_bytes == 128_000_000_000


def test_usable_capacity_is_strictly_less_than_nominal_capacity():
    for medium in TARGET_MEDIA.values():
        assert 0 < medium.usable_capacity_bytes < medium.nominal_capacity_bytes


def test_bd50_is_exactly_double_bd25_nominal_capacity():
    assert get_target_medium("bd50").nominal_capacity_bytes == 2 * get_target_medium("bd25").nominal_capacity_bytes


def test_unknown_target_medium_id_raises_value_error():
    with pytest.raises(ValueError, match="Unbekanntes Zielmedium"):
        get_target_medium("dvd6")


def test_old_bd5_bd9_ids_no_longer_resolve():
    """Regressionsschutz gegen die Korrektur: die alten, irreführenden IDs
    dürfen nicht wieder auftauchen."""
    with pytest.raises(ValueError):
        get_target_medium("bd5")
    with pytest.raises(ValueError):
        get_target_medium("bd9")


def test_custom_target_medium_accepts_explicit_size_and_format():
    medium = custom_target_medium(15_000_000_000, AuthoringFormat.BDMV)
    assert medium.id == "custom"
    assert medium.nominal_capacity_bytes == 15_000_000_000
    assert medium.authoring_format == AuthoringFormat.BDMV
    assert medium.usable_capacity_bytes < medium.nominal_capacity_bytes


def test_custom_target_medium_rejects_non_positive_size():
    with pytest.raises(ValueError, match="positive"):
        custom_target_medium(0, AuthoringFormat.DVD_VIDEO)
    with pytest.raises(ValueError, match="positive"):
        custom_target_medium(-1, AuthoringFormat.DVD_VIDEO)


# ─── BDXL-Fähigkeit: nie Unterstützung ohne Beleg behaupten ──────────────

def test_bdxl_warning_is_none_for_non_bdxl_media_regardless_of_drive():
    for medium_id in ("dvd5", "dvd9", "bdmv_on_dvd5", "bd25", "bd50"):
        medium = get_target_medium(medium_id)
        assert bdxl_capability_warning(medium, None) is None
        assert bdxl_capability_warning(medium, DriveCapabilities()) is None


def test_bdxl_warning_when_no_drive_capabilities_known():
    medium = get_target_medium("bd100")
    warning = bdxl_capability_warning(medium, None)
    assert warning is not None
    assert "unbekannt" in warning.lower() or "nicht bekannt" in warning.lower()


def test_bdxl_warning_when_drive_explicitly_lacks_bdxl():
    medium = get_target_medium("bd128")
    caps = DriveCapabilities(bd_xl=False)
    warning = bdxl_capability_warning(medium, caps)
    assert warning is not None
    assert "keine BDXL" in warning


def test_no_bdxl_warning_when_drive_confirms_bdxl_support():
    medium = get_target_medium("bd100")
    caps = DriveCapabilities(bd_xl=True)
    assert bdxl_capability_warning(medium, caps) is None


# ─── target_medium_capability_issue(): geschichtete Prüfung (Software vor
#     Hardware vor BDXL) - die eine Stelle, die create_bluray/check_target_medium
#     tatsächlich vor dem Brennen fragen ─────────────────────────────────────

@pytest.mark.parametrize("medium_id", ["bd25", "bd50", "bd100", "bd128"])
def test_physical_bluray_targets_require_bd_write_capability(medium_id):
    medium = get_target_medium(medium_id)
    caps = DriveCapabilities(bd_r=False, bd_re=False, bd_xl=True)
    issue = target_medium_capability_issue(medium, caps)
    assert issue is not None
    assert "Blu-ray-Rohlinge" in issue


@pytest.mark.parametrize("medium_id", ["bd25", "bd50"])
def test_physical_bluray_targets_accept_either_bd_r_or_bd_re(medium_id):
    medium = get_target_medium(medium_id)
    assert target_medium_capability_issue(medium, DriveCapabilities(bd_r=True, bd_re=False)) is None
    assert target_medium_capability_issue(medium, DriveCapabilities(bd_r=False, bd_re=True)) is None


def test_bdxl_targets_still_blocked_by_missing_bdxl_even_with_bd_write_capability():
    medium = get_target_medium("bd128")
    caps = DriveCapabilities(bd_r=True, bd_re=True, bd_xl=False)
    issue = target_medium_capability_issue(medium, caps)
    assert issue is not None
    assert "BDXL" in issue


def test_bd25_bd50_bd100_bd128_all_available_on_a_fully_capable_drive():
    caps = DriveCapabilities(bd_r=True, bd_re=True, bd_xl=True, dvd_write=True)
    for medium_id in ("bd25", "bd50", "bd100", "bd128"):
        assert target_medium_capability_issue(get_target_medium(medium_id), caps) is None


def test_dvd_targets_require_dvd_write_capability_not_bd():
    medium = get_target_medium("dvd5")
    caps = DriveCapabilities(dvd_write=False, bd_r=True, bd_re=True, bd_xl=True)
    issue = target_medium_capability_issue(medium, caps)
    assert issue is not None
    assert "DVD-Rohlinge" in issue


def test_bdmv_on_dvd_targets_check_dvd_write_not_bd_write():
    """bdmv_on_dvd5/9 werden auf einem DVD-Rohling gebrannt - die BD-
    Schreibfähigkeit des Laufwerks ist hier irrelevant."""
    medium = get_target_medium("bdmv_on_dvd5")
    caps = DriveCapabilities(dvd_write=True, bd_r=False, bd_re=False)
    assert target_medium_capability_issue(medium, caps) is None


def test_unknown_drive_capabilities_never_hard_block_only_bdxl_warns():
    medium = get_target_medium("bd25")
    assert target_medium_capability_issue(medium, None) is None
    bdxl_medium = get_target_medium("bd100")
    issue = target_medium_capability_issue(bdxl_medium, None)
    assert issue is not None and "nicht bekannt" in issue.lower()


def test_bdmv_authoring_unavailable_blocks_every_bdmv_target_regardless_of_drive():
    caps = DriveCapabilities(bd_r=True, bd_re=True, bd_xl=True, dvd_write=True)
    for medium_id in ("bdmv_on_dvd5", "bdmv_on_dvd9", "bd25", "bd50", "bd100", "bd128"):
        medium = get_target_medium(medium_id)
        issue = target_medium_capability_issue(medium, caps, bdmv_authoring_available=False)
        assert issue is not None
        assert "BDMV-Authoring" in issue


def test_dvd_video_targets_are_unaffected_by_bdmv_authoring_availability():
    for medium_id in ("dvd5", "dvd9"):
        medium = get_target_medium(medium_id)
        assert target_medium_capability_issue(
            medium, DriveCapabilities(dvd_write=True), bdmv_authoring_available=False,
        ) is None
