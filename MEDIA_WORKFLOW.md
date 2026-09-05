# RetroDisc media workflow

RetroDisc must make it obvious where every generated file is stored and how one step feeds the next.

## Single visible media folder

All user-facing media produced by RetroDisc belongs in one visible folder:

```text
~/Videos/RetroDisc/
```

On Windows this is typically:

```text
C:\Users\<user>\Videos\RetroDisc\
```

The central rule is deliberately simple:

> Downloaded, ripped, converted, edited, DVD-ready and ISO output files must be easy to find in the same RetroDisc media location.

Only transient working files belong in:

```text
~/Videos/RetroDisc/_temp/
```

## Why this is required

The previous workflow was confusing because different operations used different destinations. A user could download a file and then fail to find it for conversion; after conversion the resulting file could again be hard to locate for DVD creation or burning.

RetroDisc is intended to be a workflow, not a collection of unrelated tools. A normal sequence must therefore work without manual file hunting:

```text
Download
   ↓
Convert
   ↓
Edit if needed
   ↓
Create DVD / ISO
   ↓
Burn
```

The result from one step must be immediately usable as the input of the next step.

## Default routing

Unless the user explicitly chooses another output path, all user-visible results go to:

```text
~/Videos/RetroDisc/
```

That includes:

| Action | Default destination |
|---|---|
| Internet / Mediathek download | `~/Videos/RetroDisc/` |
| Disc rip | `~/Videos/RetroDisc/` |
| Format conversion | `~/Videos/RetroDisc/` |
| Trim | `~/Videos/RetroDisc/` |
| Merge | `~/Videos/RetroDisc/` |
| Upscale | `~/Videos/RetroDisc/` |
| Frame interpolation | `~/Videos/RetroDisc/` |
| Subtitle generation | `~/Videos/RetroDisc/` |
| Highlights / Smart Edit | `~/Videos/RetroDisc/` |
| DVD authoring | `~/Videos/RetroDisc/` |
| ISO creation | `~/Videos/RetroDisc/` |
| Preview / temporary work | `~/Videos/RetroDisc/_temp/` |

## Behavioral rules

1. RetroDisc must have one obvious default media location: `~/Videos/RetroDisc`.
2. RetroDisc must not scatter normal workflow results between `Downloads`, the application directory and arbitrary source-file directories.
3. The output of a completed step must remain available for the next step without another search through the filesystem.
4. Originals are never overwritten unless the user explicitly selected overwrite behavior.
5. An explicit user-selected output path may override the default location.
6. After each successful job the backend must report the real final `output_path`.
7. The UI must show the final path and provide an **Ordner öffnen** action.
8. The UI should provide **Weiterverarbeiten** so the produced file can immediately be selected for conversion, editing or DVD/burn workflows.
9. Temporary files and previews stay in `_temp`; `_temp` is not part of the user's media library.
10. Historical RetroDisc default paths should be migrated automatically to the single media folder. Arbitrary custom user paths must not be silently destroyed.

## Required user experience

Example download result:

```text
Fertig
Gespeichert unter:
C:\Users\<user>\Videos\RetroDisc\Mein Film.mp4

[Ordner öffnen] [Konvertieren] [Bearbeiten] [DVD erstellen]
```

Example conversion result:

```text
Fertig
Gespeichert unter:
C:\Users\<user>\Videos\RetroDisc\Mein Film_mp4_h264_1080p.mp4

[Ordner öffnen] [Weiterverarbeiten] [DVD erstellen]
```

The user must not need to remember whether a file came from `Downloads`, `Output`, an application data directory or the original source directory.

## Compatibility / migration

Historical defaults that RetroDisc itself created should be collapsed into the single root, including:

```text
~/Downloads/RetroDisc
~/Videos/RetroDisc/01_Quellen/Downloads
~/Videos/RetroDisc/01_Quellen/Rips
~/Videos/RetroDisc/02_Konvertiert
~/Videos/RetroDisc/03_Bearbeitet
~/Videos/RetroDisc/04_Disc
```

They all migrate to:

```text
~/Videos/RetroDisc
```

Arbitrary custom paths are not considered historical defaults and are preserved.

## Regression requirements

Tests must prove that, with default settings:

- `media_root` is `~/Videos/RetroDisc`;
- download, rip, conversion, edit and disc destinations all resolve to the same media root;
- `_temp` remains a separate internal subdirectory;
- legacy RetroDisc default paths migrate into the common root;
- arbitrary custom user paths are preserved;
- source files are not modified merely because RetroDisc chooses a default destination.

## Release gate

The workflow change is complete only when source tests, packaged acceptance and a real packaged-app smoke test confirm this sequence:

1. download a media file;
2. find it immediately in `Videos/RetroDisc`;
3. convert it;
4. find the converted result immediately in the same folder;
5. select that result for DVD/ISO creation or burning without manually searching another directory;
6. verify that the completion path displayed by RetroDisc points to the file that actually exists on disk.
