"""P2 #6/#7 und P1 #4: eine Wurzel, eine Konfiguration, eine Logdatei pro Tag.

Zwei Befunde stecken hier zusammen. Erstens umgingen zwei Komponenten die
zentrale Konfiguration: die Bibliothek legte ihre Datenbank selbst nach
``~/.retrodisc``, und der DVD-Workflow bekam seinen Temp-Ordner nur im
Konstruktor. Zweitens war der Logordner fest verdrahtet und wanderte nicht
mit, wenn der Nutzer den Medienordner verlegte.
"""

from __future__ import annotations

import ast
import datetime
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import retrodisc_launcher
from retrodisc_launcher import RetroDiscApi, RetroDiscBridge, log_file_for
from src.config.settings import (
    LIBRARY_DB_NAME,
    MEDIA_SUBFOLDERS,
    AppSettings,
    DirectorySettings,
)

LAUNCHER = (Path(__file__).parents[1] / "retrodisc_launcher.py").read_text(encoding="utf-8")
UI = (Path(__file__).parents[1] / "src" / "ui" / "app.html").read_text(encoding="utf-8")


# ── P2 #7: eine Wahl, vier Ordner ─────────────────────────────────────

def test_the_structure_the_user_was_promised(tmp_path):
    root = tmp_path / "Medien" / "RetroDisc"

    dirs = DirectorySettings.derived(root)

    assert dirs.media_root == root.resolve()
    assert dirs.download_dir == root.resolve() / "Downloads"
    assert dirs.output_dir == root.resolve() / "Videos"
    assert dirs.temp_dir == root.resolve() / "Temp"
    assert dirs.log_dir == root.resolve() / "Logs"


def test_the_library_lives_beside_the_folders_not_inside_them(tmp_path):
    dirs = DirectorySettings.derived(tmp_path / "Medien")

    assert dirs.library_db == (tmp_path / "Medien").resolve() / LIBRARY_DB_NAME


def test_set_media_root_creates_every_folder_on_disk(tmp_path):
    settings = AppSettings()
    root = tmp_path / "D_Medien"

    settings.set_media_root(root)

    for name in MEDIA_SUBFOLDERS.values():
        assert (root / name).is_dir(), f"{name} wurde nicht angelegt"


def test_managed_directories_and_the_subfolder_table_stay_in_sync(tmp_path):
    dirs = DirectorySettings.derived(tmp_path / "m")

    managed = {p.name for p in dirs.managed_directories()}

    assert managed == set(MEDIA_SUBFOLDERS.values())


def test_a_relative_media_root_is_rejected_or_anchored(tmp_path):
    """resolve_user_path darf keinen Pfad ohne Anker durchlassen."""
    dirs = DirectorySettings.derived("Medien")

    assert dirs.media_root.is_absolute()


def test_ensure_directories_now_covers_the_log_folder(tmp_path):
    settings = AppSettings()
    settings.directories = DirectorySettings.derived(tmp_path / "m")

    settings.ensure_directories()

    assert settings.directories.log_dir.is_dir()


def test_individually_configured_folders_survive_a_normal_save(tmp_path):
    """Nur set_media_root ersetzt die Einzelordner - Speichern nicht."""
    settings = AppSettings()
    settings.directories.output_dir = tmp_path / "woanders"

    reloaded = AppSettings.model_validate(settings.model_dump(mode="json"))

    assert reloaded.directories.output_dir == (tmp_path / "woanders").resolve()


# ── Die Bridge-Methode ────────────────────────────────────────────────

def test_bridge_set_media_root_reports_what_it_created(tmp_path, monkeypatch):
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = AppSettings()
    applied = []
    bridge._apply_runtime_settings = lambda: applied.append(True)
    monkeypatch.setattr(AppSettings, "save", lambda self, path=None: None)

    answer = json.loads(bridge.set_media_root(str(tmp_path / "Medien")))

    assert answer["ok"] is True
    assert answer["media_root"] == str((tmp_path / "Medien").resolve())
    assert len(answer["created"]) == len(MEDIA_SUBFOLDERS)
    assert applied == [True], "Laufende Dienste muessen die neue Wurzel bekommen"
    assert bridge.settings.directories.output_dir == (tmp_path / "Medien").resolve() / "Videos"


def test_bridge_set_media_root_reports_an_unusable_folder(tmp_path, monkeypatch):
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = AppSettings()

    answer = json.loads(bridge.set_media_root("   "))

    assert "error" in answer


def test_api_proxies_set_media_root():
    assert hasattr(RetroDiscApi, "set_media_root")
    assert hasattr(RetroDiscBridge, "set_media_root")


def test_ui_offers_the_choice_and_warns_before_replacing(tmp_path):
    assert "settingsMediaRoot" in UI
    assert "async function chooseMediaRoot()" in UI
    assert "a.set_media_root(picked.folder)" in UI
    assert "confirm(" in UI.split("async function chooseMediaRoot()")[1][:900], \
        "Das Ersetzen der Einzelordner muss bestaetigt werden"


# ── P2 #6: keine Komponente umgeht die Settings ───────────────────────

def test_the_library_path_comes_from_the_settings():
    source = inspect.getsource(RetroDiscBridge.__init__)

    assert "db_path=self.settings.directories.library_db" in source
    assert '".retrodisc"' not in source, \
        "Die Bibliothek darf ihren Pfad nicht mehr selbst festlegen"


def test_runtime_settings_carry_temp_dir_and_library():
    source = inspect.getsource(RetroDiscBridge._apply_runtime_settings)

    assert "self.dvd_workflow.temp_dir = directories.temp_dir" in source
    assert "directories.library_db" in source


def test_storage_info_no_longer_names_a_hardcoded_library_path():
    source = inspect.getsource(RetroDiscBridge.get_settings)

    assert "directories.library_db" in source
    assert '".retrodisc"' not in source


def test_an_existing_library_is_carried_over_once(tmp_path, monkeypatch):
    legacy = tmp_path / "home" / ".retrodisc" / "library.db"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"alter bestand")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    target = tmp_path / "Medien" / "library.db"

    RetroDiscBridge._migrate_legacy_library(target)

    assert target.read_bytes() == b"alter bestand"
    assert legacy.is_file(), "Das Original wird kopiert, nicht verschoben"


def test_an_existing_target_is_never_overwritten_by_the_migration(tmp_path, monkeypatch):
    legacy = tmp_path / "home" / ".retrodisc" / "library.db"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"alt")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    target = tmp_path / "library.db"
    target.write_bytes(b"aktuell")

    RetroDiscBridge._migrate_legacy_library(target)

    assert target.read_bytes() == b"aktuell"


# ── P1 #4: eine Logdatei pro Tag ──────────────────────────────────────

def test_the_log_file_is_named_by_the_day():
    name = log_file_for(datetime.date(2026, 9, 6)).name

    assert name == "retrodisc_2026-09-06.log"


def test_the_log_file_lives_in_the_configured_log_folder():
    assert log_file_for().parent == retrodisc_launcher.LOG_DIR


def test_two_days_do_not_share_a_file():
    first = log_file_for(datetime.date(2026, 9, 6))
    second = log_file_for(datetime.date(2026, 9, 7))

    assert first != second


def test_the_log_folder_follows_the_configured_media_root():
    """Vorher stand hier data_root()/"Logs" fest im Launcher."""
    tree = ast.parse(LAUNCHER)
    assigns = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "LOG_DIR" for t in node.targets)
    ]

    assert assigns, "LOG_DIR wird nicht mehr gesetzt"
    sources = [ast.get_source_segment(LAUNCHER, node) for node in assigns]
    assert any("directories.log_dir" in (s or "") for s in sources), \
        "Der Logordner kommt nicht aus den Einstellungen"


def test_both_logging_systems_write_the_same_dated_file():
    assert "LOG_FILE = log_file_for()" in LAUNCHER
    assert "configure_structlog(_STDOUT, logfile=LOG_FILE)" in LAUNCHER
    assert "logging.FileHandler(LOG_FILE" in LAUNCHER


def test_a_broken_settings_file_never_blocks_the_start():
    """Der Logordner wird vor allem anderen gebraucht - das darf nie werfen."""
    tree = ast.parse(LAUNCHER)
    handlers = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        and any("LOG_DIR" in (ast.get_source_segment(LAUNCHER, stmt) or "")
                for stmt in node.body)
    ]

    assert handlers, "Das Laden der Einstellungen beim Start ist nicht abgesichert"
