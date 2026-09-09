"""Stable disc fingerprint for re-recognising a disc without hashing all of it.

Normalises the disc *structure* (volume label, capacity, file list with sizes,
title durations, hashes of small structural files only) and hashes that. Order
of the file list never matters; Unicode labels/paths are NFC-normalised; missing
or partial data degrades gracefully instead of crashing.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

SMALL_FILE_BYTES = 1_048_576   # nur kleine Strukturdateien (IFO/BUP/index) hashen


def _nfc(value) -> str:
    return unicodedata.normalize("NFC", str(value or ""))


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_structure(structure: dict) -> dict:
    """Canonical, order-independent view. Unknown keys ignored; missing keys ok."""
    structure = structure or {}
    files = []
    for entry in structure.get("files") or []:
        path = _nfc(entry.get("path"))
        if not path:
            continue
        item = {"path": path, "size": int(entry.get("size") or 0)}
        if entry.get("sha"):
            item["sha"] = str(entry["sha"])
        files.append(item)
    files.sort(key=lambda f: f["path"])                      # Reihenfolge egal
    durations = sorted(round(float(d), 1) for d in (structure.get("durations") or []))
    return {
        "label": _nfc(structure.get("label")),
        "capacity_bytes": int(structure.get("capacity_bytes") or 0),
        "file_count": len(files),
        "files": files,
        "durations": durations,
    }


def fingerprint(structure: dict) -> str:
    canonical = normalize_structure(structure)
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_structure(root, *, label: str = "", capacity_bytes: int = 0,
                    durations=None, small_file_bytes: int = SMALL_FILE_BYTES) -> dict:
    """Walk a mounted disc / VIDEO_TS / BDMV folder into a fingerprint structure.

    Large payload files contribute only their size; small structural files
    (menus, index, playlists) also contribute a content hash.
    """
    root = Path(root)
    files = []
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue                                     # unlesbare/kaputte Einträge überspringen
            entry = {"path": path.relative_to(root).as_posix(), "size": size}
            if 0 < size <= small_file_bytes:
                try:
                    entry["sha"] = _sha_file(path)
                except OSError:
                    pass                                     # partielle Daten: Größe genügt
            files.append(entry)
    return {"label": label, "capacity_bytes": capacity_bytes,
            "durations": list(durations or []), "files": files}


def fingerprint_path(root, **kwargs) -> str:
    return fingerprint(build_structure(root, **kwargs))
