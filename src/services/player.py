"""Wiedergabe-Engine für RetroDiscs Vorschau-/Player-Funktion.

## Engine-Wahl

Geprüft wurden mpv (per JSON-IPC-Socket gesteuert), VLC/libVLC (python-vlc)
und ein einfacher HTML5-``<video>``-Tag im WebView.

* HTML5 ``<video>`` verworfen: WKWebView (macOS)/WebView2 (Windows) haben
  keinen zuverlässigen MPEG-2-, VOB-, DTS- oder Mehrspur-DVD/BD-Support -
  genau das, was ein "DVD-/Blu-ray-Player" tatsächlich braucht. Das als
  Disc-Player auszugeben wäre eine Fehldarstellung.
* ``python-vlc``/libVLC: technisch geeignet, aber in dieser Umgebung nicht
  ohne Weiteres nutzbar (nur die VLC.app-GUI-Bundle vorhanden, kein
  eigenständiges ``libvlc.dylib``/CLI) und nicht zusätzlich installiert, um
  keine zwei konkurrierende Engines gegeneinander zu testen.
* ``python-mpv`` (ctypes-Bindings an ``libmpv``): reale Installation und
  ein realer Aufruf in dieser Umgebung **stürzt beim Erzeugen der MPV-
  Instanz ab** (bestätigt, kein Python-Fehler - ein natives Signal schon
  bei ``mpv.MPV(...)``), obwohl das mpv-Binary selbst einwandfrei läuft.
  Verworfen zugunsten der robusteren Variante unten.
* **mpv über sein eigenes JSON-IPC-Protokoll** (``--input-ipc-server``),
  gesteuert als ganz normaler Subprozess über ``create_hidden_subprocess`` -
  genau dasselbe Muster wie FFmpeg/dvdauthor/growisofs überall sonst in
  diesem Projekt. Real getestet: laden, Dauer/Position abfragen, pausieren
  funktionieren zuverlässig. mpv nutzt dieselbe FFmpeg/libavcodec-
  Decoder-Basis, die RetroDisc ohnehin einsetzt (MPEG-2, H.264, HEVC, AC-3,
  DTS real bestätigt über ``mpv --*d=help``) und unterstützt Mehrfach-
  Audio-/Untertitelspuren, Kapitel sowie ``bd://``/``br://`` nativ. Kein
  zusätzlicher Python-ctypes-Layer, kein neues PyPI-Paket nötig - nur das
  ``mpv``-Binary (für Windows-Produktionsbuilds analog zu FFmpeg/dvdauthor
  über ``prepare_vendor.py`` zu vendorn - siehe Abschlussbericht,
  "VERBLEIBENDE EINSCHRÄNKUNGEN").

## Mehrsegment-Titel (mehrere VOB/M2TS-Dateien als EIN Titel)

mpv's ``edl://``-Protokoll hängt mehrere Quelldateien nahtlos zu einer
Zeitleiste zusammen (real getestet: zwei 2-Sekunden-Clips ergeben eine
durchgehend abspielbare, seekbare 4-Sekunden-Timeline). Das ist genau der
Mechanismus für "mehrere VOB-/Cell-Segmente eines Titels" bzw. "eine
Playlist mit mehreren M2TS-Clips" aus einem Titel (siehe
``player_source.py``).

## Kein Disc-Menü / kein CSS/AACS/BD+

Siehe ``drm_capabilities.py`` und die Moduldoku dort - dieser Block spielt
logische Titel/Kapitel/Streams ab, keine originalen DVD-/Blu-ray-Menüs und
keine kommerziell kopiergeschützten Discs.
"""
from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import structlog

from src.utils.subprocesses import create_hidden_subprocess, terminate_process

log = structlog.get_logger()


class PlayerError(Exception):
    pass


class PlayerBackendError(PlayerError):
    """Das Wiedergabe-Backend (mpv) ist nicht verfügbar."""


@dataclass
class TrackInfo:
    id: int
    type: str            # "audio" | "sub" | "video"
    lang: Optional[str] = None
    title: Optional[str] = None
    selected: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "lang": self.lang,
                "title": self.title, "selected": self.selected}


@dataclass
class PlayerState:
    loaded: bool = False
    path: Optional[str] = None
    label: Optional[str] = None
    paused: bool = True
    position_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None
    volume: float = 100.0
    fullscreen: bool = False
    chapter: Optional[int] = None
    chapter_count: int = 0
    audio_track: Optional[int] = None
    subtitle_track: Optional[int] = None
    tracks: list[TrackInfo] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "loaded": self.loaded, "path": self.path, "label": self.label,
            "paused": self.paused, "position_seconds": self.position_seconds,
            "duration_seconds": self.duration_seconds, "volume": self.volume,
            "fullscreen": self.fullscreen, "chapter": self.chapter,
            "chapter_count": self.chapter_count, "audio_track": self.audio_track,
            "subtitle_track": self.subtitle_track,
            "tracks": [t.to_dict() for t in self.tracks], "error": self.error,
        }


def _edl_url(segments: list[Path]) -> str:
    """Baut eine mpv-EDL-URL, die mehrere Dateien nahtlos zu einer Zeitleiste
    zusammenhängt (real getestet, siehe Moduldoku). Ein einzelnes Segment
    braucht kein EDL-Wrapping."""
    if len(segments) == 1:
        return str(segments[0])
    parts = [f"%{len(str(s))}%{s}" for s in segments]
    return "edl://" + ";".join(parts)


class _MpvIpcClient:
    """Rohe JSON-IPC-Transportschicht über den mpv-``--input-ipc-server``-
    Socket. Getrennt von ``PlayerService``, damit dessen Kommandologik ohne
    einen echten Socket testbar ist (siehe tests/test_player_service.py).

    Bewusst EIN serialisierter Lese-/Schreibzyklus statt eines separaten
    Hintergrund-Lesetasks: eine frühere Fassung mit einem dauerhaft
    laufenden Reader-Task plus futures-basiertem Dispatch zeigte unter
    echtem mpv-IPC-Verkehr (viele Events zwischen zwei Kommandos, z. B.
    nach einem ``loadfile`` mit mehreren ``audio-reconfig``/``video-
    reconfig``-Ereignissen) eine seltene, real reproduzierte Race, bei der
    eine Antwort verloren ging und ``command()`` unbegründet in den
    Timeout lief. Diese Fassung liest stattdessen strikt sequenziell,
    durch eine Lock geschützt: jedes ``command()`` schreibt seine Anfrage
    und liest Zeile für Zeile weiter, bis es seine eigene ``request_id``
    findet - Event-Zeilen werden dabei einfach mitgesammelt. Keine
    verlorene Antwort mehr möglich, weil nur noch ein einziger Leser
    jemals aktiv ist."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._reader = reader
        self._writer = writer
        self._request_ids = itertools.count(1)
        self._events: list[dict] = []
        self._closed = False
        self._lock = asyncio.Lock()

    async def command(self, *args: Any, timeout: float = 10.0) -> dict:
        if self._closed:
            raise PlayerError("mpv-Verbindung ist bereits geschlossen.")
        request_id = next(self._request_ids)
        payload = json.dumps({"command": list(args), "request_id": request_id}) + "\n"
        async with self._lock:
            self._writer.write(payload.encode("utf-8"))
            await self._writer.drain()
            return await asyncio.wait_for(self._read_until(request_id), timeout=timeout)

    async def _read_until(self, request_id: int) -> dict:
        while True:
            line = await self._reader.readline()
            if not line:
                raise PlayerError("mpv-Verbindung wurde unerwartet geschlossen.")
            try:
                message = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if message.get("request_id") == request_id:
                return message
            if "event" in message:
                self._events.append(message)

    async def get_property(self, name: str, default: Any = None) -> Any:
        response = await self.command("get_property", name)
        if response.get("error") != "success":
            return default
        return response.get("data", default)

    async def set_property(self, name: str, value: Any) -> None:
        await self.command("set_property", name, value)

    def recent_events(self, event_name: Optional[str] = None) -> list[dict]:
        if event_name is None:
            return list(self._events)
        return [e for e in self._events if e.get("event") == event_name]

    def clear_events(self) -> None:
        """Muss vor jedem neuen ``loadfile`` aufgerufen werden (siehe
        ``PlayerService.open``): sonst sieht ``_wait_for_load`` bei einem
        Titel-/Quellenwechsel auf derselben mpv-Instanz noch das
        ``file-loaded``-Ereignis der VORHERIGEN Quelle und hält den neuen
        Ladevorgang fälschlich für sofort abgeschlossen."""
        self._events.clear()

    async def close(self) -> None:
        self._closed = True
        with contextlib.suppress(Exception):
            self._writer.close()


class _ThreadedPipeIO:
    """Reader/Writer-Adapter für ein blockierendes Windows-Named-Pipe-Handle
    (siehe ``PlayerService._connect_windows_pipe``). Bietet nur die schmale
    Teilmenge, die ``_MpvIpcClient`` tatsächlich verwendet: ``readline()``
    (async, wie ``asyncio.StreamReader``) sowie ``write()``/``drain()``/
    ``close()`` (wie ``asyncio.StreamWriter``)."""

    def __init__(self, handle):
        self._handle = handle

    async def readline(self) -> bytes:
        return await asyncio.to_thread(self._handle.readline)

    def write(self, data: bytes) -> None:
        self._handle.write(data)

    async def drain(self) -> None:
        await asyncio.to_thread(self._handle.flush)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._handle.close()


class PlayerService:
    """Steuert eine mpv-Instanz für Vorschau-/Preview-Wiedergabe.

    Ein ``PlayerService`` ist zustandsbehaftet und repräsentiert GENAU EINE
    laufende mpv-Instanz - analog zu ``DiscTools``/``FFmpeg``, die ebenfalls
    externe Werkzeuge kapseln. ``close()`` beendet den Subprozess und muss
    (z. B. beim Schließen des Vorschau-Panels oder App-Ende) immer
    aufgerufen werden - insbesondere, damit ein evtl. gemounteter ISO-Pfad
    (siehe ``iso_mount.py``) danach wieder ausgehängt wird.
    """

    def __init__(self, mpv_path: Optional[str] = None, *, extra_args: Optional[list[str]] = None):
        self.mpv_path = mpv_path or shutil.which("mpv")
        self._extra_args = extra_args or []
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._ipc: Optional[_MpvIpcClient] = None
        self._ipc_path: Optional[str] = None
        self._label: Optional[str] = None
        self._on_unload = None   # optionaler async Callback (z. B. ISO-Unmount)

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        resolved = self.mpv_path and (shutil.which(self.mpv_path) or self.mpv_path)
        if not resolved or not (shutil.which(resolved) or Path(resolved).is_file()):
            raise PlayerBackendError(
                "Wiedergabe-Backend 'mpv' wurde nicht gefunden. Bitte mpv installieren "
                "(siehe README) - RetroDisc kann ohne dieses Backend keine Vorschau abspielen."
            )
        if self.is_running:
            return

        if os.name == "nt":
            self._ipc_path = rf"\\.\pipe\retrodisc-mpv-{uuid.uuid4().hex[:12]}"
        else:
            self._ipc_path = str(Path(tempfile.gettempdir()) / f"retrodisc-mpv-{uuid.uuid4().hex[:12]}.sock")

        cmd = [
            self.mpv_path, "--idle=yes", "--keep-open=yes", "--no-config",
            f"--input-ipc-server={self._ipc_path}", "--really-quiet",
            *self._extra_args,
        ]
        self._proc = await create_hidden_subprocess(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )

        reader, writer = await self._connect_ipc()
        self._ipc = _MpvIpcClient(reader, writer)
        log.info("mpv gestartet", ipc=self._ipc_path)

    async def _connect_ipc(self, *, attempts: int = 30, delay: float = 0.1):
        last_exc: Optional[Exception] = None
        for _ in range(attempts):
            try:
                if os.name == "nt":
                    return await self._connect_windows_pipe()
                return await asyncio.open_unix_connection(self._ipc_path)
            except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
                last_exc = exc
                await asyncio.sleep(delay)
        raise PlayerBackendError(f"Konnte nicht mit mpv verbinden ({self._ipc_path}): {last_exc}")

    async def _connect_windows_pipe(self):
        """Windows-Namedpipe-Zweig - nach mpv-Dokumentation implementiert,
        in dieser (macOS-)Umgebung nicht laufzeitgeprüft (siehe
        Abschlussbericht, 'VERBLEIBENDE EINSCHRÄNKUNGEN'). asyncios
        Proactor-Pipe-API erwartet getrennte Lese-/Schreib-Handles; ein
        Named Pipe ist aber ein einziges duplex-fähiges Datei-Handle -
        deshalb ``_ThreadedPipeIO`` als schlanker Adapter (blockierendes
        Lesen/Schreiben über ``asyncio.to_thread``) statt echter
        Proactor-Integration."""
        handle = await asyncio.to_thread(open, self._ipc_path, "r+b", buffering=0)
        io = _ThreadedPipeIO(handle)
        return io, io

    async def open(self, segments: list[Path], *, label: Optional[str] = None,
                  on_unload=None) -> PlayerState:
        """Lädt eine Titel-Segmentliste (siehe ``player_source.resolve_title``)
        oder eine einzelne Datei. Startet mpv bei Bedarf automatisch."""
        if not segments:
            raise PlayerError("Keine abspielbare Quelle angegeben.")
        missing = [s for s in segments if not Path(s).is_file()]
        if missing:
            raise PlayerError(f"Quelldatei nicht gefunden: {missing[0]}")

        if not self.is_running:
            await self.start()

        self._on_unload = on_unload
        self._label = label

        self._ipc.clear_events()
        url = _edl_url([Path(s) for s in segments])
        response = await self._ipc.command("loadfile", url, "replace")
        if response.get("error") != "success":
            raise PlayerError(f"mpv konnte die Quelle nicht laden: {response.get('error')}")

        loaded = await self._wait_for_load()
        if not loaded:
            error_events = self._ipc.recent_events("end-file")
            detail = error_events[-1].get("file_error") if error_events else None
            raise PlayerError(
                f"Wiedergabe fehlgeschlagen (nicht unterstützter Codec oder ungültige Quelle)"
                + (f": {detail}" if detail else ".")
            )
        return await self.get_state()

    async def _wait_for_load(self, timeout: float = 15.0) -> bool:
        """Events treffen nur als Nebeneffekt eines aktiven ``command()``-
        Aufrufs ein (siehe ``_MpvIpcClient``-Moduldoku) - deshalb hier ein
        billiges ``get_property`` pro Poll-Runde, das dabei jede
        zwischenzeitlich eingetroffene Event-Zeile mit einsammelt."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            await self._ipc.get_property("idle-active")
            if any(e.get("event") == "file-loaded" for e in self._ipc.recent_events()):
                return True
            if any(e.get("event") == "end-file" and e.get("reason") == "error"
                  for e in self._ipc.recent_events()):
                return False
            await asyncio.sleep(0.05)
        return False

    def _require_ipc(self) -> _MpvIpcClient:
        if self._ipc is None:
            raise PlayerError("Player ist nicht gestartet - zuerst open() aufrufen.")
        return self._ipc

    async def play(self) -> None:
        await self._require_ipc().set_property("pause", False)

    async def pause(self) -> None:
        await self._require_ipc().set_property("pause", True)

    async def toggle_pause(self) -> None:
        ipc = self._require_ipc()
        current = await ipc.get_property("pause", False)
        await ipc.set_property("pause", not current)

    async def stop(self) -> None:
        """Beendet die aktuelle Wiedergabe (mpv bleibt im Idle-Modus aktiv,
        für eine neue ``open()``-Quelle wiederverwendbar)."""
        if self._ipc is not None:
            await self._ipc.command("stop")
        if self._on_unload is not None:
            await self._on_unload()
            self._on_unload = None

    async def seek(self, seconds: float, *, relative: bool = False) -> None:
        # "+exact" statt mpvs Default (keyframe-genau): eine Vorschau soll auf
        # die tatsächlich angeforderte Position springen, nicht auf den
        # nächstgelegenen Keyframe (bei groben GOP-Abständen sonst ein
        # spürbarer, für Nutzer verwirrender Versatz).
        mode = ("relative" if relative else "absolute") + "+exact"
        await self._require_ipc().command("seek", seconds, mode)

    async def set_volume(self, percent: float) -> None:
        await self._require_ipc().set_property("volume", max(0.0, min(100.0, percent)))

    async def set_fullscreen(self, enabled: bool) -> None:
        await self._require_ipc().set_property("fullscreen", bool(enabled))

    async def set_audio_track(self, track_id: int) -> None:
        await self._require_ipc().set_property("aid", track_id)

    async def set_subtitle_track(self, track_id: int) -> None:
        await self._require_ipc().set_property("sid", track_id)

    async def disable_subtitles(self) -> None:
        await self._require_ipc().set_property("sid", "no")

    async def set_chapter(self, index: int) -> None:
        await self._require_ipc().set_property("chapter", index)

    async def get_state(self) -> PlayerState:
        if self._ipc is None:
            return PlayerState(loaded=False)
        ipc = self._ipc
        path = await ipc.get_property("path")
        track_list = await ipc.get_property("track-list", []) or []
        tracks = [
            TrackInfo(id=t.get("id", 0), type=t.get("type", ""), lang=t.get("lang"),
                     title=t.get("title"), selected=bool(t.get("selected")))
            for t in track_list if t.get("type") in ("audio", "sub")
        ]
        audio_track = next((t.id for t in tracks if t.type == "audio" and t.selected), None)
        subtitle_track = next((t.id for t in tracks if t.type == "sub" and t.selected), None)
        return PlayerState(
            loaded=bool(path),
            path=path,
            label=self._label,
            paused=bool(await ipc.get_property("pause", True)),
            position_seconds=await ipc.get_property("time-pos"),
            duration_seconds=await ipc.get_property("duration"),
            volume=await ipc.get_property("volume", 100.0),
            fullscreen=bool(await ipc.get_property("fullscreen", False)),
            chapter=await ipc.get_property("chapter"),
            chapter_count=len(await ipc.get_property("chapter-list", []) or []),
            audio_track=audio_track,
            subtitle_track=subtitle_track,
            tracks=tracks,
        )

    async def close(self) -> None:
        """Beendet mpv vollständig und räumt Socket/Pipe auf. Muss beim
        Schließen des Vorschau-Panels und beim App-Ende immer aufgerufen
        werden - insbesondere für einen evtl. gemounteten ISO-Pfad."""
        if self._on_unload is not None:
            await self._on_unload()
            self._on_unload = None
        if self._ipc is not None:
            with contextlib.suppress(Exception):
                await self._ipc.command("quit")
            await self._ipc.close()
            self._ipc = None
        if self._proc is not None:
            await terminate_process(self._proc)
            self._proc = None
        if self._ipc_path and os.name != "nt":
            with contextlib.suppress(OSError):
                Path(self._ipc_path).unlink(missing_ok=True)
        self._ipc_path = None
