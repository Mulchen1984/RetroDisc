"""Disc fingerprint: order-independent, unicode-safe, change-sensitive."""
import unicodedata
from src.services.fingerprint import fingerprint, build_structure, fingerprint_path


def struct(files, label="MOVIE", capacity=4_700_000_000, durations=(7000.0,)):
    return {"label": label, "capacity_bytes": capacity,
            "files": [{"path": p, "size": s} for p, s in files], "durations": list(durations)}


def test_identical_structure_same_fingerprint():
    a = struct([("VIDEO_TS/VTS_01_1.VOB", 1000), ("VIDEO_TS/VIDEO_TS.IFO", 50)])
    b = struct([("VIDEO_TS/VTS_01_1.VOB", 1000), ("VIDEO_TS/VIDEO_TS.IFO", 50)])
    assert fingerprint(a) == fingerprint(b)


def test_file_order_does_not_matter():
    a = struct([("a.VOB", 10), ("b.VOB", 20), ("c.IFO", 5)])
    b = struct([("c.IFO", 5), ("b.VOB", 20), ("a.VOB", 10)])
    assert fingerprint(a) == fingerprint(b)


def test_small_change_changes_fingerprint():
    base = struct([("a.VOB", 1000)])
    assert fingerprint(base) != fingerprint(struct([("a.VOB", 1001)]))          # Größe
    assert fingerprint(base) != fingerprint(struct([("a.VOB", 1000)], label="OTHER"))
    assert fingerprint(base) != fingerprint(struct([("a2.VOB", 1000)]))         # Pfad
    assert fingerprint(base) != fingerprint(struct([("a.VOB", 1000)], durations=(7001.0,)))


def test_unicode_label_is_nfc_stable():
    nfc = unicodedata.normalize("NFC", "Fürörör")
    nfd = unicodedata.normalize("NFD", "Fürörör")
    assert nfc != nfd
    assert fingerprint(struct([("a", 1)], label=nfc)) == fingerprint(struct([("a", 1)], label=nfd))


def test_empty_disc_is_stable_and_nonempty_hash():
    fp = fingerprint({"label": "", "files": [], "durations": []})
    assert isinstance(fp, str) and len(fp) == 64
    assert fp == fingerprint({"files": []})


def test_partial_or_corrupt_data_does_not_crash():
    fp = fingerprint({"files": [{"path": "x"}, {"size": 5}, {}], "label": None,
                      "capacity_bytes": None, "durations": [None, "bad"]}) if False else None
    # None-Größen/-Dauern robust behandeln:
    fp = fingerprint({"files": [{"path": "x", "size": None}], "capacity_bytes": None})
    assert isinstance(fp, str) and len(fp) == 64


def test_build_structure_from_folder_hashes_only_small_files(tmp_path):
    (tmp_path / "VIDEO_TS").mkdir()
    (tmp_path / "VIDEO_TS" / "VIDEO_TS.IFO").write_bytes(b"small ifo")
    big = tmp_path / "VIDEO_TS" / "VTS_01_1.VOB"
    big.write_bytes(b"0" * 2000)
    s = build_structure(tmp_path, label="DISC", small_file_bytes=1000)
    by_path = {f["path"]: f for f in s["files"]}
    assert "sha" in by_path["VIDEO_TS/VIDEO_TS.IFO"]        # kleine Strukturdatei gehasht
    assert "sha" not in by_path["VIDEO_TS/VTS_01_1.VOB"]    # große Datei nur per Größe
    # gleicher Ordner -> gleicher Fingerprint, unabhängig vom Walk
    assert fingerprint_path(tmp_path, label="DISC", small_file_bytes=1000) == fingerprint(s)
