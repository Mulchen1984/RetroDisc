# RetroDisc media workflow

RetroDisc must make it obvious where every generated file is stored and how one step feeds the next.

## Single visible root

All user-facing media produced by RetroDisc belongs under one root directory:

```text
~/Videos/RetroDisc/
```

Default layout:

```text
RetroDisc/
├── 01_Quellen/
│   ├── Downloads/
│   └── Rips/
├── 02_Konvertiert/
├── 03_Bearbeitet/
│   ├── Geschnitten/
│   ├── Zusammengefuegt/
│   ├── Hochskaliert/
│   ├── Framerate/
│   ├── Untertitel/
│   └── Highlights/
├── 04_Disc/
│   ├── DVD/
│   └── ISO/
└── _temp/
```

`_temp` is internal. Everything else is deliberately user-visible and suitable for further processing.

## Required routing

| Action | Default destination |
|---|---|
| Internet / Mediathek download | `01_Quellen/Downloads` |
| Disc rip | `01_Quellen/Rips` |
| Format conversion | `02_Konvertiert` |
| Trim | `03_Bearbeitet/Geschnitten` |
| Merge | `03_Bearbeitet/Zusammengefuegt` |
| Upscale | `03_Bearbeitet/Hochskaliert` |
| Frame interpolation | `03_Bearbeitet/Framerate` |
| Subtitle generation | `03_Bearbeitet/Untertitel` |
| Highlights / Smart Edit | `03_Bearbeitet/Highlights` |
| DVD authoring | `04_Disc/DVD` |
| ISO creation | `04_Disc/ISO` |
| Preview / transient work | `_temp` |

## Behavioral rules

1. RetroDisc must not silently write results next to an arbitrary source file.
2. An explicit user-selected output path always wins over the default routing.
3. Originals are never overwritten unless the user explicitly selected overwrite behavior.
4. After each successful job the backend must report the real final `output_path`.
5. The UI must show the final path and provide an **Ordner öffnen** action.
6. The finished output should be reusable directly as the input of the next workflow step; the user should not have to search for it again.
7. The portable build must follow the same user-media workflow. Portable tool/cache/log storage may stay beside the executable, but user media must not disappear into `RetroDisc_Data/Downloads` or `RetroDisc_Data/Output` by default.
8. Existing custom paths must be preserved. Only historical RetroDisc default paths may be migrated automatically.

## UI target

Instead of presenting unrelated Download and Output directories as the main concept, settings should present one primary media location:

```text
RetroDisc-Medienordner: C:\Users\<user>\Videos\RetroDisc
```

The numbered workflow folders are managed by RetroDisc.

On completion the UI should expose something equivalent to:

```text
Fertig
Gespeichert unter:
C:\Users\<user>\Videos\RetroDisc\03_Bearbeitet\Hochskaliert\film_2x.mp4

[Ordner öffnen] [Weiterverarbeiten]
```

`Weiterverarbeiten` should add/select the produced file for the next tool instead of forcing a new file-dialog round trip.

## Regression requirements

Add tests proving that, without explicit output paths:

- downloads and rips are under `~/Videos/RetroDisc/01_Quellen/...`;
- conversions are under `02_Konvertiert`;
- trim/merge/upscale/interpolation/subtitles/highlights are routed to their respective `03_Bearbeitet` folders even when the source is outside RetroDisc;
- DVD/ISO results are routed to `04_Disc`;
- preview files remain in `_temp`;
- custom output paths still win;
- legacy default settings migrate, but arbitrary custom user paths do not;
- source files are never modified as a side effect of choosing a default destination.

## Release gate

The workflow change is complete only when source tests, packaged acceptance, and a real packaged-app smoke test confirm that the displayed completion path matches the file that actually exists on disk.
