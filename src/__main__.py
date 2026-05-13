"""RetroDisc - Haupteinstiegspunkt.

Usage:
    python -m retrodisc
    python -m retrodisc convert input.mkv --preset mp4_h264_1080p
    python -m retrodisc download "https://youtube.com/watch?v=xxx" --format mp3
    python -m retrodisc search "Tatort München"
    python -m retrodisc burn output.iso --device /dev/sr0
    python -m retrodisc highlight konzert.mp4 --duration 300
"""

from __future__ import annotations

import asyncio
import sys

import click
import structlog
from pathlib import Path
from rich.console import Console
from rich.table import Table

from src import __version__, __app_name__
from src.config.settings import AppSettings
from src.core.ffmpeg import FFmpeg
from src.core.downloader import Downloader
from src.core.pipeline import Pipeline
from src.models.media import Job, JobType
from src.config.presets import get_preset, ALL_PRESETS, get_presets_by_category
from src.utils.sound import play_completion_sound

console = Console()
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
)


def print_banner():
    console.print(f"""
[bold cyan]
    ######+ #######+########+######+  ######+ ######+ ##+#######+ ######+
    ##+==##+##+====++==##+==+##+==##+##+===##+##+==##+##|##+====+##+====+
    ######++#####+     ##|   ######++##|   ##|##|  ##|##|#######+##|
    ##+==##+##+==+     ##|   ##+==##+##|   ##|##|  ##|##|+====##|##|
    ##|  ##|#######+   ##|   ##|  ##|+######++######++##|#######|+######+
    +=+  +=++======+   +=+   +=+  +=+ +=====+ +=====+ +=++======+ +=====+
[/bold cyan]
    [dim]All-in-One Media Suite · v{__version__}[/dim]
    [dim]Konvertieren · Brennen · Downloaden · AI-Enhanced[/dim]
    """)


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name=__app_name__)
@click.pass_context
def cli(ctx):
    """RetroDisc - All-in-One Media Suite im CloneCD-Stil."""
    if ctx.invoked_subcommand is None:
        print_banner()
        click.echo("Nutze --help für verfügbare Befehle.")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--preset", "-p", default="mp4_h264_1080p", help="Konvertierungs-Preset")
@click.option("--output", "-o", type=click.Path(), help="Output-Pfad")
@click.option("--hwaccel", type=click.Choice(["auto", "cuda", "qsv", "none"]), default="auto")
def convert(input_file, preset, output, hwaccel):
    """Konvertiert eine Mediendatei."""
    async def _run():
        settings = AppSettings.load()
        ffmpeg = FFmpeg(settings.tools.ffmpeg, settings.tools.ffprobe)
        await ffmpeg.validate()

        p = get_preset(preset)
        input_path = Path(input_file)
        output_path = Path(output) if output else input_path.with_suffix(f".{p.container}")

        console.print(f"[cyan]Konvertiere:[/cyan] {input_path.name}")
        console.print(f"[cyan]Preset:[/cyan] {p.display_name}")
        console.print(f"[cyan]Output:[/cyan] {output_path}")

        job = Job(job_type=JobType.CONVERT, input_files=[input_path])
        job.on_progress = lambda prog, text: console.print(
            f"\r[cyan]{prog:.1f}%[/cyan] {text}", end=""
        )

        hw = hwaccel if hwaccel != "none" else None
        await ffmpeg.convert(
            input_path=input_path,
            output_path=output_path,
            video_codec=p.video_codec,
            audio_codec=p.audio_codec,
            video_bitrate=p.video_bitrate,
            audio_bitrate=p.audio_bitrate,
            resolution=p.resolution,
            extra_args=p.extra_args,
            job=job,
            hwaccel=hw,
        )

        console.print(f"\n[green]OK: Fertig![/green] {output_path}")
        play_completion_sound()

    asyncio.run(_run())


@cli.command()
@click.argument("url")
@click.option("--format", "-f", "fmt", default="best", help="Format (best/720p/1080p/mp3)")
@click.option("--audio-only", "-a", is_flag=True, help="Nur Audio extrahieren")
@click.option("--subtitles", "-s", is_flag=True, help="Untertitel mitladen")
def download(url, fmt, audio_only, subtitles):
    """Lädt ein Video/Audio von YouTube oder Mediathek herunter."""
    async def _run():
        settings = AppSettings.load()
        dl = Downloader(
            ytdlp_path=settings.tools.ytdlp,
            output_dir=settings.directories.download_dir,
        )
        await dl.validate()

        console.print(f"[cyan]Download:[/cyan] {url}")
        console.print(f"[cyan]Format:[/cyan] {fmt}")

        job = Job(job_type=JobType.DOWNLOAD)
        job.on_progress = lambda prog, text: console.print(
            f"\r[cyan]{prog:.1f}%[/cyan] {text}", end=""
        )

        result = await dl.download(
            url=url,
            format=fmt if not audio_only else "bestaudio",
            extract_audio=audio_only,
            subtitles=subtitles,
            job=job,
        )

        console.print(f"\n[green]OK: Fertig![/green] {result}")
        play_completion_sound()

    asyncio.run(_run())


@cli.command()
@click.argument("query")
@click.option("--youtube/--no-youtube", default=True, help="YouTube durchsuchen")
@click.option("--mediathek/--no-mediathek", default=True, help="Mediatheken durchsuchen")
@click.option("--max", "max_results", default=10, help="Max Ergebnisse pro Quelle")
def search(query, youtube, mediathek, max_results):
    """Durchsucht YouTube und Mediatheken."""
    async def _run():
        settings = AppSettings.load()
        dl = Downloader(ytdlp_path=settings.tools.ytdlp)

        console.print(f"[cyan]Suche:[/cyan] '{query}'")

        results = await dl.search_all(
            query=query,
            include_youtube=youtube,
            include_mediathek=mediathek,
            max_results_per_source=max_results,
        )

        if not results:
            console.print("[yellow]Keine Ergebnisse gefunden.[/yellow]")
            return

        table = Table(title=f"Suchergebnisse für '{query}'")
        table.add_column("#", style="dim", width=4)
        table.add_column("Quelle", style="cyan", width=10)
        table.add_column("Titel", style="white")
        table.add_column("Dauer", style="dim", width=8)
        table.add_column("Qualität", style="green", width=8)

        for i, r in enumerate(results, 1):
            dur = ""
            if r.duration_seconds:
                m, s = divmod(int(r.duration_seconds), 60)
                dur = f"{m}:{s:02d}"
            table.add_row(
                str(i), r.source.upper(), r.title[:60], dur, r.quality or ""
            )

        console.print(table)

    asyncio.run(_run())


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--duration", "-d", default=300, help="Zieldauer in Sekunden")
@click.option("--output", "-o", type=click.Path(), help="Output-Pfad")
def highlight(input_file, duration, output):
    """Erstellt automatische Highlights aus einem Video (KI Auto-Edit)."""
    async def _run():
        from src.services.smart_edit import SmartEdit
        from src.models.media import HighlightConfig

        input_path = Path(input_file)
        output_path = Path(output) if output else input_path.with_stem(f"{input_path.stem}_highlights")

        config = HighlightConfig(target_duration_seconds=duration)
        editor = SmartEdit()

        console.print(f"[cyan]KI Auto-Edit:[/cyan] {input_path.name}")
        console.print(f"[cyan]Zieldauer:[/cyan] {duration}s")

        job = Job(job_type=JobType.SMART_EDIT, input_files=[input_path])
        job.on_progress = lambda prog, text: console.print(
            f"\r[cyan]{prog:.1f}%[/cyan] {text}", end=""
        )

        result = await editor.create_highlights(
            input_path=input_path,
            output_path=output_path,
            config=config,
            job=job,
        )

        console.print(f"\n[green]OK: Highlights erstellt![/green] {result}")
        play_completion_sound()

    asyncio.run(_run())


@cli.command()
def presets():
    """Zeigt alle verfügbaren Konvertierungs-Presets."""
    print_banner()

    for category, label in [
        ("video", "Video"), ("audio", "Audio"),
        ("device", "Geräte"), ("disc", "Disc"),
    ]:
        table = Table(title=f"{label}-Presets")
        table.add_column("Name", style="cyan")
        table.add_column("Beschreibung", style="white")
        table.add_column("Container", style="dim")

        for p in get_presets_by_category(category):
            table.add_row(p.name, p.display_name, p.container)

        console.print(table)
        console.print()


@cli.command()
def check():
    """Prüft ob alle externen Tools verfügbar sind."""
    async def _run():
        print_banner()
        settings = AppSettings.load()

        console.print("[bold]Tool-Check:[/bold]\n")

        # FFmpeg
        try:
            ffmpeg = FFmpeg(settings.tools.ffmpeg, settings.tools.ffprobe)
            versions = await ffmpeg.validate()
            console.print(f"  [green]OK:[/green] FFmpeg {versions.get('ffmpeg', '?')}")
            console.print(f"  [green]OK:[/green] FFprobe {versions.get('ffprobe', '?')}")
        except Exception as e:
            console.print(f"  [red]FEHLER:[/red] FFmpeg: {e}")

        # yt-dlp
        try:
            dl = Downloader(ytdlp_path=settings.tools.ytdlp)
            version = await dl.validate()
            console.print(f"  [green]OK:[/green] yt-dlp {version}")
        except Exception as e:
            console.print(f"  [red]FEHLER:[/red] yt-dlp: {e}")

        # Disc-Tools
        from src.core.disc import DiscTools
        disc = DiscTools()
        tools = await disc.validate()
        for name, available in tools.items():
            status = "[green]OK:[/green]" if available else "[yellow]○[/yellow] (optional)"
            console.print(f"  {status} {name}")

        console.print()

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
