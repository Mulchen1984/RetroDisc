"""DVD book type / bitsetting: classification, capability gating, args, parsing."""
import pytest
from src.services.booktype import (
    classify_media, supports_bitsetting, bitsetting_available, booktype_options,
    booktype_command, parse_book_type, BurnResult,
)


@pytest.mark.parametrize("profile,expected", [
    ("DVD-R Sequential", "DVD-R"),
    ("DVD-RW Restricted Overwrite", "DVD-RW"),
    ("DVD+R", "DVD+R"),
    ("DVD+RW", "DVD+RW"),
    ("DVD+R DL", "DVD+R DL"),
    ("DVD+R Double Layer", "DVD+R DL"),
    ("DVD-ROM", "DVD-ROM"),
    ("BD-R SRM", "BD-R"),
    ("BD-RE", "BD-RE"),
    ("", "unknown"),
    ("Frisbee", "unknown"),
])
def test_classify_media(profile, expected):
    assert classify_media(profile) == expected


def test_bitsetting_only_for_plus_family_and_only_with_tool():
    assert supports_bitsetting("DVD+R") and supports_bitsetting("DVD+R DL") and supports_bitsetting("DVD+RW")
    assert not supports_bitsetting("DVD-R") and not supports_bitsetting("BD-R")
    # Capability = Medium UND Backend
    assert bitsetting_available("DVD+R", tool_available=True)
    assert not bitsetting_available("DVD+R", tool_available=False)   # kein Tool -> nicht anbieten
    assert not bitsetting_available("DVD-R", tool_available=True)    # falsches Medium


def test_booktype_options_gated():
    assert booktype_options("DVD+R", True) == ["automatic", "native", "dvd_rom"]
    assert booktype_options("DVD+R", False) == ["automatic"]        # Tool fehlt
    assert booktype_options("DVD-R", True) == ["automatic"]         # Medium kann es nicht


def test_booktype_command_only_for_real_change():
    assert booktype_command("dvd+rw-booktype", "D:", "dvd_rom", "DVD+R") == [
        "dvd+rw-booktype", "-dvd-rom-spec", "-media", "D:"]
    assert booktype_command("dvd+rw-booktype", "D:", "automatic", "DVD+R") is None
    assert booktype_command("dvd+rw-booktype", "D:", "native", "DVD+R") is None
    assert booktype_command("dvd+rw-booktype", "D:", "dvd_rom", "DVD-R") is None   # nicht bitsettbar


@pytest.mark.parametrize("output,expected", [
    ('Legacy book type: "DVD-ROM"', "DVD-ROM"),
    ("current Book Type: DVD+R", "DVD+R"),
    ("book type = DVD-ROM", "DVD-ROM"),
    ("keine Angabe", "unknown"),
    ("", "unknown"),
])
def test_parse_book_type(output, expected):
    assert parse_book_type(output) == expected


def test_burn_result_dict_defaults_are_honest():
    r = BurnResult(media_type="DVD+R", book_type_requested="dvd_rom", book_type_actual="DVD-ROM",
                   burn_speed="8x", written_size=4700372992, verify_result="PASS")
    d = r.to_dict()
    assert d["book_type_actual"] == "DVD-ROM" and d["verify_result"] == "PASS"
    assert BurnResult().verify_result == "NOT_AVAILABLE"    # nichts vortäuschen
