from pathlib import Path

from src.config.settings import AppSettings, DirectorySettings


def test_default_media_workflow_uses_one_visible_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    d = DirectorySettings()
    root = tmp_path / "Videos" / "RetroDisc"

    assert d.media_root == root
    assert d.download_dir == root
    assert d.rip_dir == root
    assert d.output_dir == root
    assert d.edited_dir == root
    assert d.disc_dir == root
    assert d.trim_dir == root
    assert d.merge_dir == root
    assert d.upscale_dir == root
    assert d.interpolate_dir == root
    assert d.subtitle_dir == root
    assert d.highlights_dir == root
    assert d.dvd_dir == root
    assert d.iso_dir == root
    assert d.temp_dir == root / "_temp"


def test_ensure_directories_creates_media_root_and_temp(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    settings = AppSettings()
    settings.ensure_directories()

    d = settings.directories
    assert d.media_root.is_dir()
    assert d.download_dir.is_dir()
    assert d.output_dir.is_dir()
    assert d.temp_dir.is_dir()
    assert d.download_dir == d.output_dir == d.media_root


def test_historical_defaults_collapse_into_common_root(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    root = tmp_path / "Videos" / "RetroDisc"
    d = DirectorySettings(
        download_dir=tmp_path / "Downloads" / "RetroDisc",
        rip_dir=root / "01_Quellen" / "Rips",
        output_dir=root / "02_Konvertiert",
        edited_dir=root / "03_Bearbeitet",
        disc_dir=root / "04_Disc",
    )

    assert d.migrate_legacy_defaults() is True
    assert d.download_dir == root
    assert d.rip_dir == root
    assert d.output_dir == root
    assert d.edited_dir == root
    assert d.disc_dir == root


def test_custom_paths_are_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    custom = DirectorySettings(
        download_dir=tmp_path / "my-downloads",
        rip_dir=tmp_path / "my-rips",
        output_dir=tmp_path / "my-output",
        edited_dir=tmp_path / "my-edits",
        disc_dir=tmp_path / "my-disc",
    )

    assert custom.migrate_legacy_defaults() is False
    assert custom.download_dir == tmp_path / "my-downloads"
    assert custom.rip_dir == tmp_path / "my-rips"
    assert custom.output_dir == tmp_path / "my-output"
    assert custom.edited_dir == tmp_path / "my-edits"
    assert custom.disc_dir == tmp_path / "my-disc"
