"""Regression tests for durable, platform-appropriate settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import settings as settings_module
from src.config.settings import AppSettings, BurnSettings


@pytest.mark.parametrize(
    ("platform_name", "expected"),
    [("Windows", "D:"), ("Linux", "/dev/sr0"), ("Darwin", "/dev/sr0")],
)
def test_default_burn_device_matches_platform(monkeypatch, platform_name, expected):
    monkeypatch.setattr(settings_module.platform, "system", lambda: platform_name)

    assert BurnSettings().default_device == expected
    assert AppSettings().burn.default_device == expected


def test_settings_unicode_round_trip(tmp_path: Path):
    path = tmp_path / "Einstellungen_日本.json"
    original = AppSettings(language="de-Ş日本")
    original.sound.custom_sound_path = r"C:\Musik\Şarkı_日本.wav"

    original.save(path)
    loaded = AppSettings.load(path)

    assert loaded.language == original.language
    assert loaded.sound.custom_sound_path == original.sound.custom_sound_path
    # Die Datei muss echtes UTF-8 sein, nicht die ANSI-Codepage des Systems:
    # ein blosser decode()-Aufruf ohne Zusicherung hat das nicht belegt.
    payload = json.loads(path.read_bytes().decode("utf-8"))
    assert payload["language"] == original.language


def test_settings_failed_replace_keeps_previous_file(tmp_path: Path, monkeypatch):
    path = tmp_path / "settings.json"
    AppSettings(language="de").save(path)

    def fail_replace(_source, _target):
        raise OSError("simulierter Replace-Fehler")

    monkeypatch.setattr(settings_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="Replace-Fehler"):
        AppSettings(language="en").save(path)

    assert AppSettings.load(path).language == "de"
    assert list(tmp_path.glob(".settings.json.*.tmp")) == []


@pytest.mark.parametrize("invalid_json", ["", "{nicht: gueltig}"])
def test_corrupt_settings_fall_back_to_defaults_without_deleting_file(
    tmp_path: Path, invalid_json: str
):
    path = tmp_path / "settings.json"
    path.write_text(invalid_json, encoding="utf-8")

    loaded = AppSettings.load(path)

    assert loaded.language == "de"
    assert path.read_text(encoding="utf-8") == invalid_json
