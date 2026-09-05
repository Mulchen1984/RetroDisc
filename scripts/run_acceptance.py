"""Windows-Release-Acceptance: erst gegen den Quellstand, dann gegen die EXE.

Zwei Ebenen, dieselben Faelle aus ``src/acceptance.py`` - keine Duplikate:

1. **source**  - die Faelle laufen in diesem Prozess. Die Standardstroeme
   werden vorher bewusst auf ``cp1252``/``strict`` gestellt, also auf das
   ungeschuetzte Windows-Verhalten, das am 2026-09-05 einen fertigen Download
   als FAILED angezeigt hat.
2. **packaged** - die gebaute ``dist/RetroDisc.exe`` faehrt dieselben Faelle
   im eigenen gefrorenen Prozess ueber ``--acceptance-selftest`` und schreibt
   ihren Bericht als JSON. Zusaetzlich wird sie ein zweites Mal gestartet;
   das ist der Restart-Fall.

PASS/FAIL entscheidet ausschliesslich der Testcode ueber objektive
Bedingungen - Jobstatus, Dateiexistenz, Groesse, Reste, FFprobe. Fortschritt
allein zaehlt nie.

Aufruf:

    set PYTHONPATH=.venv\\Lib\\site-packages
    C:\\Users\\marco\\.local\\bin\\python3.11.exe scripts\\run_acceptance.py

Optionen: ``--source-only``, ``--packaged-only``, ``--cases a,b``.
Exitcode 0 = PASS.
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

PACKAGED_EXE = ROOT / "dist" / "RetroDisc.exe"

#: Kaltstart der Onefile-EXE plus echter Download brauchen Zeit.
PACKAGED_TIMEOUT_S = 1800

# Der echte Berichtskanal, bevor stdout fuer die Source-Ebene gekapert wird.
REPORT = sys.stdout


def hostile_console() -> io.TextIOWrapper:
    """Ein Strom, der sich wie eine ungeschuetzte Windows-Konsole verhaelt."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def run_source_level(cases: list[str] | None) -> dict:
    """Die Faelle im Quellstand, auf bewusst feindlichen Stroemen."""
    sys.stdout = hostile_console()
    sys.stderr = hostile_console()
    try:
        from retrodisc_launcher import RetroDiscBridge
        from src.acceptance import run_cases

        work_dir = Path(tempfile.mkdtemp(prefix="retrodisc_acceptance_src_"))
        bridge = RetroDiscBridge()
        bridge.settings.sound.play_on_complete = False
        try:
            report = run_cases(bridge, work_dir, cases)
        finally:
            try:
                bridge.shutdown()
            except Exception:
                pass
        report["work_dir"] = str(work_dir)
        return report
    except BaseException as exc:  # noqa: BLE001
        return {
            "level": "source",
            "release": "FAIL",
            "cases": [{
                "case": "harness",
                "status": "FAIL",
                "duration_s": 0.0,
                "metrics": {},
                "findings": [f"{type(exc).__name__}: {exc}"],
            }],
        }
    finally:
        sys.stdout = REPORT
        sys.stderr = sys.__stderr__


def _invoke_packaged(report_path: Path, cases: list[str] | None) -> tuple[int, float]:
    cmd = [str(PACKAGED_EXE), "--acceptance-selftest", "--report", str(report_path)]
    if cases:
        cmd += ["--cases", ",".join(cases)]
    started = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, timeout=PACKAGED_TIMEOUT_S)
    return proc.returncode, round(time.monotonic() - started, 1)


def run_packaged_level(cases: list[str] | None) -> dict:
    """Dieselben Faelle in der gebauten EXE, plus der Restart-Fall."""
    if not PACKAGED_EXE.is_file():
        return {
            "level": "packaged",
            "release": "FAIL",
            "cases": [{
                "case": "harness",
                "status": "FAIL",
                "duration_s": 0.0,
                "metrics": {"exe": str(PACKAGED_EXE)},
                "findings": ["Die gebaute EXE fehlt - zuerst build.py --clean"],
            }],
        }

    out_dir = Path(tempfile.mkdtemp(prefix="retrodisc_acceptance_pkg_"))
    first = out_dir / "packaged.json"
    try:
        code, elapsed = _invoke_packaged(first, cases)
    except subprocess.TimeoutExpired:
        return {
            "level": "packaged",
            "release": "FAIL",
            "cases": [{
                "case": "harness", "status": "FAIL", "duration_s": PACKAGED_TIMEOUT_S,
                "metrics": {}, "findings": ["EXE-Selbsttest lief in die Zeitgrenze"],
            }],
        }

    if not first.is_file():
        return {
            "level": "packaged",
            "release": "FAIL",
            "cases": [{
                "case": "harness", "status": "FAIL", "duration_s": elapsed,
                "metrics": {"exit_code": code},
                "findings": ["Die EXE hat keinen Bericht geschrieben"],
            }],
        }

    report = json.loads(first.read_text(encoding="utf-8"))
    report["exit_code"] = code
    report["duration_s"] = elapsed

    # J - Restart: Dieselbe EXE muss danach erneut sauber starten. Es genuegt
    # der billigste Fall; ein zweiter voller Durchlauf waere Zeitverschwendung.
    second = out_dir / "packaged-restart.json"
    started = time.monotonic()
    findings: list[str] = []
    metrics: dict = {}
    try:
        restart_code, restart_elapsed = _invoke_packaged(second, ["startup"])
        metrics = {"exit_code": restart_code, "startup_seconds": restart_elapsed}
        if restart_code != 0:
            findings.append(f"Zweiter Start endete mit Exitcode {restart_code}")
        if not second.is_file():
            findings.append("Zweiter Start schrieb keinen Bericht")
        else:
            again = json.loads(second.read_text(encoding="utf-8"))
            metrics["release"] = again.get("release")
            if again.get("release") != "PASS":
                findings.append("Startup nach Neustart nicht bestanden")
    except subprocess.TimeoutExpired:
        findings.append("Neustart lief in die Zeitgrenze")

    report["cases"].append({
        "case": "restart",
        "status": "PASS" if not findings else "FAIL",
        "duration_s": round(time.monotonic() - started, 2),
        "metrics": metrics,
        "findings": findings,
    })
    report["release"] = (
        "PASS" if all(c["status"] == "PASS" for c in report["cases"]) else "FAIL"
    )
    return report


def main(argv: list[str]) -> int:
    cases = None
    if "--cases" in argv:
        cases = [n for n in argv[argv.index("--cases") + 1].split(",") if n]
    do_source = "--packaged-only" not in argv
    do_packaged = "--source-only" not in argv

    from src.acceptance import format_report

    levels = []
    if do_source:
        levels.append(run_source_level(cases))
    if do_packaged:
        levels.append(run_packaged_level(cases))

    overall = "PASS" if all(l.get("release") == "PASS" for l in levels) else "FAIL"
    combined = {"release": overall, "levels": levels}

    for level in levels:
        print(format_report(level), file=REPORT)
        print("", file=REPORT)
    print("=" * 46, file=REPORT)
    print(f"release: {overall}", file=REPORT)
    print(json.dumps(combined, ensure_ascii=True), file=REPORT)
    REPORT.flush()
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
