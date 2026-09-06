"""P1-8, P1-9, P2-4, P3-1: ein Supportfall muss belastbare Angaben liefern.

Die Statusleiste und die Werkzeugleiste trugen ihre Versionsnummern fest im
Markup - "FFmpeg 6.1", "yt-dlp 2024", "Python 3.12", "Windows 11". Keine
dieser Angaben wurde je gemessen. In einem Supportfall sind das falsche
Auskuenfte, und sie sehen so aus wie echte.

Dazu zwei kleinere Punkte aus demselben Umfeld: das Protokoll war aus der
Anwendung heraus nicht erreichbar, und der Rip-Bereich hatte als einziger
Disc-Bereich kein "Neu suchen".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import retrodisc_launcher
from retrodisc_launcher import RetroDiscApi, RetroDiscBridge

UI = (Path(__file__).parents[1] / "src" / "ui" / "app.html").read_text(encoding="utf-8")


def _bridge(**tools) -> RetroDiscBridge:
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = SimpleNamespace(tools=SimpleNamespace(
        ffmpeg=tools.get("ffmpeg", "ffmpeg"),
        ffprobe=tools.get("ffprobe", "ffprobe"),
        ytdlp=tools.get("ytdlp", "yt-dlp"),
    ))
    return bridge


# ── P3-1: eine Versionsquelle ─────────────────────────────────────────

def test_the_application_has_exactly_one_version_source():
    from src import __version__

    assert __version__ == "1.0.0", \
        "src/__init__.py muss die ausgelieferte Version nennen"
    assert retrodisc_launcher.APP_VERSION == __version__, \
        "Der Launcher darf keine zweite Versionsnummer fuehren"


def test_the_ui_no_longer_hardcodes_the_version():
    assert "RetroDisc v1.0.0" not in UI, \
        "Die Versionsnummer steht wieder fest im Markup"
    assert "id=\"appVersion\"" in UI
    assert "'RetroDisc v' + (env.app" in UI


# ── P1-8: keine erfundenen Angaben ────────────────────────────────────

@pytest.mark.parametrize("invented", [
    "FFmpeg 6.1", "yt-dlp 2024", "Python 3.12", "Windows 11",
])
def test_the_invented_version_strings_are_gone(invented):
    assert invented not in UI, f"Erfundene Angabe steht wieder im Markup: {invented}"


def test_get_environment_reports_measured_values(monkeypatch):
    """Alles, was gemeldet wird, muss gemessen oder ausgelesen sein."""
    calls = []

    def fake_run_hidden(cmd, **kwargs):
        calls.append(cmd)
        payload = {
            "ffmpeg": b"ffmpeg version 7.0.2-full_build Copyright (c)",
            "ffprobe": b"ffprobe version 7.0.2-full_build Copyright (c)",
            "yt-dlp": b"2026.08.31",
        }[Path(cmd[0]).stem]
        return SimpleNamespace(returncode=0, stdout=payload, stderr=b"")

    monkeypatch.setattr("src.utils.subprocesses.run_hidden", fake_run_hidden)
    env = json.loads(_bridge().get_environment())

    assert env["app"] == retrodisc_launcher.APP_VERSION
    assert re.match(r"^\d+\.\d+\.\d+", env["python"]), env["python"]
    assert env["os"], "Das Betriebssystem muss gemeldet werden"
    assert env["tools"]["ffmpeg"] == {
        "available": True, "version": "7.0.2-full_build", "path": "ffmpeg"}
    assert env["tools"]["ytdlp"]["version"] == "2026.08.31"
    assert len(calls) == 3


def test_a_missing_tool_is_reported_as_unknown_not_invented(monkeypatch):
    def blocked(cmd, **kwargs):
        raise OSError("[WinError 4551] blockiert")

    monkeypatch.setattr("src.utils.subprocesses.run_hidden", blocked)
    env = json.loads(_bridge().get_environment())

    for name in ("ffmpeg", "ffprobe", "ytdlp"):
        assert env["tools"][name]["available"] is False
        assert env["tools"][name]["version"] == ""


def test_a_failing_tool_is_not_reported_as_available(monkeypatch):
    monkeypatch.setattr(
        "src.utils.subprocesses.run_hidden",
        lambda cmd, **k: SimpleNamespace(returncode=1, stdout=b"", stderr=b"kaputt"))

    env = json.loads(_bridge().get_environment())

    assert env["tools"]["ffmpeg"]["available"] is False


def test_an_unconfigured_tool_is_not_probed(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "src.utils.subprocesses.run_hidden",
        lambda cmd, **k: calls.append(cmd) or SimpleNamespace(
            returncode=0, stdout=b"x", stderr=b""))

    env = json.loads(_bridge(ffmpeg="").get_environment())

    assert env["tools"]["ffmpeg"] == {"available": False, "version": "", "path": ""}
    assert not any(c[0] == "" for c in calls)


def test_the_versions_are_probed_only_once(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "src.utils.subprocesses.run_hidden",
        lambda cmd, **k: calls.append(cmd) or SimpleNamespace(
            returncode=0, stdout=b"ffmpeg version 7.0 x", stderr=b""))
    bridge = _bridge()

    bridge.get_environment()
    bridge.get_environment()

    assert len(calls) == 3, "Jeder Blick startet erneut Prozesse"


def test_version_probing_uses_the_hidden_runner():
    """Kein Konsolenfenster - das ist eine Produktvorgabe aus CLAUDE.md."""
    import inspect

    source = inspect.getsource(RetroDiscBridge._probe_tool_version)
    assert "run_hidden" in source
    assert "subprocess.run(" not in source


def test_the_ui_asks_for_the_real_environment():
    assert "async function loadEnvironment()" in UI
    assert "a.get_environment()" in UI
    assert "await loadEnvironment();" in UI, "Beim Start wird nichts geladen"
    assert "'unbekannt'" in UI, "Ohne Messung muss 'unbekannt' stehen"


def test_tool_badges_are_addressed_by_id_not_by_position():
    """Die Position im Strip traf die falschen Felder."""
    assert "strip.querySelectorAll('.strip-badge')" not in UI
    assert "document.getElementById('badge-' + key)" in UI


# ── P1-9: Zugriff auf das Protokoll ───────────────────────────────────

def test_open_log_folder_opens_the_configured_log_directory(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(retrodisc_launcher.os, "startfile", opened.append)
    monkeypatch.setattr(retrodisc_launcher, "LOG_DIR", tmp_path / "Logs")
    bridge = object.__new__(RetroDiscBridge)

    answer = json.loads(bridge.open_log_folder())

    assert answer["ok"] is True
    assert opened == [str(tmp_path / "Logs")]
    assert (tmp_path / "Logs").is_dir(), "Der Ordner muss notfalls angelegt werden"


def test_open_log_folder_reports_a_failure(monkeypatch):
    def explode(_path):
        raise OSError("Ordner nicht erreichbar")

    monkeypatch.setattr(retrodisc_launcher.os, "startfile", explode)
    bridge = object.__new__(RetroDiscBridge)

    answer = json.loads(bridge.open_log_folder())

    assert "error" in answer


def test_the_settings_offer_the_log_folder():
    assert "openLogFolder()" in UI
    assert "Logordner öffnen" in UI
    assert "a.open_log_folder()" in UI


def test_the_environment_names_todays_log_file(monkeypatch):
    monkeypatch.setattr(
        "src.utils.subprocesses.run_hidden",
        lambda cmd, **k: SimpleNamespace(returncode=0, stdout=b"x", stderr=b""))

    env = json.loads(_bridge().get_environment())

    assert env["logfile"] == str(retrodisc_launcher.LOG_FILE)
    assert env["logfile"].endswith(".log")


# ── Verdrahtung ───────────────────────────────────────────────────────

@pytest.mark.parametrize("method", ["get_environment", "open_log_folder"])
def test_api_proxies_the_new_methods(method):
    assert hasattr(RetroDiscApi, method)
    assert hasattr(RetroDiscBridge, method)


# ── P2-4: Rip-Bereich kann neu suchen ─────────────────────────────────

def test_the_rip_area_can_search_for_drives_again():
    rip_tab = UI.split('id="tab-rip"')[1].split('id="tab-download"')[0]

    assert "loadBurners(true)" in rip_tab, \
        "Wer die Disc erst nach dem Oeffnen einlegt, kommt sonst nicht weiter"


def test_every_disc_area_can_search_for_drives_again():
    for marker in ('id="tab-burn"', 'id="tab-disccopy"', 'id="tab-rip"'):
        section = UI.split(marker)[1][:4000]
        assert "loadBurners(true)" in section, f"{marker} hat kein Neu suchen"
