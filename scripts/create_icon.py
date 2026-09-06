"""Draw the RetroDisc application icon.

**This script never touches the splash screen.** The startup image
(``assets/retrodisc_startup.png``) is a finished, hand-approved asset; icon and
splash are kept strictly apart so regenerating the icon can never overwrite it.
Anything here writes only ``retrodisc.ico``, ``retrodisc.icns`` and the icon
PNGs.

The motif is RetroDisc's own: an optical disc on a dark technical ground, with
a rewind/copy arc sweeping counter-clockwise around the hub. No photograph, no
person, no third-party mark, no CloneCD artwork - every shape here is drawn
from these coordinates.

Legibility at 16x16 and 32x32 drives the design. Only three things have to
survive that far down: the bright disc rim, the dark hub, and the rewind arc.
Everything finer (tick marks, the iridescent sweep, the inner clamp ring) is
dropped below 48 px by ``simplified``, because at that size it turns to mud and
eats the contrast the three main shapes need.

Run it with the approved runtime, not the blocked venv EXE:

    set PYTHONPATH=.venv\\Lib\\site-packages
    C:\\Users\\marco\\.local\\bin\\python3.11.exe scripts\\create_icon.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

#: Windows reads every one of these out of the single .ico file.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

#: Supersampling factor. Everything is drawn large and filtered down, which is
#: what keeps the arcs clean - PIL has no antialiasing of its own.
SS = 8

#: Below this the fine detail is dropped instead of being downsampled to mush.
#: 32 is on the simplified side on purpose: it is the size Windows uses for the
#: taskbar and for Explorer's medium icons, and the tick texture turns it grey.
SIMPLIFY_BELOW = 48

# ── Palette ───────────────────────────────────────────────────────────────
# Cool steel and cyan: technical rather than toy-like. The magenta is a single
# restrained accent that ties the icon to the retro language used in the UI.
ITILE_TOP = (16, 26, 43)
TILE_BOTTOM = (6, 10, 19)
TILE_EDGE = (44, 66, 99)
DISC_BODY = (23, 40, 61)
DISC_BODY_LIT = (37, 62, 92)
RIM_BRIGHT = (128, 226, 255)
RIM_DEEP = (30, 86, 122)
CLAMP_RING = (86, 140, 181)
ARC_CYAN = (134, 231, 255)
ARC_MAGENTA = (236, 126, 214)
HUB_EDGE = (150, 233, 255)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _tile(size: int, radius: float) -> Image.Image:
    """Dark rounded square with a vertical gradient and a thin lit edge."""
    gradient = Image.new("RGB", (1, size))
    for y in range(size):
        gradient.putpixel((0, y), _lerp(ITILE_TOP, TILE_BOTTOM, y / max(1, size - 1)))
    gradient = gradient.resize((size, size), Image.Resampling.BILINEAR)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)

    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile.paste(gradient, (0, 0), mask)
    ImageDraw.Draw(tile).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, outline=TILE_EDGE + (150,),
        width=max(1, round(size * 0.008)),
    )
    return tile


def _ring(size: int, cx: float, cy: float, radius: float, width: float,
          color: tuple[int, int, int], alpha: int = 255) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        outline=color + (alpha,), width=max(1, round(width)),
    )
    return layer


def _arc_with_head(size: int, cx: float, cy: float, radius: float, width: float,
                   start_deg: float, end_deg: float, color: tuple[int, int, int],
                   alpha: int, head: bool) -> Image.Image:
    """An arc drawn clockwise from *start* to *end*, arrowhead at the start.

    PIL angles run clockwise with y pointing down, so the head placed at the
    start end points counter-clockwise: the rewind direction.
    """
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(box, start=start_deg, end=end_deg, fill=color + (alpha,), width=max(1, round(width)))

    if not head:
        return layer

    theta = math.radians(start_deg)
    px, py = cx + radius * math.cos(theta), cy + radius * math.sin(theta)
    # Counter-clockwise tangent at theta, and the outward normal.
    tx, ty = math.sin(theta), -math.cos(theta)
    nx, ny = math.cos(theta), math.sin(theta)
    reach = width * 1.80
    span = width * 1.12
    draw.polygon(
        [
            (px + tx * reach, py + ty * reach),
            (px + nx * span, py + ny * span),
            (px - nx * span, py - ny * span),
        ],
        fill=color + (alpha,),
    )
    return layer


def draw_icon(px: int, ss: int = SS) -> Image.Image:
    """Render one square icon at *px*, supersampled by *ss*."""
    simplified = px < SIMPLIFY_BELOW
    size = px * ss
    cx = cy = size / 2

    icon = _tile(size, radius=size * 0.185)

    # Geometry, as fractions of the tile. The two tiers stay deliberately
    # close - an icon set has to look like one icon - and differ only where
    # pixels are scarce: the simplified stroke weights step up a little and
    # the arc moves inward, so a dark gap still separates it from the rim when
    # the whole tile is 16 px.
    r_outer = size * (0.398 if simplified else 0.388)
    rim_w = size * (0.068 if simplified else 0.052)
    r_clamp = size * 0.148
    r_hub = size * (0.094 if simplified else 0.082)
    r_arc = size * (0.216 if simplified else 0.228)
    arc_w = size * (0.092 if simplified else 0.078)

    # Disc body, lit from the upper left so it reads as a physical object.
    body = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(body).ellipse(
        (cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer), fill=DISC_BODY + (255,)
    )
    if not simplified:
        sheen = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(sheen).pieslice(
            (cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer),
            start=178, end=286, fill=DISC_BODY_LIT + (210,),
        )
        sheen = sheen.filter(ImageFilter.GaussianBlur(size * 0.035))
        body.alpha_composite(sheen)
    icon.alpha_composite(body)

    if not simplified:
        # Pressed-data tick marks: a faint technical texture, never a pattern
        # that competes with the arc.
        ticks = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(ticks)
        for i in range(72):
            a = math.radians(i * 5)
            r0, r1 = r_outer * 0.66, r_outer * 0.93
            tdraw.line(
                [
                    (cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
                    (cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
                ],
                fill=RIM_BRIGHT + (34,), width=max(1, round(size * 0.004)),
            )
        icon.alpha_composite(ticks)

    # Rim: a deep outer edge under a bright inner highlight gives it thickness.
    icon.alpha_composite(_ring(size, cx, cy, r_outer - rim_w * 0.18, rim_w * 1.05, RIM_DEEP, 255))
    icon.alpha_composite(_ring(size, cx, cy, r_outer - rim_w * 0.62, rim_w * 0.72, RIM_BRIGHT, 255))

    # The rewind/copy gesture: bold counter-clockwise arc with an arrowhead.
    if not simplified:
        icon.alpha_composite(
            _arc_with_head(size, cx, cy, r_arc, arc_w * 0.52, 96, 208, ARC_MAGENTA, 200, head=False)
        )
    icon.alpha_composite(
        _arc_with_head(size, cx, cy, r_arc, arc_w, 232, 66 + 360, ARC_CYAN, 255, head=True)
    )

    # Hub: clamp ring, then the dark centre hole punched back to the tile.
    if not simplified:
        icon.alpha_composite(_ring(size, cx, cy, r_clamp, size * 0.016, CLAMP_RING, 220))
    hole = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(hole)
    hdraw.ellipse((cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub), fill=TILE_BOTTOM + (255,))
    hdraw.ellipse(
        (cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub),
        outline=HUB_EDGE + (255,), width=max(1, round(size * (0.020 if simplified else 0.014))),
    )
    icon.alpha_composite(hole)

    icon = icon.resize((px, px), Image.Resampling.LANCZOS)
    if px <= 32:
        icon = icon.filter(ImageFilter.UnsharpMask(radius=0.6, percent=110, threshold=0))
    return icon


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    master = draw_icon(1024, ss=2)
    master.save(ASSETS / "retrodisc_1024.png", "PNG", optimize=True)

    # Each size is drawn at its own scale rather than resampled from the
    # master, so the small ones get the simplified geometry they need.
    frames = []
    for size in ICON_SIZES:
        frame = draw_icon(size)
        frame.save(ASSETS / f"retrodisc_{size}.png", "PNG", optimize=True)
        frames.append(frame)

    largest = frames[-1]
    largest.save(
        ASSETS / "retrodisc.ico", format="ICO",
        sizes=[(s, s) for s in ICON_SIZES],
        append_images=frames[:-1],
    )
    largest.save(ASSETS / "retrodisc_icon_preview.png", "PNG", optimize=True)

    # macOS leftover, carried along so the asset set stays coherent. No build
    # path uses it; see CLAUDE.md.
    icns = [draw_icon(s, ss=4) for s in (16, 32, 128, 256, 512)]
    icns[-1].save(ASSETS / "retrodisc.icns", format="ICNS", append_images=icns[:-1])

    for name in ("retrodisc.ico", "retrodisc.icns"):
        print(f"{name}: {(ASSETS / name).stat().st_size} bytes")


if __name__ == "__main__":
    main()
