# -*- coding: utf-8 -*-
"""Tests fuer die Authenticode-Signierung der Release-Artefakte.

Schwerpunkt sind die Eigenschaften, die sicherheitsrelevant sind und sich ohne
echtes Zertifikat pruefen lassen: Konfigurationslogik, korrektes Escaping und
vor allem, dass das Zertifikatspasswort niemals im Skripttext oder in einer
Kommandozeile landet.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import codesign  # noqa: E402


def _windows_powershell_major() -> int | None:
    """Major version of the ``powershell`` on PATH, or ``None`` if unavailable.

    The round-trip test below needs Windows PowerShell 5.1 specifically, because
    that is the interpreter whose script-file encoding behaviour it pins down.
    Probing here keeps a host without 5.1 -- or without ``powershell`` at all --
    a skip instead of a hard failure.
    """
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    major = result.stdout.decode("utf-8", errors="replace").strip()
    return int(major) if major.isdigit() else None


WINDOWS_POWERSHELL_MAJOR = _windows_powershell_major()


# ── Konfiguration ───────────────────────────────────────────────────

def test_config_is_unconfigured_without_environment():
    config = codesign.load_config(env={})
    assert not config.configured
    assert config.timestamp_url == codesign.DEFAULT_TIMESTAMP_URL
    assert config.describe == "nicht konfiguriert"


def test_config_from_pfx(tmp_path):
    pfx = tmp_path / "cert.pfx"
    config = codesign.load_config(env={
        codesign.ENV_PFX: str(pfx),
        codesign.ENV_PASSWORD: "geheim",
    })
    assert config.configured
    assert config.pfx == pfx
    assert config.password == "geheim"


def test_config_from_thumbprint_strips_spaces():
    # Der Zertifikatsdialog von Windows kopiert Thumbprints mit Leerzeichen.
    config = codesign.load_config(env={codesign.ENV_THUMBPRINT: "a1 b2 c3 d4"})
    assert config.configured
    assert config.thumbprint == "a1b2c3d4"


def test_custom_timestamp_url_is_honoured():
    config = codesign.load_config(env={
        codesign.ENV_THUMBPRINT: "AABB",
        codesign.ENV_TIMESTAMP: "http://timestamp.example/rfc3161",
    })
    assert config.timestamp_url == "http://timestamp.example/rfc3161"


# ── Skripterzeugung ─────────────────────────────────────────────────

def test_script_generation_requires_configuration(tmp_path):
    with pytest.raises(codesign.SigningError):
        codesign.build_powershell_script(tmp_path / "a.exe", codesign.load_config(env={}))


def test_password_never_appears_in_the_generated_script(tmp_path):
    """Kernregression: das Passwort darf nicht auf die Platte geschrieben werden."""
    pfx = tmp_path / "cert.pfx"
    config = codesign.load_config(env={
        codesign.ENV_PFX: str(pfx),
        codesign.ENV_PASSWORD: "streng-geheimes-passwort",
    })
    script = codesign.build_powershell_script(tmp_path / "RetroDisc.exe", config)

    assert "streng-geheimes-passwort" not in script
    # Stattdessen wird es zur Laufzeit aus der Prozessumgebung gelesen.
    assert "$env:" + codesign.ENV_PASSWORD in script


def test_script_signs_the_requested_file_with_timestamp(tmp_path):
    target = tmp_path / "RetroDisc.exe"
    config = codesign.load_config(env={codesign.ENV_THUMBPRINT: "ABCDEF"})
    script = codesign.build_powershell_script(target, config)

    assert "Set-AuthenticodeSignature" in script
    assert str(target) in script
    assert codesign.DEFAULT_TIMESTAMP_URL in script
    assert codesign.HASH_ALGORITHM in script
    assert "ABCDEF" in script


def test_script_escapes_single_quotes_in_paths(tmp_path):
    target = tmp_path / "Marco's RetroDisc.exe"
    config = codesign.load_config(env={codesign.ENV_THUMBPRINT: "ABCDEF"})
    script = codesign.build_powershell_script(target, config)
    # Ein einfaches Anfuehrungszeichen muss in PowerShell verdoppelt werden.
    assert "Marco''s RetroDisc.exe" in script


# ── sign_file ───────────────────────────────────────────────────────

def test_sign_file_rejects_missing_target(tmp_path):
    config = codesign.load_config(env={codesign.ENV_THUMBPRINT: "ABCDEF"})
    with pytest.raises(codesign.SigningError, match="fehlt"):
        codesign.sign_file(tmp_path / "gibtsnicht.exe", config)


def test_sign_file_rejects_missing_pfx(tmp_path):
    target = tmp_path / "RetroDisc.exe"
    target.write_bytes(b"MZ")
    config = codesign.load_config(env={codesign.ENV_PFX: str(tmp_path / "fehlt.pfx")})
    with pytest.raises(codesign.SigningError, match="PFX"):
        codesign.sign_file(target, config)


def test_sign_file_passes_password_through_environment_not_argv(tmp_path):
    pfx = tmp_path / "cert.pfx"
    pfx.write_bytes(b"pfx")
    target = tmp_path / "RetroDisc.exe"
    target.write_bytes(b"MZ")
    config = codesign.load_config(env={
        codesign.ENV_PFX: str(pfx),
        codesign.ENV_PASSWORD: "geheim123",
    })

    seen: dict = {}

    class Result:
        returncode = 0
        stdout = "Valid"
        stderr = ""

    def fake_runner(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs.get("env") or {}
        seen["script"] = Path(cmd[-1]).read_text(encoding="utf-8-sig")
        return Result()

    codesign.sign_file(target, config, runner=fake_runner)

    assert "geheim123" not in " ".join(seen["cmd"])
    assert "geheim123" not in seen["script"]
    assert seen["env"][codesign.ENV_PASSWORD] == "geheim123"


def test_sign_file_writes_ps51_compatible_utf8_bom_for_non_ascii_paths(tmp_path):
    pfx = tmp_path / "Zertifikat Grüße_日本.pfx"
    pfx.write_bytes(b"pfx")
    target = tmp_path / "RetroDisc Grüße_日本.exe"
    target.write_bytes(b"MZ")
    config = codesign.load_config(env={codesign.ENV_PFX: str(pfx)})
    captured: dict = {}

    class Result:
        returncode = 0
        stdout = b"Valid\r\n"
        stderr = b""

    def fake_runner(cmd, **kwargs):
        captured["raw_script"] = Path(cmd[-1]).read_bytes()
        captured["kwargs"] = kwargs
        return Result()

    codesign.sign_file(target, config, runner=fake_runner)

    raw_script = captured["raw_script"]
    assert raw_script.startswith(b"\xef\xbb\xbf")
    script = raw_script.decode("utf-8-sig")
    assert str(target) in script
    assert str(pfx) in script
    assert captured["kwargs"]["capture_output"] is True
    assert "text" not in captured["kwargs"]
    assert "encoding" not in captured["kwargs"]


@pytest.mark.skipif(
    WINDOWS_POWERSHELL_MAJOR != 5,
    reason=f"requires Windows PowerShell 5.1 (found major version {WINDOWS_POWERSHELL_MAJOR})",
)
def test_sign_file_round_trips_non_ascii_path_through_windows_powershell_51(
    monkeypatch, tmp_path
):
    """Exercise sign_file's real temporary-script and powershell -File path.

    The signing cmdlets are intentionally replaced by a harmless existence
    check, so the encoding regression is covered without a certificate.
    """
    target = tmp_path / "RetroDisc Grüße_日本.exe"
    target.write_bytes(b"MZ")
    config = codesign.load_config(env={codesign.ENV_THUMBPRINT: "ABCDEF"})
    target_literal = codesign._ps_single_quote(str(target))
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "if ($PSVersionTable.PSVersion.Major -ne 5) { exit 24 }\n"
        f"if (-not (Test-Path -LiteralPath {target_literal})) {{ exit 23 }}\n"
    )
    monkeypatch.setattr(codesign, "build_powershell_script", lambda *_: script)

    codesign.sign_file(target, config)


def test_sign_file_reports_failure(tmp_path):
    target = tmp_path / "RetroDisc.exe"
    target.write_bytes(b"MZ")
    config = codesign.load_config(env={codesign.ENV_THUMBPRINT: "ABCDEF"})

    class Result:
        returncode = 1
        stdout = b""
        stderr = "Zertifikat für 東京 nicht gefunden.".encode("utf-8")

    with pytest.raises(codesign.SigningError, match="für 東京"):
        codesign.sign_file(target, config, runner=lambda cmd, **kw: Result())


def test_sign_file_removes_the_temporary_script(tmp_path):
    target = tmp_path / "RetroDisc.exe"
    target.write_bytes(b"MZ")
    config = codesign.load_config(env={codesign.ENV_THUMBPRINT: "ABCDEF"})
    captured: dict = {}

    class Result:
        returncode = 0
        stdout = "Valid"
        stderr = ""

    def fake_runner(cmd, **kwargs):
        captured["script_path"] = Path(cmd[-1])
        return Result()

    codesign.sign_file(target, config, runner=fake_runner)
    assert not captured["script_path"].exists()


def test_verify_signature_captures_bytes_without_locale_text_mode(tmp_path):
    target = tmp_path / "RetroDisc Grüße_日本.exe"
    target.write_bytes(b"MZ")
    captured: dict = {}

    class Result:
        stdout = b"Valid\r\n"
        stderr = b""

    def fake_runner(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return Result()

    assert codesign.verify_signature(target, runner=fake_runner) == "Valid"
    assert captured["kwargs"]["capture_output"] is True
    assert "text" not in captured["kwargs"]
    assert "encoding" not in captured["kwargs"]


# ── Build-Anbindung ─────────────────────────────────────────────────

def test_build_requires_certificate_when_sign_is_requested(monkeypatch, tmp_path):
    """--sign darf niemals stillschweigend ein unsigniertes Release durchlassen."""
    import build as build_module

    monkeypatch.delenv(codesign.ENV_PFX, raising=False)
    monkeypatch.delenv(codesign.ENV_THUMBPRINT, raising=False)

    target = tmp_path / "RetroDisc.exe"
    target.write_bytes(b"MZ")

    with pytest.raises(SystemExit) as excinfo:
        build_module.sign_artifact(target, require=True)
    assert "kein Zertifikat konfiguriert" in str(excinfo.value)


def test_build_skips_signing_when_not_requested(monkeypatch, tmp_path, capsys):
    import build as build_module

    monkeypatch.delenv(codesign.ENV_PFX, raising=False)
    monkeypatch.delenv(codesign.ENV_THUMBPRINT, raising=False)

    target = tmp_path / "RetroDisc.exe"
    target.write_bytes(b"MZ")

    assert build_module.sign_artifact(target, require=False) is False
    assert "uebersprungen" in capsys.readouterr().out
