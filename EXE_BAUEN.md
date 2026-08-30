# RetroDisc — EXE Bauen (Schritt für Schritt)

## Was entsteht

Eine **einzige Datei**: `dist\RetroDisc.exe` (~30–40 MB)

- Kein Installer nötig
- Kein Ordner daneben
- Läuft auf Windows 10/11 (64-bit)
- Beim ersten Start: FFmpeg + yt-dlp werden automatisch geladen (~100 MB)

---

## Voraussetzungen

### 1. Python 3.11 oder neuer
Download: https://www.python.org/downloads/windows/

**Wichtig beim Installieren:** ✅ "Add Python to PATH" ankreuzen!

### 2. Microsoft WebView2 Runtime
Ist auf Windows 11 bereits vorinstalliert.

Für Windows 10: https://developer.microsoft.com/microsoft-edge/webview2/

---

## EXE bauen — 2 Wege

### Weg A: Einfach (Doppelklick)

1. `BUILD_EXE.bat` doppelklicken
2. Warten (2–5 Minuten)
3. Fertig → `dist\RetroDisc.exe`

### Weg B: Manuell (Kommandozeile)

```cmd
# 1. Abhängigkeiten installieren
pip install pyinstaller pywebview pydantic structlog rich click httpx yt-dlp sounddevice soundfile

# 2. EXE bauen
pyinstaller retrodisc_onefile.spec --clean --noconfirm

# 3. Fertig
dist\RetroDisc.exe
```

---

## Was passiert beim ersten Start

1. **Splash-Screen** erscheint mit springendem Schaf 🐑
2. **FFmpeg wird geprüft** — falls nicht vorhanden:
   - Download von GitHub (~85 MB ZIP)
   - Wird in `%LOCALAPPDATA%\RetroDisc\tools\` gespeichert
3. **yt-dlp wird geprüft** — falls nicht vorhanden:
   - Download von GitHub (~25 MB)
4. **Haupt-UI öffnet sich** im CloneCD-Stil

Beim zweiten Start ist alles sofort da.

---

## Datei-Struktur nach dem Build

```
dist\
└── RetroDisc.exe          ← Die einzige Datei (alles drin!)

%LOCALAPPDATA%\RetroDisc\  ← App-Daten (nach erstem Start)
├── tools\
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   └── yt-dlp.exe
├── logs\
│   └── retrodisc.log
└── settings.json
```

---

## Größe der EXE

| Inhalt | Größe |
|--------|-------|
| Python Runtime | ~8 MB |
| RetroDisc Code + UI | ~2 MB |
| yt-dlp Library | ~10 MB |
| PyWebView + httpx | ~5 MB |
| pydantic + structlog | ~3 MB |
| **Gesamt (komprimiert)** | **~28–35 MB** |

FFmpeg (~85 MB) ist **nicht** in der EXE — wird beim ersten Start geladen.
Das hält die EXE klein.

---

## Bekannte Einschränkungen

**Erster Start dauert länger** (~30 Sek.) weil PyInstaller alles in `%TEMP%` entpackt.
Ab dem zweiten Start ist es gecacht → schneller.

**Antivirus** kann die EXE blockieren (falscher Alarm bei PyInstaller-Builds).
Lösung: EXE in Antivirus-Ausnahmen eintragen, oder Code-Signierung mit einem Zertifikat.

**Windows Defender SmartScreen** zeigt beim ersten Start eine Warnung.
→ "Weitere Informationen" → "Trotzdem ausführen"

---

## Troubleshooting

**"Python nicht gefunden"**
→ Python neu installieren, ✅ "Add to PATH" ankreuzen

**"WebView2 nicht gefunden"**
→ https://developer.microsoft.com/microsoft-edge/webview2/ installieren

**Blank/weißes Fenster**
→ WebView2 aktualisieren, oder `RETRODISC_DEBUG=1 RetroDisc.exe` starten

**FFmpeg-Download schlägt fehl**
→ FFmpeg manuell von https://ffmpeg.org/ laden und in `%LOCALAPPDATA%\RetroDisc\tools\` legen

**Log-Datei** für Fehlersuche: `%LOCALAPPDATA%\RetroDisc\logs\retrodisc.log`
