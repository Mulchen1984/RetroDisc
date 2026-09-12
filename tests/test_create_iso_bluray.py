"""Tests für die gehärtete ``DiscTools.create_iso`` (Blu-ray-ISO-Erzeugung).

Zwei konkrete, real gegen die auf diesem Rechner installierte mkisofs-
Variante nachgewiesene Probleme werden hier abgesichert:

1. ``-allow-limited-size`` ist nicht überall bekannt (dvdrtools-Fork meldet
   "unrecognized option") - ein Fallback auf ``-udf -iso-level 3`` muss
   greifen, aber NICHT stillschweigend bei einem anderen, echten Fehler.
2. Der Fallback allein reicht nicht: derselbe Fork verwirft Dateien über
   4 GiB beim Fallback-Weg kommentarlos (Exit-Code 0, aber ein kaputt-
   kleines Image) - die Größenprüfung nach der Erstellung muss das fangen,
   unabhängig davon, welcher mkisofs-Fork tatsächlich läuft.
"""
from __future__ import annotations

import pytest

from src.core.disc import DiscError, DiscTools
from src.models.media import DiscType



class _FakeProc:
    def __init__(self, returncode=0, stderr=b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self):
        return b"", self._stderr


def _tools(monkeypatch, subprocess_impl) -> DiscTools:
    tools = DiscTools()
    monkeypatch.setattr("src.core.disc.shutil.which", lambda name: name)
    monkeypatch.setattr("src.core.disc.create_hidden_subprocess", subprocess_impl)
    return tools


def _bdmv_source(tmp_path, *, payload_size: int = 1024):
    source_dir = tmp_path / "BDMV_SRC"
    (source_dir / "BDMV" / "STREAM").mkdir(parents=True)
    (source_dir / "BDMV" / "STREAM" / "00000.m2ts").write_bytes(b"0" * payload_size)
    return source_dir


@pytest.mark.asyncio
async def test_blu_ray_iso_succeeds_on_first_try_when_allow_limited_size_is_supported(monkeypatch, tmp_path):
    calls = []

    async def fake_subprocess(*args, **kwargs):
        calls.append(args)
        # "-allow-limited-size" wird unterstützt -> Erfolg im ersten Versuch.
        (tmp_path / "out.iso").write_bytes(b"0" * 2048)   # >= Quellinhalt (1024 Bytes payload)
        return _FakeProc(returncode=0)

    tools = _tools(monkeypatch, fake_subprocess)
    source_dir = _bdmv_source(tmp_path)
    output = tmp_path / "out.iso"

    result = await tools.create_iso(source_dir, output, disc_type=DiscType.BLURAY)

    assert result == output
    assert len(calls) == 1
    assert "-allow-limited-size" in calls[0]


@pytest.mark.asyncio
async def test_blu_ray_iso_falls_back_when_allow_limited_size_is_unrecognized(monkeypatch, tmp_path):
    calls = []

    async def fake_subprocess(*args, **kwargs):
        calls.append(args)
        if "-allow-limited-size" in args:
            return _FakeProc(returncode=1, stderr=b"mkisofs: unrecognized option `-allow-limited-size'\n")
        (tmp_path / "out.iso").write_bytes(b"0" * 2048)
        return _FakeProc(returncode=0)

    tools = _tools(monkeypatch, fake_subprocess)
    source_dir = _bdmv_source(tmp_path)
    output = tmp_path / "out.iso"

    result = await tools.create_iso(source_dir, output, disc_type=DiscType.BLURAY)

    assert result == output
    assert len(calls) == 2
    assert "-allow-limited-size" in calls[0]
    assert "-iso-level" in calls[1] and "3" in calls[1]


@pytest.mark.asyncio
async def test_blu_ray_iso_raises_on_a_real_error_without_trying_every_fallback_silently(monkeypatch, tmp_path):
    calls = []

    async def fake_subprocess(*args, **kwargs):
        calls.append(args)
        return _FakeProc(returncode=1, stderr=b"mkisofs: Input/output error\n")

    tools = _tools(monkeypatch, fake_subprocess)
    source_dir = _bdmv_source(tmp_path)
    output = tmp_path / "out.iso"

    with pytest.raises(DiscError, match="ISO-Erstellung fehlgeschlagen"):
        await tools.create_iso(source_dir, output, disc_type=DiscType.BLURAY)
    # Ein echter Fehler (kein "unrecognized option") bricht sofort ab -
    # kein zweiter Versuch mit denselben falschen Flags.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_blu_ray_iso_rejects_a_suspiciously_small_result_even_on_exit_code_zero(monkeypatch, tmp_path):
    """Reproduziert real beobachtetes Verhalten: mkisofs verwirft eine
    >4-GiB-Datei mit Exit-Code 0 und einem winzigen Image."""
    async def fake_subprocess(*args, **kwargs):
        (tmp_path / "out.iso").write_bytes(b"0" * 512)   # winzig ggü. der Quelle
        return _FakeProc(returncode=0, stderr=b"File ... is too large - ignoring\n")

    tools = _tools(monkeypatch, fake_subprocess)
    source_dir = _bdmv_source(tmp_path, payload_size=5_000_000)
    output = tmp_path / "out.iso"

    with pytest.raises(DiscError, match="verdächtig kleines Abbild"):
        await tools.create_iso(source_dir, output, disc_type=DiscType.BLURAY)


@pytest.mark.asyncio
async def test_dvd_iso_only_tries_a_single_flag_set_no_fallback_loop(monkeypatch, tmp_path):
    """Regressionsschutz: der DVD-Pfad ist von der Blu-ray-Härtung unberührt."""
    calls = []

    async def fake_subprocess(*args, **kwargs):
        calls.append(args)
        (tmp_path / "out.iso").write_bytes(b"0" * 2048)
        return _FakeProc(returncode=0)

    tools = _tools(monkeypatch, fake_subprocess)
    source_dir = tmp_path / "DVD_SRC"
    (source_dir / "VIDEO_TS").mkdir(parents=True)
    (source_dir / "VIDEO_TS" / "VIDEO_TS.IFO").write_bytes(b"0" * 1024)
    output = tmp_path / "out.iso"

    result = await tools.create_iso(source_dir, output, disc_type=DiscType.DVD)

    assert result == output
    assert len(calls) == 1
    assert "-dvd-video" in calls[0]
    assert "-allow-limited-size" not in calls[0]
