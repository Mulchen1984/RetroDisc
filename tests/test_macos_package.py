"""Bundle tools must not depend on the development interpreter or PATH."""
import sys
from pathlib import Path
import retrodisc_launcher as launcher


def test_bundle_tool_priority(tmp_path,monkeypatch):
    macos=tmp_path/'RetroDisc.app/Contents/MacOS'
    vendor=tmp_path/'RetroDisc.app/Contents/Resources/vendor'
    macos.mkdir(parents=True);vendor.mkdir(parents=True)
    for path in [macos/'yt-dlp',vendor/'ffmpeg',vendor/'ffprobe']:
        path.touch()
    monkeypatch.setattr(sys,'platform','darwin')
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(macos/'RetroDisc'))
    monkeypatch.setattr(launcher,'BUNDLE_DIR',vendor.parent)
    tools=launcher.check_tools()
    assert tools=={'ytdlp':str(macos/'yt-dlp'),'ffmpeg':str(vendor/'ffmpeg'),'ffprobe':str(vendor/'ffprobe')}


def test_macos_spec_uses_shared_launcher_without_windows_vendor():
    spec=Path('retrodisc_macos.spec').read_text()
    assert 'retrodisc_launcher.py' in spec and "BUNDLE(" in spec
    assert 'ffmpeg.exe' not in spec and '/opt/homebrew' not in spec
    assert 'whisper-base' not in spec  # Models are external writable data.


def test_frozen_multiprocessing_guard_precedes_startup():
    source=Path('retrodisc_launcher.py').read_text().split('if __name__ == "__main__":')[-1]
    assert source.index('multiprocessing.freeze_support()') < source.index("'--package-check'")
