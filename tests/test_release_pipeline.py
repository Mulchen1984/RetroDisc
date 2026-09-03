"""Release-pipeline regressions for pinned vendor inputs and canonical CI."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest

import prepare_vendor as vendor


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_release_inputs_are_immutable_and_hashed():
    urls = (vendor.FFMPEG_URL, vendor.YTDLP_URL, vendor.DVDSTYLER_URL)
    assert all("latest" not in url.lower() for url in urls)
    assert re.fullmatch(r"[0-9a-f]{64}", vendor.FFMPEG_SHA256)
    assert re.fullmatch(r"[0-9a-f]{64}", vendor.YTDLP_SHA256)
    assert re.fullmatch(r"[0-9a-f]{64}", vendor.DVDSTYLER_SHA256)
    assert re.fullmatch(r"[0-9a-f]{40}", vendor.WHISPER_REVISION)
    assert vendor.DVD_REQUIRED_SHA256
    assert vendor.WHISPER_REQUIRED_SHA256
    for digest in (*vendor.DVD_REQUIRED_SHA256.values(), *vendor.WHISPER_REQUIRED_SHA256.values()):
        assert re.fullmatch(r"[0-9a-f]{64}", digest)

    spec = (PROJECT_ROOT / "retrodisc_final.spec").read_text(encoding="utf-8")
    for required in ("ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe", "dvdtools", "whisper-base"):
        assert required in spec


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size: int) -> bytes:
        payload, self.payload = self.payload, b""
        return payload


def test_bad_download_hash_preserves_existing_destination(tmp_path, monkeypatch):
    destination = tmp_path / "tool.exe"
    destination.write_bytes(b"known-good")
    monkeypatch.setattr(vendor.urllib.request, "urlopen", lambda *_a, **_k: _Response(b"bad"))

    with pytest.raises(RuntimeError, match="SHA-256"):
        vendor.download_with_progress(
            "https://example.invalid/tool.exe",
            destination,
            "Testtool",
            "0" * 64,
        )

    assert destination.read_bytes() == b"known-good"
    assert not destination.with_name(destination.name + ".download").exists()


def test_ffmpeg_ready_rejects_same_size_tamper(tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "VENDOR_DIR", tmp_path)
    marker = tmp_path / "ffmpeg-source.json"
    monkeypatch.setattr(vendor, "FFMPEG_SOURCE_MARKER", marker)
    payloads = {
        "ffmpeg.exe": b"A" * (10 * 1024 * 1024),
        "ffprobe.exe": b"B" * (10 * 1024 * 1024),
    }
    for name, payload in payloads.items():
        (tmp_path / name).write_bytes(payload)
    marker.write_text(
        json.dumps(
            {
                "tag": vendor.FFMPEG_TAG,
                "archive": vendor.FFMPEG_ARCHIVE,
                "url": vendor.FFMPEG_URL,
                "sha256": vendor.FFMPEG_SHA256,
                "files": {name: _sha256(payload) for name, payload in payloads.items()},
            }
        ),
        encoding="utf-8",
    )
    assert vendor.ffmpeg_is_ready()

    with (tmp_path / "ffmpeg.exe").open("r+b") as handle:
        handle.write(b"Z")
    assert (tmp_path / "ffmpeg.exe").stat().st_size == len(payloads["ffmpeg.exe"])
    assert not vendor.ffmpeg_is_ready()


def test_ffmpeg_extraction_failure_preserves_previous_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "VENDOR_DIR", tmp_path)
    marker = tmp_path / "ffmpeg-source.json"
    monkeypatch.setattr(vendor, "FFMPEG_SOURCE_MARKER", marker)
    originals = {
        "ffmpeg.exe": b"old-ffmpeg",
        "ffprobe.exe": b"old-ffprobe",
        "ffmpeg-source.json": b"old-marker",
    }
    for name, payload in originals.items():
        (tmp_path / name).write_bytes(payload)

    archive = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("bundle/bin/ffmpeg.exe", b"N" * (10 * 1024 * 1024))

    with pytest.raises(FileNotFoundError, match="ffprobe.exe"):
        vendor.extract_ffmpeg(archive)

    for name, payload in originals.items():
        assert (tmp_path / name).read_bytes() == payload


def test_tree_match_rejects_unpinned_payload(tmp_path):
    expected = {"runtime.exe": _sha256(b"runtime")}
    (tmp_path / "runtime.exe").write_bytes(b"runtime")
    assert vendor._tree_matches(tmp_path, expected)
    (tmp_path / "rogue.dll").write_bytes(b"unverified")
    assert not vendor._tree_matches(tmp_path, expected)


def test_workflow_prepares_vendor_before_verify_core_and_uses_canonical_build():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yml").read_text(
        encoding="utf-8"
    )
    assert workflow.index("python prepare_vendor.py") < workflow.index(
        "python .hermes/verify_core.py"
    )
    assert "python build.py --clean" in workflow
    assert "python build.py --clean --sign" in workflow
    assert "retrodisc_portable.py" not in workflow
    assert 'tags: [ "v*.*.*" ]' in workflow
    for secret in ("RETRODISC_SIGN_PFX_BASE64", "RETRODISC_SIGN_PASSWORD"):
        assert secret in workflow
    assert "needs: build-windows" in workflow
    assert "contents: write" in workflow


def test_workflow_uses_all_canonical_artifact_paths():
    normalized = (
        PROJECT_ROOT / ".github" / "workflows" / "build.yml"
    ).read_text(encoding="utf-8").replace("\\", "/")
    for relative in (
        "dist/RetroDisc.exe",
        "Output/RetroDisc_1.0.0_Portable.zip",
        "Output/RetroDisc_Setup_1.0.0.exe",
    ):
        assert relative in normalized
        assert f"release/{relative}" in normalized
