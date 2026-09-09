"""Open an output's actual location using the native file manager."""
import os
import sys
from pathlib import Path

from src.utils.subprocesses import run_hidden


def reveal_output(path: Path) -> None:
    path = path.expanduser().resolve()
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    if not target.exists() or (target == Path(target.anchor) and target != path):
        raise FileNotFoundError(f"Ausgabe und zugehöriger Ordner nicht gefunden: {path}")
    if sys.platform == "darwin":
        args = ["open", "-R", str(target)] if target.is_file() else ["open", str(target)]
        run_hidden(args, check=True, timeout=10, capture_output=True, text=True)
    elif sys.platform == "win32":
        os.startfile(str(target.parent if target.is_file() else target))
    else:
        run_hidden(["xdg-open", str(target.parent if target.is_file() else target)],
                   check=True, timeout=10, capture_output=True, text=True)
