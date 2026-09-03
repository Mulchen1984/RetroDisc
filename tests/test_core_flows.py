"""Regressionstests für die reparierten Kernabläufe."""

from __future__ import annotations

import ast
import importlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.config.presets import ALL_PRESETS
from src.config.settings import AppSettings
from src.core.downloader import Downloader, DownloadError
from retrodisc_launcher import RetroDiscBridge, get_splash_url


PROJECT_ROOT = Path(__file__).parent.parent
UI_FILE = PROJECT_ROOT / "src" / "ui" / "app.html"
SPLASH_FILE = PROJECT_ROOT / "src" / "ui" / "splash.html"


def test_download_url_validation():
    assert Downloader.validate_url("  https://example.com/video  ") == "https://example.com/video"
    for invalid in ("", "youtube.com/watch?v=x", "file:///tmp/video.mp4", "javascript:alert(1)"):
        with pytest.raises(DownloadError):
            Downloader.validate_url(invalid)


def test_download_command_uses_selected_quality_and_bundled_ffmpeg(tmp_path):
    downloader = Downloader(
        ytdlp_path=str(PROJECT_ROOT / "vendor" / "yt-dlp.exe"),
        ffmpeg_path=str(PROJECT_ROOT / "vendor" / "ffmpeg.exe"),
        output_dir=tmp_path,
    )
    cmd = downloader._build_download_command(
        url="https://example.com/video",
        format="720p",
        output_template=None,
        extract_audio=False,
        audio_format="mp3",
        audio_quality="320k",
        subtitles=True,
        subtitle_langs="de,en",
    )
    assert cmd[0].endswith("yt-dlp.exe")
    assert "bestvideo[height<=720]+bestaudio/best[height<=720]" in cmd
    assert "--ffmpeg-location" in cmd
    assert "--write-sub" in cmd
    assert cmd[-1] == "https://example.com/video"


def test_audio_download_command_selects_audio_and_format(tmp_path):
    downloader = Downloader(ytdlp_path="yt-dlp", output_dir=tmp_path)
    cmd = downloader._build_download_command(
        url="https://example.com/audio",
        format="flac",
        output_template=None,
        extract_audio=True,
        audio_format="flac",
        audio_quality="320k",
        subtitles=False,
        subtitle_langs="de,en",
    )
    assert "bestaudio/best" in cmd
    assert cmd[cmd.index("--audio-format") + 1] == "flac"
    assert "--write-sub" not in cmd


def test_ui_download_controls_are_addressable_and_url_is_editable():
    html = UI_FILE.read_text(encoding="utf-8")
    assert 'type="text" id="urlinp"' in html
    assert 'id="downloadQuality"' in html
    assert 'id="downloadSubtitles"' in html
    assert "a.download_url(u,quality,audioOnly,subtitles)" in html


def test_convert_icon_shows_two_complete_non_overlapping_discs():
    html = UI_FILE.read_text(encoding="utf-8")
    convert_button = re.search(
        r'<div class="cbtn" onclick="openFlow\(\'convert\'\)">(.*?)</svg>',
        html,
        re.DOTALL,
    )
    assert convert_button, "Konvertieren-Button fehlt"

    groups = re.findall(
        r'<g transform="translate\(([\d.]+),([\d.]+)\)">\s*'
        r'<ellipse cx="0" cy="0" rx="([\d.]+)" ry="([\d.]+)"',
        convert_button.group(1),
    )
    assert len(groups) == 2
    discs = [tuple(map(float, group)) for group in groups]
    stroke_half = 0.75

    for x, y, rx, ry in discs:
        assert x - rx - stroke_half >= 0
        assert x + rx + stroke_half <= 92
        assert y - ry - stroke_half >= 0
        assert y + ry + stroke_half <= 80

    left, right = sorted(discs)
    assert left[0] + left[2] + stroke_half < right[0] - right[2] - stroke_half


def test_ui_preset_values_exist_in_backend():
    html = UI_FILE.read_text(encoding="utf-8")
    select = re.search(r'<select id="presetSel".*?</select>', html, re.DOTALL)
    assert select, "presetSel fehlt"
    ui_presets = set(re.findall(r'<option value="([^"]+)"', select.group(0)))
    backend_presets = {preset.name for preset in ALL_PRESETS}
    assert ui_presets <= backend_presets


def test_all_ui_bridge_calls_are_exposed_by_retrodisc_api():
    """Every direct JavaScript bridge call must exist on the slim proxy."""
    html = UI_FILE.read_text(encoding="utf-8")
    launcher = (PROJECT_ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")
    module = ast.parse(launcher)
    api_class = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "RetroDiscApi"
    )
    exposed = {
        node.name for node in api_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    called = set(re.findall(
        r"\b(?:a|api\(\)|window\.pywebview\.api)\.([A-Za-z_]\w*)\s*\(",
        html,
    ))
    assert called <= exposed, f"Nicht exponierte Bridge-Aufrufe: {sorted(called - exposed)}"


def test_ui_has_no_duplicate_functions_or_simulated_job_fallbacks():
    """Duplicate declarations previously shadowed startup and caused recursion."""
    html = UI_FILE.read_text(encoding="utf-8")
    functions = re.findall(
        r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", html
    )
    duplicates = sorted({name for name in functions if functions.count(name) > 1})
    assert not duplicates, f"Doppelte JavaScript-Funktionen: {duplicates}"
    for forbidden in ("_origStartup", "Math.random()", "addJob(", "(Demo)"):
        assert forbidden not in html, f"Simulierter oder toter UI-Pfad gefunden: {forbidden}"


def test_ui_has_no_removed_dvd_menu_or_unsupported_search_burn_hooks():
    html = UI_FILE.read_text(encoding="utf-8")
    for forbidden in (
        "updateMenuPreview()", "burnSelectedResults", "burnSelBtn", "chkSound",
        "ISO-Image (1:1 Kopie)", "S.jobs=S.jobs.filter(j=>j.state==='running');",
    ):
        assert forbidden not in html, f"Toter oder nicht verdrahteter UI-Pfad gefunden: {forbidden}"
    launcher = (PROJECT_ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")
    for forbidden in ("get_dvd_menu_templates", "set_dvd_menu", "self._dvd_menu"):
        assert forbidden not in launcher, f"Tote DVD-Menü-API gefunden: {forbidden}"


def test_whisper_runtime_dependency_is_declared_packaged_and_importable():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^requests(?:[<>=!~].*)?(?:\s+#.*)?$", requirements, re.MULTILINE)

    setup_tree = ast.parse((PROJECT_ROOT / "setup.py").read_text(encoding="utf-8"))
    setup_call = next(
        node.value
        for node in setup_tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", None) == "setup"
    )
    install_requires = ast.literal_eval(next(
        keyword.value for keyword in setup_call.keywords
        if keyword.arg == "install_requires"
    ))
    assert any(dependency.startswith("faster-whisper") for dependency in install_requires)
    assert any(dependency.startswith("requests") for dependency in install_requires)

    build_tree = ast.parse((PROJECT_ROOT / "build.py").read_text(encoding="utf-8"))
    runtime_deps = next(
        ast.literal_eval(node.value)
        for node in build_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RUNTIME_DEPS" for target in node.targets)
    )
    assert "requests" in runtime_deps

    spec = (PROJECT_ROOT / "retrodisc_final.spec").read_text(encoding="utf-8")
    assert re.search(r'"requests"', spec)
    assert importlib.import_module("requests")
    assert importlib.import_module("faster_whisper")


def test_bridge_dynamic_jobs_submit_distinct_per_job_handlers():
    bridge = object.__new__(RetroDiscBridge)
    captured = []
    bridge.converter = SimpleNamespace()
    bridge.downloader = SimpleNamespace(validate_url=lambda url: url)
    bridge._submit_job = lambda job, handler: (
        captured.append((job, handler)) or json.dumps({"job_id": job.id})
    )

    source = PROJECT_ROOT / "tests" / "fixtures" / "test_video.mp4"
    assert "job_id" in json.loads(bridge.convert_file(str(source), "mp4_h264_1080p"))
    assert "job_id" in json.loads(bridge.download_url("https://example.com/video"))

    assert len(captured) == 2
    assert captured[0][0].id != captured[1][0].id
    assert captured[0][1] is not captured[1][1]

    launcher = (PROJECT_ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")
    module = ast.parse(launcher)
    bridge_class = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "RetroDiscBridge"
    )
    watch_method = next(
        node for node in bridge_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "set_watch_folder"
    )
    watch_source = ast.get_source_segment(launcher, watch_method)
    assert "await self.pipeline.submit(job, handler=handler)" in watch_source


def test_bridge_save_settings_merges_and_applies_runtime_dependencies(tmp_path):
    bridge = object.__new__(RetroDiscBridge)
    bridge.settings = AppSettings()
    bridge.settings.tools.mkisofs = "preserve-mkisofs"
    bridge.ffmpeg = SimpleNamespace(ffmpeg_path="old-ffmpeg", ffprobe_path="old-ffprobe")
    bridge.converter = SimpleNamespace(output_dir=None)
    bridge.downloader = SimpleNamespace(ytdlp_path="old-ytdlp", ffmpeg_path="old-ffmpeg", output_dir=None)
    bridge.disc = SimpleNamespace(
        dvdauthor="old-dvdauthor", mkisofs="old-mkisofs",
        growisofs="old-growisofs", cdrecord="old-cdrecord",
    )
    bridge.pipeline = SimpleNamespace(max_concurrent=99)

    payload = {
        "tools": {
            "ffmpeg": "new-ffmpeg",
            "ffprobe": "new-ffprobe",
            "ytdlp": "new-ytdlp",
            "dvdauthor": "new-dvdauthor",
        },
        "directories": {
            "output_dir": str(tmp_path / "output"),
            "download_dir": str(tmp_path / "downloads"),
        },
    }
    with patch.object(AppSettings, "save", autospec=True) as save_mock:
        result = json.loads(bridge.save_settings(json.dumps(payload)))

    assert result == {"ok": True}
    save_mock.assert_called_once()
    assert bridge.settings.tools.mkisofs == "preserve-mkisofs"
    assert bridge.ffmpeg.ffmpeg_path == "new-ffmpeg"
    assert bridge.ffmpeg.ffprobe_path == "new-ffprobe"
    assert bridge.converter.output_dir == tmp_path / "output"
    assert bridge.downloader.ytdlp_path == "new-ytdlp"
    assert bridge.downloader.ffmpeg_path == "new-ffmpeg"
    assert bridge.downloader.output_dir == tmp_path / "downloads"
    assert bridge.disc.dvdauthor == "new-dvdauthor"
    assert bridge.disc.mkisofs == "preserve-mkisofs"


def test_startup_branding_is_embedded_and_bridge_can_finish_splash():
    html = SPLASH_FILE.read_text(encoding="utf-8")
    assert get_splash_url().startswith("file:///")
    assert "../../assets/retrodisc_startup.png" in html
    assert "splash_complete" in html

    launcher = (PROJECT_ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")
    assert "def splash_complete(self): return self._bridge.splash_complete()" in launcher
    assert "self.window.load_html(html_content)" in launcher
    assert (PROJECT_ROOT / "assets" / "retrodisc_startup.png").is_file()


def test_splash_transition_returns_before_replacing_the_document(monkeypatch):
    scheduled = []

    class FakeWindow:
        loaded_html = None

        def load_html(self, html):
            self.loaded_html = html

    class FakeTimer:
        daemon = False

        def __init__(self, interval, callback):
            self.interval = interval
            self.callback = callback
            scheduled.append(self)

        def start(self):
            pass

    bridge = RetroDiscBridge.__new__(RetroDiscBridge)
    bridge.window = FakeWindow()
    bridge._splash_transition_started = False
    monkeypatch.setattr("retrodisc_launcher.threading.Timer", FakeTimer)

    assert json.loads(bridge.splash_complete()) == {"ok": True}
    assert bridge.window.loaded_html is None
    assert len(scheduled) == 1
    assert scheduled[0].interval > 0
    assert scheduled[0].daemon is True

    scheduled[0].callback()
    assert "<!DOCTYPE html>" in bridge.window.loaded_html

    assert json.loads(bridge.splash_complete()) == {"ok": True}
    assert len(scheduled) == 1
