"""Tests für den kanonischen Brennpfad ``DiscTools.burn_iso`` (P0 Block 3).

Reine Software-Tests ohne Hardware: der einzige Subprozess-Aufruf
(``create_hidden_subprocess`` für growisofs/cdrecord) wird gefaked, ebenso
``_run_tool``/``_read_book_type`` für Book Type und ``verify_iso_result``
für die Verifikation - jeweils auf derselben Ebene wie die bereits
bestehenden, weiterhin grünen Tests in tests/test_burn_result.py.
"""
from __future__ import annotations

import pytest

from src.core.disc import DiscError, DiscTools
from src.services.booktype import BookType
from src.services.burn_outcome import BookTypeStatus
from src.services.verify import FAIL, NOT_AVAILABLE, PASS, Check, VerifyResult


class _FakeProc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


def _tools(monkeypatch, *, returncode=0, run_tool_ok=True, verify_result=None) -> DiscTools:
    tools = DiscTools()
    tools.booktype = "dvd+rw-booktype"
    monkeypatch.setattr("src.core.disc.shutil.which", lambda name: name)

    async def fake_subprocess(*args, **kwargs):
        return _FakeProc(returncode=returncode)

    monkeypatch.setattr("src.core.disc.create_hidden_subprocess", fake_subprocess)

    async def fake_run_tool(cmd, timeout=30):
        if not run_tool_ok:
            raise RuntimeError("Werkzeug-Aufruf fehlgeschlagen")
        return "ok"

    monkeypatch.setattr(tools, "_run_tool", fake_run_tool)
    monkeypatch.setattr(tools, "_read_book_type", lambda device: _async_value("DVD-ROM"))

    result = verify_result or VerifyResult(status=PASS, message="Alle Prüfungen bestanden.")

    async def fake_verify_iso_result(iso_path, device):
        return result

    monkeypatch.setattr(tools, "verify_iso_result", fake_verify_iso_result)
    return tools


async def _async_value(value):
    return value


@pytest.fixture
def iso(tmp_path):
    path = tmp_path / "test.iso"
    path.write_bytes(b"0" * 4096)
    return path


# ─── Book Type: AUTO ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_applies_dvd_rom_when_medium_and_backend_support_it(monkeypatch, iso):
    tools = _tools(monkeypatch)
    outcome = await tools.burn_iso(iso, "E:", verify=False, book_type=BookType.AUTO, media_type="DVD+R")
    assert outcome.burn_success is True
    assert outcome.book_type_status == BookTypeStatus.APPLIED
    assert outcome.book_type_actual == "DVD-ROM"


@pytest.mark.asyncio
async def test_auto_is_not_applicable_on_non_bitsettable_medium(monkeypatch, iso):
    tools = _tools(monkeypatch)
    outcome = await tools.burn_iso(iso, "E:", verify=False, book_type=BookType.AUTO, media_type="DVD-R")
    assert outcome.burn_success is True
    assert outcome.book_type_status == BookTypeStatus.NOT_APPLICABLE
    assert outcome.book_type_warning is None


# ─── Book Type: NATIVE ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_native_never_attempts_a_change_even_on_capable_medium(monkeypatch, iso):
    tools = _tools(monkeypatch)
    calls = []
    monkeypatch.setattr(tools, "_run_tool", _record_call(calls))
    outcome = await tools.burn_iso(iso, "E:", verify=False, book_type=BookType.NATIVE, media_type="DVD+R")
    assert outcome.book_type_status == BookTypeStatus.NOT_REQUESTED
    assert calls == []


def _record_call(calls):
    async def _fake(cmd, timeout=30):
        calls.append(cmd)
        return "ok"
    return _fake


@pytest.mark.asyncio
async def test_burn_iso_default_book_type_is_native_for_backward_compatibility(monkeypatch, iso):
    """Kein book_type angegeben -> wie vor diesem Block: keine Book-Type-Aenderung."""
    tools = _tools(monkeypatch)
    outcome = await tools.burn_iso(iso, "E:", verify=False, media_type="DVD+R")
    assert outcome.book_type_status == BookTypeStatus.NOT_REQUESTED


# ─── Book Type: DVD-ROM ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dvd_rom_supported_applies_and_reads_back(monkeypatch, iso):
    tools = _tools(monkeypatch)
    outcome = await tools.burn_iso(iso, "E:", verify=False, book_type=BookType.DVD_ROM, media_type="DVD+R")
    assert outcome.book_type_status == BookTypeStatus.APPLIED
    assert outcome.book_type_actual == "DVD-ROM"
    assert outcome.book_type_warning is None


@pytest.mark.asyncio
async def test_dvd_rom_not_supported_medium_family_is_not_applicable(monkeypatch, iso):
    tools = _tools(monkeypatch)
    outcome = await tools.burn_iso(iso, "E:", verify=False, book_type=BookType.DVD_ROM, media_type="DVD-R")
    assert outcome.book_type_status == BookTypeStatus.NOT_APPLICABLE
    assert outcome.burn_success is True   # Brennen läuft trotzdem normal weiter


@pytest.mark.asyncio
async def test_dvd_rom_capable_medium_but_missing_backend_is_not_supported(monkeypatch, iso):
    tools = _tools(monkeypatch)
    monkeypatch.setattr(tools, "book_type_available", lambda media_type: False)
    outcome = await tools.burn_iso(iso, "E:", verify=False, book_type=BookType.DVD_ROM, media_type="DVD+R")
    assert outcome.book_type_status == BookTypeStatus.NOT_SUPPORTED
    assert "Bitsetting" in outcome.book_type_warning
    assert outcome.burn_success is True


@pytest.mark.asyncio
async def test_book_type_tool_failure_does_not_fail_an_otherwise_successful_burn(monkeypatch, iso):
    tools = _tools(monkeypatch, run_tool_ok=False)
    outcome = await tools.burn_iso(iso, "E:", verify=False, book_type=BookType.DVD_ROM, media_type="DVD+R")
    assert outcome.burn_success is True             # Brennen trotzdem erfolgreich
    assert outcome.book_type_status == BookTypeStatus.FAILED
    assert "Book Type konnte nicht gesetzt werden" in outcome.book_type_warning


# ─── Blu-ray: keine DVD-spezifische Book-Type-Manipulation ────────────────

@pytest.mark.asyncio
async def test_bluray_never_gets_dvd_book_type_operation_even_if_requested(monkeypatch, iso):
    from src.models.media import DiscType
    tools = _tools(monkeypatch)
    calls = []
    monkeypatch.setattr(tools, "_run_tool", _record_call(calls))
    outcome = await tools.burn_iso(iso, "E:", verify=False, disc_type=DiscType.BLURAY,
                                   book_type=BookType.AUTO, media_type="BD-R")
    assert outcome.book_type_status == BookTypeStatus.NOT_APPLICABLE
    assert calls == []


@pytest.mark.asyncio
async def test_bluray_disc_type_overrides_even_a_dvd_like_media_classification(monkeypatch, iso):
    """disc_type=BLURAY ist die maßgebliche Sperre - unabhängig davon, wie
    media_type klassifiziert wurde (Verteidigung in der Tiefe)."""
    from src.models.media import DiscType
    tools = _tools(monkeypatch)
    calls = []
    monkeypatch.setattr(tools, "_run_tool", _record_call(calls))
    outcome = await tools.burn_iso(iso, "E:", verify=False, disc_type=DiscType.BLURAY,
                                   book_type=BookType.DVD_ROM, media_type="DVD+R")
    assert outcome.book_type_status == BookTypeStatus.NOT_APPLICABLE
    assert calls == []


# ─── BD-25/BD-50/BDXL-100/BDXL-128: derselbe kanonische Brennpfad wie DVD ─
# (growisofs -Z ist medienfamilien-unabhängig; siehe DiscTools.burn_iso) ───

@pytest.mark.asyncio
@pytest.mark.parametrize("media_type", ["BD-R", "BD-RE"])
async def test_bd25_and_bd50_burn_through_the_canonical_path_with_book_type_not_applicable(monkeypatch, iso, media_type):
    from src.models.media import DiscType
    tools = _tools(monkeypatch)
    # book_type=AUTO fragt eine Book-Type-Anpassung tatsaechlich an - erst
    # damit zeigt sich, dass Blu-ray sie auf NOT_APPLICABLE abweist (mit dem
    # NATIVE-Default waere sie ohnehin nie angefragt, siehe
    # test_burn_iso_default_book_type_is_native_for_backward_compatibility).
    outcome = await tools.burn_iso(iso, "E:", verify=True, disc_type=DiscType.BLURAY,
                                   book_type=BookType.AUTO, media_type=media_type)
    assert outcome.burn_success is True
    assert outcome.book_type_status == BookTypeStatus.NOT_APPLICABLE
    assert outcome.verify.status == PASS


@pytest.mark.asyncio
async def test_bdxl_100_and_128_use_the_same_growisofs_command_shape_as_bd25(monkeypatch, iso):
    """BDXL braucht kein anderes Brennkommando - nur ein BDXL-fähiges
    Laufwerk/Medium (das die UI/Bridge vorab prüft, siehe
    tests/test_bluray_bridge.py). growisofs -Z ist dieselbe Zeile für BD-25
    und BDXL-100/128."""
    from src.models.media import DiscType
    calls = []

    async def fake_subprocess(*args, **kwargs):
        calls.append(args)
        return _FakeProc(returncode=0)

    tools = _tools(monkeypatch)
    monkeypatch.setattr("src.core.disc.create_hidden_subprocess", fake_subprocess)
    outcome = await tools.burn_iso(iso, "E:", verify=False, disc_type=DiscType.BLURAY, media_type="BD-R")
    assert outcome.burn_success is True
    assert calls[0][0] == tools.growisofs
    assert "-dvd-compat" in calls[0]
    assert any(str(arg).startswith("-Z") or arg == "-Z" for arg in calls[0])


# ─── Verify ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_success_is_reflected_in_structured_result(monkeypatch, iso):
    tools = _tools(monkeypatch, verify_result=VerifyResult(status=PASS, message="ok"))
    outcome = await tools.burn_iso(iso, "E:", verify=True, media_type="DVD+R")
    assert outcome.burn_success is True
    assert outcome.verify.status == PASS


@pytest.mark.asyncio
async def test_verify_failure_does_not_raise_and_is_distinguishable_from_burn_failure(monkeypatch, iso):
    tools = _tools(monkeypatch, verify_result=VerifyResult(
        status=FAIL, checks=[Check("hash", False, "Prüfsummen unterscheiden sich.")],
        message="Prüfsummen unterscheiden sich."))
    outcome = await tools.burn_iso(iso, "E:", verify=True, media_type="DVD+R")
    assert outcome.burn_success is True             # Brennen selbst war erfolgreich
    assert outcome.verify.status == FAIL             # Verify getrennt sichtbar fehlgeschlagen
    assert outcome.error is None                      # kein genereller Burn-Fehler


@pytest.mark.asyncio
async def test_verify_disabled_yields_not_available_status(monkeypatch, iso):
    tools = _tools(monkeypatch)
    outcome = await tools.burn_iso(iso, "E:", verify=False, media_type="DVD+R")
    assert outcome.verify.status == NOT_AVAILABLE


# ─── Burn-Fehler ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_burn_failure_raises_disc_error(monkeypatch, iso):
    tools = _tools(monkeypatch, returncode=1)
    with pytest.raises(DiscError):
        await tools.burn_iso(iso, "E:", verify=False, media_type="DVD+R")


@pytest.mark.asyncio
async def test_missing_iso_raises_before_any_subprocess_call(monkeypatch, tmp_path):
    tools = _tools(monkeypatch)
    with pytest.raises(DiscError, match="nicht gefunden"):
        await tools.burn_iso(tmp_path / "does-not-exist.iso", "E:")


# ─── Strukturierte Ergebnisserialisierung ──────────────────────────────────

@pytest.mark.asyncio
async def test_burn_outcome_serializes_to_json_safe_dict(monkeypatch, iso):
    import json
    tools = _tools(monkeypatch)
    outcome = await tools.burn_iso(iso, "E:", verify=True, book_type=BookType.DVD_ROM, media_type="DVD+R")
    encoded = json.dumps(outcome.to_dict())
    decoded = json.loads(encoded)
    assert decoded["burn_success"] is True
    assert decoded["book_type_status"] == "applied"
    assert decoded["verify"]["status"] == "PASS"
    assert decoded["error"] is None


def test_burn_outcome_is_always_truthy_on_success_for_legacy_if_checks():
    """``if await burn_iso(...):`` bestehender Aufrufer darf weiterhin greifen."""
    from src.services.burn_outcome import BurnOutcome
    assert bool(BurnOutcome(burn_success=True))
    assert bool(BurnOutcome(burn_success=False))   # Objekt selbst ist immer truthy - Erfolg wird über .burn_success gelesen, nie über Wahrheitswert


# ─── Alter Kompatibilitäts-Wrapper nutzt den neuen kanonischen Pfad ───────

@pytest.mark.asyncio
async def test_burn_iso_result_wrapper_delegates_to_real_burn_iso_subprocess_layer(monkeypatch, iso):
    """burn_iso_result() enthält selbst keine Brenn-Logik: hier wird NUR die
    Subprozess-Ebene gefaked (create_hidden_subprocess), nicht burn_iso selbst -
    der komplette Weg muss trotzdem funktionieren, weil burn_iso_result
    tatsächlich über burn_iso läuft."""
    tools = DiscTools()

    async def fake_subprocess(*args, **kwargs):
        return _FakeProc(returncode=0)

    monkeypatch.setattr("src.core.disc.create_hidden_subprocess", fake_subprocess)

    result = await tools.burn_iso_result(iso, "E:", book_type="automatic", media_type="DVD+R", verify=False)

    assert result.written_size == 4096
    assert result.verify_result == "NOT_AVAILABLE"


# ─── Queue/DVD-Workflow verwendet den kanonischen Brennpfad ───────────────

@pytest.mark.asyncio
async def test_dvd_workflow_burn_step_uses_canonical_path_with_auto_book_type(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from src.models.media import DiscType
    from src.services.dvd_workflow import DVDProject, DVDWorkflow

    source = tmp_path / "clip.mpg"       # .mpg -> Konvertierschritt wird übersprungen
    source.write_bytes(b"already-dvd-compatible")

    captured = {}

    async def fake_create_dvd_structure(**kwargs):
        return tmp_path / "DVD"

    async def fake_create_iso(**kwargs):
        iso_path = tmp_path / "out.iso"
        iso_path.write_bytes(b"iso-bytes")
        return iso_path

    async def fake_burn_iso(iso_path, device, speed=None, verify=True, disc_type=DiscType.DVD,
                            job=None, book_type=None, media_type=None):
        captured["book_type"] = book_type
        captured["device"] = device
        from src.services.burn_outcome import BurnOutcome
        return BurnOutcome(burn_success=True)

    disc = SimpleNamespace(create_dvd_structure=fake_create_dvd_structure,
                           create_iso=fake_create_iso, burn_iso=fake_burn_iso)
    workflow = DVDWorkflow(ffmpeg=SimpleNamespace(), disc_tools=disc, temp_dir=tmp_path)

    project = DVDProject(title="Test", input_files=[source], output_dir=tmp_path,
                        burn_to_disc=True, disc_device="E:")   # book_type-Default = "automatic" (AUTO)

    await workflow.run(project)

    assert captured["device"] == "E:"
    assert captured["book_type"] == BookType.AUTO


@pytest.mark.asyncio
async def test_dvd_workflow_raises_when_verify_fails_even_though_burn_succeeded(tmp_path):
    from types import SimpleNamespace

    from src.core.disc import DiscError
    from src.models.media import DiscType
    from src.services.burn_outcome import BurnOutcome
    from src.services.dvd_workflow import DVDProject, DVDWorkflow
    from src.services.verify import FAIL, VerifyResult

    source = tmp_path / "clip.mpg"
    source.write_bytes(b"already-dvd-compatible")

    async def fake_create_dvd_structure(**kwargs):
        return tmp_path / "DVD"

    async def fake_create_iso(**kwargs):
        iso_path = tmp_path / "out.iso"
        iso_path.write_bytes(b"iso-bytes")
        return iso_path

    async def fake_burn_iso(iso_path, device, speed=None, verify=True, disc_type=DiscType.DVD,
                            job=None, book_type=None, media_type=None):
        return BurnOutcome(burn_success=True, verify=VerifyResult(status=FAIL, message="Prüfsummen unterscheiden sich."))

    disc = SimpleNamespace(create_dvd_structure=fake_create_dvd_structure,
                           create_iso=fake_create_iso, burn_iso=fake_burn_iso)
    workflow = DVDWorkflow(ffmpeg=SimpleNamespace(), disc_tools=disc, temp_dir=tmp_path)
    project = DVDProject(title="Test", input_files=[source], output_dir=tmp_path,
                        burn_to_disc=True, disc_device="E:")

    with pytest.raises(DiscError, match="Verifikation fehlgeschlagen"):
        await workflow.run(project)


def test_create_dvd_bridge_threads_book_type_into_dvd_project():
    """Reine Verdrahtungsprüfung ohne I/O: create_dvd() baut den Job so auf,
    dass der Handler ein DVDProject mit dem übergebenen book_type erzeugt."""
    import ast
    import inspect

    from retrodisc_launcher import RetroDiscBridge

    source = inspect.getsource(RetroDiscBridge.create_dvd)
    assert 'book_type: str = "automatic"' in source
    assert "book_type=j.params[\"book_type\"]" in source


# ─── Disc-Copy verwendet den kanonischen Brennpfad ─────────────────────────

@pytest.mark.asyncio
async def test_copy_disc_handler_passes_book_type_to_canonical_burn_iso(monkeypatch, tmp_path):
    """Ergänzt tests/test_disc_copy_flow.py: bestätigt explizit, dass der
    Disc-Copy-Handler book_type an den kanonischen burn_iso weiterreicht.

    Der Handler wird direkt aufgerufen (``_submit_job`` abgefangen und der
    Handler-Closure sofort ausgeführt) - kein Pipeline-Thread nötig, analog
    zum Aufbau in test_disc_copy_flow.py."""
    import retrodisc_launcher as launcher
    from src.config.settings import AppSettings
    from src.services.booktype import BookType
    from src.services.burn_outcome import BurnOutcome
    from src.services.ripper import DiscRipper

    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(AppSettings, "_default_config_path", staticmethod(lambda: config_path))
    AppSettings(directories={
        "output_dir": tmp_path / "output", "download_dir": tmp_path / "downloads",
        "temp_dir": tmp_path / "temp",
    }).save()
    monkeypatch.setattr(launcher, "check_tools", lambda: {})
    monkeypatch.setattr("src.services.library.MediaLibrary.open", lambda self: None)

    bridge = launcher.RetroDiscBridge()
    captured = {}
    try:
        async def rip(self, source, output, fmt, job=None):
            output.write_bytes(b"copied filesystem")
            return output

        async def burn_iso(image_path, device=None, job=None, **kwargs):
            captured["book_type"] = kwargs.get("book_type")
            return BurnOutcome(burn_success=True)

        submitted = []
        monkeypatch.setattr(bridge, "_submit_job",
                            lambda job, handler: submitted.append((job, handler)) or '{"job_id":"x"}')
        monkeypatch.setattr(DiscRipper, "rip", rip)
        monkeypatch.setattr(bridge.disc, "burn_iso", burn_iso)

        bridge.copy_disc("D:", "E:", book_type="dvd_rom")
        job, handler = submitted[-1]
        await handler(job)
    finally:
        bridge._loop.call_soon_threadsafe(bridge._loop.stop)
        bridge._thread.join(timeout=5)
        bridge._loop.close()

    assert captured.get("book_type") == BookType.DVD_ROM


# ─── list_target_media: reine Weitergabe der CapacityPlanner-Registry ─────

def test_list_target_media_bridge_method_matches_the_registry():
    """Reine Lesefunktion ohne Abhängigkeit zu self - kann daher ungebunden
    aufgerufen werden, ohne einen vollständigen Bridge-Konstruktor zu brauchen."""
    import json

    import retrodisc_launcher as launcher
    from src.config.target_media import TARGET_MEDIA

    result = json.loads(launcher.RetroDiscBridge.list_target_media(None))

    assert {m["id"] for m in result} == set(TARGET_MEDIA)
    bd128 = next(m for m in result if m["id"] == "bd128")
    assert bd128["requires_bdxl"] is True
    assert bd128["is_physical_bluray"] is True
    assert bd128["authoring_format"] == "bdmv"
    dvd5 = next(m for m in result if m["id"] == "dvd5")
    assert dvd5["is_physical_bluray"] is False
    assert dvd5["requires_bdxl"] is False
    assert "custom" not in {m["id"] for m in result}
