"""Regressionstests fuer den Windows-Installer und seinen Deinstaller.

Hintergrund: Der Deinstaller entfernte urspruenglich nur ``RetroDisc.lnk`` und
versuchte danach ein einfaches ``rmdir`` auf den Startmenue-Ordner. Weil
``install()`` dort zusaetzlich eine Deinstallations-Verknuepfung ablegt, war der
Ordner nicht leer: das ``rmdir`` scheiterte und hinterliess einen verwaisten
Startmenue-Ordner mit einer Verknuepfung auf ein bereits geloeschtes Skript.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_SOURCE = ROOT / "installer" / "retrodisc_installer.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("retrodisc_installer", INSTALLER_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _first_quoted(line: str) -> str | None:
    parts = line.split('"')
    return parts[1] if len(parts) >= 2 else None


def _removal_plan(script: str) -> tuple[set[Path], set[Path], set[Path]]:
    """Zerlegt das Deinstallationsskript in geloeschte Dateien und Ordner."""
    deleted_files: set[Path] = set()
    removed_dirs: set[Path] = set()
    recursive_dirs: set[Path] = set()
    for raw in script.splitlines():
        # Eine Zeile kann mehrere Befehle tragen, etwa die Selbstloesch-
        # Uebergabe "(goto) 2>nul & rmdir /s /q ...".
        for segment in raw.split("&"):
            line = segment.strip()
            lowered = line.lower()
            target = _first_quoted(line)
            if not target:
                continue
            expanded = Path(os.path.expandvars(target))
            if lowered.startswith("del "):
                deleted_files.add(expanded)
            elif lowered.startswith("rmdir"):
                removed_dirs.add(expanded)
                if "/s" in lowered:
                    recursive_dirs.add(expanded)
    return deleted_files, removed_dirs, recursive_dirs


def _is_covered(path: Path, deleted_files: set[Path], recursive_dirs: set[Path]) -> bool:
    if path in deleted_files:
        return True
    return any(parent in recursive_dirs for parent in path.parents)


@pytest.fixture()
def installed(tmp_path, monkeypatch):
    """Fuehrt eine echte install()-Runde in einer isolierten Umgebung aus."""
    module = load_installer()

    appdata = tmp_path / "Roaming"
    localappdata = tmp_path / "Local"
    userprofile = tmp_path / "User"
    (userprofile / "Desktop").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))
    monkeypatch.setenv("USERPROFILE", str(userprofile))

    embedded = tmp_path / "embedded" / module.EXE_NAME
    embedded.parent.mkdir(parents=True)
    embedded.write_bytes(b"MZ fake payload")
    monkeypatch.setattr(module, "resource_path", lambda relative: embedded)

    created: list[Path] = []

    def fake_create_shortcut(link_path, target, working_dir, description):
        link_path = Path(link_path)
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.write_text("shortcut", encoding="utf-8")
        created.append(link_path)
        return True

    monkeypatch.setattr(module, "create_shortcut", fake_create_shortcut)

    install_dir = localappdata / "Programs" / module.APP_NAME
    rc = module.install(
        install_dir=install_dir,
        desktop_shortcut=True,
        start_menu_shortcut=True,
        launch=False,
    )
    assert rc == 0

    script = (install_dir / "Uninstall RetroDisc.cmd").read_text(encoding="utf-8")
    return module, install_dir, created, script


def test_install_places_program_uninstaller_and_shortcuts(installed):
    module, install_dir, created, _script = installed

    assert (install_dir / module.EXE_NAME).is_file()
    assert (install_dir / "Uninstall RetroDisc.cmd").is_file()
    # Desktop-Verknuepfung plus Start- und Deinstallations-Verknuepfung.
    assert len(created) == 3
    assert all(link.is_file() for link in created)


def test_uninstaller_removes_every_shortcut_the_installer_creates(installed):
    """Kernregression: keine vom Installer erzeugte Verknuepfung darf zurueckbleiben."""
    _module, _install_dir, created, script = installed

    deleted_files, _removed_dirs, recursive_dirs = _removal_plan(script)

    uncovered = [str(link) for link in created if not _is_covered(link, deleted_files, recursive_dirs)]
    assert not uncovered, f"Deinstaller entfernt diese Verknuepfungen nicht: {uncovered}"


def test_uninstaller_removes_start_menu_folder_recursively(installed):
    """Ein nicht rekursives rmdir scheitert am nicht leeren App-Ordner."""
    module, _install_dir, _created, script = installed

    start_menu = module.start_menu_dir()
    _deleted, removed_dirs, recursive_dirs = _removal_plan(script)

    assert start_menu in removed_dirs, "Startmenue-Ordner wird gar nicht entfernt"
    assert start_menu in recursive_dirs, (
        "Startmenue-Ordner wird ohne /s entfernt und bleibt wegen der "
        "Deinstallations-Verknuepfung als verwaister Ordner zurueck"
    )


def test_uninstaller_removes_the_installation_directory(installed):
    _module, install_dir, _created, script = installed

    assert f'set "RD_TARGET={install_dir}"' in script
    assert "Remove-Item -LiteralPath $t -Recurse -Force" in script


def test_uninstaller_hands_self_deletion_to_hidden_helper(installed):
    """Der Eltern-cmd darf den eigenen Installationsordner nicht synchron loeschen."""
    _module, install_dir, _created, script = installed

    lines = [line.strip() for line in script.splitlines() if line.strip()]
    assignment = next(i for i, line in enumerate(lines) if line.startswith('set "RD_TARGET='))
    leave_dir = next(i for i, line in enumerate(lines) if line.lower() == 'cd /d "%temp%"')
    helper = next(i for i, line in enumerate(lines) if line.lower().startswith('start "" /b powershell.exe'))

    assert str(install_dir) in lines[assignment]
    assert assignment < leave_dir < helper
    assert "-WindowStyle Hidden" in lines[helper]
    assert "-LiteralPath $t" in lines[helper]
    assert not any(
        line.lower().startswith(("rmdir", "del")) and str(install_dir) in line
        for line in lines
    )


def test_uninstaller_reports_success_before_removing_itself(installed):
    """Der Nutzer muss die Erfolgsmeldung und pause noch sehen."""
    _module, _install_dir, _created, script = installed

    lines = [line.strip() for line in script.splitlines() if line.strip()]
    fertig = next(i for i, line in enumerate(lines) if line.lower().startswith("echo fertig"))
    pause = next(i for i, line in enumerate(lines) if line.lower() == "pause")
    removal = next(i for i, line in enumerate(lines) if line.lower().startswith('start "" /b powershell.exe'))

    assert fertig < removal, "Erfolgsmeldung wuerde nach dem Abbruch nie erscheinen"
    assert pause < removal, "pause wuerde nach dem Abbruch nie erreicht"


@pytest.mark.skipif(sys.platform != "win32", reason="uninstaller is a Windows .cmd")
def test_generated_uninstaller_deletes_its_own_directory(tmp_path, monkeypatch):
    """Reale Regression fuer Exitcode 32 und den leeren Restordner."""
    module = load_installer()
    install_dir = tmp_path / "Local Programs" / "RetroDisc QA & Co"
    (install_dir / "sub").mkdir(parents=True)
    (install_dir / module.EXE_NAME).write_bytes(b"MZ fake payload")
    (install_dir / "sub" / "blob.bin").write_bytes(b"x" * 8192)

    appdata = tmp_path / "Roaming"
    userprofile = tmp_path / "User"
    temp_dir = tmp_path / "Temp"
    (appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "RetroDisc").mkdir(parents=True)
    (userprofile / "Desktop").mkdir(parents=True)
    temp_dir.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("USERPROFILE", str(userprofile))
    monkeypatch.setenv("TEMP", str(temp_dir))
    monkeypatch.setenv("TMP", str(temp_dir))

    module.write_uninstaller(install_dir)
    uninstaller = install_dir / "Uninstall RetroDisc.cmd"
    env = dict(os.environ)
    proc = subprocess.run(
        f'call "{uninstaller}"',
        cwd=str(install_dir),
        env=env,
        shell=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode == 0, (
        f"uninstaller exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    deadline = time.time() + 30
    while time.time() < deadline and install_dir.exists():
        time.sleep(0.25)

    assert not install_dir.exists(), (
        "Installationsordner blieb nach der Deinstallation bestehen: "
        f"{sorted(p.name for p in install_dir.rglob('*'))}"
    )
    assert install_dir.parent.is_dir()


def test_uninstaller_script_contains_no_unresolved_placeholder(installed):
    """Das Skript wird per f-String erzeugt; Backslash-Pfade duerfen nicht verfaelscht werden."""
    _module, install_dir, _created, script = installed

    assert "{install_dir}" not in script
    assert str(install_dir) in script
    assert r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\RetroDisc" in script
    assert r"%USERPROFILE%\Desktop\RetroDisc.lnk" in script
