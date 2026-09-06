"""Windows-Acceptance-Faelle, die in der gebauten EXE selbst laufen koennen.

Am 2026-09-05 waren alle Source-Gates gruen und ein manueller Test fand
trotzdem einen echten Releaseblocker: ein fertiger Download wurde als FAILED
angezeigt, weil das Loggen des Dateinamens auf einem cp1252-Strom scheiterte.
Kein Source-Gate konnte das finden - pytest, Smoke und ``verify_core`` laufen
auf einem UTF-8-faehigen Kanal, die gebaute Anwendung unter Windows nicht.

Dieses Modul enthaelt die Faelle **einmal**. Es wird von zwei Ebenen benutzt:

* ``scripts/run_acceptance.py`` faehrt sie gegen den Quellstand.
* ``retrodisc_launcher.py`` faehrt sie auf ``--acceptance-selftest`` in der
  gepackten EXE, also im echten gefrorenen Prozess mit gebuendelten Werkzeugen.

Grundregel jedes Falls: bewertet wird der **fachliche Endzustand**, niemals der
Fortschritt. 100 % allein ist nie ein Erfolg.

Im normalen Produktbetrieb wird nichts hiervon importiert oder ausgefuehrt.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

# Jeder Hilfsprozess laeuft ueber den Wrapper, damit unter Windows kein
# Konsolenfenster aufblitzt - dieselbe Regel wie im uebrigen Produktcode.
from src.utils.subprocesses import run_hidden

#: yt-dlp-Zwischendateien, die nach einem sauberen Lauf nie liegen bleiben.
TRANSIENT_SUFFIXES = {".part", ".ytdl", ".tmp", ".temp", ".frag", ".aria2"}

#: Stabiles oeffentliches Video, dessen Titel Hangul enthaelt ("강남스타일").
#: Diese Zeichen sind in cp1252 nicht darstellbar - genau die Bedingung, die
#: den Blocker vom 2026-09-05 ausgeloest hat.
UNICODE_URL = "https://www.youtube.com/watch?v=9bZkp7q19f0"


def not_cp1252_encodable(text: str) -> str:
    """Die Zeichen aus *text*, die eine Windows-ANSI-Konsole nicht kann."""
    out = []
    for char in text:
        try:
            char.encode("cp1252")
        except UnicodeEncodeError:
            out.append(char)
    return "".join(out)


class Context:
    """Alles, was ein Fall braucht: die echte Bridge und ein Arbeitsordner."""

    def __init__(self, bridge, work_dir: Path) -> None:
        self.bridge = bridge
        self.work_dir = work_dir

    def ffmpeg_path(self) -> str:
        return str(getattr(self.bridge.ffmpeg, "ffmpeg_path", "ffmpeg"))

    def await_job(self, job_id: str, timeout_s: float):
        """Wartet auf einen Endzustand und gibt den Job zurueck."""
        from src.models.media import JobState

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            job = self.bridge.pipeline.get_job(job_id)
            if job and job.state in {
                JobState.DONE,
                JobState.FAILED,
                JobState.CANCELLED,
            }:
                return job
            time.sleep(0.25)
        raise TimeoutError(f"Job {job_id} wurde nicht in {timeout_s:g}s fertig.")

    def make_test_video(self, name: str, seconds: int = 2) -> Path:
        """Erzeugt ein echtes kleines Video mit dem gebuendelten FFmpeg.

        Bewusst erzeugt statt aus ``tests/fixtures`` geladen: die Fixtures sind
        nicht im Bundle, und so wird zugleich das gebuendelte FFmpeg geprueft.
        """
        target = self.work_dir / name
        proc = run_hidden(
            [
                self.ffmpeg_path(), "-y",
                "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=15:duration={seconds}",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(target),
            ],
            capture_output=True,
        )
        if proc.returncode != 0 or not target.is_file():
            raise RuntimeError(
                "Testvideo konnte nicht erzeugt werden: "
                + proc.stderr.decode("utf-8", "replace")[-400:]
            )
        return target


# ── Faelle ────────────────────────────────────────────────────────────────
# Jeder Fall gibt (metrics, findings) zurueck. Eine leere Befundliste = PASS.


def case_startup(ctx: Context) -> tuple[dict, list[str]]:
    """A - Die Anwendung ist vollstaendig initialisiert und benutzbar."""
    findings: list[str] = []
    metrics = {
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version.split()[0],
        "stdout_encoding": getattr(sys.stdout, "encoding", None),
        "stdout_errors": getattr(sys.stdout, "errors", None),
    }

    for attr in ("ffmpeg", "downloader", "pipeline", "converter", "disc"):
        if getattr(ctx.bridge, attr, None) is None:
            findings.append(f"Bridge-Komponente fehlt: {attr}")

    # Die gebuendelten Werkzeuge muessen wirklich startbar sein, nicht nur
    # als Pfad existieren.
    # FFmpeg kennt nur "-version" mit einem Strich, yt-dlp nur "--version".
    # Der falsche Schalter meldet einen Fehlercode und wuerde ein
    # funktionierendes Werkzeug als kaputt ausweisen.
    for label, path, flag in (
        ("ffmpeg", ctx.ffmpeg_path(), "-version"),
        ("ytdlp", str(getattr(ctx.bridge.downloader, "ytdlp_path", "yt-dlp")), "--version"),
    ):
        try:
            proc = run_hidden([path, flag], capture_output=True, timeout=60)
            metrics[f"{label}_returncode"] = proc.returncode
            if proc.returncode != 0:
                findings.append(f"{label} startet nicht (rc={proc.returncode})")
        except (OSError, subprocess.SubprocessError) as exc:
            findings.append(f"{label} nicht startbar: {exc}")

    # Nach dem charmap-Blocker: der Ausgabekanal darf nicht strict sein.
    errors = metrics["stdout_errors"]
    if errors is not None and errors == "strict":
        findings.append(
            "sys.stdout ist auf errors='strict' - ein undarstellbares Zeichen "
            "wuerde erneut fertige Jobs scheitern lassen"
        )
    return metrics, findings


def case_settings(ctx: Context) -> tuple[dict, list[str]]:
    """B - Ein gespeicherter Wert ueberlebt das Neuladen von der Platte."""
    from src.config.settings import AppSettings

    findings: list[str] = []
    original = ctx.bridge.settings.sound.play_on_complete
    probe = not original
    metrics = {"field": "sound.play_on_complete", "original": original, "written": probe}

    try:
        saved = json.loads(
            ctx.bridge.save_settings(json.dumps({"sound": {"play_on_complete": probe}}))
        )
        if saved.get("error"):
            findings.append(f"save_settings meldete: {saved['error']}")

        # Frisch von der Platte lesen - genau wie ein Neustart es taete.
        reloaded = AppSettings.load().sound.play_on_complete
        metrics["reloaded"] = reloaded
        if reloaded != probe:
            findings.append(
                f"Wert ging verloren: geschrieben {probe}, nach Neuladen {reloaded}"
            )
    finally:
        # Die Einstellungen des Nutzers bleiben unveraendert zurueck.
        ctx.bridge.save_settings(json.dumps({"sound": {"play_on_complete": original}}))
        restored = AppSettings.load().sound.play_on_complete
        metrics["restored"] = restored
        if restored != original:
            findings.append(
                f"Ausgangswert nicht wiederhergestellt: {restored} statt {original}"
            )
    return metrics, findings


def case_unicode_download(ctx: Context) -> tuple[dict, list[str]]:
    """C+D - Echter Download; der Titel enthaelt undarstellbare Zeichen."""
    findings: list[str] = []
    out_dir = ctx.work_dir / "download"
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx.bridge.settings.directories.download_dir = out_dir
    ctx.bridge.settings.directories.output_dir = ctx.work_dir / "Videos"
    metrics: dict = {"url": UNICODE_URL, "output_dir": str(out_dir)}

    probe = run_hidden(
        [str(ctx.bridge.downloader.ytdlp_path), "--no-warnings",
         "--dump-single-json", "--skip-download", UNICODE_URL],
        capture_output=True,
    )
    if probe.returncode != 0:
        return metrics, [
            "Titelabfrage fehlgeschlagen: "
            + probe.stderr.decode("utf-8", "replace")[-300:]
        ]

    title = str(json.loads(probe.stdout.decode("utf-8"))["title"])
    offending = not_cp1252_encodable(title)
    metrics["title_ascii"] = ascii(title)
    metrics["non_cp1252_chars"] = ascii(offending)
    if not offending:
        # Ohne undarstellbares Zeichen wuerde der Fall gruen sein, ohne den
        # Blocker zu reproduzieren. Das ist ein Fehlschlag, kein Erfolg.
        return metrics, [
            "Der Titel enthaelt kein in cp1252 undarstellbares Zeichen; "
            "dieser Lauf wuerde den Blocker nicht reproduzieren"
        ]

    queued = json.loads(ctx.bridge.download_url(UNICODE_URL, format="480p"))
    if queued.get("error"):
        return metrics, [f"Download-Start fehlgeschlagen: {queued['error']}"]

    job = ctx.await_job(queued["job_id"], 900)
    metrics["job_state"] = job.state.value
    metrics["progress"] = getattr(job, "progress", None)
    metrics["job_error"] = job.error_message

    from src.models.media import JobState

    if job.state is not JobState.DONE:
        findings.append(
            f"Jobstatus {job.state.value}, erwartet done"
            + (f": {job.error_message}" if job.error_message else "")
        )
    if not job.output_path or not Path(job.output_path).is_file():
        findings.append("Ausgabedatei fehlt")
    else:
        output = Path(job.output_path)
        metrics["output_path_ascii"] = ascii(str(output))
        metrics["output_bytes"] = output.stat().st_size
        if output.stat().st_size <= 0:
            findings.append("Ausgabedatei ist leer")
        if output.parent.resolve() != ctx.bridge.settings.directories.output_dir.resolve():
            findings.append("Ausgabedatei liegt nicht im konfigurierten Ordner")
        if not not_cp1252_encodable(output.name):
            findings.append("Dateiname ohne undarstellbares Zeichen - beweist nichts")

    leftovers = [
        p.name for p in out_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in TRANSIENT_SUFFIXES
    ]
    dirs = [p.name for p in out_dir.rglob(".retrodisc-dl-*") if p.is_dir()]
    metrics["transient_leftovers"] = [ascii(n) for n in leftovers]
    metrics["leftover_dirs"] = [ascii(n) for n in dirs]
    if leftovers:
        findings.append(f"transiente Reste: {leftovers}")
    if dirs:
        findings.append(f"Arbeitsverzeichnisse nicht aufgeraeumt: {dirs}")
    return metrics, findings


def case_conversion(ctx: Context) -> tuple[dict, list[str]]:
    """F - Echte Konvertierung; die Ausgabe muss von FFprobe lesbar sein."""
    from src.models.media import JobState

    findings: list[str] = []
    source = ctx.make_test_video("acceptance-source.mp4")
    out_dir = ctx.work_dir / "convert"
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics: dict = {"source_bytes": source.stat().st_size, "preset": "mp3_320k"}

    queued = json.loads(
        ctx.bridge.convert_file(str(source), "mp3_320k", str(out_dir), True)
    )
    if queued.get("error"):
        return metrics, [f"Konvertierung nicht gestartet: {queued['error']}"]

    job = ctx.await_job(queued["job_id"], 300)
    metrics["job_state"] = job.state.value
    if job.state is not JobState.DONE:
        findings.append(
            f"Jobstatus {job.state.value}, erwartet done"
            + (f": {job.error_message}" if job.error_message else "")
        )

    if not job.output_path or not Path(job.output_path).is_file():
        findings.append("Ausgabedatei fehlt")
        return metrics, findings

    output = Path(job.output_path)
    metrics["output_path"] = str(output)
    metrics["output_bytes"] = output.stat().st_size
    if output.stat().st_size <= 0:
        findings.append("Ausgabedatei ist leer")

    # FFprobe muss die Datei wirklich oeffnen koennen - Existenz reicht nicht.
    probed = json.loads(ctx.bridge.probe_file(str(output)))
    if probed.get("error"):
        findings.append(f"FFprobe kann die Ausgabe nicht lesen: {probed['error']}")
    else:
        codec = probed.get("audio_codec")
        metrics["audio_codec"] = codec
        metrics["duration"] = probed.get("duration_formatted")
        if codec != "mp3":
            findings.append(f"Audio-Codec ist {codec!r}, erwartet 'mp3'")
    return metrics, findings


def case_error_handling(ctx: Context) -> tuple[dict, list[str]]:
    """I - Ungueltige Eingabe endet kontrolliert; die App bleibt benutzbar."""
    findings: list[str] = []
    metrics: dict = {}

    # 1. Offensichtlich ungueltige URL -> kontrollierte Fehlermeldung.
    answer = json.loads(ctx.bridge.download_url("nicht-einmal-eine-url"))
    metrics["invalid_url_answer"] = answer
    message = str(answer.get("error", ""))
    if not message:
        findings.append("Ungueltige URL wurde ohne Fehlermeldung angenommen")
    elif len(message) < 5:
        findings.append(f"Fehlermeldung ist nicht verstaendlich: {message!r}")

    # 2. Nicht existierende Datei konvertieren -> Job endet kontrolliert.
    missing = ctx.work_dir / "gibt-es-nicht.mp4"
    queued = json.loads(ctx.bridge.convert_file(str(missing), "mp3_320k", None, True))
    if queued.get("error"):
        # Schon beim Einreichen kontrolliert abgelehnt - ebenfalls in Ordnung.
        metrics["missing_file_rejected_at_submit"] = queued["error"]
    else:
        from src.models.media import JobState

        job = ctx.await_job(queued["job_id"], 120)
        metrics["missing_file_job_state"] = job.state.value
        metrics["missing_file_error"] = job.error_message
        if job.state is not JobState.FAILED:
            findings.append(
                f"Fehlerhafter Job endete als {job.state.value}, erwartet failed"
            )
        if not (job.error_message or "").strip():
            findings.append("Gescheiterter Job traegt keine Fehlermeldung")

    # 3. Die Anwendung muss danach weiterarbeiten.
    still_ok = ctx.make_test_video("after-error.mp4", seconds=1)
    probed = json.loads(ctx.bridge.probe_file(str(still_ok)))
    metrics["usable_after_error"] = not probed.get("error")
    if probed.get("error"):
        findings.append(f"App nach Fehlerfall nicht mehr benutzbar: {probed['error']}")
    return metrics, findings


def case_media_tools(ctx: Context) -> tuple[dict, list[str]]:
    """G - Trim, Merge, Upscale und Interpolation ueber den Bridge-Pfad.

    Die Dienste dahinter sind laengst belegt, aber ``scripts/release_smoke.py``
    ruft ``FFmpeg`` und ``VideoUpscaler`` **direkt** auf. Genau in der Schicht
    dazwischen sass ein Fehler: die Bridge baute ihre Jobs mit einem
    positionalen ``Job(JobType..., ...)``. Das erste Feld von ``Job`` ist aber
    ``id``, nicht ``job_type`` - der Enum landete in der ID, die JSON-Antwort
    war nicht serialisierbar, und sieben Schaltflaechen taten schlicht nichts.
    Kein Gate konnte das sehen, weil keines die Bridge-Werkzeuge fuhr.

    Der Fall bewertet nur den fachlichen Endzustand: Job ``done``, Datei da,
    und FFprobe muss die Ausgabe wirklich lesen koennen.
    """
    from src.models.media import JobState

    findings: list[str] = []
    metrics: dict = {}
    out_dir = ctx.work_dir / "tools"
    out_dir.mkdir(parents=True, exist_ok=True)
    source = ctx.make_test_video("acceptance-tools.mp4", seconds=3)

    def finish(label: str, answer_json: str, timeout_s: float) -> Optional[Path]:
        """Wartet einen eingereihten Job ab und liefert seine Ausgabedatei."""
        answer = json.loads(answer_json)
        if answer.get("error"):
            findings.append(f"{label} nicht gestartet: {answer['error']}")
            return None
        job_id = answer.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            findings.append(f"{label} lieferte keine brauchbare Job-ID: {job_id!r}")
            return None
        job = ctx.await_job(job_id, timeout_s)
        metrics[f"{label}_job_state"] = job.state.value
        if job.state is not JobState.DONE:
            findings.append(
                f"{label} endete als {job.state.value}, erwartet done"
                + (f": {job.error_message}" if job.error_message else "")
            )
            return None
        if not job.output_path or not Path(job.output_path).is_file():
            findings.append(f"{label}: Ausgabedatei fehlt")
            return None
        output = Path(job.output_path)
        metrics[f"{label}_bytes"] = output.stat().st_size
        if output.stat().st_size <= 0:
            findings.append(f"{label}: Ausgabedatei ist leer")
            return None
        return output

    def video_stream(label: str, output: Path) -> dict:
        probed = json.loads(ctx.bridge.probe_file(str(output)))
        if probed.get("error"):
            findings.append(f"{label}: FFprobe kann die Ausgabe nicht lesen: {probed['error']}")
            return {}
        streams = probed.get("video") or []
        if not streams:
            findings.append(f"{label}: Ausgabe enthaelt keine Videospur")
            return {}
        return streams[0]

    first = finish(
        "trim_a",
        ctx.bridge.trim_video(str(source), 0.0, 1.5, str(out_dir / "trim-a.mp4")),
        180,
    )
    second = finish(
        "trim_b",
        ctx.bridge.trim_video(str(source), 1.5, 3.0, str(out_dir / "trim-b.mp4")),
        180,
    )

    if first and second:
        merged = finish(
            "merge",
            ctx.bridge.merge_videos(
                json.dumps([str(first), str(second)]), str(out_dir / "merged.mp4")
            ),
            240,
        )
        if merged:
            video_stream("merge", merged)

    upscaled = finish("upscale", ctx.bridge.upscale_video(str(source), 2), 600)
    if upscaled:
        stream = video_stream("upscale", upscaled)
        metrics["upscale_resolution"] = (stream.get("width"), stream.get("height"))
        source_stream = video_stream("upscale_source", source)
        if stream and source_stream and stream.get("width") and source_stream.get("width"):
            if stream["width"] < source_stream["width"] * 2:
                findings.append(
                    f"Upscale lieferte {stream['width']}px statt mindestens "
                    f"{source_stream['width'] * 2}px Breite"
                )

    interpolated = finish("interpolate", ctx.bridge.interpolate_video(str(source), 30.0), 600)
    if interpolated:
        stream = video_stream("interpolate", interpolated)
        metrics["interpolate_fps"] = stream.get("fps")

    return metrics, findings


#: Reihenfolge ist bewusst: erst billig und grundlegend, dann teuer.
CASES: dict[str, Callable[[Context], tuple[dict, list[str]]]] = {
    "startup": case_startup,
    "settings": case_settings,
    "conversion": case_conversion,
    "error_handling": case_error_handling,
    "media_tools": case_media_tools,
    "unicode_download": case_unicode_download,
}


def run_cases(
    bridge,
    work_dir: Path,
    selected: Optional[list[str]] = None,
) -> dict:
    """Faehrt die gewaehlten Faelle gegen *bridge* und liefert den Bericht."""
    names = selected or list(CASES)
    report = {
        "level": "packaged" if getattr(sys, "frozen", False) else "source",
        "cases": [],
    }
    ctx = Context(bridge, work_dir)

    for name in names:
        func = CASES.get(name)
        if func is None:
            report["cases"].append(
                {"case": name, "status": "FAIL", "findings": ["unbekannter Fall"]}
            )
            continue
        started = time.monotonic()
        try:
            metrics, findings = func(ctx)
        except BaseException as exc:  # noqa: BLE001 - jeder Fehler ist ein Befund
            metrics, findings = {}, [f"{type(exc).__name__}: {exc}"]
            if isinstance(exc, UnicodeEncodeError):
                findings.append("charmap/UnicodeEncodeError - genau der alte Blocker")
        report["cases"].append({
            "case": name,
            "status": "PASS" if not findings else "FAIL",
            "duration_s": round(time.monotonic() - started, 2),
            "metrics": metrics,
            "findings": findings,
        })

    report["release"] = (
        "PASS" if all(c["status"] == "PASS" for c in report["cases"]) else "FAIL"
    )
    return report


def format_report(report: dict) -> str:
    lines = [f"RetroDisc Acceptance ({report['level']})", "=" * 46]
    for case in report["cases"]:
        lines.append(
            f"  {case['status']:4}  {case['case']:18} {case.get('duration_s', 0):>7.2f}s"
        )
        for key, value in (case.get("metrics") or {}).items():
            lines.append(f"          {key}: {value}")
        for finding in case.get("findings") or []:
            lines.append(f"          BEFUND: {finding}")
    lines.append("")
    lines.append(f"release: {report['release']}")
    return "\n".join(lines)


def run_from_argv(argv: list[str]) -> int:
    """Einstiegspunkt des Launcher-Hooks in der gepackten EXE.

    ``--acceptance-selftest [--cases a,b] [--report PFAD]``
    """
    from retrodisc_launcher import RetroDiscBridge

    selected = None
    report_path = None
    if "--cases" in argv:
        selected = [n for n in argv[argv.index("--cases") + 1].split(",") if n]
    if "--report" in argv:
        report_path = Path(argv[argv.index("--report") + 1])

    work_dir = Path(tempfile.mkdtemp(prefix="retrodisc_acceptance_"))
    bridge = RetroDiscBridge()
    bridge.settings.sound.play_on_complete = False
    try:
        report = run_cases(bridge, work_dir, selected)
    finally:
        try:
            bridge.shutdown()
        except Exception:
            pass

    report["work_dir"] = str(work_dir)
    text = format_report(report)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8"
        )
        (report_path.with_suffix(".txt")).write_text(text, encoding="utf-8")
    elif sys.stdout is not None:
        # Ohne Report-Datei bleibt nur der Standardkanal. Die gepackte EXE ist
        # windowed gebaut (console=False), dort kann sys.stdout None sein -
        # deshalb ist --report der Normalfall und print nur der Notnagel.
        print(text)
    return 0 if report["release"] == "PASS" else 1
