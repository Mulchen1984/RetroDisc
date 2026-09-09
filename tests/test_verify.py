"""VerifyService result aggregation and pure checks."""
import pytest
from src.services.verify import (
    VerifyResult, Check, PASS, PASS_WITH_WARNINGS, FAIL, NOT_AVAILABLE,
    size_check, hash_check, structure_check, booktype_check,
)


@pytest.mark.asyncio
async def test_verify_iso_result_maps_outcomes():
    from src.core.disc import DiscTools, DiscError
    tools = object.__new__(DiscTools)

    async def ok(_i, _d):
        return True
    tools.verify_iso = ok
    assert (await tools.verify_iso_result("x.iso", "E:")).status == PASS

    async def short(_i, _d):
        raise DiscError("Das gebrannte Medium ist kürzer als das ISO-Image.")
    tools.verify_iso = short
    res = await tools.verify_iso_result("x.iso", "E:")
    assert res.status == FAIL and res.checks[0].name == "size"

    async def mismatch(_i, _d):
        raise DiscError("Disc-Verifikation fehlgeschlagen: Prüfsummen stimmen nicht überein.")
    tools.verify_iso = mismatch
    assert (await tools.verify_iso_result("x.iso", "E:")).status == FAIL

    async def unreadable(_i, _d):
        raise DiscError("Disc-Verifikation konnte nicht gelesen werden: boom")
    tools.verify_iso = unreadable
    assert (await tools.verify_iso_result("x.iso", "E:")).status == NOT_AVAILABLE


def test_aggregate_pass_when_all_ok():
    r = VerifyResult.from_checks([Check("a", True), Check("b", True)])
    assert r.status == PASS


def test_aggregate_fail_dominates():
    r = VerifyResult.from_checks([Check("a", True), Check("b", False, "kaputt")])
    assert r.status == FAIL and "kaputt" in r.message


def test_aggregate_warning_when_no_hard_error():
    r = VerifyResult.from_checks([Check("a", True), Check("b", False, "größer", severity="warning")])
    assert r.status == PASS_WITH_WARNINGS


def test_not_available_when_no_real_checks():
    assert VerifyResult.from_checks([]).status == NOT_AVAILABLE
    assert VerifyResult.from_checks([Check("a", None)]).status == NOT_AVAILABLE


def test_size_check():
    assert size_check(1000, 1000).ok is True
    assert size_check(1000, 999).ok is False and size_check(1000, 999).severity == "error"
    warn = size_check(1000, 1100, tolerance=0)
    assert warn.ok is False and warn.severity == "warning"       # größer = Warnung, kein Datenverlust
    assert size_check(0, 100).ok is None                          # nicht vergleichbar


def test_hash_check():
    assert hash_check("abc", "abc").ok is True
    assert hash_check("abc", "xyz").ok is False
    assert hash_check("abc", None).ok is None


def test_structure_check():
    assert structure_check({"a", "b"}, {"a", "b"}).ok is True
    missing = structure_check({"a", "b"}, {"a"})
    assert missing.ok is False and missing.severity == "error"
    extra = structure_check({"a"}, {"a", "b"})
    assert extra.ok is False and extra.severity == "warning"
    assert structure_check(set(), set()).ok is None


def test_booktype_check():
    assert booktype_check("dvd_rom", "DVD-ROM").ok is True
    mism = booktype_check("dvd_rom", "DVD+R")
    assert mism.ok is False and mism.severity == "warning"        # nur Warnung, Disc ist beschrieben
    assert booktype_check("automatic", "DVD+R").ok is None
    assert booktype_check("dvd_rom", "unknown").ok is None        # nicht rücklesbar -> Warnung/none


def _make_dvd(root, *, vob_size=5000, with_bup=True):
    vts = root / "VIDEO_TS"; vts.mkdir(parents=True)
    (vts / "VIDEO_TS.IFO").write_bytes(b"ifo")
    if with_bup:
        (vts / "VIDEO_TS.BUP").write_bytes(b"bup")
    (vts / "VTS_01_1.VOB").write_bytes(b"0" * vob_size)


def _make_bd(root):
    bdmv = root / "BDMV"; (bdmv / "PLAYLIST").mkdir(parents=True); (bdmv / "STREAM").mkdir()
    (bdmv / "index.bdmv").write_bytes(b"index")
    (bdmv / "MovieObject.bdmv").write_bytes(b"mobj")
    (bdmv / "PLAYLIST" / "00000.mpls").write_bytes(b"mpls")
    (bdmv / "STREAM" / "00000.m2ts").write_bytes(b"0" * 8000)


def test_verify_disc_structure_identical_dvd_passes(tmp_path):
    from src.services.verify import verify_disc_structure, detect_disc_kind, scan_tree
    ref, tgt = tmp_path / "ref", tmp_path / "tgt"
    _make_dvd(ref); _make_dvd(tgt)
    assert detect_disc_kind(scan_tree(ref)) == "dvd"
    assert verify_disc_structure(ref, tgt).status == PASS


def test_verify_disc_structure_missing_required_fails(tmp_path):
    from src.services.verify import verify_disc_structure
    ref, tgt = tmp_path / "ref", tmp_path / "tgt"
    _make_dvd(ref)
    (tgt / "VIDEO_TS").mkdir(parents=True)
    (tgt / "VIDEO_TS" / "VTS_01_1.VOB").write_bytes(b"0" * 5000)   # IFO fehlt
    r = verify_disc_structure(tgt if False else ref, tgt, kind="dvd")
    assert r.status == FAIL and any("VIDEO_TS.IFO" in c.detail for c in r.checks)


def test_verify_disc_structure_missing_and_size_mismatch(tmp_path):
    from src.services.verify import verify_disc_structure
    ref, tgt = tmp_path / "ref", tmp_path / "tgt"
    _make_dvd(ref, vob_size=5000); _make_dvd(tgt, vob_size=4000)   # Größe weicht ab
    r = verify_disc_structure(ref, tgt)
    assert r.status == FAIL and any(c.name == "file_sizes" and c.ok is False for c in r.checks)


def test_verify_disc_structure_extra_file_is_warning(tmp_path):
    from src.services.verify import verify_disc_structure
    ref, tgt = tmp_path / "ref", tmp_path / "tgt"
    _make_dvd(ref); _make_dvd(tgt)
    (tgt / "VIDEO_TS" / "EXTRA.NFO").write_bytes(b"x")
    assert verify_disc_structure(ref, tgt).status == PASS_WITH_WARNINGS


def test_verify_disc_structure_bd_valid_and_broken(tmp_path):
    from src.services.verify import verify_disc_structure, detect_disc_kind, scan_tree
    ref, tgt = tmp_path / "ref", tmp_path / "tgt"
    _make_bd(ref); _make_bd(tgt)
    assert detect_disc_kind(scan_tree(ref)) == "bd"
    assert verify_disc_structure(ref, tgt).status == PASS
    (tgt / "BDMV" / "MovieObject.bdmv").unlink()                   # Pflichtdatei entfernt
    assert verify_disc_structure(ref, tgt).status == FAIL


def test_verify_disc_structure_hash_mismatch_same_size(tmp_path):
    from src.services.verify import verify_disc_structure
    ref, tgt = tmp_path / "ref", tmp_path / "tgt"
    _make_dvd(ref); _make_dvd(tgt)
    (tgt / "VIDEO_TS" / "VIDEO_TS.IFO").write_bytes(b"XXX")        # gleiche Größe, anderer Inhalt
    ok = verify_disc_structure(ref, tgt, compare_hash=False)
    assert ok.status == PASS                                       # ohne Hash: Größe gleich -> PASS
    bad = verify_disc_structure(ref, tgt, compare_hash=True)
    assert bad.status == FAIL and any(c.name == "file_hashes" and c.ok is False for c in bad.checks)


def test_full_result_dict_is_serialisable():
    r = VerifyResult.from_checks([size_check(1000, 1000), hash_check("a", "a"),
                                  booktype_check("dvd_rom", "DVD-ROM")])
    d = r.to_dict()
    assert d["status"] == PASS and len(d["checks"]) == 3 and all("name" in c for c in d["checks"])
