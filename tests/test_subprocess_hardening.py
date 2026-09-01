"""Regressionstests für die Windows-Release-Härtung der Subprozess-Aufrufe.

Gebündelte CLI-Helfer (FFmpeg, yt-dlp, dvdauthor, cdrecord, PowerShell …)
dürfen unter Windows kein Konsolenfenster aufblitzen lassen. Bewusste
Benutzeraktionen (Explorer/Finder/Standardplayer öffnen) müssen dagegen
sichtbar und unverändert bleiben.
"""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import src.utils.subprocesses as sp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = sp._CREATE_NO_WINDOW

# Produktive Module, deren Hintergrund-CLI-Aufrufe versteckt laufen müssen.
BACKGROUND_MODULES = (
    "src/core/disc.py",
    "src/core/downloader.py",
    "src/core/ffmpeg.py",
    "src/services/dvd_workflow.py",
    "src/services/upscaler.py",
    "src/ui/desktop.py",
)


# ── Helper-Verhalten: creationflags / CREATE_NO_WINDOW ──────────────

def test_create_no_window_constant_matches_win32_value():
    # 0x08000000 == subprocess.CREATE_NO_WINDOW; Fallback muss identisch sein.
    assert NO_WINDOW == 0x08000000


@pytest.mark.asyncio
async def test_create_hidden_subprocess_injects_flag_on_windows():
    seen: dict = {}

    async def fake_exec(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return "proc"

    with patch.object(sp.os, "name", "nt"), \
         patch.object(sp.asyncio, "create_subprocess_exec", fake_exec):
        result = await sp.create_hidden_subprocess(
            "ffmpeg", "-version", stdout=sp.asyncio.subprocess.PIPE
        )

    assert result == "proc"
    assert seen["args"] == ("ffmpeg", "-version")
    assert seen["kwargs"]["stdout"] == sp.asyncio.subprocess.PIPE
    assert seen["kwargs"]["creationflags"] & NO_WINDOW


@pytest.mark.asyncio
async def test_create_hidden_subprocess_keeps_existing_creationflags():
    seen: dict = {}

    async def fake_exec(*args, **kwargs):
        seen.update(kwargs)
        return "proc"

    extra = 0x00000200  # CREATE_NEW_PROCESS_GROUP
    with patch.object(sp.os, "name", "nt"), \
         patch.object(sp.asyncio, "create_subprocess_exec", fake_exec):
        await sp.create_hidden_subprocess("dvdauthor", creationflags=extra)

    assert seen["creationflags"] & NO_WINDOW
    assert seen["creationflags"] & extra


@pytest.mark.asyncio
async def test_create_hidden_subprocess_untouched_off_windows():
    seen: dict = {}

    async def fake_exec(*args, **kwargs):
        seen["kwargs"] = kwargs
        return "proc"

    with patch.object(sp.os, "name", "posix"), \
         patch.object(sp.asyncio, "create_subprocess_exec", fake_exec):
        await sp.create_hidden_subprocess("ffmpeg", "-version")

    assert "creationflags" not in seen["kwargs"]


def test_run_hidden_injects_flag_on_windows():
    seen: dict = {}

    def fake_run(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args[0], 0, "", "")

    with patch.object(sp.os, "name", "nt"), \
         patch.object(sp.subprocess, "run", fake_run):
        sp.run_hidden(["powershell", "-NoProfile", "-Command", "x"],
                      capture_output=True, text=True, timeout=15)

    assert seen["kwargs"]["creationflags"] & NO_WINDOW
    assert seen["kwargs"]["timeout"] == 15
    assert seen["kwargs"]["capture_output"] is True


def test_run_hidden_untouched_off_windows():
    seen: dict = {}

    def fake_run(*args, **kwargs):
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args[0], 0, "", "")

    with patch.object(sp.os, "name", "posix"), \
         patch.object(sp.subprocess, "run", fake_run):
        sp.run_hidden(["eject", "/dev/sr0"])

    assert "creationflags" not in seen["kwargs"]


def test_run_hidden_propagates_timeout_expired():
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

    with patch.object(sp.subprocess, "run", fake_run):
        with pytest.raises(subprocess.TimeoutExpired):
            sp.run_hidden(["powershell", "-Command", "x"], timeout=1)


# ── Statische Absicherung: keine nackten produktiven Aufrufe ────────

def _attribute_chain(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


@pytest.mark.parametrize("rel_path", BACKGROUND_MODULES)
def test_background_modules_have_no_bare_subprocess_calls(rel_path):
    source = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=rel_path)

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _attribute_chain(node.func)
        if chain == "asyncio.create_subprocess_exec":
            offenders.append(f"{rel_path}:{node.lineno} {chain}")
        if chain == "asyncio.create_subprocess_shell":
            offenders.append(f"{rel_path}:{node.lineno} {chain}")
        if chain in {"subprocess.run", "subprocess.call",
                     "subprocess.check_call", "subprocess.check_output"}:
            offenders.append(f"{rel_path}:{node.lineno} {chain}")

    assert not offenders, "Nackte Hintergrund-Subprozesse: " + ", ".join(offenders)


@pytest.mark.parametrize("rel_path", BACKGROUND_MODULES)
def test_background_modules_import_hidden_helpers(rel_path):
    source = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")
    if "create_subprocess" in source or "asyncio.subprocess" in source:
        assert "from src.utils.subprocesses import" in source


# ── Negativtest: Benutzeraktionen bleiben bewusst sichtbar ──────────

def _function_source(module_source: str, func_name: str) -> str:
    tree = ast.parse(module_source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return ast.get_source_segment(module_source, node) or ""
    raise AssertionError(f"Funktion {func_name} nicht gefunden")


def test_desktop_user_actions_stay_visible():
    source = (PROJECT_ROOT / "src/ui/desktop.py").read_text(encoding="utf-8")

    open_folder = _function_source(source, "open_output_folder")
    assert 'subprocess.Popen(["explorer"' in open_folder
    assert 'subprocess.Popen(["open"' in open_folder
    assert 'subprocess.Popen(["xdg-open"' in open_folder
    for hidden in ("create_hidden_subprocess", "run_hidden", "creationflags",
                   "CREATE_NO_WINDOW"):
        assert hidden not in open_folder

    preview = _function_source(source, "preview_trim")
    assert "os.startfile(" in preview
    assert 'subprocess.Popen(["open"' in preview
    assert 'subprocess.Popen(["xdg-open"' in preview
    for hidden in ("create_hidden_subprocess", "run_hidden", "creationflags",
                   "CREATE_NO_WINDOW"):
        assert hidden not in preview


def test_desktop_drive_query_is_hidden():
    source = (PROJECT_ROOT / "src/ui/desktop.py").read_text(encoding="utf-8")
    query = _function_source(source, "_query_drive_names")
    assert "create_hidden_subprocess(" in query
    assert "asyncio.create_subprocess_exec(" not in query


@pytest.mark.parametrize("rel_path", ("retrodisc_portable.py", "retrodisc_launcher.py"))
def test_launchers_keep_startfile_and_webbrowser_untouched(rel_path):
    source = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")
    # Bewusste Öffnen-Aktionen für den Benutzer bleiben sichtbar/unverändert.
    assert "os.startfile(" in source
    assert "webbrowser.open(" in source
    assert "create_hidden_subprocess" not in source


# ── PowerShell-Timeout-Pfad der Brenner-Erkennung ──────────────────

def _bare_bridge(module):
    return object.__new__(module.RetroDiscBridge)


def test_portable_detect_burners_handles_powershell_timeout():
    import retrodisc_portable as portable

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

    with patch("platform.system", return_value="Windows"), \
         patch.object(sp.subprocess, "run", fake_run):
        raw = portable.RetroDiscBridge.detect_burners(_bare_bridge(portable))

    payload = json.loads(raw)
    assert payload["drives"] == []
    assert "Zeit" in payload["error"]


def test_launcher_detect_burners_survives_powershell_timeout():
    import retrodisc_launcher as launcher

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

    with patch("platform.system", return_value="Windows"), \
         patch.object(sp.subprocess, "run", fake_run):
        raw = launcher.RetroDiscBridge.detect_burners(_bare_bridge(launcher))

    payload = json.loads(raw)
    assert payload["drives"] == []
    assert payload["error"]


def test_portable_module_imports_subprocess_for_timeout_guard():
    """Regression: `except subprocess.TimeoutExpired` darf nicht mit
    NameError abstürzen, weil der Import entfernt wurde."""
    import retrodisc_portable as portable

    assert hasattr(portable, "subprocess")
    detect_src = _function_source(
        (PROJECT_ROOT / "retrodisc_portable.py").read_text(encoding="utf-8"),
        "detect_burners",
    )
    assert "subprocess.TimeoutExpired" in detect_src
