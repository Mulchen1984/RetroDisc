"""Die Startseite muss bei jeder Windows-Skalierung fuenf Aktionen zeigen.

Gemessen wird das von ``scripts/verify_home_layout.py``, das die Seite in einem
echten WebView2-Fenster bei 100 %, 125 % und 150 % vermisst. Dieser Test kann
das nicht: er braucht keine Oberflaeche und laeuft in jedem ``pytest``-Lauf
mit. Er sichert stattdessen die Regeln ab, aus denen das gemessene Ergebnis
folgt - damit ein spaeterer Griff in das CSS nicht unbemerkt genau den Fehler
zurueckholt, der hier behoben wurde:

* die Reihe der fuenf Kacheln brach um, sobald der CSS-Viewport schmal wurde
  (gekapptes Fenster bei 125 %/150 %), und die fuenfte Kachel verschwand aus
  dem sichtbaren Bereich;
* die Groessen waren feste Pixelwerte, die diesen Fall gar nicht abdecken
  konnten.

Zusaetzlich wird die CloneCD-Bildsprache aus ``CLAUDE.md`` festgehalten:
Brennen = Disc + Stift, Rippen = Disc + Brille, Disc kopieren = zwei Discs,
alles als eigene Inline-SVGs ohne fremde Grafikdateien.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "src" / "ui" / "app.html").read_text(encoding="utf-8")

STYLE = "\n".join(
    match.group(1)
    for match in re.finditer(r"<style[^>]*>(.*?)</style>", UI, re.DOTALL | re.IGNORECASE)
)
# Ohne die Kommentare, sonst haengen sie beim Zerlegen am naechsten Selektor.
STYLE_RULES = re.sub(r"/\*.*?\*/", "", STYLE, flags=re.DOTALL)

# "width" muss die Eigenschaft selbst treffen, nicht "min-width" oder
# "max-width" - sonst misst der Test den falschen Wert.
def declaration(body: str, property_name: str) -> str | None:
    match = re.search(rf"(?<![-\w]){property_name}\s*:\s*([^;]+);", body)
    return match.group(1).strip() if match else None


def rules_for(selector: str) -> list[str]:
    """Alle Regelkoerper, deren Selektorliste genau ``selector`` enthaelt.

    Absichtlich alle und nicht nur der erste: der Fehler bestand einmal darin,
    dass ein zweiter Block weiter unten die gute Regel wieder mit festen
    Pixelwerten ueberschrieben hat.
    """
    bodies = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", STYLE_RULES):
        selectors = [part.strip() for part in match.group(1).split(",")]
        if selector in selectors:
            bodies.append(match.group(2))
    return bodies


def card(flow: str) -> str:
    """Das Markup einer Startseiten-Kachel."""
    match = re.search(
        rf"""<div class="cbtn" onclick="openFlow\('{flow}'\)">(.*?)</svg>""",
        UI,
        re.DOTALL,
    )
    assert match, f"Kachel {flow} fehlt"
    return match.group(1)


# ── Die Reihe darf nicht umbrechen ────────────────────────────────────────


def test_the_row_of_actions_never_wraps():
    bodies = rules_for(".cc-row")
    assert bodies, ".cc-row ist nicht mehr definiert"
    assert any("flex-wrap:nowrap" in body.replace(" ", "") for body in bodies)
    assert not any(
        "flex-wrap:wrap" in body.replace(" ", "") for body in bodies
    ), "Die Aktionsreihe darf nicht umbrechen - genau das hat die fuenfte Kachel verschluckt"


def test_the_tiles_are_sized_against_the_viewport_not_in_fixed_pixels():
    bodies = rules_for(".cbtn")
    assert bodies, ".cbtn ist nicht mehr definiert"
    sized = [body for body in bodies if declaration(body, "width")]
    assert sized, ".cbtn bekommt keine Breite mehr"
    for body in sized:
        width = declaration(body, "width")
        height = declaration(body, "height")
        assert width and "vw" in width, (
            f"Feste Kachelbreite {width!r}: bei gekapptem Fenster passen fuenf "
            "davon nicht mehr nebeneinander"
        )
        assert height and "vw" in height, f"Feste Kachelhoehe {height!r}"


def test_no_later_rule_overrides_the_tiles_with_fixed_pixels():
    """Der zweite, feste Block von frueher darf nicht zurueckkehren."""
    for selector in (".cbtn", ".cc-ico"):
        for body in rules_for(selector):
            for property_name in ("width", "height"):
                value = declaration(body, property_name)
                if value:
                    assert not re.fullmatch(r"\d+(\.\d+)?px", value), (
                        f"{selector} setzt {property_name} wieder fest auf {value}"
                    )


def test_the_icons_scale_with_their_tile():
    bodies = rules_for(".cc-ico svg")
    assert bodies, "Die Symbole skalieren nicht mit der Kachel"
    assert any("width:100%" in body.replace(" ", "") for body in bodies)


def test_the_secondary_actions_share_the_same_budget():
    """Ihr fester Aussenabstand hat sie frueher aus dem Fenster geschoben."""
    bodies = rules_for(".cc-stage .secondary")
    assert bodies, "Die Zusatzaktionen haben keine eigene Startseiten-Regel"
    assert any("margin-top:0" in body.replace(" ", "") for body in bodies)


# ── CloneCD-Bildsprache aus CLAUDE.md ─────────────────────────────────────


def test_burning_is_a_disc_with_a_pen():
    svg = card("burn")
    assert '<ellipse cx="0" cy="0"' in svg, "Brennen zeigt keine Disc"
    assert 'class="cc-pen"' in svg, "Brennen zeigt keinen Stift"


def test_ripping_is_a_disc_with_glasses():
    svg = card("rip")
    assert '<ellipse cx="0" cy="0"' in svg, "Rippen zeigt keine Disc"
    assert 'class="cc-glasses"' in svg, "Rippen zeigt keine Brille"


def test_the_pen_keeps_its_tilt_under_the_animation():
    """Ein CSS-transform auf derselben Gruppe wuerde das Attribut ersetzen."""
    svg = card("burn")
    match = re.search(r'<g class="cc-pen">\s*<g transform="rotate\(', svg)
    assert match, "Die Schreibgeste sitzt nicht auf einer eigenen Gruppe"


def test_the_gestures_are_calm_and_can_be_switched_off():
    assert "@keyframes cc-write" in STYLE, "Die Schreibbewegung fehlt"
    assert "@keyframes cc-scan" in STYLE, "Die Lesebewegung fehlt"
    assert "prefers-reduced-motion" in STYLE, (
        "Die Bewegungen lassen sich nicht abschalten"
    )
    # Keine hektischen Effekte: beide Gesten laufen ueber mehrere Sekunden.
    for name in ("cc-write", "cc-scan"):
        durations = re.findall(rf"animation:{name}\s+([\d.]+)s", STYLE.replace(" ", " "))
        assert durations, f"{name} wird nicht verwendet"
        assert all(float(value) >= 5 for value in durations), (
            f"{name} laeuft zu schnell fuer eine dezente Geste"
        )


def test_the_start_screen_draws_its_own_artwork():
    """Keine fremden Grafikdateien - CLAUDE.md verlangt eigene SVGs."""
    home = re.search(r'<div id="homeview">(.*?)\n  </div>', UI, re.DOTALL)
    assert home, "Startseite nicht gefunden"
    markup = home.group(1)
    assert "<img" not in markup, "Die Startseite laedt eine Bilddatei"
    # url(#...) verweist auf einen Verlauf im selben SVG; alles andere waere
    # eine fremde Grafik.
    external = re.findall(r"url\(\s*(?!#)([^)]*)\)", markup)
    assert not external, f"Die Startseite laedt fremde Grafiken: {external}"
    assert markup.count("<svg") == 5, "Nicht jede Aktion zeichnet ihr eigenes SVG"
