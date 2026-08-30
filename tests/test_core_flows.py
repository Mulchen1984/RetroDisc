"""Regressionstests für die reparierten Kernabläufe."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from src.config.presets import ALL_PRESETS
from src.core.downloader import Downloader, DownloadError
from retrodisc_launcher import get_splash_url


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


def test_startup_branding_is_embedded_and_bridge_can_finish_splash():
    html = SPLASH_FILE.read_text(encoding="utf-8")
    assert get_splash_url().startswith("file:///")
    assert "../../assets/retrodisc_startup.png" in html
    assert "splash_complete" in html

    launcher = (PROJECT_ROOT / "retrodisc_launcher.py").read_text(encoding="utf-8")
    assert "def splash_complete(self): return self._bridge.splash_complete()" in launcher
    assert "self.window.load_html(html_content)" in launcher
    assert (PROJECT_ROOT / "assets" / "retrodisc_startup.png").is_file()
