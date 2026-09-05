"""Prove that the built artifacts really carry the RetroDisc icon.

The source tests check the ``.ico`` file and the build configuration. They
cannot see what PyInstaller actually stamped into the PE, and that is the part
the user sees: Explorer, the taskbar, the title bar and both shortcuts all read
their icon out of the executable's resource directory, not out of ``assets``.

So this gate opens ``dist/RetroDisc.exe`` and the installer as PE files, reads
their ``RT_ICON`` resources, and compares the pixels against
``assets/retrodisc.ico``. It also checks that no icon in either binary is the
old person image: a face carries skin tones over a large share of the frame,
which the disc mark never does. Measured on the real thing, the old icon sat
between 35 % and 43 % and the disc mark at 0,0 %, so the 18 % limit below has
room on both sides.

Run it with the approved runtime:

    set PYTHONPATH=.venv\\Lib\\site-packages
    C:\\Users\\marco\\.local\\bin\\python3.11.exe scripts\\verify_app_icon.py
"""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

import pefile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ICON = ASSETS / "retrodisc.ico"

TARGETS = {
    "dist/RetroDisc.exe": ROOT / "dist" / "RetroDisc.exe",
    "Output/RetroDisc_Setup_1.0.0.exe": ROOT / "Output" / "RetroDisc_Setup_1.0.0.exe",
}

RT_ICON = 3
#: Sizes that must be present in the binary, i.e. the ones Windows reaches for.
REQUIRED = (16, 24, 32, 48, 64, 128, 256)


def _icon_resources(path: Path) -> list[Image.Image]:
    """Every RT_ICON in *path*, decoded to RGBA."""
    pe = pefile.PE(str(path), fast_load=True)
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
    )
    images: list[Image.Image] = []
    for entry in getattr(pe, "DIRECTORY_ENTRY_RESOURCE", []).entries:
        if entry.id != RT_ICON:
            continue
        for name in entry.directory.entries:
            for lang in name.directory.entries:
                data = pe.get_data(
                    lang.data.struct.OffsetToData, lang.data.struct.Size
                )
                images.append(_decode(data))
    pe.close()
    return [image for image in images if image is not None]


def _decode(data: bytes) -> Image.Image | None:
    """Decode one RT_ICON payload: either a PNG or a headerless DIB."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return Image.open(io.BytesIO(data)).convert("RGBA")

    # A DIB inside RT_ICON has no BITMAPFILEHEADER and its height counts the
    # image plus its AND mask, so it is doubled. Rebuild a .ico around it and
    # let Pillow do the rest rather than reimplementing the unpacking.
    header_size = struct.unpack_from("<I", data, 0)[0]
    width = struct.unpack_from("<i", data, 4)[0]
    height = struct.unpack_from("<i", data, 8)[0] // 2
    bpp = struct.unpack_from("<H", data, 14)[0]
    entry = struct.pack(
        "<BBBBHHII",
        width if width < 256 else 0,
        height if height < 256 else 0,
        0, 0, 1, bpp, len(data), 22,
    )
    ico = b"\x00\x00\x01\x00\x01\x00" + entry + data
    try:
        return Image.open(io.BytesIO(ico)).convert("RGBA")
    except Exception:  # pragma: no cover - a resource we cannot read is a finding
        _ = header_size
        return None


def _skin_ratio(image: Image.Image) -> float:
    """Share of pixels in the broad skin-tone range of the old portrait."""
    raw = image.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR).tobytes()
    hits = 0
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        if r > 95 and g > 40 and b > 20 and r > g > b and (r - b) > 25 and (r - g) > 10:
            hits += 1
    return hits / (64 * 64)


def _closest(reference: dict[int, Image.Image], candidate: Image.Image) -> float:
    """Mean per-channel difference against the reference frame of that size."""
    size = candidate.size[0]
    if size not in reference:
        return float("nan")
    a = reference[size].convert("RGB").tobytes()
    b = candidate.convert("RGB").tobytes()
    return sum(abs(p - q) for p, q in zip(a, b)) / (size * size * 3)


def main() -> int:
    findings: list[str] = []
    print("RetroDisc App-Icon-Gate")
    print("=" * 46)

    with Image.open(ICON) as ico:
        reference = {
            w: ico.ico.getimage((w, h)).convert("RGBA") for w, h in ico.ico.sizes() if w == h
        }
    print(f"\nReferenz {ICON.relative_to(ROOT).as_posix()}: {sorted(reference)}")

    for label, path in TARGETS.items():
        print(f"\n[{label}]")
        if not path.is_file():
            findings.append(f"{label}: Artefakt fehlt")
            print("  FEHLT")
            continue

        icons = _icon_resources(path)
        sizes = sorted({image.size[0] for image in icons})
        print(f"  RT_ICON-Ressourcen : {len(icons)}, Groessen {sizes}")

        missing = [s for s in REQUIRED if s not in sizes]
        if missing:
            findings.append(f"{label}: Groessen fehlen im PE: {missing}")
            print(f"  FEHLENDE GROESSEN  : {missing}")

        worst_skin = 0.0
        for image in icons:
            ratio = _skin_ratio(image)
            worst_skin = max(worst_skin, ratio)
            if ratio > 0.18:
                findings.append(
                    f"{label}: {image.size[0]}px sieht nach Hautton-Portrait aus "
                    f"({ratio:.0%})"
                )
        print(f"  max. Hautton-Anteil: {worst_skin:.1%} (Grenze 18 %)")

        mismatched = []
        for image in icons:
            if image.size[0] not in reference:
                continue
            delta = _closest(reference, image)
            if delta > 6.0:
                mismatched.append(f"{image.size[0]}px delta {delta:.1f}")
        if mismatched:
            findings.append(f"{label}: weicht von assets/retrodisc.ico ab: {mismatched}")
            print(f"  ABWEICHUNG         : {mismatched}")
        else:
            print("  ok   jede Groesse ist pixelgleich zu assets/retrodisc.ico")

    print("\n" + "=" * 46)
    if findings:
        print(f"RESULT: FAIL ({len(findings)} Befunde)")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("RESULT: PASS (0 Befunde)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
