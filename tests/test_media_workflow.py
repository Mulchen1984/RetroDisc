from pathlib import Path

from src.config.settings import AppSettings, DirectorySettings


def test_default_media_workflow_is_under_videos(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    d = DirectorySettings()
    root = tmp_path / "Videos" / "RetroDisc"

    assert d.media_root == root
    assert d.download_dir == root / "01_Quellen" / "Downloads"
    assert d.rip_dir == root / "01_Quellen" / "Rips"
    assert d.output_dir == root / "02_Konvertiert"
    assert d.trim_dir == root / "03_Bearbeitet" / "Geschnitten"
    assert d.merge_dir == root / "03_Bearbeitet" / "Zusammengefuegt"
    assert d.upscale_dir == root / "03_Bearbeitet" / "Hochskaliert"
    assert d.interpolate_dir == root / "03_Bearbeitet" / "Framerate"
    assert d.subtitle_dir == root / "03_Bearbeitet" / "Untertitel"
    assert d.highlights_dir == root / "03_Bearbeitet" / "Highlights"
    assert d.dvd_dir == root / "04_Disc" / "DVD"
    assert d.iso_dir == root / "04_Disc" / "ISO"
    assert d.temp_dir == root / "_temp"


def test_ensure_directories_creates_complete_workflow(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    settings = AppSettings()
    settings.ensure_directories()

    d = settings.directories
    for path in (
        d.media_root,
        d.download_dir,
        d.rip_dir,
        d.output_dir,
        d.trim_dir,
        d.merge_dir,
        d.upscale_dir,
        d.interpolate_dir,
        d.subtitle_dir,
        d.highlights_dir,
        d.dvd_dir,
        d.iso_dir,
        d.temp_dir,
    ):
        assert path.is_dir()


def test_legacy_defaults_migrate_but_custom_paths_do_not(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    d = DirectorySettings(
        output_dir=tmp_path / "Videos" / "RetroDisc",
        download_dir=tmp_path / "Downloads" / "RetroDisc",
    )
    assert d.migrate_legacy_defaults() is True
    assert d.output_dir == tmp_path / "Videos" / "RetroDisc" / "02_Konvertiert"
    assert d.download_dir == tmp_path / "Videos" / "RetroDisc" / "01_Quellen" / "Downloads"

    custom = DirectorySettings(
        output_dir=tmp_path / "my-output",
        download_dir=tmp_path / "my-downloads",
    )
    assert custom.migrate_legacy_defaults() is False
    assert custom.output_dir == tmp_path / "my-output"
    assert custom.download_dir == tmp_path / "my-downloads"
