# RetroDisc — All-in-One Media Suite

RetroDisc ist eine portable **Windows**-Media-App zum Konvertieren, Downloaden,
Brennen und Bearbeiten von Medien.

> **Plattform:** RetroDisc wird ausschließlich für Windows gebaut, getestet und
> ausgeliefert. `build.py`, `prepare_vendor.py` und die CI erzeugen nur
> Windows-Artefakte. Im Repository liegen noch macOS-Reste (`BUILD_MACOS.sh`,
> `create_dmg.py`, `retrodisc.spec`, `FUER_QWEN.md`); sie sind an keinem Gate
> belegt und werden nicht unterstützt.

## Windows 11 bauen

Erzeugt beide gewünschten Windows-Artefakte:

- Portable App: `dist\RetroDisc.exe`
- Portable ZIP: `Output\RetroDisc_1.0.0_Portable.zip`
- Installer: `Output\RetroDisc_Setup_1.0.0.exe`

### Einfacher Weg

Doppelklick auf:

```bat
BUILD_WINDOWS_ALL.bat
```

### Terminal

```bat
python build.py --install-deps --skip-tests
```

Der Build lädt/packt FFmpeg und FFprobe über `prepare_vendor.py`, sodass die portable EXE beim Nutzer ohne separaten FFmpeg-Download laufen kann.

## Installer

Der Standard-Build erzeugt einen einfachen Windows-Installer als EXE ohne externe Build-Abhängigkeit wie Inno Setup:

```text
Output\RetroDisc_Setup_1.0.0.exe
```

Der Installer installiert standardmäßig nach:

```text
%LOCALAPPDATA%\Programs\RetroDisc
```

und erstellt Startmenü-/Desktop-Verknüpfungen.

Optional liegt weiterhin ein Inno-Setup-Script unter `installer\retrodisc_setup.iss`, falls ein klassischer Inno-Installer gewünscht ist.

## Code-Signierung (Smart App Control)

Windows Smart App Control (SAC) blockiert unsignierte Builds. Gemessen auf dem
Entwicklungsrechner betrifft das insbesondere `RetroDisc_Setup_1.0.0.exe`; die
Blockade erscheint im Ereignisprotokoll unter
`Microsoft-Windows-CodeIntegrity/Operational` als Event 3033 und 3077.

Ein **selbst ausgestelltes Zertifikat löst das nicht.** SAC prüft nicht den
lokalen Zertifikatspeicher, sondern die eigene Richtlinie und Microsofts
Reputationsdienst. Erforderlich ist ein öffentlich vertrauenswürdiges
Code-Signing-Zertifikat; ein **EV-Zertifikat** erhält die nötige Reputation
sofort, ein frisches OV-Zertifikat muss sie erst aufbauen.

Zertifikat hinterlegen — entweder aus dem Windows-Zertifikatspeicher:

```bat
set RETRODISC_SIGN_THUMBPRINT=A1B2C3D4E5F6...
```

oder als PFX-Datei:

```bat
set RETRODISC_SIGN_PFX=C:\pfad\zertifikat.pfx
set RETRODISC_SIGN_PASSWORD=...
```

Optional ein abweichender Zeitstempelserver über `RETRODISC_SIGN_TIMESTAMP_URL`
(Vorgabe: `http://timestamp.digicert.com`). Der Zeitstempel sorgt dafür, dass
die Signatur nach Ablauf des Zertifikats gültig bleibt.

Dann signierend bauen:

```bat
python build.py --clean --sign
```

`--sign` bricht ab, wenn kein Zertifikat konfiguriert ist — ein unbemerkt
unsigniertes Release ist damit ausgeschlossen. Signiert wird zuerst
`dist\RetroDisc.exe` und erst danach verpackt, damit Portable-ZIP und Installer
die signierte EXE enthalten; die Setup-EXE wird anschließend selbst signiert.
Das Zertifikatspasswort wird ausschließlich über die Prozessumgebung übergeben
und landet weder in einer Datei noch in einer Kommandozeile.

Ohne `--sign` läuft der Build weiterhin durch, weist am Ende aber ausdrücklich
darauf hin, dass die Artefakte unsigniert sind.

## GitHub Actions

Nach einem Push zu GitHub baut `.github/workflows/build.yml` die
Windows-Artefakte automatisch: portable EXE, Portable-ZIP und Installer über
`python build.py --clean`. Vor dem Bauen laufen dieselben Source-Gates wie
lokal. Ein Push auf ein Tag `v*.*.*` erzeugt zusätzlich ein Release und
verlangt dafür zwingend die Signaturgeheimnisse
`RETRODISC_SIGN_PFX_BASE64` und `RETRODISC_SIGN_PASSWORD` — ohne sie bricht der
Tag-Build ab, damit kein unsigniertes Release entsteht.

macOS-Artefakte werden nicht gebaut.
