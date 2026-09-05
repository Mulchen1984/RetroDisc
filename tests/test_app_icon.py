"""The application icon is RetroDisc's own disc mark, everywhere.

The icon that shipped until 2026-09-05 was a cropped caricature of a real
person. It reached the taskbar, the window title bar, the EXE, the installer
and both shortcuts, because Windows takes all of that from the one ``.ico``
the build points at, and the splash carried the same artwork.

These tests hold three things:

* the ``.ico`` really contains every size Windows asks for, each with its own
  drawn frame rather than one image resampled seven times;
* every build path that stamps an icon points at that same file;
* nothing in the repository still carries the old picture - neither the asset,
  nor the script that cropped it, nor a document telling a tester to expect it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ICON = ASSETS / "retrodisc.ico"
SPLASH = ASSETS / "retrodisc_startup.png"

#: Windows picks a different one of these per surface: 16 for the title bar,
#: 24/32 for the taskbar and Explorer, 256 for the extra-large view.
REQUIRED_SIZES = (16, 24, 32, 48, 64, 128, 256)

#: The splash window in retrodisc_launcher.main(); the artwork is drawn to
#: match so object-fit: contain leaves no letterbox.
SPLASH_WINDOW = (900, 640)


@pytest.fixture(scope="module")
def frames() -> dict[int, Image.Image]:
    with Image.open(ICON) as ico:
        return {s: ico.ico.getimage((s, s)).convert("RGBA") for s in REQUIRED_SIZES}


def test_the_ico_carries_every_size_windows_asks_for():
    with Image.open(ICON) as ico:
        declared = {w for w, h in ico.ico.sizes() if w == h}
    assert set(REQUIRED_SIZES) <= declared, (
        f"missing sizes: {sorted(set(REQUIRED_SIZES) - declared)}"
    )


def test_no_size_is_blank_or_transparent(frames):
    for size, frame in frames.items():
        assert frame.getbbox() is not None, f"{size}px frame is empty"
        alpha = frame.getchannel("A").histogram()
        coverage = sum(alpha[201:]) / (size * size)
        assert coverage > 0.55, f"{size}px frame is mostly transparent ({coverage:.0%})"


def test_the_background_is_dark_and_the_mark_is_bright(frames):
    """A dark ground with a light mark is what keeps 16x16 readable.

    Measured over the whole frame rather than at a chosen pixel: at 16px the
    disc reaches close to the tile edge, so any fixed sample point is as
    likely to land on the bright rim as on the ground.
    """
    for size, frame in frames.items():
        luma = frame.convert("RGB").convert("L")
        opaque = frame.getchannel("A").point(lambda v: 255 if v > 200 else 0)
        counts = luma.histogram(mask=opaque)
        total = sum(counts)

        seen, median = 0, 255
        for value, count in enumerate(counts):
            seen += count
            if seen >= total / 2:
                median = value
                break
        brightest = max(value for value, count in enumerate(counts) if count)

        assert median < 80, f"{size}px: ground is not dark (median luma {median})"
        assert brightest > 170, f"{size}px: no bright mark to read ({brightest})"


def test_small_sizes_are_drawn_for_their_size_not_resampled_from_the_largest(frames):
    """A 16px downscale of a 256px master loses the shape to grey mush."""
    largest = frames[256]
    for size in (16, 24, 32):
        resampled = largest.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
        assert frames[size].tobytes() != resampled.tobytes(), (
            f"{size}px frame is just a downscale of the 256px one"
        )


def test_every_build_path_stamps_this_one_icon():
    expected = 'assets" / "retrodisc.ico'
    for name in ("build.py", "retrodisc_final.spec"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert expected in source, f"{name} does not point at assets/retrodisc.ico"

    # The installer inherits the icon it stamps from the same file, and both
    # shortcuts inherit theirs from the installed EXE.
    installer = (ROOT / "installer" / "retrodisc_installer.py").read_text(encoding="utf-8")
    assert "$Shortcut.IconLocation" in installer
    assert "IconLocation = '{str(target).replace(\"'\", \"''\")}',0'" in installer or (
        re.search(r"IconLocation\s*=\s*'\{str\(target\)[^}]*\},0'", installer)
    ), "shortcuts no longer take their icon from the installed EXE"


def test_the_splash_artwork_matches_its_window_and_is_referenced():
    """A tolerance, not an exact ratio: the splash is a hand-made asset.

    The property that matters is that ``object-fit: contain`` leaves no visible
    letterbox, so a few percent off is fine and a 4:3 image in a 1.41:1 window
    is not.
    """
    assert SPLASH.is_file()
    with Image.open(SPLASH) as splash:
        width, height = splash.size
    assert width >= 1200, "splash artwork is too small for a 900px-wide window"

    wanted = SPLASH_WINDOW[0] / SPLASH_WINDOW[1]
    actual = width / height
    assert abs(actual - wanted) / wanted < 0.04, (
        f"splash aspect {actual:.3f} is too far from the window's {wanted:.3f}; "
        "object-fit: contain would letterbox it"
    )
    html = (ROOT / "src" / "ui" / "splash.html").read_text(encoding="utf-8")
    assert "../../assets/retrodisc_startup.png" in html


def test_the_splash_is_shown_for_about_two_seconds():
    """The startup image is meant to be seen, not to flash past.

    Two timers add up: the wait after ``pywebviewready`` before the finish is
    requested, and the short hand-off delay before the main document replaces
    the splash.
    """
    html = (ROOT / "src" / "ui" / "splash.html").read_text(encoding="utf-8")
    delays = [int(value) for value in re.findall(r"window\.setTimeout\([^,]+,\s*(\d+)\)", html)]
    assert len(delays) == 2, f"expected two splash timers, found {delays}"

    total_ms = sum(delays)
    assert 1800 <= total_ms <= 2600, (
        f"splash budget is {total_ms} ms, which is not about two seconds"
    )


def test_the_icon_generator_never_writes_the_splash():
    """Icon and splash are strictly separate assets.

    The splash is a finished, approved image. Regenerating the icon must not
    be able to overwrite it, so the generator may not name it at all.
    """
    source = (ROOT / "scripts" / "create_icon.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Docstrings may name the splash - explaining the rule is the point. Only
    # a string the code actually uses could become a path it writes to.
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    live = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    assert not [s for s in live if "retrodisc_startup" in s], (
        "scripts/create_icon.py names the splash file in live code and could "
        "overwrite it again"
    )
    assert "def draw_startup" not in source


def test_the_icon_generator_draws_its_own_artwork_from_no_photograph():
    generator = (ROOT / "scripts" / "create_icon.py").read_text(encoding="utf-8")
    assert "def draw_icon" in generator
    # It must not open any bitmap as its source; every shape is drawn.
    assert "Image.open" not in generator, "the generator reads an external image again"

    assert not (ROOT / "scripts" / "generate_icon.py").exists(), (
        "the caricature generator is back"
    )


def test_the_title_bar_mark_is_the_disc_and_not_a_face():
    """The in-app header carried the caricature as inline SVG, not as a file.

    A repository sweep for image references could not see it, and neither
    could the icon gate on the PE resources - it only showed up in a
    screenshot of the running app.
    """
    html = (ROOT / "src" / "ui" / "app.html").read_text(encoding="utf-8")
    header = re.search(
        r'<div class="win-title">(.*?)</svg>', html, re.DOTALL
    )
    assert header, "title bar mark is gone"
    svg = header.group(1)

    assert 'aria-label="RetroDisc"' in svg
    # The disc: a hub, a rim and the rewind arrowhead.
    assert svg.count("<circle") >= 3, "title bar mark lost its disc rings"
    assert "<polygon" in svg, "title bar mark lost its rewind arrowhead"
    # A face is two small eye ellipses plus a quadratic-curve mouth.
    assert "<ellipse" not in svg, "title bar mark has ellipses again (eyes?)"
    assert " Q" not in svg, "title bar mark has a quadratic curve again (mouth?)"


def test_no_tracked_file_still_carries_the_old_person_image():
    """Text and binaries both: the picture must be gone, not just unreferenced."""
    banned = re.compile(r"trump|karikatur|caricature", re.I)
    offenders: list[str] = []

    skip_dirs = {".git", ".venv", "build", "dist", "Output", "vendor", "__pycache__"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in skip_dirs for part in path.parts):
            continue
        if path == Path(__file__):
            continue  # this scanner has to name what it is looking for
        if path.suffix.lower() in {".png", ".ico", ".icns", ".jpg", ".jpeg", ".gif"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if banned.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}")

    # RELEASE_AUDIT_STATUS.md is the binding journal. A dated entry recording
    # what a past run actually showed stays as written - rewriting it would
    # falsify the audit record - so only that file may still name the old
    # artwork, and only in its history.
    unexpected = [o for o in offenders if not o.startswith("RELEASE_AUDIT_STATUS.md:")]
    assert unexpected == [], f"old artwork still referenced: {unexpected}"
