#!/usr/bin/env python3
"""Reproducible release-artifact gate for RetroDisc on Windows.

Earlier audits ran the artifact checks by hand, so the release evidence could
not be reproduced from the repository. This script performs the same checks as
a committed, repeatable gate:

1. size and SHA-256 of ``dist/RetroDisc.exe``, the portable ZIP and the setup
   EXE -- the exact values that belong in ``RELEASE_AUDIT_STATUS.md``,
2. ZIP integrity: the packaged EXE must be byte-identical to the ``dist`` EXE
   and the ZIP must carry the documented side files,
3. Authenticode status of app and installer,
4. a real silent installation into a fully isolated sandbox, a byte-identity
   check of the installed EXE, and a real uninstall that must leave nothing
   behind.

The install step redirects ``USERPROFILE``, ``APPDATA`` and ``LOCALAPPDATA``
into a temporary sandbox, so neither the real desktop nor the real start menu
is touched. Nothing outside the sandbox is written, and no policy, ACL or
signature is changed.

Usage::

    python scripts/verify_release_artifacts.py
    python scripts/verify_release_artifacts.py --skip-install
    python scripts/verify_release_artifacts.py --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.subprocesses import decode_console_output  # noqa: E402

APP_EXE = ROOT / "dist" / "RetroDisc.exe"
PORTABLE_ZIP = ROOT / "Output" / "RetroDisc_1.0.0_Portable.zip"
SETUP_EXE = ROOT / "Output" / "RetroDisc_Setup_1.0.0.exe"

ZIP_EXE_MEMBER = "RetroDisc/RetroDisc.exe"
ZIP_REQUIRED = (ZIP_EXE_MEMBER, "RetroDisc/README.md", "RetroDisc/START_WINDOWS.txt")
UNINSTALLER = "Uninstall RetroDisc.cmd"

_failures: list[str] = []
_notes: list[str] = []


def fail(message: str) -> None:
    _failures.append(message)
    print(f"  FAIL {message}")


def ok(message: str) -> None:
    print(f"  ok   {message}")


def note(message: str) -> None:
    _notes.append(message)
    print(f"  note {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def authenticode_status(path: Path) -> str:
    """Return the Authenticode status word, or a reason why it is unknown."""
    if os.name != "nt":
        return "not-windows"
    ps = (
        "$ErrorActionPreference='Stop';"
        f"(Get-AuthenticodeSignature -LiteralPath '{str(path)}').Status"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover - host dependent
        return f"unknown ({exc.__class__.__name__})"
    if result.returncode != 0:
        return f"unknown ({decode_console_output(result.stderr).strip()[:120]})"
    return decode_console_output(result.stdout).strip() or "unknown (empty)"


def check_artifacts() -> dict:
    print("\n[1] Artefakte")
    info: dict[str, dict] = {}
    for label, path in (
        ("app_exe", APP_EXE),
        ("portable_zip", PORTABLE_ZIP),
        ("setup_exe", SETUP_EXE),
    ):
        if not path.exists():
            fail(f"missing artifact: {path}")
            continue
        entry = {"path": str(path), "size": path.stat().st_size, "sha256": sha256(path)}
        info[label] = entry
        ok(f"{path.name}: {entry['size']} bytes, SHA-256 {entry['sha256']}")
    return info


def check_zip(info: dict) -> None:
    print("\n[2] ZIP-Integritaet")
    if "portable_zip" not in info or "app_exe" not in info:
        fail("cannot check ZIP without both ZIP and dist EXE")
        return
    with zipfile.ZipFile(PORTABLE_ZIP) as archive:
        names = set(archive.namelist())
        for required in ZIP_REQUIRED:
            if required in names:
                ok(f"contains {required}")
            else:
                fail(f"ZIP is missing {required}")
        extra = sorted(n for n in names if n not in ZIP_REQUIRED and not n.endswith("/"))
        if extra:
            note(f"additional ZIP members: {', '.join(extra)}")
        if ZIP_EXE_MEMBER not in names:
            return
        digest = hashlib.sha256()
        with archive.open(ZIP_EXE_MEMBER) as member:
            for chunk in iter(lambda: member.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
    packaged = digest.hexdigest().upper()
    if packaged == info["app_exe"]["sha256"]:
        ok("packaged EXE is byte-identical to dist/RetroDisc.exe")
    else:
        fail(f"packaged EXE differs: {packaged} != {info['app_exe']['sha256']}")


def check_signatures(info: dict) -> dict:
    print("\n[3] Authenticode")
    statuses: dict[str, str] = {}
    for label, path in (("app_exe", APP_EXE), ("setup_exe", SETUP_EXE)):
        if label not in info:
            continue
        status = authenticode_status(path)
        statuses[label] = status
        if status == "Valid":
            ok(f"{path.name}: {status}")
        else:
            note(f"{path.name}: {status} -- unsigned artifacts cannot be handed to third parties")
    return statuses


def _sandbox_env(sandbox: Path) -> dict[str, str]:
    home = sandbox / "Home"
    roaming = home / "AppData" / "Roaming"
    local = home / "AppData" / "Local"
    for directory in (home / "Desktop", roaming, local, sandbox / "Temp"):
        directory.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["USERPROFILE"] = str(home)
    env["APPDATA"] = str(roaming)
    env["LOCALAPPDATA"] = str(local)
    env["TEMP"] = env["TMP"] = str(sandbox / "Temp")
    return env


def check_install_uninstall(info: dict) -> dict:
    print("\n[4] Installation und Deinstallation (isolierte Sandbox)")
    result: dict[str, object] = {"ran": False}
    if os.name != "nt":
        note("install gate only runs on Windows")
        return result
    if "setup_exe" not in info or "app_exe" not in info:
        fail("cannot run install gate without setup EXE and dist EXE")
        return result

    sandbox = Path(tempfile.mkdtemp(prefix="retrodisc-artifact-qa-"))
    result["sandbox"] = str(sandbox)
    try:
        env = _sandbox_env(sandbox)
        install_dir = sandbox / "Install" / "RetroDisc"
        desktop_link = Path(env["USERPROFILE"]) / "Desktop" / "RetroDisc.lnk"
        start_menu = (
            Path(env["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "RetroDisc"
        )

        proc = subprocess.run(
            [str(SETUP_EXE), "--silent", "--dir", str(install_dir)],
            capture_output=True,
            env=env,
            cwd=str(sandbox),
            timeout=900,
        )
        stderr = decode_console_output(proc.stderr).strip()
        if proc.returncode == 0:
            ok("installer exit code 0")
        else:
            fail(f"installer exit code {proc.returncode}")
        if stderr:
            fail(f"installer stderr not empty: {stderr[:300]}")
        else:
            ok("installer stderr empty")

        installed_exe = install_dir / "RetroDisc.exe"
        if installed_exe.exists():
            installed_hash = sha256(installed_exe)
            result["installed_sha256"] = installed_hash
            if installed_hash == info["app_exe"]["sha256"]:
                ok("installed EXE is byte-identical to dist/RetroDisc.exe")
            else:
                fail(f"installed EXE differs: {installed_hash}")
        else:
            fail(f"installed EXE missing: {installed_exe}")

        uninstaller = install_dir / UNINSTALLER
        if uninstaller.exists():
            ok(f"uninstaller written: {UNINSTALLER}")
        else:
            fail(f"uninstaller missing: {uninstaller}")

        for label, path in (("desktop shortcut", desktop_link), ("start menu folder", start_menu)):
            if path.exists():
                ok(f"isolated {label} created")
            else:
                fail(f"isolated {label} missing: {path}")

        if not uninstaller.exists():
            return result

        # The uninstaller ends with `pause`; feed it a newline so the parent
        # process terminates without a console.
        removal = subprocess.run(
            ["cmd", "/c", str(uninstaller)],
            capture_output=True,
            input=b"\r\n",
            env=env,
            cwd=str(sandbox),
            timeout=600,
        )
        removal_stderr = decode_console_output(removal.stderr).strip()
        if removal.returncode == 0:
            ok("uninstaller parent exit code 0")
        else:
            fail(f"uninstaller parent exit code {removal.returncode}")
        if removal_stderr:
            fail(f"uninstaller stderr not empty: {removal_stderr[:300]}")
        else:
            ok("uninstaller stderr empty")

        # A hidden PowerShell helper removes the install directory only after
        # the batch process has exited, so poll instead of asserting at once.
        deadline = time.monotonic() + 60
        start = time.monotonic()
        while install_dir.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        result["removal_ms"] = elapsed_ms
        if install_dir.exists():
            leftovers = [str(p.relative_to(install_dir)) for p in install_dir.rglob("*")][:10]
            fail(f"install directory still present after {elapsed_ms} ms: {leftovers}")
        else:
            ok(f"install directory removed after {elapsed_ms} ms")

        for label, path in (("desktop shortcut", desktop_link), ("start menu folder", start_menu)):
            if path.exists():
                fail(f"isolated {label} left behind: {path}")
            else:
                ok(f"isolated {label} removed")

        result["ran"] = True
        return result
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="RetroDisc release artifact gate")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="only hash and inspect the artifacts, do not install",
    )
    parser.add_argument("--json", action="store_true", help="print a machine-readable summary")
    args = parser.parse_args()

    print("RetroDisc Release-Artefakt-Gate")
    print("=" * 40)
    info = check_artifacts()
    check_zip(info)
    signatures = check_signatures(info)
    install = {"ran": False, "skipped": True} if args.skip_install else check_install_uninstall(info)

    summary = {
        "artifacts": info,
        "authenticode": signatures,
        "install": install,
        "failures": _failures,
        "notes": _notes,
    }
    if args.json:
        print("\n" + json.dumps(summary, indent=2))

    print("\n" + "=" * 40)
    if _failures:
        print(f"RESULT: FAIL ({len(_failures)} finding(s))")
        for item in _failures:
            print(f"  - {item}")
        return 1
    print("RESULT: PASS (0 findings)")
    if _notes:
        print("Hinweise (kein Gate-Fehler):")
        for item in _notes:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
