# Runtime-Gate auf einem Zweitrechner

Auf dem Entwicklungsrechner ist Smart App Control erzwingend aktiv
(`VerifiedAndReputablePolicyState = 1`, Policy `{0283AC0F-FFF1-49AE-ADA1-8A933130CAD6}`).
Die unsignierte `RetroDisc.exe` wird dort ohne Prozessstart abgewiesen
(CodeIntegrity-Events 3033/3077). Der verpflichtende finale Runtime-Gate wird
deshalb auf einem zweiten Windows-Rechner **ohne** Smart App Control gefahren.

Smart App Control wird auf dem Entwicklungsrechner nicht abgeschaltet: Das ist
unter Windows eine Einbahnstraße und nur durch eine Neuinstallation reversibel.

## Vorbedingung auf dem Zweitrechner prüfen

```powershell
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' |
    Select-Object VerifiedAndReputablePolicyState
```

- `0` oder Wert fehlt → Smart App Control ist aus, der Gate ist fahrbar.
- `2` → Auswertungsmodus, blockiert nicht, Ergebnis bitte im Protokoll vermerken.
- `1` → auch dieser Rechner blockiert; er ist als Testziel ungeeignet.

Windows-Version und Build zusätzlich festhalten: `winver` bzw.
`Get-ComputerInfo | Select-Object OsName, OsVersion, OsBuildNumber`.

## Zu übertragende Dateien

Nur die Artefakte des freigegebenen Commits, keine Quellen:

- `Output/RetroDisc_1.0.0_Portable.zip`
- `Output/RetroDisc_Setup_1.0.0.exe`

Die zugehörigen SHA-256-Hashes stehen im Journal von
`RELEASE_AUDIT_STATUS.md` beim jeweiligen Build. Vor dem Test auf dem
Zweitrechner zwingend abgleichen:

```powershell
Get-FileHash .\RetroDisc_1.0.0_Portable.zip -Algorithm SHA256
Get-FileHash .\RetroDisc_Setup_1.0.0.exe   -Algorithm SHA256
```

Stimmt ein Hash nicht, ist der Test wertlos — Übertragung wiederholen.

## Gate 1 — Portable

1. ZIP entpacken, enthaltene `RetroDisc.exe` hashen und mit dem
   Journal-Hash der `dist`-EXE vergleichen (muss byteidentisch sein).
2. EXE starten. Erwartet: Trump-Startbild ca. 2–3 Sekunden, danach
   Hauptfenster mit Titel `RetroDisc 1.0`.
3. Prüfen, dass beim Start und während der Arbeit **kein** Konsolenfenster
   aufblitzt.
4. Fehlerkanal kontrollieren: Es darf kein Traceback erscheinen
   (früherer Splash-Race, siehe Journal 2026-08-31).

## Gate 2 — Reale Medien

Im laufenden Programm nacheinander:

1. Konvertierung einer echten Videodatei nach MP3 — Fortschritt läuft,
   Endzustand `done`, Ausgabedatei existiert und ist abspielbar.
2. Laufenden Job abbrechen — Endzustand `cancelled`, keine Restdatei.
3. YouTube-Download einer öffentlich verfügbaren URL.
4. **Brenner-Erkennung** — hier besonders genau hinsehen: Auf einem System
   mit deutschsprachigen Laufwerksnamen oder Umlauten in der
   PowerShell-Ausgabe war das die Stelle, die vor Commit `a9b5853` leer
   zurückkam. Erwartet: alle optischen Laufwerke mit Name und Buchstabe.
5. DVD-ISO erzeugen und, falls Rohling und Brenner vorhanden, einen
   echten Brennvorgang samt Rückleseprobe. Physische Brenn-/Rip-Tests sind
   hardware- und medienabhängig und werden separat ausgewiesen.

## Gate 3 — Installation und Deinstallation

1. `RetroDisc_Setup_1.0.0.exe` ausführen, in den Standardpfad installieren.
2. Installierte EXE hashen — muss byteidentisch zur `dist`-EXE sein.
3. Programm über die Verknüpfung starten, Hauptfenster prüfen.
4. Über den mitgelieferten Uninstaller deinstallieren. Erwartet:
   Exitcode 0, leere stderr-Ausgabe, Installationsordner nach wenigen
   Sekunden vollständig entfernt, Desktop- und Startmenüverknüpfung weg.

## Ergebnis eintragen

Ergebnisse mit Datum, Windows-Build, den geprüften Hashes und dem
SAC-Zustand des Testrechners als neuen Journalblock in
`RELEASE_AUDIT_STATUS.md` aufnehmen. Ein bestandener Gate auf dem
Zweitrechner belegt die Lauffähigkeit der Artefakte — er ersetzt **keine**
Code-Signatur. Für eine öffentliche Weitergabe an Dritte bleibt ein
vertrauenswürdiges Code-Signing-Zertifikat und ein Build mit
`python build.py --clean --sign` erforderlich.
