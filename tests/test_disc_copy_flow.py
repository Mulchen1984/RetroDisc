"""Disc kopieren ist ein eigener Flow, nicht Teil von Konvertieren.

Das Doppel-Disc-Symbol auf der Startseite gehoert fachlich zu "Disc kopieren".
Es stand vorher auf der Konvertieren-Karte und hat damit die falsche Aktion
beworben.

Geprueft wird beides: die Startseite mit fuenf klar getrennten Aktionen und
die Regeln des Kopier-Flows - Quelle ist ein Leselaufwerk, Ziel ein Brenner,
On-the-fly nur mit zwei verschiedenen Laufwerken.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Die Bridge-Fixture wird wiederverwendet, nicht kopiert.
from test_disc_flows import disc_bridge  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "src" / "ui" / "app.html").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")


# ── Startseite ────────────────────────────────────────────────────────────


def home_cards() -> list[tuple[str, str]]:
    """(Flow-Name, Beschriftung) der Startseiten-Karten, in Reihenfolge."""
    return re.findall(
        r"""<div class="cbtn" onclick="openFlow\('([a-z]+)'\)">.*?"""
        r"""<div class="cc-label">([^<]+)</div>""",
        UI,
        re.DOTALL,
    )


def test_the_start_screen_offers_five_distinct_actions():
    assert home_cards() == [
        ("disccopy", "Disc kopieren"),
        ("convert", "Konvertieren"),
        ("burn", "Brennen"),
        ("rip", "Rippen"),
        ("download", "Download"),
    ]


def test_the_start_screen_text_matches_the_number_of_actions():
    assert "fuenf Aktionen" in UI
    assert "vier Aktionen" not in UI


def test_the_two_disc_icon_now_belongs_to_disc_copy():
    """Das Symbol mit zwei Discs bewirbt jetzt die richtige Aktion."""
    card = re.search(
        r"""<div class="cbtn" onclick="openFlow\('disccopy'\)">(.*?)</svg>""",
        UI,
        re.DOTALL,
    )
    assert card, "Disc-kopieren-Karte fehlt"
    discs = re.findall(r'<ellipse cx="0" cy="0" rx="[\d.]+"', card.group(1))
    assert len(discs) >= 2, "Disc kopieren traegt nicht das Doppel-Disc-Symbol"


def test_convert_has_its_own_icon_without_discs():
    """Konvertieren darf nicht laenger mit Discs beworben werden."""
    card = re.search(
        r"""<div class="cbtn" onclick="openFlow\('convert'\)">(.*?)</svg>""",
        UI,
        re.DOTALL,
    )
    assert card, "Konvertieren-Karte fehlt"
    svg = card.group(1)
    assert "<ellipse" not in svg, "Konvertieren zeigt weiterhin Disc-Ellipsen"
    assert "<rect" in svg, "Konvertieren hat kein eigenes Symbol bekommen"


# ── Laufwerkserkennung wird wiederverwendet ───────────────────────────────


def test_disc_copy_reuses_the_existing_drive_detection():
    """Es darf keine zweite Erkennung geben - nur ein detect_burners-Aufruf."""
    assert UI.count("detect_burners()") == 1
    load = re.search(r"async function loadBurners\(force\)\{(.*?)\n\}", UI, re.DOTALL)
    assert load, "loadBurners fehlt"
    body = load.group(1)
    assert "copySourceSelect" in body and "copyTargetSelect" in body


def test_opening_the_copy_flow_loads_the_drives():
    match = re.search(r"function openFlow\(name\)\{(.*?)\n\}", UI, re.DOTALL)
    assert match, "openFlow fehlt"
    assert "name==='disccopy'" in match.group(1)
    assert "loadBurners(false)" in match.group(1)


# ── On-the-fly-Regeln in der Oberflaeche ──────────────────────────────────


def test_on_the_fly_is_disabled_by_default_until_two_drives_are_known():
    radio = re.search(r'<input type="radio"[^>]*id="copyModeOnTheFly"[^>]*>', UI)
    assert radio, "On-the-fly-Option fehlt"
    assert "disabled" in radio.group(0)


def test_on_the_fly_requires_two_different_drives():
    body = re.search(r"function updateCopyModes\(\)\{(.*?)\n\}", UI, re.DOTALL)
    assert body, "updateCopyModes fehlt"
    logic = body.group(1)
    assert "COPY_DRIVES.length>1" in logic, "Zwei-Laufwerk-Bedingung fehlt"
    assert "source.value===target.value" in logic, "Gleichheitspruefung fehlt"
    assert "onTheFly.disabled = !possible" in logic


def test_the_user_is_told_why_on_the_fly_is_unavailable():
    """Eine verstaendliche Meldung, kein stilles Deaktivieren."""
    body = re.search(r"function updateCopyModes\(\)\{(.*?)\n\}", UI, re.DOTALL)
    logic = body.group(1)
    assert "zwei optische Laufwerke" in logic
    assert "dasselbe Laufwerk" in logic


# ── Backend-Regeln ────────────────────────────────────────────────────────


def _error(bridge, *args) -> str:
    return json.loads(bridge.copy_disc(*args)).get("error", "")


def test_copy_disc_is_reachable_from_the_ui(monkeypatch):
    """Ohne Proxy auf RetroDiscApi kommt der Aufruf nie im Backend an."""
    assert "def copy_disc(self, *args): return self._bridge.copy_disc(*args)" in LAUNCHER
    assert "a.copy_disc(source,target,mode)" in UI


def test_on_the_fly_refuses_the_same_drive_for_source_and_target(disc_bridge):
    create, _ = disc_bridge
    bridge = create(Path("."))
    message = _error(bridge, "D:", "D:", "onthefly")
    assert "zwei verschiedene Laufwerke" in message


def test_copying_over_an_image_accepts_a_single_drive(disc_bridge):
    """Mit nur einem Laufwerk bleibt der Weg ueber ein Abbild zulaessig.

    Geprueft wird die Regel, nicht das Einreihen: in dieser Testumgebung
    laeuft keine Pipeline, ein Submit endet daher immer mit einem eigenen
    Fehler. Entscheidend ist, dass die Laufwerkspruefung nicht abweist.
    """
    create, _ = disc_bridge
    bridge = create(Path("."))
    message = _error(bridge, "D:", "D:", "image")
    assert "verschiedene Laufwerke" not in message
    assert "Laufwerk ausgewählt" not in message


def test_missing_drives_are_rejected_with_a_clear_message(disc_bridge):
    create, _ = disc_bridge
    bridge = create(Path("."))
    assert "Quelllaufwerk" in _error(bridge, "", "E:", "image")
    assert "Ziellaufwerk" in _error(bridge, "D:", "", "image")


def test_an_unknown_copy_mode_is_rejected(disc_bridge):
    create, _ = disc_bridge
    bridge = create(Path("."))
    assert "Kopiermodus" in _error(bridge, "D:", "E:", "teleport")


def test_on_the_fly_is_not_silently_replaced_by_the_image_path(disc_bridge):
    """Der Nutzer darf nicht etwas anderes bekommen, als er gewaehlt hat.

    Ein echtes On-the-fly-Kopieren gibt es im Backend nicht. Statt still auf
    den Abbild-Weg auszuweichen, wird das ausdruecklich gesagt.
    """
    create, _ = disc_bridge
    bridge = create(Path("."))
    message = _error(bridge, "D:", "E:", "onthefly")
    assert "noch nicht" in message and "Abbild" in message


def test_the_filesystem_level_limitation_is_documented():
    """copy_disc darf keinen 1:1-Klon versprechen.

    rip_disc(..., "iso") liest das gemountete Dateisystem und erzeugt daraus
    mit mkisofs ein neues Abbild - das ist kein sektorweises Klonen.
    """
    body = re.search(r'def copy_disc\(self.*?""".*?"""', LAUNCHER, re.DOTALL)
    assert body, "copy_disc fehlt"
    doc = body.group(0)
    assert "Dateisystem-Kopie" in doc
    assert "kein sektorweiser" in doc or "kein sektorweises" in doc
    # Auch der Nutzer muss es in der Oberflaeche sehen.
    assert "nicht Sektor fuer Sektor" in UI


def test_copy_disc_composes_the_existing_rip_and_burn_paths():
    """Kein zweiter Rip- oder Brennpfad - die vorhandenen werden benutzt."""
    body = re.search(
        r"def copy_disc\(self.*?return self\._submit_job\(job, _handler\)",
        LAUNCHER,
        re.DOTALL,
    )
    assert body, "copy_disc fehlt"
    source = body.group(0)
    assert "DiscRipper" in source, "Der vorhandene Ripper wird nicht benutzt"
    assert "self.disc.burn_iso" in source, "Der vorhandene Brennpfad fehlt"


# ── Kein Laufwerks-Scan beim Programmstart ────────────────────────────────


def _startup_body() -> str:
    match = re.search(r"async function startup\(\) \{(.*?)\n\}", UI, re.DOTALL)
    assert match, "startup() fehlt"
    return match.group(1)


def test_startup_never_scans_optical_drives():
    """Die Erkennung startet unter Windows PowerShell - nicht beim Hochfahren.

    Das war der Grund fuer aufblitzende Konsolenfenster beim normalen Start.
    """
    # Nur echter Code zaehlt: ein Kommentar, der erklaert, warum hier NICHT
    # erkannt wird, darf den Test nicht ausloesen.
    body = "\n".join(
        line for line in _startup_body().splitlines()
        if not line.lstrip().startswith("//")
    )
    for call in ("loadBurners(", "detect_burners", "run_powershell_hidden"):
        assert call not in body, f"startup() ruft {call} auf"


def test_the_home_screen_triggers_no_drive_detection():
    """goHome darf nichts erkennen - der Home-Screen braucht keine Laufwerke."""
    match = re.search(r"function goHome\(\)\{(.*?)\n\}", UI, re.DOTALL)
    assert match, "goHome fehlt"
    assert "loadBurners" not in match.group(1)


def test_only_the_three_disc_areas_trigger_detection():
    match = re.search(r"function openFlow\(name\)\{(.*?)\n\}", UI, re.DOTALL)
    assert match, "openFlow fehlt"
    body = match.group(1)
    assert "name==='burn'" in body
    assert "name==='rip'" in body
    assert "name==='disccopy'" in body
    assert body.count("loadBurners") == 1, "mehr als ein Erkennungspfad"


def test_detection_result_is_cached_for_the_session():
    match = re.search(r"async function loadBurners\(force\)\{(.*?)\n\}", UI, re.DOTALL)
    assert match, "loadBurners(force) fehlt"
    body = match.group(1)
    assert "if(DRIVES_LOADED && !force) return;" in body
    # Nur ein erfolgreicher Lauf darf als erledigt gelten.
    assert "DRIVES_LOADED = true;" in body


def test_refresh_buttons_force_a_fresh_scan():
    assert UI.count("loadBurners(true)") == 2, "Neu-suchen-Knoepfe erzwingen nicht"


def test_no_periodic_background_drive_detection():
    """Ein Timer auf die Erkennung waere genau das, was vermieden werden soll."""
    for timer in re.findall(r"set(?:Interval|Timeout)\((.*?),", UI):
        if "loadBurners" in timer:
            assert "setInterval" not in UI[max(0, UI.index(timer) - 12):UI.index(timer)], \
                "periodische Laufwerkserkennung gefunden"
    assert "setInterval(loadBurners" not in UI
    assert "setInterval(() => loadBurners" not in UI
