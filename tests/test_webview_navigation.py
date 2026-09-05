"""Die WebView-History darf niemals RetroDiscs Navigation sein.

RetroDisc ist eine Desktop-Anwendung. Die seitlichen Maustasten loesen in
Chromium - und damit in WebView2 - Vor-/Zurueck-Navigation aus. Weil der
Splash ueber ``load_html`` ersetzt wird, existiert ein History-Eintrag:
Maus-Zurueck landet auf dem Splash-Dokument, in dem die Anwendung nicht mehr
existiert und der Nutzer festsitzt.

Abgesichert wird das auf zwei Ebenen, die hier beide geprueft werden:

* ``retrodisc_launcher.block_webview_history_navigation`` haengt sich an den
  WebView2-Hook ``NavigationStarting`` und bricht ``BackOrForward`` ab.
* ``src/ui/app.html`` faengt die Maustasten 3 und 4 ab und mappt Zurueck auf
  den eigenen Handler.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import retrodisc_launcher as launcher

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "src" / "ui" / "app.html").read_text(encoding="utf-8")


# ── Ebene 1: der WebView2-Hook ────────────────────────────────────────────


class _Args:
    def __init__(self, kind: str) -> None:
        self.NavigationKind = kind
        self.Cancel = False


class _Control:
    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):  # pragma: no cover - nicht benutzt
        raise AssertionError("Das Control selbst ist kein Event")


class _NavigationEvent:
    """Minimales Gegenstueck zu einem .NET-Event."""

    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _Form:
    def __init__(self) -> None:
        self.webview = type("W", (), {"NavigationStarting": _NavigationEvent()})()


@pytest.fixture
def attached(monkeypatch):
    """Haengt den Riegel an ein gefaelschtes WebView2-Control."""
    form = _Form()

    class _BrowserView:
        instances = {"win-1": form}

    module = type("winforms", (), {"BrowserView": _BrowserView})
    monkeypatch.setitem(
        __import__("sys").modules, "webview.platforms.winforms", module
    )
    window = type("Win", (), {"uid": "win-1"})()
    assert launcher.block_webview_history_navigation(window) is True
    handlers = form.webview.NavigationStarting.handlers
    assert len(handlers) == 1
    return handlers[0]


def test_back_and_forward_navigation_is_cancelled(attached):
    args = _Args("BackOrForward")
    attached(None, args)
    assert args.Cancel is True


def test_the_apps_own_document_load_is_not_cancelled(attached):
    """load_html ist NewDocument - der Splash-Uebergang muss weiter laufen."""
    for kind in ("NewDocument", "Reload"):
        args = _Args(kind)
        attached(None, args)
        assert args.Cancel is False, f"{kind} darf nicht abgebrochen werden"


def test_an_sdk_without_navigationkind_does_not_break_navigation(attached):
    """Fehlt die Eigenschaft, wird erlaubt statt blockiert."""
    args = type("A", (), {"Cancel": False})()
    attached(None, args)
    assert args.Cancel is False


def test_missing_backend_degrades_to_false_instead_of_raising(monkeypatch):
    """Auf macOS oder einem anderen Backend darf nichts abstuerzen."""
    import builtins

    real_import = builtins.__import__

    def _no_winforms(name, *args, **kwargs):
        if "winforms" in name:
            raise ImportError("kein Windows-Backend")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_winforms)
    window = type("Win", (), {"uid": "win-1"})()
    assert launcher.block_webview_history_navigation(window) is False


def test_the_guard_is_installed_before_the_window_starts():
    source = (ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")
    assert "block_webview_history_navigation(window)" in source
    assert source.index("block_webview_history_navigation(window)") < source.index(
        "webview.start(debug=debug)"
    )


# ── Ebene 2: die Maustasten in der UI ─────────────────────────────────────


def test_side_mouse_buttons_are_intercepted():
    for event in ("mousedown", "mouseup", "auxclick"):
        assert f"addEventListener('{event}'" in UI, f"{event} nicht behandelt"
    assert "MOUSE_BACK = 3" in UI and "MOUSE_FORWARD = 4" in UI
    # Capture-Phase: ein spaeteres preventDefault kaeme fuer die Navigation
    # zu spaet.
    assert UI.count("}, true);") >= 3


def test_normal_mouse_buttons_are_never_blocked():
    """Nur 3 und 4. Links, rechts und Mitte bleiben unangetastet."""
    match = re.search(
        r"function isSideButton\(e\)\{(.+?)\}", UI, re.S
    )
    assert match, "isSideButton fehlt"
    body = match.group(1)
    assert "MOUSE_BACK" in body and "MOUSE_FORWARD" in body
    for blocked in ("e.button === 0", "e.button === 1", "e.button === 2"):
        assert blocked not in UI, f"{blocked} darf nicht abgefangen werden"


def test_the_back_button_maps_to_the_apps_own_handler():
    assert "function appBack()" in UI
    match = re.search(r"function appBack\(\)\{(.+?)\n\}", UI, re.S)
    assert match and "goHome()" in match.group(1)
    # Der vorhandene interne Zurueck-Knopf bleibt unveraendert.
    assert 'class="back" onclick="goHome()"' in UI


def test_the_ui_never_navigates_through_the_webview_history():
    """Die App-Navigation laeuft ueber showTab/openFlow, nie ueber History.

    Genau das ist der Kern: die WebView-History gehoert der Anwendung nicht.
    Ein History-basierter Zurueck-Weg wuerde beim Splash-Dokument landen.
    """
    # Nur echter Code zaehlt. Ein Kommentar, der erklaert, warum history.back()
    # hier NICHT benutzt wird, darf den Test nicht ausloesen.
    code = re.sub(r"/\*.*?\*/", "", UI, flags=re.S)
    code = "\n".join(
        line for line in code.splitlines() if not line.lstrip().startswith("//")
    )
    forbidden = (
        "history.back(",
        "history.forward(",
        "history.go(",
        "history.pushState(",
        "history.replaceState(",
        "window.history",
    )
    found = [needle for needle in forbidden if needle in code]
    assert found == [], f"History-Navigation in der UI: {found}"
