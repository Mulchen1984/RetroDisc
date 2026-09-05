"""Regression tests for ISO disc-type selection in DiscRipper."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.models.media import DiscType
from src.services.ripper import DiscRipper


class _DiscStub:
    def __init__(self):
        self.disc_type = None

    async def create_iso(self, source_dir, output_path, volume_label, disc_type, job=None):
        self.disc_type = disc_type
        return Path(output_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("VIDEO_TS", DiscType.DVD),
        ("BDMV", DiscType.BLURAY),
        (None, DiscType.CD),
    ],
)
async def test_iso_rip_uses_structure_to_select_disc_type(tmp_path, marker, expected):
    source = tmp_path / "disc"
    source.mkdir()
    if marker:
        (source / marker).mkdir()

    disc = _DiscStub()
    ripper = DiscRipper(ffmpeg=None, disc_tools=disc)
    output = tmp_path / "copy.iso"

    assert await ripper.rip(str(source), output, "iso") == output
    assert disc.disc_type is expected
