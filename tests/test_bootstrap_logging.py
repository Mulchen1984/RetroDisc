"""Regression coverage for the stdlib logger used by the tool bootstrap."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from src.bootstrap import TOOLS, ToolBootstrap


def test_bootstrap_existing_tools_can_be_logged(tmp_path: Path, caplog):
    for info in TOOLS.values():
        (tmp_path / info["exe"]).write_bytes(b"tool")

    with caplog.at_level(logging.INFO, logger="retrodisc.bootstrap"):
        assert ToolBootstrap(tmp_path).check_missing() == []

    assert "Tool gefunden" in caplog.text


def test_bootstrap_stdlib_logger_has_no_structlog_keyword_arguments():
    source_path = Path(__file__).parents[1] / "src" / "bootstrap.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed = {"exc_info", "stack_info", "stacklevel", "extra"}
    invalid: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "log":
            continue
        for keyword in node.keywords:
            if keyword.arg is not None and keyword.arg not in allowed:
                invalid.append((node.lineno, keyword.arg))

    assert invalid == []
