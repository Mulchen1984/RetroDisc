"""Source detection: kinds, validation, safety."""
from src.services.pipeline.source import (
    SourceDetectionService, SourceKind, iso_capabilities,
)

DET = SourceDetectionService(now=lambda: 1000.0)


def test_video_file():
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    f = d / "movie.mp4"; f.write_bytes(b"0" * 5000)
    s = DET.detect(str(f))
    assert s.kind == SourceKind.FILE and s.media_kind == "video" and s.size == 5000 and s.available


def test_dvd_folder(tmp_path):
    (tmp_path / "VIDEO_TS").mkdir(); (tmp_path / "VIDEO_TS" / "VIDEO_TS.IFO").write_bytes(b"x")
    (tmp_path / "VIDEO_TS" / "VTS_01_1.VOB").write_bytes(b"0" * 1000)
    s = DET.detect(str(tmp_path))
    assert s.kind == SourceKind.DVD_FOLDER and s.media_kind == "disc" and s.size >= 1000


def test_bluray_folder(tmp_path):
    (tmp_path / "BDMV").mkdir(); (tmp_path / "BDMV" / "index.bdmv").write_bytes(b"x")
    assert DET.detect(str(tmp_path)).kind == SourceKind.BLURAY_FOLDER


def test_iso_file_and_capabilities(tmp_path):
    iso = tmp_path / "disc.iso"; iso.write_bytes(b"0" * 2048)
    assert DET.detect(str(iso)).kind == SourceKind.ISO
    caps = iso_capabilities()
    assert caps["inspect"] and caps["detect_type"] and caps["mount"] is False   # ehrlich


def test_unknown_dir_and_file(tmp_path):
    (tmp_path / "random").mkdir()
    assert DET.detect(str(tmp_path / "random")).kind == SourceKind.UNKNOWN
    txt = tmp_path / "notes.txt"; txt.write_bytes(b"x")
    s = DET.detect(str(txt))
    assert s.kind == SourceKind.UNKNOWN and s.warnings


def test_missing_and_empty():
    assert DET.detect("/nope/does/not/exist").available is False
    assert DET.detect("").available is False


def test_optical_device_not_touched():
    for dev in ("E:", "E:\\", "/dev/sr0"):
        s = DET.detect(dev)
        assert s.kind == SourceKind.OPTICAL_DISC and s.device == dev and s.media_kind == "disc"


def test_symlink_resolved_safely(tmp_path):
    import os
    real = tmp_path / "real.mkv"; real.write_bytes(b"0" * 100)
    link = tmp_path / "link.mkv"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        return                              # kein Symlink-Support -> Test überspringen
    s = DET.detect(str(link))
    assert s.kind == SourceKind.FILE and s.path.endswith("real.mkv")   # aufgelöst
