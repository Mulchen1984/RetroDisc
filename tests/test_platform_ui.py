"""Native desktop presentation and real directory validation."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src.utils import platform_ui
from src.config.settings import AppSettings, DirectorySettings
from retrodisc_launcher import RetroDiscBridge, RetroDiscApi

@pytest.mark.parametrize('system,version,expected',[('Darwin','15.6','macOS 15.6'),('Darwin','','macOS'),('Windows','10.0.26100','Windows (10.0.26100)'),('Windows','','Windows')])
def test_platform_bridge_uses_actual_version(monkeypatch,system,version,expected):
    monkeypatch.setattr(platform_ui.platform,'system',lambda:system)
    monkeypatch.setattr(platform_ui.platform,'mac_ver',lambda:(version,(),''))
    monkeypatch.setattr(platform_ui.platform,'version',lambda:version)
    bridge=object.__new__(RetroDiscBridge)
    api=object.__new__(RetroDiscApi);api._bridge=bridge
    assert json.loads(api.get_platform_info())['label']==expected
    assert platform_ui.native_window_options()=={'frameless':False,'resizable':True}


def test_no_fake_window_controls_and_native_frame():
    html=Path('src/ui/app.html').read_text()
    launcher=Path('retrodisc_launcher.py').read_text()
    assert '<div class="win-btn"' not in html
    assert '>Windows 11<' not in html
    assert launcher.count('**native_window_options()')==2
    assert 'id="platformLabel"' in html


def test_directory_missing_invalid_and_permissions(tmp_path,monkeypatch):
    path=tmp_path/'Grüße 日本'/'Audio'
    assert not AppSettings.validate_directory(path)['exists']
    assert not path.exists()  # Opening settings never creates arbitrary typed paths.
    AppSettings.validate_directory(path,create=True)
    assert path.is_dir()
    with pytest.raises(ValueError,match='Absoluter'):
        AppSettings.validate_directory(Path('relative'))
    file=tmp_path/'file';file.write_text('x')
    with pytest.raises(ValueError,match='Kein Verzeichnis'):
        AppSettings.validate_directory(file)
    monkeypatch.setattr('src.config.settings.tempfile.TemporaryFile',Mock(side_effect=PermissionError('read-only')))
    with pytest.raises(PermissionError,match='read-only'):
        AppSettings.validate_directory(path)


def test_all_four_user_directories_created(tmp_path):
    dirs=DirectorySettings(**{name:tmp_path/name for name in DirectorySettings.model_fields})
    AppSettings(directories=dirs).ensure_directories()
    assert all(path.is_dir() for _,path in dirs)


def test_runtime_tool_status_not_unrelated_detection(tmp_path,monkeypatch):
    bridge=object.__new__(RetroDiscBridge);bridge.settings=AppSettings()
    bridge.settings.tools.ffmpeg=str(tmp_path/'custom ffmpeg')
    monkeypatch.setattr('shutil.which',lambda p:p if p==bridge.settings.tools.ffmpeg else None)
    result=json.loads(bridge.get_tool_status())
    assert result['ffmpeg']=={'available':True,'path':bridge.settings.tools.ffmpeg}
    assert result['ffprobe']['available'] is False


@pytest.mark.parametrize('system,folder',[('Darwin','Movies'),('Windows','Videos')])
def test_platform_paths_are_home_relative(tmp_path,monkeypatch,system,folder):
    monkeypatch.setattr('src.config.settings.platform.system',lambda:system)
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    dirs=DirectorySettings()
    assert dirs.output_dir==tmp_path/folder/'RetroDisc'
    assert dirs.audio_dir==tmp_path/('Music' if system=='Darwin' else 'Videos')/'RetroDisc'


def test_menu_actions_execute_in_node(tmp_path):
    import re,subprocess,shutil
    node=shutil.which('node')
    if not node: pytest.skip('Node missing')
    html=Path('src/ui/app.html').read_text()
    source=html[html.index('function menuAction('):html.index('// ── BACKEND API BRIDGE')]
    script=tmp_path/'menus.js'
    script.write_text(source+'''
const assert=require('node:assert/strict');let opened='',help='',file=false;
function openFlow(name){opened=name} function setStat(){} function alert(s){help=s}
function openFileDialog(){file=true}
menuAction('file');assert.ok(file);
menuAction('extras');assert.equal(opened,'settings');
menuAction('help');assert.ok(help.includes('experimentell'));assert.ok(help.includes('noch nicht ausführbar'));
''')
    subprocess.run([node,str(script)],check=True,capture_output=True,text=True)
    defined=set(re.findall(r'(?:async\s+)?function\s+(\w+)\s*\(',html))
    called=set()
    for handler in re.findall(r'on(?:click|change)="([^"]*)"',html):
        called.update(re.findall(r'(?<![.\w])(\w+)\s*\(',handler))
    assert not called-defined-{'if','alert','Number','JSON','confirm'}
