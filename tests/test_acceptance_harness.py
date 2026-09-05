"""Der Acceptance-Harness selbst muss belastbar sein.

Zwei Eigenschaften entscheiden ueber seinen Wert:

* Er darf den **normalen Produktbetrieb nicht veraendern**. Der Hook in
  ``retrodisc_launcher.main()`` wird ausschliesslich ueber ein explizites
  Argument betreten; ohne dieses Argument wird ``src.acceptance`` nicht
  einmal importiert.
* Er darf **nicht gruen werden, ohne etwas zu beweisen**. Ein Fall, der
  seine eigene Vorbedingung nicht erfuellt, muss FAIL melden - sonst haette
  er den charmap-Blocker vom 2026-09-05 genauso durchgelassen wie die
  bisherigen Source-Gates.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from src import acceptance

ROOT = Path(__file__).resolve().parents[1]


def test_launcher_hook_only_runs_behind_the_explicit_flag():
    source = (ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")
    assert 'ACCEPTANCE_FLAG = "--acceptance-selftest"' in source

    # Der Import muss INNERHALB des Zweigs stehen. Auf Modulebene waere
    # src.acceptance bei jedem Produktstart geladen. Geprueft wird der
    # Syntaxbaum, nicht der Text - ein Kommentar darf das Modul nennen.
    tree = ast.parse(source)
    module_level_imports = [
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in getattr(node, "names", [])
    ] + [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not any(
        name and "acceptance" in name for name in module_level_imports
    ), f"src.acceptance darf nicht auf Modulebene importiert werden: {module_level_imports}"

    guard = source.index("if ACCEPTANCE_FLAG in sys.argv:")
    imported = source.index("from src.acceptance import run_from_argv")
    assert guard < imported


def test_importing_the_launcher_does_not_pull_in_the_harness():
    """Ohne Flag darf der Produktstart das Acceptance-Modul nicht laden."""
    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('rdl', r'retrodisc_launcher.py')\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "print('LOADED' if 'src.acceptance' in sys.modules else 'ABSENT')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, timeout=300
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-800:]
    assert b"ABSENT" in proc.stdout


class _FakeCompleted:
    def __init__(self, stdout: bytes) -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = b""


def test_unicode_case_fails_when_the_title_proves_nothing(tmp_path, monkeypatch):
    """Ein rein westlicher Titel darf NICHT als bestanden gelten.

    Genau das ist der Unterschied zu einem wertlosen Gate: ohne ein in cp1252
    undarstellbares Zeichen reproduziert der Lauf den Blocker nicht, also ist
    er kein Beleg.
    """
    monkeypatch.setattr(
        acceptance,
        "run_hidden",
        lambda *a, **k: _FakeCompleted(b'{"title": "Ein ganz normales Video"}'),
    )

    class _Bridge:
        class downloader:
            ytdlp_path = "yt-dlp"
            output_dir = None

        def download_url(self, *a, **k):  # pragma: no cover - darf nie laufen
            raise AssertionError("Der Download haette nicht starten duerfen")

    ctx = acceptance.Context(_Bridge(), tmp_path)
    _metrics, findings = acceptance.case_unicode_download(ctx)
    assert findings
    assert any("undarstellbares Zeichen" in f for f in findings)


def test_a_raising_case_is_reported_as_fail_not_a_crash(tmp_path, monkeypatch):
    def explode(_ctx):
        raise RuntimeError("kaputt")

    monkeypatch.setitem(acceptance.CASES, "startup", explode)
    report = acceptance.run_cases(object(), tmp_path, ["startup"])

    assert report["release"] == "FAIL"
    assert report["cases"][0]["status"] == "FAIL"
    assert "RuntimeError: kaputt" in report["cases"][0]["findings"][0]


def test_one_failing_case_fails_the_whole_release(tmp_path, monkeypatch):
    monkeypatch.setitem(acceptance.CASES, "green", lambda _ctx: ({}, []))
    monkeypatch.setitem(acceptance.CASES, "red", lambda _ctx: ({}, ["Befund"]))
    report = acceptance.run_cases(object(), tmp_path, ["green", "red"])

    assert [c["status"] for c in report["cases"]] == ["PASS", "FAIL"]
    assert report["release"] == "FAIL"


def test_not_cp1252_encodable_finds_exactly_the_offending_characters():
    assert acceptance.not_cp1252_encodable("Voll normal, mit Umlaut ä") == ""
    assert acceptance.not_cp1252_encodable("Video \U0001F600") == "\U0001F600"
    assert acceptance.not_cp1252_encodable("강남스타일") == "강남스타일"
