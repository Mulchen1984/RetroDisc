# RetroDisc — All-in-One Media Suite

RetroDisc ist eine portable Windows-/macOS-Media-App zum Konvertieren, Downloaden, Brennen und Bearbeiten von Medien.

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

## GitHub Actions

Nach einem Push zu GitHub baut `.github/workflows/build.yml` Windows- und macOS-Artefakte automatisch.
