"""DriveInspector capability parsing: robust, detection-only."""
import pytest
from src.services.drive_inspector import parse_inquiry, parse_capabilities

MULTI = """INQUIRY:                [HL-DT-ST][DVDRAM GH24NSD1 ][LN00]
GET [CURRENT] CONFIGURATION:
 Mounted Media:         11h, DVD-R Sequential
 Supported Profiles: DVD-ROM, DVD-R, DVD-RW, DVD+R, DVD+RW, DVD+R DL, BD-ROM, BD-R, BD-RE
 Write Speed #0:        8.0x1385=11080KB/s
 Write Speed #1:        4.0x1385=5540KB/s
"""


def test_parse_inquiry_vendor_model_firmware():
    assert parse_inquiry(MULTI) == ("HL-DT-ST", "DVDRAM GH24NSD1", "LN00")
    assert parse_inquiry("no inquiry here") == ("", "", "")


def test_full_multi_format_drive():
    c = parse_capabilities(MULTI, drive_letter="E:")
    assert c.drive_letter == "E:" and c.vendor == "HL-DT-ST" and c.firmware == "LN00"
    assert c.dvd_read and c.dvd_write
    assert c.dvd_plus_r and c.dvd_plus_rw and c.dvd_plus_r_dl and c.dvd_dash_r and c.dvd_dash_rw
    assert c.bd_read and c.bd_r and c.bd_re and not c.bd_xl
    assert "8.0x" in c.write_speeds and "4.0x" in c.write_speeds


def test_empty_and_garbage_report_nothing():
    empty = parse_capabilities("")
    assert not any([empty.dvd_read, empty.dvd_write, empty.bd_read]) and empty.vendor == ""
    junk = parse_capabilities("Frisbee 12345 no optical media here")
    assert not junk.dvd_write and not junk.bd_read


def test_dvd_rom_read_only_has_no_write():
    c = parse_capabilities("Supported Profiles: DVD-ROM")
    assert c.dvd_read and not c.dvd_write and not c.dvd_dash_r and not c.dvd_plus_r and not c.bd_read


def test_dvd_writer_without_bluray():
    c = parse_capabilities("Profiles: DVD-ROM, DVD-R, DVD-RW, DVD+R, DVD+RW, DVD+R DL")
    assert c.dvd_write and c.dvd_plus_r_dl
    assert not c.bd_read and not c.bd_r and not c.bd_re


def test_bdxl_detected():
    c = parse_capabilities("INQUIRY: [PIONEER][BD-RW BDR][1.0]\nProfiles: BD-ROM, BD-R, BD-RE, BD-RE XL, BD-R XL")
    assert c.bd_read and c.bd_r and c.bd_re and c.bd_xl


def test_unicode_vendor_parsed():
    c = parse_capabilities("INQUIRY: [Fürör][Mödel Ω][v1]\nProfiles: DVD-ROM")
    assert c.vendor == "Fürör" and c.model == "Mödel Ω" and c.dvd_read


def test_to_dict_serialisable():
    d = parse_capabilities(MULTI).to_dict()
    assert d["dvd_plus_r_dl"] is True and isinstance(d["write_speeds"], list)


@pytest.mark.asyncio
async def test_inspect_drive_parses_tool_output(monkeypatch):
    from src.core.disc import DiscTools
    tools = object.__new__(DiscTools); tools.mediainfo = "dvd+rw-mediainfo"

    class FakeProc:
        async def communicate(self):
            return (MULTI.encode("utf-8"), b"")

    async def fake_create(*args, **kwargs):
        return FakeProc()
    monkeypatch.setattr("src.core.disc.create_hidden_subprocess", fake_create)
    caps = await tools.inspect_drive("E:")
    assert caps.drive_letter == "E:" and caps.vendor == "HL-DT-ST"
    assert caps.bd_re and caps.dvd_plus_r_dl and caps.dvd_write


@pytest.mark.asyncio
async def test_inspect_drive_handles_missing_tool(monkeypatch):
    from src.core.disc import DiscTools
    tools = object.__new__(DiscTools); tools.mediainfo = "nope"

    async def boom(*args, **kwargs):
        raise OSError("executable not found")
    monkeypatch.setattr("src.core.disc.create_hidden_subprocess", boom)
    caps = await tools.inspect_drive("E:")
    assert caps.drive_letter == "E:" and caps.vendor == "" and not caps.dvd_write   # nichts vortäuschen
