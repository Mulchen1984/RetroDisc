"""Disc kopieren ist ein eigener Flow, nicht Teil von Konvertieren.

Das Doppel-Disc-Symbol auf der Startseite gehoert fachlich zu "Disc kopieren".
Es stand vorher auf der Konvertieren-Karte und hat damit die falsche Aktion
beworben.

Geprueft wird beides: die Startseite mit fuenf klar getrennten Aktionen und
die Regeln des Kopier-Flows - Quelle ist ein Leselaufwerk, Ziel ein Brenner,
On-the-fly nur mit zwei verschiedenen Laufwerken.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Die Bridge-Fixture wird wiederverwendet, nicht kopiert.
from test_disc_flows import disc_bridge  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "src" / "ui" / "app.html").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")


# ── Startseite ────────────────────────────────────────────────────────────


def home_cards() -> list[tuple[str, str]]:
    """(Flow-Name, Beschriftung) der Startseiten-Karten, in Reihenfolge."""
    return re.findall(
        r"""<div class="cbtn" onclick="openFlow\('([a-z]+)'\)">.*?"""
        r"""<div class="cc-label">([^<]+)</div>""",
        UI,
        re.DOTALL,
    )


def test_the_start_screen_offers_five_distinct_actions():
    assert home_cards() == [
        ("disccopy", "Disc kopieren"),
        ("convert", "Konvertieren"),
        ("burn", "Brennen"),
        ("rip", "Rippen"),
        ("download", "Download"),
    ]


def test_the_start_screen_text_matches_the_number_of_actions():
    assert "fuenf Aktionen" in UI
    assert "vier Aktionen" not in UI


def test_the_two_disc_icon_now_belongs_to_disc_copy():
    """Das Symbol mit zwei Discs bewirbt jetzt die richtige Aktion."""
    card = re.search(
        r"""<div class="cbtn" onclick="openFlow\('disccopy'\)">(.*?)</svg>""",
        UI,
        re.DOTALL,
    )
    assert card, "Disc-kopieren-Karte fehlt"
    discs = re.findall(r'<ellipse cx="0" cy="0" rx="[\d.]+"', card.group(1))
    assert len(discs) >= 2, "Disc kopieren traegt nicht das Doppel-Disc-Symbol"


def test_convert_has_its_own_icon_without_discs():
    """Konvertieren darf nicht laenger mit Discs beworben werden."""
    card = re.search(
        r"""<div class="cbtn" onclick="openFlow\('convert'\)">(.*?)</svg>""",
        UI,
        re.DOTALL,
    )
    assert card, "Konvertieren-Karte fehlt"
    svg = card.group(1)
    assert "<ellipse" not in svg, "Konvertieren zeigt weiterhin Disc-Ellipsen"
    assert "<rect" in svg, "Konvertieren hat kein eigenes Symbol bekommen"


# ── Laufwerkserkennung wird wiederverwendet ───────────────────────────────


def test_disc_copy_reuses_the_existing_drive_detection():
    """Es darf keine zweite Erkennung geben - nur ein detect_burners-Aufruf."""
    assert UI.count("detect_burners()") == 1
    load = re.search(r"async function loadBurners\(force\)\{(.*?)\n\}", UI, re.DOTALL)
    assert load, "loadBurners fehlt"
    body = load.group(1)
    assert "copySourceSelect" in body and "copyTargetSelect" in body


def test_opening_the_copy_flow_loads_the_drives():
    match = re.search(r"function openFlow\(name\)\{(.*?)\n\}", UI, re.DOTALL)
    assert match, "openFlow fehlt"
    assert "name==='disccopy'" in match.group(1)
    assert "loadBurners(false)" in match.group(1)


# ── On-the-fly-Regeln in der Oberflaeche ──────────────────────────────────


def test_on_the_fly_is_disabled_by_default_until_two_drives_are_known():
    radio = re.search(r'<input type="radio"[^>]*id="copyModeOnTheFly"[^>]*>', UI)
    assert radio, "On-the-fly-Option fehlt"
    assert "disabled" in radio.group(0)


def test_on_the_fly_requires_two_different_drives():
    body = re.search(r"function updateCopyModes\(\)\{(.*?)\n\}", UI, re.DOTALL)
    assert body, "updateCopyModes fehlt"
    logic = body.group(1)
    assert "COPY_DRIVES.length>1" in logic, "Zwei-Laufwerk-Bedingung fehlt"
    assert "source.value===target.value" in logic, "Gleichheitspruefung fehlt"
    assert "onTheFly.disabled = !possible" in logic


def test_the_user_is_told_why_on_the_fly_is_unavailable():
    """Eine verstaendliche Meldung, kein stilles Deaktivieren."""
    body = re.search(r"function updateCopyModes\(\)\{(.*?)\n\}", UI, re.DOTALL)
    logic = body.group(1)
    assert "zwei optische Laufwerke" in logic
    assert "dasselbe Laufwerk" in logic


# ── Backend-Regeln ────────────────────────────────────────────────────────


def _error(bridge, *args) -> str:
    return json.loads(bridge.copy_disc(*args)).get("error", "")


def test_copy_disc_is_reachable_from_the_ui(monkeypatch):
    """Ohne Proxy auf RetroDiscApi kommt der Aufruf nie im Backend an."""
    assert "def copy_disc(self, *args): return self._bridge.copy_disc(*args)" in LAUNCHER
    assert "a.copy_disc(source,target,mode)" in UI


def test_on_the_fly_refuses_the_same_drive_for_source_and_target(disc_bridge):
    create, _ = disc_bridge
    bridge = create(Path("."))
    message = _error(bridge, "D:", "D:", "onthefly")
    assert "zwei verschiedene Laufwerke" in message



def test_missing_drives_are_rejected_with_a_clear_message(disc_bridge):
    create, _ = disc_bridge
    bridge = create(Path("."))
    assert "Quelllaufwerk" in _error(bridge, "", "E:", "image")
    assert "Ziellaufwerk" in _error(bridge, "D:", "", "image")


def test_an_unknown_copy_mode_is_rejected(disc_bridge):
    create, _ = disc_bridge
    bridge = create(Path("."))
    assert "Kopiermodus" in _error(bridge, "D:", "E:", "teleport")


def test_on_the_fly_is_not_silently_replaced_by_the_image_path(disc_bridge):
    """Der Nutzer darf nicht etwas anderes bekommen, als er gewaehlt hat.

    Ein echtes On-the-fly-Kopieren gibt es im Backend nicht. Statt still auf
    den Abbild-Weg auszuweichen, wird das ausdruecklich gesagt.
    """
    create, _ = disc_bridge
    bridge = create(Path("."))
    message = _error(bridge, "D:", "E:", "onthefly")
    assert "noch nicht" in message and "Abbild" in message


def test_the_filesystem_level_limitation_is_documented():
    """copy_disc darf keinen 1:1-Klon versprechen.

    rip_disc(..., "iso") liest das gemountete Dateisystem und erzeugt daraus
    mit mkisofs ein neues Abbild - das ist kein sektorweises Klonen.
    """
    body = re.search(r'def copy_disc\(self.*?""".*?"""', LAUNCHER, re.DOTALL)
    assert body, "copy_disc fehlt"
    doc = body.group(0)
    assert "Dateisystem-Kopie" in doc
    assert "kein sektorweiser" in doc or "kein sektorweises" in doc
    # Auch der Nutzer muss es in der Oberflaeche sehen.
    assert "nicht Sektor fuer Sektor" in UI


# ── Kein Laufwerks-Scan beim Programmstart ────────────────────────────────


def _startup_body() -> str:
    match = re.search(r"async function startup\(\) \{(.*?)\n\}", UI, re.DOTALL)
    assert match, "startup() fehlt"
    return match.group(1)


def test_startup_never_scans_optical_drives():
    """Die Erkennung startet unter Windows PowerShell - nicht beim Hochfahren.

    Das war der Grund fuer aufblitzende Konsolenfenster beim normalen Start.
    """
    # Nur echter Code zaehlt: ein Kommentar, der erklaert, warum hier NICHT
    # erkannt wird, darf den Test nicht ausloesen.
    body = "\n".join(
        line for line in _startup_body().splitlines()
        if not line.lstrip().startswith("//")
    )
    for call in ("loadBurners(", "detect_burners", "run_powershell_hidden"):
        assert call not in body, f"startup() ruft {call} auf"


def test_the_home_screen_triggers_no_drive_detection():
    """goHome darf nichts erkennen - der Home-Screen braucht keine Laufwerke."""
    match = re.search(r"function goHome\(\)\{(.*?)\n\}", UI, re.DOTALL)
    assert match, "goHome fehlt"
    assert "loadBurners" not in match.group(1)


def test_only_the_three_disc_areas_trigger_detection():
    match = re.search(r"function openFlow\(name\)\{(.*?)\n\}", UI, re.DOTALL)
    assert match, "openFlow fehlt"
    body = match.group(1)
    assert "name==='burn'" in body
    assert "name==='rip'" in body
    assert "name==='disccopy'" in body
    assert body.count("loadBurners") == 1, "mehr als ein Erkennungspfad"


def test_detection_result_is_cached_for_the_session():
    match = re.search(r"async function loadBurners\(force\)\{(.*?)\n\}", UI, re.DOTALL)
    assert match, "loadBurners(force) fehlt"
    body = match.group(1)
    assert "if(DRIVES_LOADED && !force) return;" in body
    # Nur ein erfolgreicher Lauf darf als erledigt gelten.
    assert "DRIVES_LOADED = true;" in body


def test_refresh_buttons_force_a_fresh_scan():
    """Jeder Knopf, der die Erkennung anstoesst, muss sie auch erzwingen.

    Frueher stand hier eine feste Anzahl. Das prueft nicht die Eigenschaft,
    sondern den Stand: ein berechtigter dritter Knopf - der Rip-Bereich hatte
    als einziger keinen - liess den Test scheitern, obwohl nichts kaputt war.
    """
    handlers = re.findall(r'onclick="loadBurners\((.*?)\)"', UI)

    assert handlers, "Kein Neu-suchen-Knopf gefunden"
    assert all(arg.strip() == "true" for arg in handlers), \
        f"Ein Knopf stoesst die Erkennung ohne force an: {handlers}"


def test_no_periodic_background_drive_detection():
    """Ein Timer auf die Erkennung waere genau das, was vermieden werden soll."""
    for timer in re.findall(r"set(?:Interval|Timeout)\((.*?),", UI):
        if "loadBurners" in timer:
            assert "setInterval" not in UI[max(0, UI.index(timer) - 12):UI.index(timer)], \
                "periodische Laufwerkserkennung gefunden"
    assert "setInterval(loadBurners" not in UI
    assert "setInterval(() => loadBurners" not in UI


# Execute real copy handlers through the pipeline; only physical I/O is replaced.
import asyncio
from types import SimpleNamespace
import pytest
from src.models.media import JobState, JobType
from src.services.ripper import DiscRipper


@pytest.fixture
def copy_runtime(disc_bridge, monkeypatch):
    create, _ = disc_bridge
    bridge = create(Path("."))
    submitted = []
    calls = []
    waiting = asyncio.Event()
    completed = asyncio.Event()
    info = {"present": True, "blank": True, "rewritable": False, "profile": "DVD+R"}

    def submit(job, handler):
        submitted.append((job, handler))
        job.on_progress = lambda *_: waiting.set() if job.params.get("awaiting_copy_medium") else None
        return json.dumps({"job_id": job.id})

    async def rip(self, source, output, fmt, job=None):
        calls.append(("rip", source, output))
        output.write_bytes(b"copied filesystem")
        return output

    async def burn(image, device, job=None):
        assert image.read_bytes() == b"copied filesystem"
        calls.append(("burn", device, image))

    async def probe(device):
        calls.append(("probe", device))
        return dict(info)

    monkeypatch.setattr(bridge, "_submit_job", submit)
    monkeypatch.setattr(DiscRipper, "rip", rip)
    monkeypatch.setattr(bridge.disc, "burn_iso", burn)
    monkeypatch.setattr(bridge.disc, "get_disc_info", probe)
    bridge.pipeline.play_sound = False
    bridge.pipeline.on_job_complete = lambda job: completed.set()
    bridge.pipeline.on_job_failed = lambda job: completed.set()
    return SimpleNamespace(bridge=bridge, submitted=submitted, calls=calls,
                           waiting=waiting, completed=completed, info=info)


async def start_copy(runtime, source="D:", target="E:"):
    result = json.loads(runtime.bridge.copy_disc(source, target))
    job, handler = runtime.submitted[-1]
    assert result["job_id"] == job.id
    assert job.job_type == JobType.RIP_DVD
    await runtime.bridge.pipeline.submit(job, handler)
    runner = asyncio.create_task(runtime.bridge.pipeline.start())
    return job, runner


async def stop_copy(runtime, runner):
    await runtime.bridge.pipeline.shutdown()
    await runner


@pytest.mark.asyncio
async def test_two_drives_rip_then_burn_without_media_confirmation(copy_runtime):
    r = copy_runtime
    job, runner = await start_copy(r)
    try:
        await asyncio.wait_for(r.completed.wait(), 2)
        assert job.state == JobState.DONE
        assert [c[0] for c in r.calls] == ["rip", "burn"]
    finally:
        await stop_copy(r, runner)


@pytest.mark.asyncio
async def test_single_drive_waits_until_confirmed_blank_medium(copy_runtime, monkeypatch):
    r = copy_runtime
    job, runner = await start_copy(r, "D:", "d:/")
    try:
        await asyncio.wait_for(r.waiting.wait(), 2)
        assert [c[0] for c in r.calls] == ["rip"]
        assert job.state == JobState.RUNNING
        assert json.loads(r.bridge.get_queue())[0]["awaiting_copy_medium"] is True
        for unsuitable in (
            {"present": False, "blank": True},
            {"present": True, "blank": False, "rewritable": False},
            {"present": True, "blank": False, "rewritable": True},
            {"error": "drive read failed", "present": True, "blank": True},
        ):
            r.info.clear()
            r.info.update(unsuitable)
            assert "error" in await r.bridge._confirm_copy_medium(job.id)
            assert not any(c[0] == "burn" for c in r.calls)
            assert job.params["awaiting_copy_medium"] is True
        r.info.clear()
        r.info.update(present=True, blank=True, rewritable=True, profile="DVD+RW")
        from retrodisc_launcher import RetroDiscApi
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(r.bridge, "_async", lambda coro: asyncio.run_coroutine_threadsafe(coro, loop))
        response = await asyncio.to_thread(RetroDiscApi(r.bridge).confirm_copy_medium, job.id)
        assert json.loads(response) == {"ok": True}
        await asyncio.wait_for(r.completed.wait(), 2)
        assert job.state == JobState.DONE
        assert [c[0] for c in r.calls].count("burn") == 1
        assert not job.params["awaiting_copy_medium"]
        assert "error" in await r.bridge._confirm_copy_medium(job.id)
    finally:
        await stop_copy(r, runner)


@pytest.mark.asyncio
async def test_cancel_waiting_copy_preserves_image_without_burning(copy_runtime):
    r = copy_runtime
    job, runner = await start_copy(r, "D:", "D:")
    try:
        await asyncio.wait_for(r.waiting.wait(), 2)
        assert await r.bridge.pipeline.cancel_job(job.id)
        await r.bridge.pipeline.shutdown()
        assert job.state == JobState.CANCELLED
        assert not job.params["awaiting_copy_medium"]
        assert job.output_path.read_bytes() == b"copied filesystem"
        assert not any(c[0] == "burn" for c in r.calls)
        assert "error" in await r.bridge._confirm_copy_medium(job.id)
    finally:
        await stop_copy(r, runner)


@pytest.mark.asyncio
async def test_copy_paths_are_unique_and_existing_files_survive(copy_runtime):
    r = copy_runtime
    for _ in range(2):
        r.bridge.copy_disc("D:", "E:")
    first, second = [item[0] for item in r.submitted]
    assert first.id != second.id
    assert first.output_path != second.output_path
    assert first.id in first.output_path.name
    assert second.id in second.output_path.name
    existing = first.output_path
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"user image")
    await asyncio.gather(*(handler(job) for job, handler in r.submitted))
    assert existing.read_bytes() == b"user image"
    assert first.output_path != existing
    assert first.output_path != second.output_path
    assert first.output_path.read_bytes() == second.output_path.read_bytes() == b"copied filesystem"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["rip", "burn"])
async def test_copy_io_errors_fail_job_without_unwanted_burn(copy_runtime, monkeypatch, stage):
    r = copy_runtime
    async def fail(*args, **kwargs):
        if stage == "rip":
            Path(args[2]).write_bytes(b"partial")
        raise OSError("simulated I/O failure")
    if stage == "rip":
        monkeypatch.setattr(DiscRipper, "rip", fail)
    else:
        monkeypatch.setattr(r.bridge.disc, "burn_iso", fail)
    job, runner = await start_copy(r)
    try:
        await asyncio.wait_for(r.completed.wait(), 2)
        assert job.state == JobState.FAILED
        assert "simulated I/O failure" in job.error_message
        assert job.output_path.exists() == (stage == "burn")
        assert not any(c[0] == "burn" for c in r.calls)
    finally:
        await stop_copy(r, runner)


@pytest.mark.asyncio
async def test_cancel_during_medium_probe_cannot_resume_burning(copy_runtime, monkeypatch):
    r = copy_runtime
    entered, release = asyncio.Event(), asyncio.Event()
    async def probe(device):
        entered.set()
        await release.wait()
        return {"present": True, "blank": True, "profile": "DVD+R"}
    monkeypatch.setattr(r.bridge.disc, "get_disc_info", probe)
    job, runner = await start_copy(r, "D:", "D:")
    try:
        await asyncio.wait_for(r.waiting.wait(), 2)
        check = asyncio.create_task(r.bridge._confirm_copy_medium(job.id))
        await asyncio.wait_for(entered.wait(), 2)
        await r.bridge.pipeline.cancel_job(job.id)
        release.set()
        assert "error" in await check
        assert not any(c[0] == "burn" for c in r.calls)
    finally:
        release.set()
        await stop_copy(r, runner)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile,capacity", [
    ("", None), ("unknown", None), ("DVD-ROM", None),
    ("BD-ROM", None), ("CD-R", None), ("DVD+R", 1),
])
async def test_blank_but_unsuitable_medium_never_releases_copy(copy_runtime, profile, capacity):
    r = copy_runtime
    r.info.update(profile=profile)
    if capacity is not None:
        r.info["capacity_bytes"] = capacity
    job, runner = await start_copy(r, "D:", "D:")
    try:
        await asyncio.wait_for(r.waiting.wait(), 2)
        result = await r.bridge._confirm_copy_medium(job.id)
        assert "error" in result
        assert not job._copy_media_ready.is_set()
        assert [call[0] for call in r.calls] == ["rip", "probe"]
    finally:
        await stop_copy(r, runner)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["DVD-R Sequential", "DVD+R Double Layer", "BD-R", "BD-RE"])
async def test_supported_blank_profile_allows_burn(copy_runtime, profile):
    r = copy_runtime
    r.info.update(profile=profile, rewritable=profile == "BD-RE")
    job, runner = await start_copy(r, "D:", "D:")
    try:
        await asyncio.wait_for(r.waiting.wait(), 2)
        assert await r.bridge._confirm_copy_medium(job.id) == {"ok": True}
        await asyncio.wait_for(r.completed.wait(), 2)
        assert job.state == JobState.DONE
        assert [call[0] for call in r.calls] == ["rip", "probe", "burn"]
    finally:
        await stop_copy(r, runner)


@pytest.mark.asyncio
async def test_probe_exception_keeps_copy_waiting_and_allows_retry(copy_runtime, monkeypatch):
    r = copy_runtime
    original_probe = r.bridge.disc.get_disc_info
    async def fail(device):
        raise OSError("drive temporarily unavailable")
    monkeypatch.setattr(r.bridge.disc, "get_disc_info", fail)
    job, runner = await start_copy(r, "D:", "D:")
    try:
        await asyncio.wait_for(r.waiting.wait(), 2)
        result = await r.bridge._confirm_copy_medium(job.id)
        assert "drive temporarily unavailable" in result["error"]
        assert not job._copy_media_ready.is_set()
        assert [call[0] for call in r.calls] == ["rip"]
        monkeypatch.setattr(r.bridge.disc, "get_disc_info", original_probe)
        assert await r.bridge._confirm_copy_medium(job.id) == {"ok": True}
        await asyncio.wait_for(r.completed.wait(), 2)
        assert job.state == JobState.DONE
    finally:
        await stop_copy(r, runner)


@pytest.mark.asyncio
async def test_cancel_during_rip_removes_partial_reserved_image(copy_runtime, monkeypatch):
    r = copy_runtime
    entered = asyncio.Event()
    async def rip(self, source, output, fmt, job=None):
        output.write_bytes(b"partial copy")
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(DiscRipper, "rip", rip)
    job, runner = await start_copy(r, "D:", "D:")
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert await r.bridge.pipeline.cancel_job(job.id)
        await r.bridge.pipeline.shutdown()
        assert job.state == JobState.CANCELLED
        assert not job.output_path.exists()
        assert not r.calls
    finally:
        await stop_copy(r, runner)
