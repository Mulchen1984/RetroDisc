"""Acceptance-Gate: realer Download mit einem Titel, den cp1252 nicht kann.

Am 2026-09-05 meldete ein manueller Test einen fertigen, korrekt
veroeffentlichten YouTube-Download als FAILED, weil das blosse Loggen des
Dateinamens auf einem cp1252-Strom eine ``UnicodeEncodeError`` warf. Kein
automatisiertes Gate hatte das gefunden: pytest, Smoke und ``verify_core``
laufen alle auf einem UTF-8-faehigen Kanal, die gebaute Anwendung unter
Windows nicht.

Dieses Skript schliesst genau diese Luecke. Es stellt die Standardstroeme
**vor** dem Import des Launchers auf cp1252/strict - also auf das ungeschuetzte
Windows-Verhalten - und faehrt danach einen echten Download ueber den
produktiven Bridge-Pfad.

Bewertet wird der fachliche Endzustand, nie der Fortschritt:
``JobState.DONE``, Datei vorhanden, Groesse > 0, keine transienten Reste.

Aufruf (aus dem Repository-Wurzelverzeichnis):

    set PYTHONPATH=.venv\\Lib\\site-packages
    C:\\Users\\marco\\.local\\bin\\python3.11.exe scripts\\verify_unicode_download.py

Exitcode 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Stabiles oeffentliches Video, dessen Titel Hangul enthaelt ("강남스타일").
# Diese Zeichen sind in cp1252 nicht darstellbar - genau die Bedingung, die den
# Fehler ausgeloest hat.
DEFAULT_URL = "https://www.youtube.com/watch?v=9bZkp7q19f0"

#: Reste, die nach einem sauberen Download nie im Ausgabeordner liegen duerfen.
TRANSIENT_SUFFIXES = {".part", ".ytdl", ".tmp", ".temp", ".frag", ".aria2"}

# Der echte Berichtskanal, bevor stdout gekapert wird.
REPORT = sys.stdout


def hostile_console() -> io.TextIOWrapper:
    """Ein Strom, der sich wie eine ungeschuetzte Windows-Konsole verhaelt."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def not_cp1252_encodable(text: str) -> str:
    out = []
    for char in text:
        try:
            char.encode("cp1252")
        except UnicodeEncodeError:
            out.append(char)
    return "".join(out)


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else DEFAULT_URL
    started = time.monotonic()

    # Ungeschuetzte Windows-Stroeme herstellen, BEVOR der Launcher importiert
    # wird. Nur so beweist der Lauf, dass der Launcher sie selbst absichert.
    sys.stdout = hostile_console()
    sys.stderr = hostile_console()

    from retrodisc_launcher import RetroDiscBridge  # noqa: E402
    from src.models.media import JobState  # noqa: E402

    out_dir = Path(tempfile.mkdtemp(prefix="retrodisc_unicode_dl_"))
    bridge = RetroDiscBridge()
    bridge.settings.sound.play_on_complete = False
    bridge.downloader.output_dir = out_dir

    findings: list[str] = []
    result: dict[str, object] = {"case": "unicode_download", "url": url}

    try:
        # Vorbedingung: Ohne ein nicht darstellbares Zeichen im Titel wuerde
        # dieser Lauf gruen sein, ohne irgendetwas zu beweisen.
        probe = subprocess.run(
            [str(bridge.downloader.ytdlp_path), "--no-warnings",
             "--dump-single-json", "--skip-download", url],
            capture_output=True,
        )
        if probe.returncode != 0:
            raise RuntimeError(
                "Titelabfrage fehlgeschlagen: "
                + probe.stderr.decode("utf-8", "replace")[:300]
            )
        title = str(json.loads(probe.stdout.decode("utf-8"))["title"])
        offending = not_cp1252_encodable(title)
        result["title_ascii"] = ascii(title)
        result["non_cp1252_chars"] = ascii(offending)
        if not offending:
            raise RuntimeError(
                "Der Titel enthaelt kein in cp1252 undarstellbares Zeichen; "
                "dieser Lauf wuerde den Fehler nicht reproduzieren."
            )

        queued = json.loads(bridge.download_url(url, format="480p"))
        if queued.get("error"):
            raise RuntimeError(f"Download-Start fehlgeschlagen: {queued['error']}")

        job_id = queued["job_id"]
        deadline = time.monotonic() + 900
        job = None
        while time.monotonic() < deadline:
            job = bridge.pipeline.get_job(job_id)
            if job and job.state in {
                JobState.DONE,
                JobState.FAILED,
                JobState.CANCELLED,
            }:
                break
            time.sleep(0.25)
        else:
            raise TimeoutError("Download wurde nicht innerhalb von 900 s fertig.")

        result["job_state"] = job.state.value
        result["job_error"] = job.error_message or None
        result["progress"] = getattr(job, "progress", None)

        # Fachlicher Endzustand - 100 % Fortschritt allein zaehlt nicht.
        if job.state is not JobState.DONE:
            findings.append(
                f"Jobstatus ist {job.state.value}, erwartet DONE"
                + (f" ({job.error_message})" if job.error_message else "")
            )
        if not job.output_path or not Path(job.output_path).is_file():
            findings.append("Ausgabedatei fehlt")
        else:
            output = Path(job.output_path)
            size = output.stat().st_size
            result["output_path_ascii"] = ascii(str(output))
            result["output_bytes"] = size
            if size <= 0:
                findings.append("Ausgabedatei ist leer")
            if not output.parent.resolve() == out_dir.resolve():
                findings.append("Ausgabedatei liegt nicht im konfigurierten Ordner")
            if not not_cp1252_encodable(output.name):
                findings.append(
                    "Der Dateiname enthaelt kein undarstellbares Zeichen; "
                    "der Lauf beweist den Fix nicht"
                )

        leftovers = [
            p.name
            for p in out_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in TRANSIENT_SUFFIXES
        ]
        work_dirs = [p.name for p in out_dir.iterdir() if p.is_dir()]
        result["transient_leftovers"] = [ascii(n) for n in leftovers]
        result["leftover_dirs"] = [ascii(n) for n in work_dirs]
        if leftovers:
            findings.append(f"transiente Reste im Ausgabeordner: {leftovers}")
        if work_dirs:
            findings.append(f"Arbeitsverzeichnisse nicht aufgeraeumt: {work_dirs}")

    except BaseException as exc:  # noqa: BLE001 - jeder Fehler ist ein Befund
        result["exception"] = f"{type(exc).__name__}: {exc}"
        findings.append(result["exception"])
        if isinstance(exc, UnicodeEncodeError):
            findings.append(
                "charmap/UnicodeEncodeError aufgetreten - genau der Blocker"
            )
    finally:
        try:
            bridge.shutdown()
        except Exception:
            pass

    result["duration_s"] = round(time.monotonic() - started, 1)
    result["findings"] = findings
    result["status"] = "PASS" if not findings else "FAIL"

    print("RetroDisc Unicode-Download-Gate", file=REPORT)
    print("=" * 40, file=REPORT)
    for key in (
        "url",
        "title_ascii",
        "non_cp1252_chars",
        "job_state",
        "progress",
        "output_path_ascii",
        "output_bytes",
        "transient_leftovers",
        "leftover_dirs",
        "duration_s",
    ):
        if key in result:
            print(f"  {key:22}: {result[key]}", file=REPORT)
    for finding in findings:
        print(f"  BEFUND: {finding}", file=REPORT)
    print(f"\nRESULT: {result['status']}", file=REPORT)
    print(json.dumps(result, ensure_ascii=True), file=REPORT)
    REPORT.flush()

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
