"""RD-04: Die gepackte EXE muss echte Pipeline-Logs schreiben.

``retrodisc_final.spec`` baut mit ``console=False``. In diesem Build ist
``sys.stdout`` ``None``, und ``configure_structlog`` wich bisher auf
``os.devnull`` aus. Damit verschwand *saemtliche* structlog-Ausgabe -
Pipeline, Downloader, Converter, Disc, Ripper -, waehrend im Logfile nur die
stdlib-Zeilen des Launchers standen. Das eigene Runtime-Gate hat das gemessen
und nicht als Befund gelesen: 19 Logzeilen fuer einen vollstaendigen Start.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import structlog

from src.utils.logging_setup import (
    FanoutStream,
    configure_structlog,
    open_log_stream,
)

# Ein Zeichen, das cp1252 nicht darstellen kann - der charmap-Fall.
UNICODE_NAME = "Björk – Jóga 【4K】.mp4"


@pytest.fixture(autouse=True)
def _restore_structlog():
    yield
    structlog.reset_defaults()


class _NoConsole:
    """Steht fuer den windowed Build: es gibt keinen stdout."""


def test_without_a_console_the_log_still_reaches_the_file(tmp_path, monkeypatch):
    """Der eigentliche Befund."""
    monkeypatch.setattr("src.utils.logging_setup.sys.stdout", None)
    logfile = tmp_path / "logs" / "retrodisc.log"

    configure_structlog(None, logfile=logfile)
    structlog.get_logger().info("Job abgeschlossen", job_id="abc", elapsed="1.0s")

    content = logfile.read_text(encoding="utf-8")
    assert "Job abgeschlossen" in content
    assert "job_id" in content


def test_without_a_console_and_without_a_file_nothing_raises(monkeypatch):
    """Der alte Rueckfall bleibt erhalten - er darf nur nicht der Normalfall sein."""
    monkeypatch.setattr("src.utils.logging_setup.sys.stdout", None)

    configure_structlog(None)
    structlog.get_logger().info("Download abgeschlossen", path=UNICODE_NAME)


def test_a_console_build_writes_to_both(tmp_path, monkeypatch):
    console = tmp_path / "console.txt"
    logfile = tmp_path / "retrodisc.log"

    with open(console, "w", encoding="utf-8") as handle:
        configure_structlog(handle, logfile=logfile)
        structlog.get_logger().info("Konvertierung", output="film.mp4")

    assert "Konvertierung" in console.read_text(encoding="utf-8")
    assert "Konvertierung" in logfile.read_text(encoding="utf-8")


def test_the_logfile_survives_an_undisplayable_character(tmp_path, monkeypatch):
    """Die charmap-Lektion darf auf dem neuen Weg nicht zurueckkehren."""
    monkeypatch.setattr("src.utils.logging_setup.sys.stdout", None)
    logfile = tmp_path / "retrodisc.log"

    configure_structlog(None, logfile=logfile)
    structlog.get_logger().info("Download abgeschlossen", path=UNICODE_NAME)

    assert "Download abgeschlossen" in logfile.read_text(encoding="utf-8")


def test_the_log_is_appended_not_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.logging_setup.sys.stdout", None)
    logfile = tmp_path / "retrodisc.log"
    logfile.write_text("aeltere Sitzung\n", encoding="utf-8")

    configure_structlog(None, logfile=logfile)
    structlog.get_logger().info("Neue Sitzung")

    content = logfile.read_text(encoding="utf-8")
    assert "aeltere Sitzung" in content
    assert "Neue Sitzung" in content


def test_the_logfile_parent_is_created(tmp_path):
    stream = open_log_stream(tmp_path / "tief" / "logs" / "retrodisc.log")
    stream.close()

    assert (tmp_path / "tief" / "logs" / "retrodisc.log").is_file()


# ── FanoutStream: ein kaputter Strom darf die anderen nicht mitreissen ─

def test_a_broken_stream_does_not_stop_the_others():
    class Broken:
        def write(self, _data):
            raise ValueError("I/O operation on closed file")

        def flush(self):
            raise ValueError("closed")

    class Good:
        def __init__(self):
            self.written = []

        def write(self, data):
            self.written.append(data)

        def flush(self):
            pass

    good = Good()
    fan = FanoutStream([Broken(), good])

    fan.write("wichtige Zeile\n")
    fan.flush()

    assert good.written == ["wichtige Zeile\n"]


def test_fanout_ignores_none_streams():
    class Good:
        def __init__(self):
            self.written = []

        def write(self, data):
            self.written.append(data)

        def flush(self):
            pass

    good = Good()
    fan = FanoutStream([None, good, None])
    fan.write("x")

    assert good.written == ["x"]


# ── Der Launcher muss die Datei wirklich uebergeben ───────────────────

def test_launcher_hands_the_logfile_to_structlog():
    source = (Path(__file__).parents[1] / "retrodisc_launcher.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "configure_structlog"
    ]

    assert calls, "configure_structlog wird im Launcher nicht mehr aufgerufen"
    assert any(kw.arg == "logfile" for call in calls for kw in call.keywords), \
        "Ohne logfile= protokolliert der windowed Build wieder ins Leere"


def test_launcher_uses_one_logfile_for_both_systems():
    """stdlib und structlog duerfen nicht in verschiedene Dateien schreiben."""
    source = (Path(__file__).parents[1] / "retrodisc_launcher.py").read_text(encoding="utf-8")

    assert "configure_structlog(_STDOUT, logfile=LOG_FILE)" in source
    assert "logging.FileHandler(LOG_FILE" in source
