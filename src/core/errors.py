"""Typed RetroDisc errors so the UI can show clear messages, logs keep detail.

Each error carries a machine ``code`` and a user-facing German ``message``; the
original technical detail stays in ``detail`` (for logs, never forced into UI).
"""
from __future__ import annotations


class RetroDiscError(Exception):
    """Base class. ``code`` is stable for tests/UI; ``message`` is user-facing."""
    code = "retrodisc_error"
    default_message = "Ein Fehler ist aufgetreten."

    def __init__(self, message: str | None = None, *, detail: str = "", code: str | None = None):
        self.message = message or self.default_message
        self.detail = detail
        if code:
            self.code = code
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {"error": self.message, "code": self.code, "detail": self.detail}


class DriveError(RetroDiscError):
    code = "drive_error"
    default_message = "Das optische Laufwerk konnte nicht angesprochen werden."


class MediaError(RetroDiscError):
    code = "media_error"
    default_message = "Mit dem eingelegten Medium stimmt etwas nicht."


class ProbeError(RetroDiscError):
    code = "probe_error"
    default_message = "Die Medieninformationen konnten nicht gelesen werden."


class ReadError(RetroDiscError):
    code = "read_error"
    default_message = "Die Disc konnte nicht vollständig gelesen werden."


class EncodeError(RetroDiscError):
    code = "encode_error"
    default_message = "Die Kodierung ist fehlgeschlagen."


class AuthoringError(RetroDiscError):
    code = "authoring_error"
    default_message = "Die Disc-Struktur konnte nicht erstellt werden."


class BurnError(RetroDiscError):
    code = "burn_error"
    default_message = "Der Brennvorgang ist fehlgeschlagen."


class VerifyError(RetroDiscError):
    code = "verify_error"
    default_message = "Die Überprüfung ist fehlgeschlagen."


class StorageError(RetroDiscError):
    code = "storage_error"
    default_message = "Nicht genügend Speicherplatz für diesen Vorgang."


class ExternalToolError(RetroDiscError):
    code = "external_tool_error"
    default_message = "Ein benötigtes Werkzeug fehlt oder lieferte einen Fehler."

    def __init__(self, message: str | None = None, *, tool: str = "", returncode: int | None = None,
                 detail: str = "", code: str | None = None):
        self.tool = tool
        self.returncode = returncode
        super().__init__(message, detail=detail, code=code)

    def to_dict(self) -> dict:
        return super().to_dict() | {"tool": self.tool, "returncode": self.returncode}
