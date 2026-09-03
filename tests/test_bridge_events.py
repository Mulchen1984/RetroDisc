"""Regression tests for best-effort UI event delivery."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from types import SimpleNamespace

from retrodisc_launcher import RetroDiscBridge


def test_launcher_stdlib_logger_has_no_structlog_keyword_arguments():
    source_path = Path(__file__).parents[1] / "retrodisc_launcher.py"
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


def test_emit_does_not_propagate_disconnected_webview(caplog):
    class ClosedWindow:
        def evaluate_js(self, _script):
            raise RuntimeError("WebView wurde geschlossen")

    bridge = object.__new__(RetroDiscBridge)
    bridge.window = ClosedWindow()

    with caplog.at_level(logging.WARNING, logger="retrodisc"):
        bridge._emit("job_done", {"id": "job-1"})

    assert "job_done" in caplog.text
    assert "WebView wurde geschlossen" in caplog.text


def test_submit_job_succeeds_when_queue_event_cannot_reach_window():
    class ClosedWindow:
        def evaluate_js(self, _script):
            raise RuntimeError("WebView wurde geschlossen")

    class CompletedFuture:
        def result(self, timeout=None):
            return "job-1"

    class PipelineStub:
        _is_running = True

        async def submit(self, _job, handler=None):
            return "job-1"

    def complete_without_loop(coro):
        coro.close()
        return CompletedFuture()

    bridge = object.__new__(RetroDiscBridge)
    bridge.window = ClosedWindow()
    bridge.pipeline = PipelineStub()
    bridge._async = complete_without_loop
    bridge._wire_job_progress = lambda _job: None
    job = SimpleNamespace(
        id="job-1",
        params={"display_name": "Testjob"},
        job_type=SimpleNamespace(value="convert"),
    )

    import json

    result = json.loads(bridge._submit_job(job, handler=object()))

    assert result == {"job_id": "job-1", "status": "queued"}
