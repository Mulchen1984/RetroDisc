"""Einzelgate: realer Download mit einem Titel, den cp1252 nicht darstellen kann.

Der Fall selbst steht in ``src/acceptance.py`` (``case_unicode_download``) und
wird von beiden Acceptance-Ebenen benutzt. Dieses Skript ist nur der bequeme
Einzelaufruf, damit der am 2026-09-05 gefundene Blocker ohne den vollstaendigen
Acceptance-Lauf nachgeprueft werden kann.

    set PYTHONPATH=.venv\\Lib\\site-packages
    C:\\Users\\marco\\.local\\bin\\python3.11.exe scripts\\verify_unicode_download.py

Exitcode 0 = PASS.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# scripts/ ist kein Paket, deshalb die Datei direkt laden.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "retrodisc_run_acceptance", Path(__file__).with_name("run_acceptance.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
main = _module.main

if __name__ == "__main__":
    raise SystemExit(main([sys.argv[0], "--source-only", "--cases", "unicode_download"]))
