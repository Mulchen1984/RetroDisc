"""Release-pipeline regressions for pinned vendor inputs and canonical CI."""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
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

    # Packaging goes through build.py only: no direct PyInstaller invocation, no
    # raw .spec, no one-file flags, no retired portable entry point in the CI.
    assert "retrodisc_portable.py" not in workflow
    assert "retrodisc_portable" not in workflow
    assert "-m PyInstaller" not in workflow
    assert "--onefile" not in workflow
    assert ".spec" not in workflow
    # Windows-only since 2026-09-03: one build runner, no macOS job, no
    # superseded openai-whisper dependency.
    assert "macos" not in workflow.lower()
    assert "openai-whisper" not in workflow and "openai_whisper" not in workflow

    assert 'tags: [ "v*.*.*" ]' in workflow
    for secret in ("RETRODISC_SIGN_PFX_BASE64", "RETRODISC_SIGN_PASSWORD"):
        assert secret in workflow
    assert "needs: build-windows" in workflow
    assert "contents: write" in workflow


@pytest.mark.parametrize("failed_gate", [0, 1, 2, 3, 4, 5, 6, None])
def test_workflow_stops_at_each_failed_source_gate(failed_gate):
    """Execute the workflow's PowerShell control flow with native exit stubs."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required to exercise the Windows workflow")
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yml").read_text(
        encoding="utf-8"
    )
    step = workflow.split("      - name: Source-Gates ausführen\n", 1)[1].split(
        "\n      - name:", 1
    )[0]
    assert "shell: pwsh" in step
    script = textwrap.dedent(step.split("        run: |\n", 1)[1])
    commands = re.findall(r"^(?:python|node) .+$", script, re.MULTILINE)
    assert commands == [
        "python -m pytest -q",
        "python -m compileall -q src installer scripts tools build.py retrodisc_launcher.py prepare_vendor.py",
        "python prepare_vendor.py",
        "python .hermes/verify_core.py",
        "python scripts/verify_ui_bridge.py",
        "node --check build/ui-audit/inline.js",
        "python scripts/release_smoke.py",
    ]
    executable = "'" + sys.executable.replace("'", "''") + "'"
    for index, command in enumerate(commands):
        code = f'import sys; print("gate-{index}"); sys.exit({17 if index == failed_gate else 0})'
        script = script.replace(command, f"& {executable} -c '{code}'", 1)
    # GitHub's PowerShell wrapper checks only the final native exit code. A
    # marker proves that an earlier failure cannot continue to a later gate.
    script = (
        "$ErrorActionPreference = 'Stop'\n" + script
        + "\nWrite-Output 'completed'\nexit $LASTEXITCODE\n"
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == (0 if failed_gate is None else 17), result.stderr
    reached = len(commands) if failed_gate is None else failed_gate + 1
    expected = [f"gate-{index}" for index in range(reached)]
    if failed_gate is None:
        expected.append("completed")
    assert result.stdout.splitlines() == expected


def test_workflow_tag_release_is_fail_closed_on_signature_and_artifacts():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yml").read_text(
        encoding="utf-8"
    )
    # A missing signing secret must abort a tag build before anything is built.
    tag_guard = workflow.index("Tag-Release verweigert: RETRODISC_SIGN_PFX_BASE64")
    signed_build = workflow.index("python build.py --clean --sign")
    assert tag_guard < signed_build

    # The pipeline itself re-checks Authenticode on the two EXEs for tag builds,
    # gated on the tag ref, before upload and release.
    assert "Get-AuthenticodeSignature" in workflow
    assert "$status -ne 'Valid'" in workflow  # unique to the enforcement step
    assert (
        "Signaturpflicht auf Tags durchsetzen\n"
        "        if: ${{ startsWith(github.ref, 'refs/tags/v') }}"
    ) in workflow
    sig_step = workflow.index("Signaturpflicht auf Tags durchsetzen")
    assert sig_step < workflow.index("Windows-Artefakte hochladen")
    assert sig_step < workflow.index("GitHub Release erstellen")

    # The signed tag build must fail the job on a non-zero build exit, and the
    # release job is unreachable unless build-windows succeeded on a v* tag.
    assert 'if ($LASTEXITCODE -ne 0) { throw "Signierter Release-Build fehlgeschlagen." }' in workflow
    assert "fail_on_unmatched_files: true" in workflow
    release_job = workflow.index("GitHub Release erstellen")
    assert "needs: build-windows" in workflow[release_job:]
    # The release job's own gate is the brace-free form; step gates use ${{ }}.
    assert "if: startsWith(github.ref, 'refs/tags/v')" in workflow[release_job:]


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


def test_workflow_artifact_paths_match_build_py():
    """The workflow must ship exactly what canonical build.py writes."""
    build_py = (PROJECT_ROOT / "build.py").read_text(encoding="utf-8")
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "build.yml"
    ).read_text(encoding="utf-8").replace("\\", "/")

    assert 'DIST_DIR = HERE / "dist"' in build_py
    assert 'OUTPUT_DIR = HERE / "Output"' in build_py
    expected = {
        'APP_EXE = DIST_DIR / "RetroDisc.exe"': "dist/RetroDisc.exe",
        'PORTABLE_ZIP = OUTPUT_DIR / "RetroDisc_1.0.0_Portable.zip"':
            "Output/RetroDisc_1.0.0_Portable.zip",
        'SETUP_EXE = OUTPUT_DIR / "RetroDisc_Setup_1.0.0.exe"':
            "Output/RetroDisc_Setup_1.0.0.exe",
    }
    for definition, rel_path in expected.items():
        assert definition in build_py, f"build.py no longer defines: {definition}"
        assert rel_path in workflow, f"workflow lost artifact path: {rel_path}"
        assert f"release/{rel_path}" in workflow


class _MidstreamFailure:
    """A response that yields one chunk, then dies like a dropped connection."""

    def __init__(self, error):
        self._error = error
        self._chunk = b"\x00" * 4096
        self.headers = {"Content-Length": "10485760"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        if self._chunk:
            chunk, self._chunk = self._chunk, b""
            return chunk
        raise self._error


@pytest.mark.parametrize(
    "error",
    [
        http.client.IncompleteRead(b"\x00" * 4096),
        urllib.error.URLError("connection reset by peer"),
        OSError("socket hang up"),
    ],
    ids=["incomplete_read", "url_error", "os_error"],
)
def test_midstream_download_failure_preserves_destination(tmp_path, monkeypatch, error):
    destination = tmp_path / "tool.exe"
    destination.write_bytes(b"known-good")
    monkeypatch.setattr(
        vendor.urllib.request,
        "urlopen",
        lambda *_a, **_k: _MidstreamFailure(error),
    )

    with pytest.raises(type(error)):
        vendor.download_with_progress(
            "https://example.invalid/tool.exe",
            destination,
            "Testtool",
            "0" * 64,
        )

    assert destination.read_bytes() == b"known-good"
    assert not destination.with_name(destination.name + ".download").exists()


def test_prepare_ffmpeg_verifies_archive_digest_before_extracting(tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "VENDOR_DIR", tmp_path)
    monkeypatch.setattr(vendor, "FFMPEG_SOURCE_MARKER", tmp_path / "ffmpeg-source.json")
    monkeypatch.setattr(vendor, "ffmpeg_is_ready", lambda: False)

    seen: dict[str, object] = {}
    extracted: list[Path] = []

    def fake_download(url, dest, label, expected_sha256=None):
        seen["url"] = url
        seen["expected_sha256"] = expected_sha256
        raise RuntimeError(f"{label}: SHA-256 stimmt nicht")

    monkeypatch.setattr(vendor, "download_with_progress", fake_download)
    monkeypatch.setattr(vendor, "extract_ffmpeg", lambda path: extracted.append(path))

    with pytest.raises(RuntimeError, match="SHA-256"):
        vendor.prepare_ffmpeg()

    assert seen["url"] == vendor.FFMPEG_URL
    assert seen["expected_sha256"] == vendor.FFMPEG_SHA256
    assert re.fullmatch(r"[0-9a-f]{64}", str(seen["expected_sha256"]))
    assert extracted == []  # a rejected archive never reaches extraction


def test_replace_files_rolls_back_on_partial_failure(tmp_path):
    target_root = tmp_path / "vendor"
    target_root.mkdir()
    originals = {"a.bin": b"old-a", "b.bin": b"old-b", "marker.json": b"old-marker"}
    for name, data in originals.items():
        (target_root / name).write_bytes(data)

    work = tmp_path / "work"
    staging = work / "staging"
    staging.mkdir(parents=True)
    (staging / "a.bin").write_bytes(b"new-a")
    (staging / "b.bin").write_bytes(b"new-b")
    # marker.json is deliberately absent from staging: the third install step
    # raises only after a.bin and b.bin are already swapped in.

    with pytest.raises(FileNotFoundError):
        vendor._replace_files(staging, target_root, ("a.bin", "b.bin", "marker.json"))

    for name, data in originals.items():
        assert (target_root / name).read_bytes() == data


def test_whisper_ready_requires_pinned_files_and_provenance_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "VENDOR_DIR", tmp_path)
    root = tmp_path / "whisper-base"
    root.mkdir()
    payloads = {
        "config.json": b'{"model_type": "base"}',
        "model.bin": b"CT2-WEIGHTS",
        "tokenizer.json": b"{}",
        "vocabulary.txt": b"a\nb\nc\n",
    }
    for name, data in payloads.items():
        (root / name).write_bytes(data)
    monkeypatch.setattr(
        vendor,
        "WHISPER_REQUIRED_SHA256",
        {name: _sha256(data) for name, data in payloads.items()},
    )
    good_marker = {"repository": vendor.WHISPER_REPO, "revision": vendor.WHISPER_REVISION}
    marker_path = root / "RETRODISC_SOURCE.json"
    marker_path.write_text(json.dumps(good_marker), encoding="utf-8")
    assert vendor.whisper_is_ready()

    # A marker from another pinned revision is rejected even though every model
    # file still hashes correctly.
    marker_path.write_text(
        json.dumps({"repository": vendor.WHISPER_REPO, "revision": "0" * 40}),
        encoding="utf-8",
    )
    assert not vendor.whisper_is_ready()

    # An unpinned extra file anywhere in the recursively bundled tree fails.
    marker_path.write_text(json.dumps(good_marker), encoding="utf-8")
    assert vendor.whisper_is_ready()
    (root / "extra_adapter.bin").write_bytes(b"unverified")
    assert not vendor.whisper_is_ready()


@pytest.mark.parametrize("junk", ["[]", "42", '"a string"', "null", "true", "not json"])
def test_readiness_checks_survive_a_corrupt_marker(tmp_path, monkeypatch, junk):
    """A malformed marker means "rebuild", never an exception out of the probe."""
    monkeypatch.setattr(vendor, "VENDOR_DIR", tmp_path)
    marker = tmp_path / "ffmpeg-source.json"
    monkeypatch.setattr(vendor, "FFMPEG_SOURCE_MARKER", marker)
    marker.write_text(junk, encoding="utf-8")
    assert vendor.ffmpeg_is_ready() is False  # a real bool, never an exception

    (tmp_path / "m.json").write_text(junk, encoding="utf-8")
    assert vendor._manifest_tree_matches(tmp_path, "m.json", {"v": "1"}) is False
    assert vendor._marker_metadata_matches(tmp_path, "m.json", {"v": "1"}) is False
