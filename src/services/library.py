"""RetroDisc Media Library — Mediathek-Verwaltung mit Thumbnail-Generierung.

Scannt Ordner, analysiert alle Mediendateien, generiert Thumbnails
und verwaltet die Mediathek als SQLite-Datenbank.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import structlog
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.ffmpeg import FFmpeg
from src.models.media import MediaFile, MediaType

log = structlog.get_logger()


class MediaLibrary:
    """
    Lokale Mediathek mit SQLite-Datenbank und Thumbnail-Cache.

    Scannt Ordner automatisch, analysiert alle Mediendateien
    und stellt sie mit Metadaten und Thumbnails bereit.

    Beispiel:
        lib = MediaLibrary(db_path="retrodisc.db")
        await lib.scan_folder("/home/marco/Videos")
        files = await lib.search("Tatort")
        # → Liste von MediaFile-Objekten
    """

    VIDEO_EXTS = {
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
        ".webm", ".mpg", ".mpeg", ".vob", ".ts", ".m4v",
        ".3gp", ".ogv", ".divx",
    }
    AUDIO_EXTS = {
        ".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a",
        ".wma", ".ac3", ".dts", ".opus", ".mka",
    }
    ALL_EXTS = VIDEO_EXTS | AUDIO_EXTS

    def __init__(
        self,
        db_path: Optional[Path] = None,
        thumb_dir: Optional[Path] = None,
        ffmpeg: Optional[FFmpeg] = None,
    ):
        self.db_path = db_path or Path.home() / ".retrodisc" / "library.db"
        self.thumb_dir = thumb_dir or self.db_path.parent / "thumbnails"
        self.ffmpeg = ffmpeg or FFmpeg()
        self._conn: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        """Öffnet die Datenbankverbindung und erstellt Schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._create_schema()
        log.info("Media Library geöffnet", db=str(self.db_path))

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def _create_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS media_files (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                path        TEXT UNIQUE NOT NULL,
                filename    TEXT NOT NULL,
                folder      TEXT NOT NULL,
                media_type  TEXT NOT NULL,
                container   TEXT,
                duration    REAL,
                file_size   INTEGER,
                width       INTEGER,
                height      INTEGER,
                fps         REAL,
                video_codec TEXT,
                audio_codec TEXT,
                channels    INTEGER,
                has_subs    INTEGER DEFAULT 0,
                title       TEXT,
                artist      TEXT,
                album       TEXT,
                thumb_path  TEXT,
                scanned_at  TEXT,
                modified_at TEXT
            );

            CREATE TABLE IF NOT EXISTS scan_folders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                path        TEXT UNIQUE NOT NULL,
                recursive   INTEGER DEFAULT 1,
                last_scan   TEXT,
                file_count  INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_media_folder ON media_files(folder);
            CREATE INDEX IF NOT EXISTS idx_media_type ON media_files(media_type);
            CREATE INDEX IF NOT EXISTS idx_media_title ON media_files(title);
            CREATE VIRTUAL TABLE IF NOT EXISTS media_fts
                USING fts5(path, filename, title, artist, album,
                           content=media_files, content_rowid=id);
        """)
        self._conn.commit()

    # ─── Scanning ────────────────────────────────────────────────────

    async def scan_folder(
        self,
        folder: Path | str,
        recursive: bool = True,
        generate_thumbs: bool = True,
        on_progress: Optional[callable] = None,
    ) -> int:
        """
        Scannt einen Ordner und fügt alle Mediendateien zur Bibliothek hinzu.

        Args:
            folder: Zu scannender Ordner
            recursive: Unterordner einschließen
            generate_thumbs: Thumbnails für Videos erstellen
            on_progress: Callback(current, total, filename)

        Returns:
            Anzahl neu hinzugefügter Dateien
        """
        folder = Path(folder)
        if not folder.exists():
            raise FileNotFoundError(f"Ordner nicht gefunden: {folder}")

        pattern = "**/*" if recursive else "*"
        all_files = [
            f for f in folder.glob(pattern)
            if f.is_file() and f.suffix.lower() in self.ALL_EXTS
        ]

        log.info("Scan gestartet", folder=str(folder), files=len(all_files))

        # Scan-Folder registrieren
        self._conn.execute("""
            INSERT OR REPLACE INTO scan_folders(path, recursive, last_scan, file_count)
            VALUES (?, ?, ?, ?)
        """, (str(folder), int(recursive), datetime.now().isoformat(), len(all_files)))

        added = 0
        for i, file_path in enumerate(all_files):
            if on_progress:
                on_progress(i + 1, len(all_files), file_path.name)

            try:
                was_added = await self._add_file(
                    file_path, generate_thumb=generate_thumbs
                )
                if was_added:
                    added += 1
            except Exception as e:
                log.warning("Datei konnte nicht analysiert werden",
                            file=file_path.name, error=str(e))

        self._conn.commit()
        log.info("Scan abgeschlossen", added=added, total=len(all_files))
        return added

    async def _add_file(self, path: Path, generate_thumb: bool = True) -> bool:
        """Fügt eine einzelne Datei zur Bibliothek hinzu."""
        mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()

        # Bereits vorhanden und unverändert?
        existing = self._conn.execute(
            "SELECT modified_at FROM media_files WHERE path = ?", (str(path),)
        ).fetchone()

        if existing and existing["modified_at"] == mtime:
            return False

        # Analyse mit FFprobe
        media = await self.ffmpeg.probe(path)

        # Thumbnail generieren
        thumb_path = None
        if generate_thumb and media.media_type == MediaType.VIDEO:
            thumb_path = await self._gen_thumb(path, media.duration_seconds)

        # In DB speichern
        v = media.video_streams[0] if media.video_streams else None
        a = media.audio_streams[0] if media.audio_streams else None

        self._conn.execute("""
            INSERT OR REPLACE INTO media_files
                (path, filename, folder, media_type, container, duration,
                 file_size, width, height, fps, video_codec, audio_codec,
                 channels, has_subs, title, artist, album, thumb_path,
                 scanned_at, modified_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            str(path), path.name, str(path.parent),
            media.media_type.value, media.container,
            media.duration_seconds, media.file_size_bytes,
            v.width if v else None, v.height if v else None,
            v.fps if v else None,
            v.codec if v else None,
            a.codec if a else None,
            a.channels if a else None,
            int(len(media.subtitle_streams) > 0),
            media.title, media.artist, media.album,
            str(thumb_path) if thumb_path else None,
            datetime.now().isoformat(), mtime,
        ))

        # FTS Index aktualisieren
        row_id = self._conn.execute(
            "SELECT id FROM media_files WHERE path = ?", (str(path),)
        ).fetchone()["id"]
        self._conn.execute(
            "INSERT OR REPLACE INTO media_fts(rowid, path, filename, title, artist, album) VALUES (?,?,?,?,?,?)",
            (row_id, str(path), path.name,
             media.title or "", media.artist or "", media.album or "")
        )

        return True

    async def _gen_thumb(self, path: Path, duration: float) -> Optional[Path]:
        """Generiert ein Thumbnail für ein Video."""
        safe_name = path.stem[:60].replace("/", "_").replace("\\", "_")
        thumb_path = self.thumb_dir / f"{safe_name}_{hash(str(path)) & 0xFFFFFF:06x}.jpg"

        if thumb_path.exists():
            return thumb_path

        try:
            # Thumbnail bei 15% der Gesamtdauer (nicht ganz am Anfang)
            t = max(2.0, duration * 0.15)
            await self.ffmpeg.generate_thumbnail(
                input_path=path,
                output_path=thumb_path,
                time_seconds=t,
                width=240,
            )
            return thumb_path
        except Exception as e:
            log.debug("Thumbnail-Fehler", file=path.name, error=str(e))
            return None

    # ─── Querying ────────────────────────────────────────────────────

    def get_all(
        self,
        media_type: Optional[str] = None,
        folder: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
        order_by: str = "filename",
    ) -> list[dict]:
        """Gibt alle Medien zurück, optional gefiltert."""
        where_clauses = []
        params = []

        if media_type:
            where_clauses.append("media_type = ?")
            params.append(media_type)
        if folder:
            where_clauses.append("folder LIKE ?")
            params.append(f"{folder}%")

        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        order = order_by if order_by in ("filename", "duration", "file_size", "scanned_at") else "filename"

        rows = self._conn.execute(f"""
            SELECT * FROM media_files
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()

        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Volltextsuche in Dateinamen, Titeln, Artists."""
        rows = self._conn.execute("""
            SELECT m.* FROM media_files m
            JOIN media_fts f ON m.id = f.rowid
            WHERE media_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query + "*", limit)).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Gibt Statistiken über die Bibliothek zurück."""
        row = self._conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN media_type='video' THEN 1 ELSE 0 END) as videos,
                SUM(CASE WHEN media_type='audio' THEN 1 ELSE 0 END) as audio,
                SUM(file_size) as total_size,
                SUM(duration) as total_duration
            FROM media_files
        """).fetchone()
        return dict(row)

    def get_by_path(self, path: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM media_files WHERE path = ?", (path,)
        ).fetchone()
        return dict(row) if row else None

    def remove_missing(self) -> int:
        """Entfernt Einträge für nicht mehr vorhandene Dateien."""
        all_paths = self._conn.execute("SELECT id, path FROM media_files").fetchall()
        removed = 0
        for row in all_paths:
            if not Path(row["path"]).exists():
                self._conn.execute("DELETE FROM media_files WHERE id = ?", (row["id"],))
                removed += 1
        self._conn.commit()
        log.info("Fehlende Dateien bereinigt", removed=removed)
        return removed

    def get_scan_folders(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM scan_folders ORDER BY path").fetchall()
        return [dict(r) for r in rows]
