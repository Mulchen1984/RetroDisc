import os
import sys
from pathlib import Path
from types import SimpleNamespace

from src.config.settings import AppSettings
from src.services.voice import LocalVoice
from scripts.caption_burn_acceptance import run


def test_redirected_windows_localappdata(tmp_path,monkeypatch):
    monkeypatch.setattr('platform.system',lambda:'Windows')
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'Redirected Local'))
    assert AppSettings._default_config_path()==tmp_path/'Redirected Local/RetroDisc/settings.json'


def test_windows_tts_does_not_probe_apple(monkeypatch):
    monkeypatch.setattr(sys,'platform','win32')
    monkeypatch.setattr('shutil.which',lambda _: (_ for _ in ()).throw(AssertionError('No Apple tool lookup on Windows')))
    caps=LocalVoice.capability()
    assert not caps['available'] and caps['engine']=='unavailable'


def test_caption_without_libass_is_unavailable(tmp_path,monkeypatch):
    monkeypatch.setattr('subprocess.run',lambda *a,**k:SimpleNamespace(stdout=' TS scale V->V Scale'))
    assert run('ffmpeg','ffprobe',tmp_path)['status']=='CAPABILITY_UNAVAILABLE'
    assert not list(tmp_path.iterdir())


def test_windows_spec_packages_shared_runtime():
    spec=Path('retrodisc_final.spec').read_text()
    for name in ('faster_whisper','ctranslate2','tokenizers','yt_dlp','webview.platforms.edgechromium',
                 'webview.platforms.winforms','ffmpeg.exe','ffprobe.exe','whisper-base'):
        assert name in spec
    assert 'collect_submodules("src")' in spec
    assert 'raise SystemExit(f"Required runtime missing:' in spec
    import pkgutil,src
    modules={m.name for m in pkgutil.walk_packages(src.__path__,prefix='src.')}
    assert {'src.services.director','src.services.smart_edit','src.services.restoration',
            'src.services.translation','src.services.voice','src.services.subtitle','src.utils.package_check'}<=modules
