"""Create RetroDisc Windows icon assets from the bundled Trump branding image."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "retrodisc_startup.png"
MASTER_SIZE = 1024
# Tight square portrait: hair, face, pointing hand and suit remain recognizable
# when Windows renders the icon at taskbar sizes.
SOURCE_CROP = (240, 20, 880, 660)


def build_master() -> Image.Image:
    source = Image.open(SOURCE).convert("RGB")
    portrait = source.crop(SOURCE_CROP).resize(
        (MASTER_SIZE, MASTER_SIZE), Image.Resampling.LANCZOS
    )
    portrait = ImageEnhance.Contrast(portrait).enhance(1.06)
    portrait = ImageEnhance.Color(portrait).enhance(1.08)
    portrait = portrait.filter(ImageFilter.UnsharpMask(radius=1.6, percent=115, threshold=3))

    # Transparent rounded-square silhouette with a crisp retro-neon frame.
    radius = 176
    mask = Image.new("L", (MASTER_SIZE, MASTER_SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (14, 14, MASTER_SIZE - 15, MASTER_SIZE - 15), radius=radius, fill=255
    )
    icon = Image.new("RGBA", (MASTER_SIZE, MASTER_SIZE), (0, 0, 0, 0))
    icon.paste(portrait, (0, 0), mask)

    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle(
        (16, 16, MASTER_SIZE - 17, MASTER_SIZE - 17),
        radius=radius,
        outline=(0, 229, 255, 255),
        width=22,
    )
    draw.rounded_rectangle(
        (39, 39, MASTER_SIZE - 40, MASTER_SIZE - 40),
        radius=radius - 22,
        outline=(255, 32, 174, 235),
        width=10,
    )
    return icon


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = build_master()
    master.save(ASSETS / "retrodisc_1024.png", "PNG", optimize=True)

    for size in (16, 24, 32, 48, 64, 128, 256):
        resized = master.resize((size, size), Image.Resampling.LANCZOS)
        if size <= 32:
            resized = resized.filter(ImageFilter.UnsharpMask(radius=0.55, percent=150, threshold=1))
        resized.save(ASSETS / f"retrodisc_{size}.png", "PNG", optimize=True)

    master.save(
        ASSETS / "retrodisc.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    master.resize((256, 256), Image.Resampling.LANCZOS).save(
        ASSETS / "retrodisc_icon_preview.png", "PNG", optimize=True
    )
    print(ASSETS / "retrodisc.ico")


if __name__ == "__main__":
    main()
