"""RD-01/RD-02: Der Nutzer muss sein Ergebnis sehen und oeffnen koennen.

Das Backend kannte den Ausgabepfad immer schon. Gepruft wird hier, dass er
den Nutzer auch erreicht: als Datei- und Pfadangabe in der Jobzeile, ueber
einen Knopf, der die Datei oeffnet, und ueber einen Ordnerknopf, der nicht
mehr blind in ``output_dir`` zeigt. Der Downloadfall ist der Kern: Downloads
liegen unter ``download_dir``, und genau dort hat der alte, feste Griff auf
``output_dir`` den Nutzer im falschen Ordner stehen lassen.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import retrodisc_launcher
from retrodisc_launcher import RetroDiscApi, RetroDiscBridge

UI_HTML = Path(__file__).parents[1] / "src" / "ui" / "app.html"


def _bridge(rows, output_dir: Path) -> RetroDiscBridge:
    """Bridge ohne Konstruktor - nur mit dem, was diese Methoden anfassen."""
    bridge = object.__new__(RetroDiscBridge)
    bridge.get_queue = lambda: json.dumps(rows)
    bridge.settings = SimpleNamespace(
        directories=SimpleNamespace(output_dir=output_dir)
    )
    return bridge


def _row(job_id, output=None, created="2026-09-06T12:00:00", **extra):
    row = {"id": job_id, "created": created, "output": output,
           "download": None, "state": "done"}
    row.update(extra)
    return row


@pytest.fixture()
def opened(monkeypatch):
    """Faengt os.startfile ab; der Test soll nichts wirklich oeffnen."""
    calls: list[str] = []
    monkeypatch.setattr(retrodisc_launcher.os, "startfile", calls.append)
    return calls


# ── RD-01: Datei oeffnen ──────────────────────────────────────────────

def test_open_job_file_opens_exactly_that_jobs_file(tmp_path, opened):
    target = tmp_path / "Videos" / "Konzert.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    bridge = _bridge([_row("job-1", str(target))], tmp_path / "Videos")

    assert json.loads(bridge.open_job_file("job-1")) == {"ok": True}
    assert opened == [str(target)]


def test_open_job_file_reports_a_job_without_a_result(tmp_path, opened):
    bridge = _bridge([_row("job-1", None)], tmp_path)

    answer = json.loads(bridge.open_job_file("job-1"))

    assert "error" in answer
    assert "noch keine Datei" in answer["error"]
    assert opened == []


def test_open_job_file_reports_a_deleted_result(tmp_path, opened):
    missing = tmp_path / "weg.mp4"
    bridge = _bridge([_row("job-1", str(missing))], tmp_path)

    answer = json.loads(bridge.open_job_file("job-1"))

    assert "error" in answer
    assert str(missing) in answer["error"]
    assert opened == []


# ── RD-02: Ordner oeffnen folgt dem Auftrag, nicht der Einstellung ────

def test_open_output_folder_follows_a_download_out_of_the_output_tree(tmp_path, opened):
    """Der eigentliche Befund: Downloads liegen nicht in output_dir."""
    configured_output = tmp_path / "Videos"
    configured_output.mkdir()
    download = tmp_path / "Downloads" / "job-1" / "Video.mp4"
    download.parent.mkdir(parents=True)
    download.write_bytes(b"x")
    bridge = _bridge([_row("job-1", str(download))], configured_output)

    answer = json.loads(bridge.open_output_folder())

    assert answer["ok"] is True
    assert opened == [str(download.parent)]
    assert opened != [str(configured_output)]


def test_open_output_folder_takes_the_newest_job_with_a_result(tmp_path, opened):
    older = tmp_path / "alt" / "a.mp4"
    newer = tmp_path / "neu" / "b.mp4"
    for path in (older, newer):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x")
    # get_queue liefert absteigend nach Erstellungszeit; das juengste zuerst.
    rows = [_row("job-2", str(newer), created="2026-09-06T13:00:00"),
            _row("job-1", str(older), created="2026-09-06T12:00:00")]
    bridge = _bridge(rows, tmp_path / "Videos")

    bridge.open_output_folder()

    assert opened == [str(newer.parent)]


def test_open_output_folder_skips_results_whose_folder_is_gone(tmp_path, opened):
    survivor = tmp_path / "da" / "a.mp4"
    survivor.parent.mkdir(parents=True)
    survivor.write_bytes(b"x")
    rows = [_row("job-2", str(tmp_path / "geloescht" / "b.mp4"),
                 created="2026-09-06T13:00:00"),
            _row("job-1", str(survivor), created="2026-09-06T12:00:00")]
    bridge = _bridge(rows, tmp_path / "Videos")

    bridge.open_output_folder()

    assert opened == [str(survivor.parent)]


def test_open_output_folder_falls_back_to_the_configured_folder(tmp_path, opened):
    configured_output = tmp_path / "Videos"
    bridge = _bridge([_row("job-1", None)], configured_output)

    answer = json.loads(bridge.open_output_folder())

    assert answer["ok"] is True
    assert opened == [str(configured_output)]
    assert configured_output.is_dir(), "Der Rueckfallordner muss angelegt werden"


def test_latest_output_dir_survives_a_broken_queue(tmp_path, caplog):
    configured_output = tmp_path / "Videos"
    bridge = _bridge([], configured_output)

    def explode():
        raise RuntimeError("Historie nicht lesbar")

    bridge.get_queue = explode

    assert bridge._latest_output_dir() == configured_output


# ── Verdrahtung: UI -> RetroDiscApi -> RetroDiscBridge ────────────────

def test_api_proxies_open_job_file():
    assert hasattr(RetroDiscApi, "open_job_file")
    assert hasattr(RetroDiscBridge, "open_job_file")


def test_job_row_shows_name_path_and_both_buttons():
    ui = UI_HTML.read_text(encoding="utf-8")

    assert "baseName(j.output)" in ui, "Der Dateiname muss eigenstaendig erscheinen"
    assert "<strong>Pfad:</strong>" in ui, "Der vollstaendige Pfad muss erscheinen"
    assert "openJobFolder(this.dataset.job,'output')" in ui
    assert "openJobFile(this.dataset.job)" in ui
    assert "a.open_job_file(jobId)" in ui


def test_base_name_helper_handles_windows_paths():
    """Der Dateiname wird aus dem Pfad abgeleitet, nicht vom Backend geholt."""
    ui = UI_HTML.read_text(encoding="utf-8")
    assert "function baseName(p){ return String(p||'').split(/[\\\\/]/).pop(); }" in ui
