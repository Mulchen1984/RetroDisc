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
4. **Zuerst Windows abschliessen (Nutzerauftrag 2026-09-05).** macOS ist wieder
   als Ziel gewuenscht, wird aber erst nach dem Windows-Abschluss bearbeitet.
   Aktuell ist nur der Windows-Bauweg belegt. Die CI hat genau einen Buildjob
   (`build-windows`); der macOS-Job wurde am 2026-09-03 bewusst gestrichen.
   `BUILD_MACOS.sh`, `create_dmg.py` und `assets/retrodisc.icns` sind
   verbliebene macOS-Reste: an keinem Gate belegt, von keinem Buildpfad
   referenziert, nicht unterstützt. `retrodisc.spec` und
   `retrodisc_onefile.spec` sind dagegen ältere **Windows**-Specs, nicht
   macOS — produktiv ist allein `retrodisc_final.spec` über `build.py`.
5. **Smart App Control nie umgehen oder abschalten.** Ein Abschalten ist unter
   Windows nur durch eine Neuinstallation reversibel.
