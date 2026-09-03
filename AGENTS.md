# AGENTS.md

Die Arbeitsanweisungen für dieses Repository stehen in **[CLAUDE.md](CLAUDE.md)**
und gelten unverändert für jeden Agenten.

Kurzfassung, damit nichts schiefgeht:

1. **Zuerst `RELEASE_AUDIT_STATUS.md` lesen.** Das ist das verbindliche Status-
   und Journaldokument. Arbeitsblöcke hinten anhängen, Status nur mit echten
   Belegen ändern, Aussagen über Artefakte immer an deren SHA-256 binden.
2. **Nicht `.venv\Scripts\python.exe` benutzen** — Smart App Control blockiert
   diese kopierte EXE. Stattdessen:
   `set PYTHONPATH=.venv\Lib\site-packages` und
   `C:\Users\marco\.local\bin\python3.11.exe ...`
3. **Bauen nur mit `python build.py --clean`** und nur aus einem eingefrorenen
   Commit. Die frühere, hier direkt eingetragene PyInstaller-Kommandozeile war
   veraltet und ist entfernt.
4. **RetroDisc ist ein Windows-Produkt.** macOS-Reste im Repository sind an
   keinem Gate belegt und nicht unterstützt.
5. **Smart App Control nie umgehen oder abschalten.** Ein Abschalten ist unter
   Windows nur durch eine Neuinstallation reversibel.
