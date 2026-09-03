#!/usr/bin/env python3
"""Disc-Gate ohne physischen Rohling.

Ein echter Brenn- und Rip-Test braucht Hardware und ein Medium. Alles davor
laesst sich aber vollstaendig automatisiert pruefen, indem eine real erzeugte
DVD-ISO unter Windows als virtuelles Laufwerk eingebunden wird.

Geprueft wird:

1. Verfuegbarkeit der gebuendelten DVD-Werkzeuge,
2. echte DVD-Erstellung ueber den produktiven ``DVDWorkflow`` (dvdauthor +
   mkisofs) aus einer Testdatei,
3. Einbinden dieser ISO als virtuelles DVD-Laufwerk,
4. Laufwerkserkennung ueber denselben PowerShell-Helfer wie im Produkt, das
   virtuelle Laufwerk muss auftauchen,
5. ``BurnSettings.default_device``,
6. ``DiscTools.get_disc_info`` auf dem virtuellen Laufwerk,
7. der vollstaendige Rip-Workflow von diesem Laufwerk, nach MKV und nach ISO,
8. der Brennaufruf als Dry-Run: der zusammengebaute ``growisofs``-Befehl wird
   mit realistischen Parametern geprueft, aber nicht ausgefuehrt,
9. Fehlerfaelle: fehlendes Laufwerk, Laufwerk ohne Medium, nicht
   beschreibbares Medium.

Nicht abgedeckt und ausdruecklich offen: der reale physische Brennvorgang auf
einen Rohling und das Zurueckrippen davon. Das bleibt ein Hardware-Test.

Aufruf::

    python scripts/verify_disc_workflow.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.settings import BurnSettings  # noqa: E402
from src.core import disc as disc_module  # noqa: E402
from src.core.disc import DiscTools  # noqa: E402
from src.core.ffmpeg import FFmpeg  # noqa: E402
from src.services.dvd_workflow import DVDProject, DVDWorkflow  # noqa: E402
from src.services.ripper import DiscRipper  # noqa: E402
from src.utils.subprocesses import decode_console_output, run_powershell_hidden  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "test_video.mp4"
VENDOR = ROOT / "vendor"
DVDTOOLS = VENDOR / "dvdtools"

_failures: list[str] = []
_open: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok   {msg}")


def fail(msg: str) -> None:
    _failures.append(msg)
    print(f"  FAIL {msg}")


def pending(msg: str) -> None:
    _open.append(msg)
    print(f"  OFFEN {msg}")


def _powershell(command: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        timeout=timeout,
    )


def mount_iso(iso: Path) -> str | None:
    """Bindet die ISO als virtuelles Laufwerk ein und liefert den Buchstaben."""
    command = (
        "$ErrorActionPreference='Stop';"
        f"$img = Mount-DiskImage -ImagePath '{iso}' -PassThru;"
        "Start-Sleep -Milliseconds 800;"
        "($img | Get-Volume).DriveLetter"
    )
    result = _powershell(command)
    letter = decode_console_output(result.stdout).strip()
    if result.returncode != 0 or not letter:
        print(f"       Mount-Ausgabe: {decode_console_output(result.stderr).strip()[:300]}")
        return None
    return f"{letter}:"


def dismount_iso(iso: Path) -> None:
    _powershell(f"Dismount-DiskImage -ImagePath '{iso}' | Out-Null")


def detect_drives() -> list[dict]:
    """Laufwerkserkennung ueber genau den Helfer, den das Produkt benutzt."""
    ps = (
        "Get-CimInstance Win32_CDROMDrive | ForEach-Object { [PSCustomObject]@{ "
        "Name=$_.Name; Drive=$_.Drive; MediaLoaded=$_.MediaLoaded; "
        "MediaType=$_.MediaType } } | ConvertTo-Json -Compress"
    )
    out = run_powershell_hidden(ps, timeout=60)
    if out.returncode != 0:
        return []
    raw = (out.stdout or "").strip()
    if not raw:
        return []
    data = json.loads(raw)
    return [data] if isinstance(data, dict) else data


def make_disc_tools() -> DiscTools:
    return DiscTools(
        dvdauthor_path=str(DVDTOOLS / "dvdauthor.exe"),
        mkisofs_path=str(DVDTOOLS / "mkisofs.exe"),
        growisofs_path=str(DVDTOOLS / "growisofs.exe"),
        mediainfo_path=str(DVDTOOLS / "dvd+rw-mediainfo.exe"),
    )


async def build_iso(work: Path) -> Path:
    ffmpeg = FFmpeg(
        ffmpeg_path=str(VENDOR / "ffmpeg.exe"), ffprobe_path=str(VENDOR / "ffprobe.exe")
    )
    workflow = DVDWorkflow(
        ffmpeg=ffmpeg, disc_tools=make_disc_tools(), temp_dir=work / "dvd-temp"
    )
    return await workflow.run(
        DVDProject(
            title="RetroDisc Disc Gate",
            input_files=[FIXTURE],
            output_dir=work,
            standard="PAL",
            aspect="16:9",
            only_iso=True,
        )
    )


class _FakeProc:
    """Ersetzt den Brenn-Subprozess: der Befehl wird geprueft, nicht ausgefuehrt."""

    returncode = 0

    async def communicate(self):
        return b"100% done\n", b""


async def run_gate(work: Path) -> None:
    tools = make_disc_tools()

    print("\n[1] Gebuendelte DVD-Werkzeuge")
    # cdrecord/wodim brennt ausschliesslich CDs. Die Oberflaeche bietet kein
    # CD-Brennen an, der Weg ist nur ueber burn_iso(disc_type=DiscType.CD)
    # erreichbar. Das Werkzeug wird deshalb bewusst nicht mitgeliefert und
    # gilt hier als optional, nicht als fehlend.
    optional = {"cdrecord"}
    validation = await tools.validate()
    for name, available in sorted(validation.items()):
        if available:
            ok(f"{name}: vorhanden")
        elif name in optional:
            pending(f"{name}: nicht gebuendelt -- CD-Brennen erfordert ein externes {name}")
        else:
            fail(f"{name}: FEHLT")

    print("\n[2] Echte DVD-Erstellung (dvdauthor + mkisofs)")
    iso = await build_iso(work)
    if iso.is_file() and iso.stat().st_size > 0:
        ok(f"ISO erzeugt: {iso.name}, {iso.stat().st_size} Bytes")
    else:
        fail(f"ISO fehlt oder ist leer: {iso}")
        return

    print("\n[3] Laufwerke vor dem Einbinden")
    before = detect_drives()
    for drive in before:
        ok(f"{drive.get('Name')} -> {drive.get('Drive')} (Medium: {drive.get('MediaLoaded')})")
    physical = {d.get("Drive") for d in before}

    print("\n[4] ISO als virtuelles DVD-Laufwerk einbinden")
    letter = mount_iso(iso)
    if not letter:
        fail("ISO liess sich nicht als virtuelles Laufwerk einbinden")
        return
    ok(f"virtuelles Laufwerk: {letter}")

    try:
        print("\n[5] Laufwerkserkennung mit eingebundenem Medium")
        after = detect_drives()
        virtual = [d for d in after if d.get("Drive") == letter]
        if virtual:
            entry = virtual[0]
            ok(f"virtuelles Laufwerk erkannt: {entry.get('Name')} -> {entry.get('Drive')}")
            if entry.get("MediaLoaded"):
                ok("MediaLoaded ist True")
            else:
                fail("MediaLoaded ist False, obwohl ein Medium eingebunden ist")
        else:
            fail(f"virtuelles Laufwerk {letter} taucht in der Erkennung nicht auf")
        if physical <= {d.get("Drive") for d in after}:
            ok(f"physische Laufwerke weiterhin erkannt: {sorted(x for x in physical if x)}")
        else:
            fail("ein physisches Laufwerk ist aus der Erkennung verschwunden")

        print("\n[6] default_device")
        default_device = BurnSettings().default_device
        if sys.platform == "win32":
            if default_device.endswith(":") and len(default_device) == 2:
                ok(f"default_device unter Windows: {default_device}")
            else:
                fail(f"default_device ist kein Windows-Laufwerksbuchstabe: {default_device!r}")
        else:
            ok(f"default_device: {default_device}")

        print("\n[7] Disc-Erkennung auf dem virtuellen Laufwerk")
        info = await tools.get_disc_info(letter)
        if info.get("present"):
            ok(f"present=True, type={info.get('type')}, label={info.get('label')!r}")
        else:
            fail(f"Medium nicht erkannt: {info}")
        if info.get("readable"):
            ok("readable=True")
        else:
            fail(f"Medium als nicht lesbar gemeldet: {info}")
        if (Path(letter + "/") / "VIDEO_TS").is_dir():
            ok("VIDEO_TS-Struktur auf dem Medium vorhanden")
        else:
            fail("VIDEO_TS fehlt auf dem eingebundenen Medium")

        print("\n[8] Rip-Workflow vom virtuellen Laufwerk")
        ripper = DiscRipper(
            ffmpeg=FFmpeg(
                ffmpeg_path=str(VENDOR / "ffmpeg.exe"),
                ffprobe_path=str(VENDOR / "ffprobe.exe"),
            ),
            disc_tools=tools,
        )
        ripped_iso = await ripper.rip(letter, work / "rip-copy.iso", output_format="iso")
        if ripped_iso.is_file() and ripped_iso.stat().st_size > 0:
            ok(f"Rip nach ISO: {ripped_iso.name}, {ripped_iso.stat().st_size} Bytes")
        else:
            fail(f"Rip nach ISO lieferte keine Datei: {ripped_iso}")
        ripped_mkv = await ripper.rip(letter, work / "rip-video.mkv", output_format="mkv_h265")
        if ripped_mkv.is_file() and ripped_mkv.stat().st_size > 0:
            ok(f"Rip nach MKV/H.265: {ripped_mkv.name}, {ripped_mkv.stat().st_size} Bytes")
            probe = await FFmpeg(
                ffmpeg_path=str(VENDOR / "ffmpeg.exe"),
                ffprobe_path=str(VENDOR / "ffprobe.exe"),
            ).probe(ripped_mkv)
            if probe.video_streams:
                stream = probe.video_streams[0]
                ok(
                    f"gerippte Datei ist abspielbar: {stream.width}x{stream.height}, "
                    f"{probe.duration_seconds:.2f}s"
                )
            else:
                fail("gerippte MKV enthaelt keinen Videostream")
        else:
            fail(f"Rip nach MKV lieferte keine Datei: {ripped_mkv}")

        print("\n[9] Brennaufruf als Dry-Run (Befehl geprueft, nicht ausgefuehrt)")
        captured: dict = {}

        async def fake_subprocess(*cmd, **kwargs):
            captured["cmd"] = list(cmd)
            captured["kwargs"] = kwargs
            return _FakeProc()

        original = disc_module.create_hidden_subprocess
        disc_module.create_hidden_subprocess = fake_subprocess
        try:
            burned = await tools.burn_iso(iso, device="D:", speed=8, verify=False)
        finally:
            disc_module.create_hidden_subprocess = original
        cmd = captured.get("cmd", [])
        if burned:
            ok("burn_iso meldet Erfolg auf dem abgefangenen Aufruf")
        else:
            fail("burn_iso meldet trotz Exitcode 0 keinen Erfolg")
        if cmd and cmd[0].endswith("growisofs.exe"):
            ok(f"Brennwerkzeug: {Path(cmd[0]).name}")
        else:
            fail(f"unerwartetes Brennwerkzeug: {cmd[:1]}")
        for expected in ("-dvd-compat", f"-Z", f"D:={iso}", "-speed", "8"):
            if expected in cmd:
                ok(f"Parameter vorhanden: {expected}")
            else:
                fail(f"Parameter fehlt im Brennbefehl: {expected}")

        print("\n[10] Fehlerfaelle")
        missing = await tools.get_disc_info("Z:")
        if missing.get("present") is False:
            ok("fehlendes Laufwerk Z: -> present=False, keine Ausnahme")
        else:
            fail(f"fehlendes Laufwerk falsch gemeldet: {missing}")

        empty = [d for d in after if d.get("Drive") in physical and not d.get("MediaLoaded")]
        if empty:
            device = empty[0]["Drive"]
            info_empty = await tools.get_disc_info(device)
            if info_empty.get("present") is False:
                ok(f"leeres Laufwerk {device} -> present=False, keine Ausnahme")
            else:
                fail(f"leeres Laufwerk {device} falsch gemeldet: {info_empty}")
        else:
            pending("kein leeres physisches Laufwerk verfuegbar, Fall 'kein Medium' ungeprueft")

        if info.get("blank") is False and info.get("rewritable") is False:
            ok("eingebundenes Medium wird korrekt als nicht beschreibbar gemeldet "
               "(blank=False, rewritable=False)")
        else:
            fail(f"nicht beschreibbares Medium falsch klassifiziert: {info}")

        try:
            await tools.burn_iso(work / "gibt-es-nicht.iso", device=letter, verify=False)
        except disc_module.DiscError:
            ok("Brennen mit fehlender ISO wird sauber als DiscError abgewiesen")
        else:
            fail("Brennen mit fehlender ISO lief ohne Fehler durch")

    finally:
        dismount_iso(iso)
        print(f"\n  virtuelles Laufwerk wieder ausgehaengt: {iso.name}")

    pending(
        "realer physischer Brennvorgang auf einen Rohling und Rueckleseprobe "
        "davon -- Hardware-Test, kein Rohling verfuegbar"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="RetroDisc Disc-Gate ohne Rohling")
    parser.add_argument("--keep", action="store_true", help="Arbeitsordner behalten")
    args = parser.parse_args()

    # Werkzeugausgaben koennen Ersatzzeichen enthalten, die die ANSI-Codepage
    # der Konsole nicht kodieren kann. Ohne das bricht der Bericht ab.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - hostabhaengig
            pass

    print("RetroDisc Disc-Gate (virtuelles Laufwerk)")
    print("=" * 44)
    if sys.platform != "win32":
        print("Dieses Gate laeuft nur unter Windows.")
        return 1

    work = Path(tempfile.mkdtemp(prefix="retrodisc-disc-gate-"))
    try:
        asyncio.run(run_gate(work))
    finally:
        if args.keep:
            print(f"\nArbeitsordner behalten: {work}")
        else:
            import shutil

            shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 44)
    if _failures:
        print(f"RESULT: FAIL ({len(_failures)} Befund(e))")
        for item in _failures:
            print(f"  - {item}")
        return 1
    print("RESULT: PASS (0 Befunde)")
    for item in _open:
        print(f"  OFFEN: {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
