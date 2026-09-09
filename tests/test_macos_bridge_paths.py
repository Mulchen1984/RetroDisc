"""Targeted native platform regressions without opening Finder or downloading tools."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from retrodisc_launcher import RetroDiscBridge, show_download_splash


@pytest.mark.parametrize('system', ['darwin', 'win32'])
def test_output_folder_uses_native_opener(tmp_path, monkeypatch, system):
    monkeypatch.setattr(sys, 'platform', system)
    path = tmp_path / 'Video & Grüße 日本'
    path.mkdir()
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = SimpleNamespace(directories=SimpleNamespace(output_dir=path))
    run = Mock()
    startfile = Mock()
    monkeypatch.setattr('src.utils.reveal.run_hidden', run)
    monkeypatch.setattr(os, 'startfile', startfile, raising=False)
    assert json.loads(bridge.open_output_folder()) == {'ok': True}
    if system == 'darwin':
        assert run.call_args.args == (['open', str(path.resolve())],)
        assert run.call_args.kwargs['check'] is True
        startfile.assert_not_called()
    else:
        startfile.assert_called_once_with(str(path))
        run.assert_not_called()


def test_output_folder_reports_open_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = SimpleNamespace(directories=SimpleNamespace(output_dir=tmp_path))
    monkeypatch.setattr('src.utils.reveal.run_hidden', Mock(side_effect=subprocess.TimeoutExpired('open', 10)))
    assert 'error' in json.loads(bridge.open_output_folder())


def test_macos_missing_tools_never_download_windows_exes(monkeypatch, caplog):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    download = Mock(side_effect=AssertionError('Windows download on macOS'))
    monkeypatch.setattr('retrodisc_launcher.download_tool', download)
    show_download_splash(['ffmpeg', 'ytdlp'])
    download.assert_not_called()
    assert 'Native Tools im PATH' in caplog.text


@pytest.mark.parametrize('system', ['darwin', 'win32'])
@pytest.mark.parametrize('kind', ['file', 'directory', 'missing'])
def test_actual_output_location(tmp_path, monkeypatch, system, kind):
    from retrodisc_launcher import RetroDiscApi
    monkeypatch.setattr(sys, 'platform', system)
    folder = tmp_path / 'Video & Grüße 日本'
    folder.mkdir()
    output = folder / "film ' <test> #1.mp4"
    if kind == 'file':
        output.write_bytes(b'video')
    elif kind == 'directory':
        output = folder
    run, startfile = Mock(), Mock()
    monkeypatch.setattr('src.utils.reveal.run_hidden', run)
    monkeypatch.setattr(os, 'startfile', startfile, raising=False)
    bridge = object.__new__(RetroDiscBridge)
    api = object.__new__(RetroDiscApi)
    api._bridge = bridge
    # No settings: opening an actual output must not consult the default folder.
    assert json.loads(api.open_output_folder(str(output))) == {'ok': True}
    if system == 'darwin':
        expected = ['open', '-R', str(output)] if kind == 'file' else ['open', str(folder)]
        assert run.call_args.args[0] == expected
        assert not run.call_args.kwargs.get('shell', False)
        startfile.assert_not_called()
    else:
        startfile.assert_called_once_with(str(folder))
        run.assert_not_called()


def test_completed_convert_queue_returns_final_path(tmp_path):
    from src.models.media import Job, JobType
    job = Job(job_type=JobType.CONVERT)
    job.output_path = tmp_path / 'actual converted.mp4'
    job.mark_done()
    bridge = object.__new__(RetroDiscBridge)
    bridge.pipeline = SimpleNamespace(_queue=[], _running=[], completed_jobs=[job])
    assert json.loads(bridge.get_queue())[0]['output'] == str(job.output_path)
