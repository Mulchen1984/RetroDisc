"""Regression tests for literal, user-safe Media Library FTS queries."""

from pathlib import Path

from src.services.library import MediaLibrary


def _add_media(lib: MediaLibrary, *, path: str, title: str = "", artist: str = "") -> None:
    cursor = lib._conn.execute(
        """
        INSERT INTO media_files(path, filename, folder, media_type, title, artist)
        VALUES (?, ?, ?, 'video', ?, ?)
        """,
        (path, Path(path).name, str(Path(path).parent), title, artist),
    )
    lib._conn.execute(
        """
        INSERT INTO media_fts(rowid, path, filename, title, artist, album)
        VALUES (?, ?, ?, ?, ?, '')
        """,
        (cursor.lastrowid, path, Path(path).name, title, artist),
    )
    lib._conn.commit()


def test_search_handles_special_characters_without_fts_syntax_errors(tmp_path):
    lib = MediaLibrary(db_path=tmp_path / "library.db", thumb_dir=tmp_path / "thumbs")
    lib.open()
    try:
        _add_media(
            lib,
            path=str(tmp_path / "Rock & Roll (Live) 2024.mp4"),
            title='Rock & Roll: "Live"',
        )

        results = lib.search('Rock & Roll ("Live") 2024')
        assert [item["filename"] for item in results] == ["Rock & Roll (Live) 2024.mp4"]

        # These strings are invalid or meaningful FTS5 expressions when sent
        # to MATCH verbatim.  They must remain harmless user text.
        assert lib.search('" OR * ( NEAR') == []
        assert lib.search("*** !!!") == []
    finally:
        lib.close()


def test_search_preserves_literal_prefix_search_without_operator_semantics(tmp_path):
    lib = MediaLibrary(db_path=tmp_path / "library.db", thumb_dir=tmp_path / "thumbs")
    lib.open()
    try:
        _add_media(lib, path=str(tmp_path / "Urlaub.mp4"), title="Urlaub am Meer")
        _add_media(lib, path=str(tmp_path / "Winter.mp4"), title="Winter am Meer")

        assert [item["filename"] for item in lib.search("Urlau Meer")] == ["Urlaub.mp4"]
        # OR is searched as a literal word rather than widening the query.
        assert lib.search("Urlaub OR Winter") == []
    finally:
        lib.close()
