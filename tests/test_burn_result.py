"""burn_iso_result orchestration incl. book type, without hardware."""
import pytest
from src.core.disc import DiscTools, DiscError


def _tools(monkeypatch, *, tool="dvd+rw-booktype", which=True):
    t = object.__new__(DiscTools)
    t.booktype = tool
    monkeypatch.setattr("src.core.disc.shutil.which", lambda name: (name if which else None))
    calls = {"set": [], "burned": False}

    async def fake_burn(iso, device, *, speed=None, verify=True, disc_type=None, job=None):
        calls["burned"] = True
        return True

    async def fake_run_tool(cmd, timeout=30):
        calls["set"].append(cmd)
        return "ok"

    async def fake_read(device):
        return "DVD-ROM"

    t.burn_iso = fake_burn
    t._run_tool = fake_run_tool
    t._read_book_type = fake_read
    return t, calls


@pytest.mark.asyncio
async def test_dvd_rom_bitsetting_sets_and_reads_back(monkeypatch, tmp_path):
    iso = tmp_path / "x.iso"; iso.write_bytes(b"0" * 4096)
    t, calls = _tools(monkeypatch)
    r = await t.burn_iso_result(iso, "E:", book_type="dvd_rom", media_type="DVD+R", verify=True)
    assert calls["burned"] and calls["set"]                 # Book Type gesetzt + gebrannt
    assert r.book_type_actual == "DVD-ROM" and r.verify_result == "PASS"
    assert r.written_size == 4096 and not r.warnings


@pytest.mark.asyncio
async def test_dash_media_never_attempts_bitsetting(monkeypatch, tmp_path):
    iso = tmp_path / "x.iso"; iso.write_bytes(b"0" * 10)
    t, calls = _tools(monkeypatch)
    r = await t.burn_iso_result(iso, "E:", book_type="dvd_rom", media_type="DVD-R")
    assert calls["burned"] and not calls["set"]             # DVD- kann kein Bitsetting
    assert r.warnings == []                                  # kein Fehler, einfach ignoriert


@pytest.mark.asyncio
async def test_bitsetting_requested_but_no_backend_warns(monkeypatch, tmp_path):
    iso = tmp_path / "x.iso"; iso.write_bytes(b"0" * 10)
    t, calls = _tools(monkeypatch, tool="", which=False)     # kein dvd+rw-booktype
    r = await t.burn_iso_result(iso, "E:", book_type="dvd_rom", media_type="DVD+R")
    assert calls["burned"] and not calls["set"]
    assert any("Bitsetting" in w for w in r.warnings)        # ehrliche Warnung statt Vortäuschen


@pytest.mark.asyncio
async def test_automatic_book_type_is_noop(monkeypatch, tmp_path):
    iso = tmp_path / "x.iso"; iso.write_bytes(b"0" * 10)
    t, calls = _tools(monkeypatch)
    r = await t.burn_iso_result(iso, "E:", book_type="automatic", media_type="DVD+R", verify=False)
    assert calls["burned"] and not calls["set"]
    assert r.verify_result == "NOT_AVAILABLE" and r.book_type_requested == "automatic"


@pytest.mark.asyncio
async def test_burn_failure_propagates(monkeypatch, tmp_path):
    iso = tmp_path / "x.iso"; iso.write_bytes(b"0" * 10)
    t, _ = _tools(monkeypatch)

    async def boom(*a, **k):
        raise DiscError("Brennvorgang fehlgeschlagen")
    t.burn_iso = boom
    with pytest.raises(DiscError):
        await t.burn_iso_result(iso, "E:", book_type="automatic", media_type="DVD+R")
