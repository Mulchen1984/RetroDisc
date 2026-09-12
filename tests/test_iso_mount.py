"""Tests für iso_mount.py - temporäres Mounten von DVD-/Blu-ray-ISOs.

Der reale Mount/Unmount-Zyklus (``hdiutil attach``/``detach`` auf macOS)
wird gegen ein echtes, mit ``mkisofs`` erzeugtes ISO getestet, nicht
gemockt - genau das ist die konkret geforderte Eigenschaft ("sauberes
Mounten mit sicherem Cleanup"). Übersprungen, wenn ``mkisofs`` bzw. (unter
Windows) das Bordmittel nicht verfügbar ist.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from src.services.iso_mount import IsoMountError, mount, mount_iso

pytestmark = pytest.mark.skipif(
    os.name != "posix" or shutil.which("hdiutil") is None or shutil.which("mkisofs") is None,
    reason="hdiutil/mkisofs nicht verfügbar (nur auf macOS in dieser Session real getestet)",
)


@pytest.fixture
def sample_iso(tmp_path):
    content_dir = tmp_path / "iso_src"
    content_dir.mkdir()
    (content_dir / "movie.mp4").write_bytes(b"fake-video-bytes")
    iso_path = tmp_path / "sample.iso"
    result = subprocess.run(
        ["mkisofs", "-V", "TESTISO", "-o", str(iso_path), "-udf", str(content_dir)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return iso_path


@pytest.mark.asyncio
async def test_mount_and_unmount_leaves_no_persistent_mount(sample_iso):
    mounted = await mount(sample_iso)
    try:
        assert mounted.root.is_dir()
        assert (mounted.root / "movie.mp4").is_file()
    finally:
        await mounted.unmount()
    assert not mounted.root.exists()


@pytest.mark.asyncio
async def test_mount_iso_context_manager_unmounts_even_on_exception(sample_iso):
    root_ref = {}
    with pytest.raises(RuntimeError):
        async with mount_iso(sample_iso) as mounted:
            root_ref["root"] = mounted.root
            assert mounted.root.is_dir()
            raise RuntimeError("boom")
    assert not root_ref["root"].exists()


@pytest.mark.asyncio
async def test_mounting_a_missing_file_raises_before_any_attach_attempt(tmp_path):
    with pytest.raises(IsoMountError, match="nicht gefunden"):
        await mount(tmp_path / "does-not-exist.iso")


@pytest.mark.asyncio
async def test_double_unmount_is_a_safe_no_op(sample_iso):
    mounted = await mount(sample_iso)
    await mounted.unmount()
    await mounted.unmount()   # darf nicht erneut hdiutil detach aufrufen/fehlschlagen
