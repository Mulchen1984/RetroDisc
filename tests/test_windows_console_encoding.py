"""Regression: ein nicht darstellbarer Dateiname darf keinen Job scheitern lassen.

Am 2026-09-05 meldete ein manueller Acceptance-Test einen fertigen, korrekt
veroeffentlichten YouTube-Download (rund 273 MB) als FAILED. In der Statusleiste
stand ``'charmap' codec can't encode character ... : character maps to
<undefined>``.

Ursache: Windows gibt einem Prozess Standardstroeme mit der ANSI-Codepage
(cp1252). structlog war nicht konfiguriert und benutzte seine Default-
``PrintLoggerFactory``, die genau auf diesen Strom schreibt. Der Aufruf
``log.info("Download abgeschlossen", path=...)`` lag innerhalb des ``try`` von
``Downloader.download()``; ein Emoji im YouTube-Titel liess damit das blosse
Loggen des Dateinamens - und in der Folge den laengst fertigen Job - scheitern.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog

from src.core.downloader import Downloader
from src.utils.logging_setup import (
    configure_structlog,
    make_stream_utf8_safe,
    open_null_stream,
)

# Ein Zeichen, das cp1252 nicht darstellen kann - in YouTube-Titeln alltaeglich.
UNDARSTELLBAR = "\U0001F600"
UNICODE_NAME = f"Grosses Video {UNDARSTELLBAR} [abc123].mp4"


def cp1252_stream() -> io.TextIOWrapper:
    """Ein Strom, der sich exakt wie eine Windows-Konsole verhaelt."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


@pytest.fixture(autouse=True)
def _restore_structlog():
    yield
    structlog.reset_defaults()


class _FinishedProcess:
    def __init__(self, stdout: bytes = b"") -> None:
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(stdout)
        self.stdout.feed_eof()
        self.returncode = 0

    async def wait(self) -> int:
        return self.returncode


def _work_dir_from_cmd(cmd: tuple) -> Path:
    parts = [str(c) for c in cmd]
    return Path(parts[parts.index("-o") + 1]).parent


def test_cp1252_stream_really_rejects_the_character():
    """Negativkontrolle: ohne den Fix scheitert genau dieser Schreibvorgang.

    Ohne diese Zusicherung koennte der Regressionstest unten gruen sein, weil
    das Zeichen harmlos ist - statt weil der Fix wirkt.
    """
    with pytest.raises(UnicodeEncodeError):
        cp1252_stream().write(UNICODE_NAME)


def test_make_stream_utf8_safe_accepts_what_cp1252_cannot_encode():
    safe = make_stream_utf8_safe(cp1252_stream())
    safe.write(UNICODE_NAME)  # darf nicht werfen
    safe.flush()
    assert safe.encoding.lower().replace("_", "-") == "utf-8"
    assert safe.errors == "replace"


def test_make_stream_utf8_safe_tolerates_absent_streams():
    """PyInstaller-Windowed-Builds haben keine Standardstroeme."""
    assert make_stream_utf8_safe(None) is None


def test_structlog_bound_to_a_safe_stream_logs_the_name_without_raising():
    safe = make_stream_utf8_safe(cp1252_stream())
    configure_structlog(safe)
    structlog.get_logger().info("Download abgeschlossen", path=UNICODE_NAME)
    safe.flush()


def test_configure_structlog_falls_back_when_there_is_no_stream():
    """Ohne Konsole darf die Konfiguration nicht scheitern."""
    target = configure_structlog(open_null_stream())
    structlog.get_logger().info("Download abgeschlossen", path=UNICODE_NAME)
    target.close()


@pytest.mark.asyncio
async def test_download_with_unprintable_name_completes_on_a_charmap_console(tmp_path):
    """Der reproduzierte Fehlerfall, end-to-end durch den Produktpfad.

    structlog schreibt hier bewusst auf einen cp1252/strict-Strom, also genau
    auf das ungeschuetzte Windows-Verhalten. Der Download muss trotzdem
    durchlaufen und die Datei am Ziel liegen.
    """
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=cp1252_stream())
    )

    downloader = Downloader(
        ytdlp_path="yt-dlp", output_dir=tmp_path, ffmpeg_path="ffmpeg"
    )

    async def fake_create(*cmd, **_kwargs):
        work_dir = _work_dir_from_cmd(cmd)
        media = work_dir / UNICODE_NAME
        media.write_bytes(b"downloaded-media")
        (work_dir / f"Grosses Video {UNDARSTELLBAR} [abc123].de.srt").write_text(
            "1\n00:00:00,0 --> 00:00:01,0\nhallo\n", encoding="utf-8"
        )
        return _FinishedProcess(
            stdout=f"[download] 100%\n__RETRODISC_FILE__:{media}\n".encode("utf-8")
        )

    with patch("src.core.downloader.create_hidden_subprocess", new=fake_create):
        result = await downloader.download("https://example.invalid/v")

    # Fachlicher Endzustand, nicht blosser Fortschritt: Rueckgabe, Datei, Inhalt.
    assert result == tmp_path / UNICODE_NAME
    assert result.is_file()
    assert result.read_bytes() == b"downloaded-media"
    # Der Untertitel bleibt bei seinem Video, das Arbeitsverzeichnis ist weg.
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        f"Grosses Video {UNDARSTELLBAR} [abc123].de.srt",
        UNICODE_NAME,
    ]


def test_launcher_does_not_bind_logging_to_a_raw_stdout():
    """Der Launcher muss die Stroeme sichern, bevor Handler sie einsammeln."""
    source = Path("retrodisc_launcher.py").read_text(encoding="utf-8")
    assert "configure_console_encoding()" in source
    assert "configure_structlog(" in source
    assert "logging.StreamHandler(sys.stdout)" not in source
    assert source.index("configure_console_encoding()") < source.index(
        "logging.basicConfig("
    )
