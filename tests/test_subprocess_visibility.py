"""Regression tests for invisible background CLI processes on Windows."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.utils.subprocesses as hidden_processes


PROJECT_ROOT = Path(__file__).parent.parent


def _completed_process(args, returncode=0):
    return subprocess.CompletedProcess(args=args, returncode=returncode)


def test_run_hidden_hides_window_and_preserves_existing_flags(monkeypatch):
    seen = {}

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return _completed_process(args)

    monkeypatch.setattr(hidden_processes, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(hidden_processes.subprocess, "run", fake_run)

    hidden_processes.run_hidden(["tool.exe"], creationflags=0x10)

    assert seen["creationflags"] & hidden_processes._CREATE_NO_WINDOW
    assert seen["creationflags"] & 0x10


def test_run_hidden_does_not_pass_windows_flag_on_posix(monkeypatch):
    seen = {}

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return _completed_process(args)

    monkeypatch.setattr(hidden_processes, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(hidden_processes.subprocess, "run", fake_run)

    hidden_processes.run_hidden(["tool"])

    assert "creationflags" not in seen


@pytest.mark.asyncio
async def test_async_hidden_process_uses_create_no_window(monkeypatch):
    seen = {}
    sentinel = object()

    async def fake_exec(*args, **kwargs):
        seen.update(kwargs)
        return sentinel

    monkeypatch.setattr(hidden_processes, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        hidden_processes.asyncio, "create_subprocess_exec", fake_exec
    )

    result = await hidden_processes.create_hidden_subprocess("tool.exe")

    assert result is sentinel
    assert seen["creationflags"] & hidden_processes._CREATE_NO_WINDOW


@pytest.mark.asyncio
async def test_async_hidden_process_preserves_flags_and_skips_them_on_posix(monkeypatch):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(
        hidden_processes.asyncio, "create_subprocess_exec", fake_exec
    )
    monkeypatch.setattr(hidden_processes, "os", SimpleNamespace(name="nt"))
    await hidden_processes.create_hidden_subprocess("tool.exe", creationflags=0x10)
    assert calls[-1]["creationflags"] & hidden_processes._CREATE_NO_WINDOW
    assert calls[-1]["creationflags"] & 0x10

    monkeypatch.setattr(hidden_processes, "os", SimpleNamespace(name="posix"))
    await hidden_processes.create_hidden_subprocess("tool")
    assert "creationflags" not in calls[-1]


def test_product_code_has_no_unwrapped_background_cli_launches():
    """New bundled CLI launches must use the central no-window wrappers."""
    files = [PROJECT_ROOT / "retrodisc_launcher.py", PROJECT_ROOT / "retrodisc_portable.py"]
    files.extend((PROJECT_ROOT / "src").rglob("*.py"))
    wrapper = PROJECT_ROOT / "src" / "utils" / "subprocesses.py"
    forbidden = {
        ("asyncio", "create_subprocess_exec"),
        ("asyncio", "create_subprocess_shell"),
        ("subprocess", "run"),
        ("subprocess", "call"),
        ("subprocess", "check_call"),
        ("subprocess", "check_output"),
    }
    findings = []

    for path in files:
        if path == wrapper:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            func = getattr(node, "func", None)
            owner = getattr(getattr(func, "value", None), "id", None)
            name = getattr(func, "attr", None)
            if (owner, name) in forbidden:
                findings.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")
            if (owner, name) == ("subprocess", "Popen"):
                first_arg = node.args[0] if node.args else None
                command = None
                if isinstance(first_arg, (ast.List, ast.Tuple)) and first_arg.elts:
                    command = getattr(first_arg.elts[0], "value", None)
                if command not in {"explorer", "open", "xdg-open"}:
                    findings.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")

    assert findings == []


def test_portable_burner_detection_degrades_cleanly_on_timeout(monkeypatch):
    import retrodisc_portable as portable

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=15)

    monkeypatch.setattr(portable.platform, "system", lambda: "Windows")
    monkeypatch.setattr(hidden_processes, "run_hidden", timeout)
    bridge = portable.RetroDiscBridge.__new__(portable.RetroDiscBridge)

    result = json.loads(bridge.detect_burners())

    assert result["drives"] == []
    assert "Zeitueberschreitung" in result["error"]
