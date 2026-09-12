"""Regressionstests für RetroDiscBridge.shutdown() - den zentralen,
idempotenten Cleanup-Pfad für Cmd+Q, Schließen-Kreuz und normalen App-Exit.

Hintergrund (siehe RetroDiscBridge.shutdown()-Docstring in
retrodisc_launcher.py): Cmd+Q lief auf macOS bisher NIE durch main()s
finally-Block, weil pywebviews should_close() bei Cmd+Q über
applicationShouldTerminate_ aufgerufen wird und AppKit den Prozess danach
über sein eigenes exit() beendet - ein laufender mpv-Prozess und ein
gemountetes Vorschau-ISO blieben dadurch real verwaist zurück (siehe
"Bodo Schäfer"-Session, in der genau das reproduziert wurde).

Der Fix hängt dieselbe shutdown()-Methode zusätzlich an
window.events.closing (läuft synchron für BEIDE Beendigungswege, siehe
main()). Ein echtes pywebview-Fenster mit echtem NSApplication-Runloop
lässt sich in pytest nicht sinnvoll aufbauen (kein GUI-Test irgendwo sonst
im Projekt) - deshalb wird hier:

1. Die Verdrahtung (window.events.closing += bridge.shutdown) per
   Quelltext-Prüfung abgesichert, damit ein versehentliches Entfernen
   sofort auffällt.
2. shutdown() selbst vollständig real geprüft: echter mpv-Prozess wird
   real beendet, ein echtes gemountetes ISO wird real ausgehängt,
   mehrfacher Aufruf ist ein sicherer, schneller No-Op.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import retrodisc_launcher as launcher
from retrodisc_launcher import RetroDiscBridge
from src.config.settings import AppSettings

pytestmark = [
    pytest.mark.skipif(shutil.which("mpv") is None, reason="mpv ist in dieser Umgebung nicht installiert"),
    pytest.mark.skipif(shutil.which("mkisofs") is None, reason="mkisofs ist in dieser Umgebung nicht installiert"),
]

_SECTOR_SIZE = 2048
_TT_SRPT_POINTER_OFFSET = 0xC4


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    """Wie tests/test_player_bridge.py::bridge, aber OHNE eigenes
    Cleanup im finally - die Tests hier rufen bridge.shutdown() selbst
    auf und prüfen genau dessen Wirkung. Ein zweiter Cleanup-Versuch nach
    einem bereits erfolgten shutdown() würde auf dem gestoppten Loop nur
    unnötig auf Timeouts warten (siehe Idempotenz-Test unten - genau das
    darf NICHT passieren)."""
    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output", "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }, library_db_path=tmp_path / ".retrodisc" / "library.db").save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    b = RetroDiscBridge()
    b.pipeline._is_running = True
    try:
        yield b
    finally:
        if not b._shutdown_done:
            try:
                b._async(b.player.close()).result(timeout=10)
            except Exception:
                pass
            b._loop.call_soon_threadsafe(b._loop.stop)
        b._thread.join(timeout=5)


def _real_vob(path, duration=1, size="352x288"):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=25",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-c:v", "mpeg2video", "-c:a", "ac3", "-f", "vob", str(path)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return path


def _build_video_ts_ifo(entries, tt_srpt_sector=1):
    header = bytearray(_SECTOR_SIZE)
    header[0:12] = b"DVDVIDEO-VMG"
    header[_TT_SRPT_POINTER_OFFSET:_TT_SRPT_POINTER_OFFSET + 4] = tt_srpt_sector.to_bytes(4, "big")
    table = bytearray()
    table += len(entries).to_bytes(2, "big")
    table += b"\x00\x00"
    table += (0).to_bytes(4, "big")
    for vts_number, vts_ttn, chapter_count, angle_count in entries:
        entry = bytearray(12)
        entry[0] = 0x03
        entry[1] = angle_count
        entry[2:4] = chapter_count.to_bytes(2, "big")
        entry[6] = vts_number
        entry[7] = vts_ttn
        table += entry
    return bytes(header) + b"\x00" * (tt_srpt_sector * _SECTOR_SIZE - len(header)) + bytes(table)


def _real_video_ts(tmp_path, entries):
    root = tmp_path / "device" / "VIDEO_TS"
    root.mkdir(parents=True)
    (root / "VIDEO_TS.IFO").write_bytes(_build_video_ts_ifo(entries))
    return root.parent


def _iso_from(content_dir, out_iso):
    result = subprocess.run(["mkisofs", "-V", "TESTDISC", "-o", str(out_iso), "-udf", str(content_dir)],
                            capture_output=True)
    assert result.returncode == 0, result.stderr
    return out_iso


# ─── Verdrahtung: window.events.closing hängt an bridge.shutdown ──────────

def test_closing_event_is_wired_to_bridge_shutdown():
    """Quelltext-Regressionsschutz: ohne echtes GUI-Fenster/NSApplication-
    Runloop lässt sich der Cmd+Q-Pfad selbst nicht end-to-end auslösen -
    dieser Test stellt sicher, dass die Verdrahtung, die den ursprünglichen
    Bug behebt, nicht versehentlich wieder verschwindet."""
    source = launcher.__file__
    with open(source, encoding="utf-8") as f:
        text = f.read()
    assert re.search(r"window\.events\.closing\s*\+=\s*bridge\.shutdown", text), (
        "window.events.closing ist nicht mehr an bridge.shutdown gehängt - "
        "Cmd+Q würde den Player/ISO-Cleanup wieder überspringen (siehe "
        "RetroDiscBridge.shutdown()-Docstring)."
    )


# ─── shutdown() beendet einen wirklich laufenden mpv-Prozess ──────────────

@pytest.mark.asyncio
async def test_shutdown_terminates_a_running_mpv_process(bridge, tmp_path):
    clip = _real_vob(tmp_path / "clip.mp4", duration=3)
    result = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))
    assert result.get("error") is None, result

    mpv_pid = bridge.player._proc.pid
    assert _pid_alive(mpv_pid), "mpv sollte nach player_open() laufen"

    bridge.shutdown()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and _pid_alive(mpv_pid):
        time.sleep(0.1)
    assert not _pid_alive(mpv_pid), "mpv-Prozess ist nach shutdown() verwaist zurückgeblieben"


def _pid_alive(pid: int) -> bool:
    import os
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


# ─── shutdown() hängt ein gemountetes Vorschau-ISO wieder aus ─────────────

@pytest.mark.asyncio
async def test_shutdown_unmounts_a_mounted_preview_iso(bridge, tmp_path):
    device = _real_video_ts(tmp_path, [(1, 1, 2, 1)])
    _real_vob(device / "VIDEO_TS" / "VTS_01_1.VOB")
    iso_path = _iso_from(device, tmp_path / "dvd.iso")

    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "dvd_iso", "path": str(iso_path), "title_index": 0})))
    assert result.get("error") is None, result
    mount_root = bridge._player_mount.root
    assert mount_root.is_dir()

    bridge.shutdown()

    assert not mount_root.exists(), "ISO ist nach shutdown() nicht ausgehängt worden"


# ─── Idempotenz: zweiter Aufruf ist ein schneller, sicherer No-Op ─────────

@pytest.mark.asyncio
async def test_shutdown_is_idempotent(bridge, tmp_path, caplog):
    clip = _real_vob(tmp_path / "clip.mp4")
    json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))

    bridge.shutdown()

    start = time.monotonic()
    bridge.shutdown()   # zweiter Aufruf - darf NICHT erneut auf die
                        # internen 3/5/10/15s-Timeouts des gestoppten
                        # Async-Loops laufen (siehe shutdown()-Docstring)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"zweiter shutdown()-Aufruf war nicht idempotent ({elapsed:.1f}s statt <1s)"


@pytest.mark.asyncio
async def test_shutdown_logs_completion(bridge, tmp_path, caplog):
    caplog.set_level("INFO")
    clip = _real_vob(tmp_path / "clip.mp4")
    json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(clip)})))

    bridge.shutdown()

    assert any("Shutdown abgeschlossen" in r.message for r in caplog.records), (
        "shutdown() hat keinen Abschluss-Log-Eintrag hinterlassen - ohne "
        "diesen lässt sich ein erfolgreicher Cmd+Q-Cleanup nicht von einem "
        "stillschweigend übersprungenen unterscheiden."
    )


# ─── Maßgeblicher End-zu-Ende-Test: echtes Fenster, echtes Cmd+Q ──────────

@pytest.mark.skipif(sys.platform != "darwin", reason="AppKit.NSApplication.terminate_ gibt es nur auf macOS")
def test_real_cmd_q_terminates_mpv_and_unmounts_iso(tmp_path, monkeypatch, caplog):
    """Löst Cmd+Q NICHT über Tastatur-/Fenster-Simulation aus (auf einem
    Entwicklungsrechner unzuverlässig: Fensterfokus kann jederzeit an eine
    andere App wandern, siehe Beobachtung während der manuellen
    Verifikation dieses Fixes), sondern über exakt dieselbe Objective-C-
    Aktion, an die pywebview Cmd+Q bindet:
    AppKit.NSApplication.terminate_ (siehe webview/platforms/cocoa.py,
    dort an die Taste 'q' gebunden). Das ist deterministisch und prüft
    genau den Mechanismus, der den ursprünglichen Bug verursacht hat
    (windowWillClose_ läuft bei Cmd+Q NICHT, nur should_close() ->
    window.events.closing.set() - siehe RetroDiscBridge.shutdown()).

    Ein echtes pywebview-Fenster mit echtem NSApplication-Runloop läuft in
    einem Kindprozess, damit ein hängender Runloop den Testlauf nicht
    blockiert (harter Timeout von außen statt pytest-internem Timeout)."""
    script = tmp_path / "repro.py"
    marker_ok = tmp_path / "mpv_pid.txt"
    script.write_text(f'''
import json, subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
import retrodisc_launcher as launcher
from retrodisc_launcher import RetroDiscBridge
from src.config.settings import AppSettings

tmp = Path({str(tmp_path)!r})
AppSettings._default_config_path = staticmethod(lambda: tmp / "settings.json")
AppSettings(directories={{"output_dir": tmp / "output", "download_dir": tmp / "downloads",
                          "temp_dir": tmp / "temp"}},
            library_db_path=tmp / ".retrodisc" / "library.db").save()
launcher.check_tools = lambda: {{}}
from src.services.library import MediaLibrary
MediaLibrary.open = lambda self: None

clip = tmp / "clip.mp4"
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    "-f", "lavfi", "-i", "testsrc=duration=20:size=320x240:rate=25",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)],
    capture_output=True, check=True)

import webview
bridge = RetroDiscBridge()
window = webview.create_window(title="RetroDisc-Test", url=str(Path("src/ui/app.html").resolve()),
                                js_api=bridge, width=900, height=640)
bridge.window = window
window.events.closing += bridge.shutdown

def drive():
    time.sleep(2)
    result = json.loads(bridge.player_open(json.dumps({{"kind": "file", "path": str(clip)}})))
    assert result.get("error") is None, result
    Path({str(marker_ok)!r}).write_text(str(bridge.player._proc.pid))
    time.sleep(1)
    import AppKit
    AppKit.NSApplication.sharedApplication().terminate_(None)

threading.Thread(target=drive, daemon=True).start()
webview.start()
''')
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True, text=True, timeout=30,
    )
    assert marker_ok.is_file(), (
        "player_open() im Kindprozess ist nie erfolgreich durchgelaufen "
        f"(stdout={proc.stdout!r} stderr={proc.stderr[-800:]!r})"
    )
    mpv_pid = int(marker_ok.read_text())

    assert "Shutdown abgeschlossen" in proc.stdout + proc.stderr, (
        "Cmd+Q (AppKit.terminate_) hat keinen Shutdown-Log-Eintrag erzeugt - "
        "window.events.closing ist vermutlich nicht mehr an bridge.shutdown gehängt."
    )
    assert not _pid_alive(mpv_pid), (
        "mpv-Prozess ist nach echtem Cmd+Q (terminate_) verwaist zurückgeblieben"
    )
