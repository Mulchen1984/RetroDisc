"""Windows-Bereitschaft, so weit ohne echten Windows-Rechner/-VM prüfbar
(siehe RELEASE_AUDIT_STATUS.md, Windows-Bereitschaftsblock).

Kein Wine, keine Windows-VM in dieser Entwicklungsumgebung verfügbar - das
schließt einen ECHTEN Test von Named-Pipe-Verbindungsaufbau, echtem
Mount-DiskImage/UAC-Verhalten und sichtbarer Konsolenfensterunterdrückung aus.
Diese Datei deckt genau die Teile ab, die plattformunabhängig sind:

* die Laufwerksbuchstaben-zu-Root-Pfad-Logik in
  ``RetroDiscBridge._player_open`` (reine String-/Path-Konstruktion, nie
  zuvor mit einem echten zweistelligen Laufwerksbuchstaben wie ``"E:"``
  getestet - jeder bestehende player-bridge-Test übergibt stattdessen ein
  echtes Verzeichnis);
* den ``_ThreadedPipeIO``-Adapter aus ``player.py`` (der Teil des
  Named-Pipe-Zweigs, der reine Python-Logik ist, unabhängig vom echten
  Windows-Handle);
* Dateipfade mit Leerzeichen und Sonderzeichen (Umlaute, Klammern) durch
  den regulären ``file``-Zweig.

``create_hidden_subprocess``/``run_hidden``s ``CREATE_NO_WINDOW``-Injektion
ist bereits in ``tests/test_subprocess_hardening.py`` real abgedeckt und wird
hier nicht dupliziert.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import retrodisc_launcher as launcher
from retrodisc_launcher import RetroDiscBridge
from src.config.settings import AppSettings
from src.services import player_source
from src.services.player import _ThreadedPipeIO


@pytest.fixture
def bridge(tmp_path, monkeypatch):
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
        try:
            b._async(b.player.close()).result(timeout=10)
        except Exception:
            pass
        b._loop.call_soon_threadsafe(b._loop.stop)
        b._thread.join(timeout=5)


# ─── Laufwerksbuchstaben (dvd_title/bluray_title) ──────────────────────────

@pytest.mark.parametrize("device", ["E:", "g:"])
def test_bare_drive_letter_fixup_turns_a_relative_windows_path_into_an_anchored_root(device):
    """The fix-up branch's *raison d'être* is a Windows-only, PosixPath-
    invisible distinction: PureWindowsPath('E:') means 'current directory of
    drive E' (NOT absolute), while PureWindowsPath('E:/') is the actual root
    (absolute). Verified directly with PureWindowsPath - which models real
    Windows path semantics on any host OS - because PosixPath (what Path()
    resolves to on this macOS dev machine) collapses trailing slashes and
    cannot represent this distinction at all, so running the real code
    in-process here would silently prove nothing about the Windows case."""
    from pathlib import PureWindowsPath

    assert PureWindowsPath(device).is_absolute() is False, (
        f"{device!r} is unexpectedly already absolute - the fix-up would be a no-op"
    )

    fixed = device.rstrip("\\/") + "/"  # the exact expression used in _player_open
    assert PureWindowsPath(fixed).is_absolute() is True
    assert PureWindowsPath(fixed).drive.lower() == device.rstrip(":").lower() + ":"


@pytest.mark.asyncio
@pytest.mark.parametrize("device", ["E:", "g:"])
async def test_player_open_reaches_resolve_title_for_a_bare_drive_letter(
    bridge, tmp_path, monkeypatch, device,
):
    """Confirms the branch is actually taken (resolve_title runs, the drive
    letter itself is preserved) end-to-end through the bridge - the Windows-
    only root-vs-relative distinction is covered separately above, since
    PosixPath cannot represent it."""
    captured = {}

    def fake_resolve_title(root, disc_type, title_index):
        captured["root"] = root
        return player_source.PlaybackSource(disc_type=disc_type, segments=[])

    monkeypatch.setattr(player_source, "resolve_title", fake_resolve_title)

    result = json.loads(bridge.player_open(json.dumps(
        {"kind": "dvd_title", "device": device, "title_index": 0})))

    assert captured["root"].as_posix().rstrip("/") == device.rstrip(":") + ":"
    assert result.get("error") == "Keine abspielbare Quelle angegeben."


@pytest.mark.asyncio
@pytest.mark.parametrize("device", [
    "E:\\",                       # already has a trailing separator
    "F:/",                        # already has a trailing separator
    r"\\SERVER\Share With Space",  # UNC path, not a drive letter at all
])
async def test_player_open_leaves_a_device_that_is_not_a_bare_drive_letter_untouched(
    bridge, tmp_path, monkeypatch, device,
):
    """Only the exact two-character 'X:' form is special-cased (see the test
    above). Anything else - including a drive letter that already carries
    its own separator - must reach player_source.resolve_title() as
    Path(device) unchanged; re-normalising it here would be redundant and,
    for a UNC path, actively wrong."""
    captured = {}

    def fake_resolve_title(root, disc_type, title_index):
        captured["root"] = root
        return player_source.PlaybackSource(disc_type=disc_type, segments=[])

    monkeypatch.setattr(player_source, "resolve_title", fake_resolve_title)

    bridge.player_open(json.dumps({"kind": "dvd_title", "device": device, "title_index": 0}))

    assert captured["root"] == Path(device)


# ─── _ThreadedPipeIO (Named-Pipe-Adapter, plattformunabhängige Logik) ──────

class _FakeBlockingPipeHandle:
    """Steht für ein Windows-Named-Pipe-Handle (``open(path, 'r+b',
    buffering=0)``): blockierendes readline()/write()/flush()/close(), exakt
    die Teilmenge, die _ThreadedPipeIO tatsächlich anspricht."""

    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)
        self.written: list[bytes] = []
        self.flushed = 0
        self.closed = False

    def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    def write(self, data: bytes) -> None:
        if self.closed:
            raise ValueError("write on closed handle")
        self.written.append(data)

    def flush(self) -> None:
        self.flushed += 1

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_threaded_pipe_io_readline_returns_each_queued_line_via_to_thread():
    handle = _FakeBlockingPipeHandle([b'{"event":"a"}\n', b'{"event":"b"}\n'])
    io = _ThreadedPipeIO(handle)

    assert await io.readline() == b'{"event":"a"}\n'
    assert await io.readline() == b'{"event":"b"}\n'
    assert await io.readline() == b""  # EOF, matches asyncio.StreamReader.readline()


@pytest.mark.asyncio
async def test_threaded_pipe_io_write_and_drain_reach_the_underlying_handle():
    handle = _FakeBlockingPipeHandle([])
    io = _ThreadedPipeIO(handle)

    io.write(b'{"command":["get_property","idle-active"]}\n')
    await io.drain()

    assert handle.written == [b'{"command":["get_property","idle-active"]}\n']
    assert handle.flushed == 1


@pytest.mark.asyncio
async def test_threaded_pipe_io_close_is_idempotent_and_swallows_errors():
    handle = _FakeBlockingPipeHandle([])
    io = _ThreadedPipeIO(handle)

    io.close()
    io.close()  # a second close (e.g. shutdown racing an already-closed pipe)

    assert handle.closed is True


@pytest.mark.asyncio
async def test_threaded_pipe_io_close_survives_a_handle_that_raises():
    class _RaisingHandle(_FakeBlockingPipeHandle):
        def close(self):
            raise OSError("pipe already broken")

    io = _ThreadedPipeIO(_RaisingHandle([]))
    io.close()  # must not propagate - close() is called from cleanup paths


# ─── Leerzeichen und Sonderzeichen in Dateipfaden ──────────────────────────

@pytest.mark.asyncio
async def test_player_open_file_kind_accepts_spaces_umlauts_and_brackets_in_the_path(
    bridge, tmp_path, monkeypatch,
):
    """The file-kind branch never touches the string beyond Path(...).is_file()
    - this exercises that with a name real Windows users actually produce
    (downloaded titles, umlauts, release-group brackets)."""
    tricky = tmp_path / "Übung Bär (2024) [Testrip] - Kopie.mp4"
    tricky.write_bytes(b"placeholder")

    result = json.loads(bridge.player_open(json.dumps({"kind": "file", "path": str(tricky)})))

    # No mpv is started for this assertion's purpose; only the path handling
    # up to PlayerService.open() is under test, so a missing-mpv style error
    # is fine, but a "Datei nicht gefunden" error would mean the special
    # characters broke path resolution - that is what must never happen.
    assert result.get("error") != f"Datei nicht gefunden: {tricky}"
