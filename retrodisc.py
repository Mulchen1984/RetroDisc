"""
RetroDisc — Windows Desktop App Entry Point
============================================
Diese Datei wird von PyInstaller zur retrodisc.exe kompiliert.
Sie startet die PyWebView-Fenster-App mit dem Python-Backend.
"""

import sys
import os
import logging
from pathlib import Path

# ── Pfad-Setup für PyInstaller (frozen bundle) ────────────────────────
if getattr(sys, "frozen", False):
    # Läuft als EXE (PyInstaller)
    BASE_DIR = Path(sys.executable).parent
    BUNDLE_DIR = Path(sys._MEIPASS)
    # Src-Module aus dem Bundle laden
    sys.path.insert(0, str(BUNDLE_DIR))
    # Tools liegen neben der EXE
    TOOLS_DIR = BASE_DIR / "tools"
    os.environ["RETRODISC_TOOLS"] = str(TOOLS_DIR)
    os.environ["RETRODISC_FROZEN"] = "1"
else:
    # Läuft als Python-Skript (Entwicklung)
    BASE_DIR = Path(__file__).parent
    BUNDLE_DIR = BASE_DIR
    TOOLS_DIR = BASE_DIR / "tools"

# ── Logging konfigurieren ────────────────────────────────────────────
log_dir = BASE_DIR / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "retrodisc.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("retrodisc")


def check_and_download_tools():
    """
    Prüft ob externe Tools vorhanden sind.
    Falls nicht → Zeigt Download-Dialog und lädt nach.
    """
    from src.bootstrap import ToolBootstrap
    bootstrap = ToolBootstrap(tools_dir=TOOLS_DIR)
    missing = bootstrap.check_missing()

    if missing:
        log.info(f"Fehlende Tools: {missing}")
        # Im Windows-Modus: Splash-Screen mit Download-Fortschritt
        bootstrap.download_missing_sync(missing)

    return bootstrap.get_tool_paths()


def main():
    """Startet die RetroDisc Desktop-App."""
    log.info("RetroDisc wird gestartet...")
    log.info(f"BASE_DIR: {BASE_DIR}")
    log.info(f"Frozen: {getattr(sys, 'frozen', False)}")

    try:
        import webview
    except ImportError:
        # Fallback: Einfach die HTML-Datei im Standard-Browser öffnen
        log.warning("PyWebView nicht verfügbar — öffne im Browser")
        import webbrowser
        html_path = BUNDLE_DIR / "src" / "ui" / "app.html"
        webbrowser.open(f"file:///{html_path}")
        input("RetroDisc läuft im Browser. Enter zum Beenden...")
        return

    # Tool-Pfade ermitteln / herunterladen
    try:
        tool_paths = check_and_download_tools()
        log.info(f"Tools bereit: {list(tool_paths.keys())}")
    except Exception as e:
        log.warning(f"Tool-Check fehlgeschlagen: {e} — fahre trotzdem fort")
        tool_paths = {}

    # Settings laden / erstellen
    from src.config.settings import AppSettings
    from src.config.settings import ToolPaths

    settings = AppSettings.load()

    # Tool-Pfade aus dem Bundle eintragen (falls vorhanden)
    if "ffmpeg" in tool_paths:
        settings.tools.ffmpeg = str(tool_paths["ffmpeg"])
        settings.tools.ffprobe = str(tool_paths.get("ffprobe", "ffprobe"))
    if "ytdlp" in tool_paths:
        settings.tools.ytdlp = str(tool_paths["ytdlp"])

    settings.ensure_directories()
    settings.save()

    # UI-Datei
    ui_html = BUNDLE_DIR / "src" / "ui" / "app.html"
    if not ui_html.exists():
        log.error(f"UI-Datei nicht gefunden: {ui_html}")
        sys.exit(1)

    # Desktop-App starten
    log.info("Starte Desktop-Fenster...")
    from src.ui.desktop import RetroDiscAPI

    api = RetroDiscAPI()

    window = webview.create_window(
        title="RetroDisc 1.0 — All-in-One Media Suite",
        url=str(ui_html),
        js_api=api,
        width=1280,
        height=820,
        min_size=(960, 640),
        background_color="#d4d0c8",
        text_select=False,
        confirm_close=False,
    )

    api.window = window

    # Callbacks registrieren
    window.events.loaded += lambda: log.info("UI geladen")
    window.events.closed += lambda: log.info("Fenster geschlossen")

    debug_mode = os.environ.get("RETRODISC_DEBUG", "0") == "1"

    webview.start(
        debug=debug_mode,
        http_server=True,
        http_port=0,  # Zufälliger freier Port
    )

    log.info("RetroDisc beendet.")


if __name__ == "__main__":
    main()
