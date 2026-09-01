# -*- coding: utf-8 -*-
"""Authenticode-Signierung der RetroDisc-Release-Artefakte.

Warum das noetig ist
--------------------
Windows Smart App Control (SAC) laesst eine EXE nur zu, wenn sie von einem in
der SAC-Richtlinie hinterlegten Aussteller signiert ist oder Microsofts
Reputationsdienst sie als sicher einstuft. Unsignierte Builds werden mit
CodeIntegrity-Event 3033/3077 blockiert.

Wichtig und bewusst nicht verschwiegen: Ein **selbst ausgestelltes** Zertifikat
loest das nicht. Auch im Stammspeicher installiert steht es nicht in der
SAC-Richtlinie, und SAC blockiert weiter. Erst ein oeffentlich
vertrauenswuerdiges Code-Signing-Zertifikat -- praktisch ein EV-Zertifikat --
verschafft die noetige Reputation. Dieses Modul stellt die Signierung bereit;
welches Zertifikat verwendet wird, entscheidet die Konfiguration.

Konfiguration ueber Umgebungsvariablen
--------------------------------------
Entweder eine PFX-Datei::

    RETRODISC_SIGN_PFX=C:\\pfad\\zum\\zertifikat.pfx
    RETRODISC_SIGN_PASSWORD=...            (optional)

oder ein Zertifikat aus dem Windows-Zertifikatspeicher::

    RETRODISC_SIGN_THUMBPRINT=A1B2C3...

optional::

    RETRODISC_SIGN_TIMESTAMP_URL=http://timestamp.digicert.com

Das Passwort wird niemals in eine Datei oder in eine Kommandozeile geschrieben.
Es wird ausschliesslich per Prozessumgebung an PowerShell bzw. signtool
uebergeben.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

ENV_PFX = "RETRODISC_SIGN_PFX"
ENV_PASSWORD = "RETRODISC_SIGN_PASSWORD"
ENV_THUMBPRINT = "RETRODISC_SIGN_THUMBPRINT"
ENV_TIMESTAMP = "RETRODISC_SIGN_TIMESTAMP_URL"

DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"
HASH_ALGORITHM = "SHA256"


class SigningError(RuntimeError):
    """Signierung wurde angefordert, konnte aber nicht durchgefuehrt werden."""


@dataclass(frozen=True)
class SigningConfig:
    pfx: Path | None = None
    password: str | None = None
    thumbprint: str | None = None
    timestamp_url: str = DEFAULT_TIMESTAMP_URL

    @property
    def configured(self) -> bool:
        return self.pfx is not None or bool(self.thumbprint)

    @property
    def describe(self) -> str:
        if self.pfx is not None:
            return f"PFX-Datei {self.pfx}"
        if self.thumbprint:
            return f"Zertifikat mit Thumbprint {self.thumbprint}"
        return "nicht konfiguriert"


def load_config(env: dict[str, str] | None = None) -> SigningConfig:
    """Liest die Signierkonfiguration aus der Umgebung."""
    source = os.environ if env is None else env
    pfx_raw = (source.get(ENV_PFX) or "").strip()
    thumbprint = (source.get(ENV_THUMBPRINT) or "").strip().replace(" ", "")
    password = source.get(ENV_PASSWORD) or None
    timestamp = (source.get(ENV_TIMESTAMP) or "").strip() or DEFAULT_TIMESTAMP_URL
    return SigningConfig(
        pfx=Path(pfx_raw) if pfx_raw else None,
        password=password,
        thumbprint=thumbprint or None,
        timestamp_url=timestamp,
    )


def build_powershell_script(target: Path, config: SigningConfig) -> str:
    """PowerShell-Signierskript. Erfordert kein Windows SDK.

    Das Passwort wird ueber $env:RETRODISC_SIGN_PASSWORD gelesen und steht
    daher nie im Skripttext.
    """
    if not config.configured:
        raise SigningError("Signierung ist nicht konfiguriert.")

    target_literal = _ps_single_quote(str(target))
    timestamp_literal = _ps_single_quote(config.timestamp_url)

    if config.pfx is not None:
        pfx_literal = _ps_single_quote(str(config.pfx))
        acquire = (
            "$pw = $env:" + ENV_PASSWORD + "\n"
            "if ([string]::IsNullOrEmpty($pw)) { $pw = '' }\n"
            "$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2("
            + pfx_literal + ", $pw)\n"
        )
    else:
        thumb_literal = _ps_single_quote(str(config.thumbprint))
        acquire = (
            "$thumb = " + thumb_literal + "\n"
            "$cert = Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.Thumbprint -eq $thumb }\n"
            "if (-not $cert) { $cert = Get-ChildItem Cert:\\LocalMachine\\My | "
            "Where-Object { $_.Thumbprint -eq $thumb } }\n"
            "if (-not $cert) { throw \"Zertifikat $thumb nicht im Zertifikatspeicher gefunden.\" }\n"
            "$cert = $cert | Select-Object -First 1\n"
        )

    return (
        "$ErrorActionPreference = 'Stop'\n"
        + acquire
        + "$result = Set-AuthenticodeSignature -FilePath " + target_literal
        + " -Certificate $cert -HashAlgorithm " + HASH_ALGORITHM
        + " -TimestampServer " + timestamp_literal + "\n"
        "Write-Output $result.Status\n"
        "if ($result.Status -ne 'Valid') { throw \"Signierung fehlgeschlagen: $($result.StatusMessage)\" }\n"
    )


def _ps_single_quote(value: str) -> str:
    """Escaped einen Wert als PowerShell-Literal in einfachen Anfuehrungszeichen."""
    return "'" + value.replace("'", "''") + "'"


def sign_file(target: Path, config: SigningConfig, runner=subprocess.run) -> None:
    """Signiert eine Datei. Wirft SigningError, wenn das fehlschlaegt."""
    if not config.configured:
        raise SigningError("Signierung ist nicht konfiguriert.")
    if not target.is_file():
        raise SigningError(f"Zu signierende Datei fehlt: {target}")
    if config.pfx is not None and not config.pfx.is_file():
        raise SigningError(f"PFX-Datei nicht gefunden: {config.pfx}")

    env = dict(os.environ)
    if config.password:
        env[ENV_PASSWORD] = config.password

    script = build_powershell_script(target, config)
    handle = tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8")
    try:
        handle.write(script)
        handle.close()
        result = runner(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", handle.name],
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise SigningError(
                f"Signierung von {target.name} fehlgeschlagen "
                f"(Exitcode {result.returncode}): {(result.stderr or '').strip()}"
            )
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


def verify_signature(target: Path, runner=subprocess.run) -> str:
    """Gibt den Authenticode-Status zurueck, z. B. 'Valid' oder 'NotSigned'."""
    command = (
        "(Get-AuthenticodeSignature -FilePath " + _ps_single_quote(str(target)) + ").Status"
    )
    result = runner(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
    )
    return (result.stdout or "").strip() or "Unknown"
