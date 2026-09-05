"""Signing has to happen in the right order, and stay optional.

Signing a finished ZIP or a finished installer signs the outer shell. Windows
reads the signature of the file it actually runs, so the EXE has to be signed
**before** it is packed into either. That is an ordering property of
``build.py``, invisible to any check that only looks at ``dist/RetroDisc.exe``
at the end - which is exactly why the artifact gate now unpacks the ZIP and
inspects the installed copy too.

The other half is that none of this may become mandatory. A contributor
without a certificate must still get a working development build; only
``--sign`` and ``--require-signed`` turn a missing signature into a failure.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from tools import codesign

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build.py"
GATE = ROOT / "scripts" / "verify_release_artifacts.py"


def _main_call_order() -> list[str]:
    """The names build.py's main() calls, in source order."""
    tree = ast.parse(BUILD.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls: list[str] = []
    for node in ast.walk(main):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.append((node.lineno, node.func.id))
    return [name for _, name in sorted(calls)]


def test_the_exe_is_signed_before_it_is_packed_into_anything():
    order = _main_call_order()
    for name in ("build_portable_exe", "sign_artifact", "build_portable_zip",
                 "build_setup_exe", "verify_zip_signature"):
        assert name in order, f"build.py main() no longer calls {name}"

    build_exe = order.index("build_portable_exe")
    first_sign = order.index("sign_artifact")
    zip_step = order.index("build_portable_zip")
    installer = order.index("build_setup_exe")

    assert build_exe < first_sign, "the EXE is packed before it is built"
    assert first_sign < zip_step, (
        "the ZIP is packed before the EXE is signed - it would ship unsigned bytes"
    )
    assert first_sign < installer, (
        "the installer embeds the EXE before it is signed"
    )
    # The installer is signed after it exists, i.e. a second sign_artifact call.
    assert order.count("sign_artifact") >= 2, "the installer is never signed"
    assert order.index("verify_zip_signature") > zip_step


def test_the_zip_signature_is_checked_on_the_unpacked_file():
    """Reading the ZIP entry is not enough - the check must extract it."""
    source = BUILD.read_text(encoding="utf-8")
    body = source.split("def verify_zip_signature")[1].split("\ndef ")[0]
    assert "extract" in body, "the ZIP check never unpacks the EXE"
    assert "verify_signature" in body
    assert "require" in body and "SystemExit" in body, (
        "an unsigned EXE in the ZIP does not fail the release build"
    )


def test_signing_is_optional_but_release_mode_is_hard():
    source = BUILD.read_text(encoding="utf-8")
    assert '"--sign"' in source
    # Without configuration and without --sign: skip, do not abort.
    assert "Signierung uebersprungen" in source
    # With --sign but no certificate: abort.
    assert "--sign angefordert, aber kein Zertifikat konfiguriert" in source

    gate = GATE.read_text(encoding="utf-8")
    assert '"--require-signed"' in gate
    assert "report = fail if require_signed else note" in gate


def test_the_gate_checks_the_zip_copy_and_the_installed_copy():
    gate = GATE.read_text(encoding="utf-8")
    signatures = gate.split("def check_signatures")[1].split("\ndef ")[0]
    assert "archive.extract" in signatures, "the gate trusts the ZIP without unpacking"

    install = gate.split("def check_install_uninstall")[1].split("\ndef ")[0]
    assert "authenticode_status(installed_exe)" in install, (
        "the gate never checks the signature of the installed EXE"
    )


def test_no_post_hoc_signing_script_remains():
    """Signing finished artifacts is the failure mode this design avoids."""
    assert not (ROOT / "scripts" / "sign_release.ps1").exists()


# ── Secrets ───────────────────────────────────────────────────────────────


def test_no_certificate_material_is_tracked_or_hard_coded():
    skip_dirs = {".git", ".venv", "build", "dist", "Output", "vendor", "__pycache__"}
    material = {".pfx", ".p12", ".pem", ".key", ".crt"}
    found = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in material
        and not any(part in skip_dirs for part in path.parts)
    ]
    assert found == [], f"certificate material inside the repository: {found}"

    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.pfx", "*.p12", "*.key"):
        assert pattern in ignored, f".gitignore does not block {pattern}"


def test_no_thumbprint_or_password_is_hard_coded_in_the_build():
    """Configuration comes from the environment, never from the source."""
    for path in (BUILD, GATE, ROOT / "tools" / "codesign.py"):
        source = path.read_text(encoding="utf-8")
        # A thumbprint is 40 hex characters.
        assert not [
            token for token in source.replace('"', " ").replace("'", " ").split()
            if len(token) == 40 and all(c in "0123456789abcdefABCDEF" for c in token)
        ], f"{path.name} appears to hard-code a certificate thumbprint"

    # The env var names may appear, a value never may.
    source = (ROOT / "tools" / "codesign.py").read_text(encoding="utf-8")
    assert 'ENV_PASSWORD = "RETRODISC_SIGN_PASSWORD"' in source
    assert "os.environ" in source, "the password is not read from the environment"


def test_the_password_never_reaches_a_script_file_or_a_command_line():
    config = codesign.SigningConfig(
        pfx=Path(r"C:\secure\cert.pfx"), password="super-secret-value"
    )
    script = codesign.build_powershell_script(Path(r"C:\out\RetroDisc.exe"), config)
    assert "super-secret-value" not in script
    assert codesign.ENV_PASSWORD in script, "the script must read it from the environment"


def test_configuration_is_read_from_the_environment():
    empty = codesign.load_config(env={})
    assert not empty.configured

    with_thumb = codesign.load_config(env={codesign.ENV_THUMBPRINT: "AA BB CC"})
    assert with_thumb.configured
    assert with_thumb.thumbprint == "AABBCC", "spaces from a copied thumbprint survive"

    with_pfx = codesign.load_config(env={codesign.ENV_PFX: r"C:\secure\cert.pfx"})
    assert with_pfx.configured
    assert with_pfx.timestamp_url == codesign.DEFAULT_TIMESTAMP_URL


def test_signing_refuses_to_run_when_it_is_not_configured():
    with pytest.raises(codesign.SigningError):
        codesign.sign_file(Path("whatever.exe"), codesign.SigningConfig())


def test_signing_docs_state_that_a_dev_certificate_is_not_enough():
    doc = (ROOT / "SIGNING.md").read_text(encoding="utf-8")
    lowered = doc.lower()
    assert "development certificate" in lowered
    assert "publicly trusted" in lowered
    assert "untrustedroot" in lowered, (
        "the doc does not say what a dev-signed file looks like elsewhere"
    )


@pytest.mark.skipif(os.name != "nt", reason="Authenticode is a Windows concept")
def test_verify_signature_reports_a_status_for_an_unsigned_file(tmp_path):
    target = tmp_path / "unsigned.exe"
    target.write_bytes(b"MZ" + b"\0" * 512)
    assert codesign.verify_signature(target) != "Valid"
