# macOS bundle using the shared production launcher; Windows spec stays independent.
import sys
import shutil
import importlib.util
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

if sys.platform != 'darwin':
    raise SystemExit('This spec requires macOS.')
root = Path(SPECPATH)
data = [(str(root/'src/ui'), 'src/ui'), (str(root/'assets'), 'assets')]
binaries = []
hidden = collect_submodules('src') + ['webview.platforms.cocoa']
for package in ('faster_whisper','ctranslate2','tokenizers','huggingface_hub','av','numpy','yt_dlp'):
    if importlib.util.find_spec(package) is None:raise SystemExit(f'Missing required package: {package}')
    d,b,h = collect_all(package)
    data += d; binaries += b; hidden += h
for tool in ('ffmpeg','ffprobe'):
    path = shutil.which(tool)
    if not path:raise SystemExit(f'{tool} missing from build PATH')
    binaries.append((path,'vendor'))
# Separate native yt-dlp entry shares the onedir libraries, no system Python required.
y = Analysis([str(root/'scripts/bundled_ytdlp.py')], pathex=[str(root)],
    hiddenimports=collect_submodules('yt_dlp'), excludes=['pytest'], noarchive=False)
yexe = EXE(PYZ(y.pure),y.scripts,exclude_binaries=True,name='yt-dlp',console=True)
a = Analysis([str(root/'retrodisc_launcher.py')],pathex=[str(root)],datas=data,binaries=binaries,
    hiddenimports=hidden,excludes=['pytest','tkinter','torch','tensorflow','PyQt5','PyQt6','PySide6'],noarchive=False)
exe = EXE(PYZ(a.pure),a.scripts,exclude_binaries=True,name='RetroDisc',console=False)
coll = COLLECT(exe,yexe,a.binaries,a.datas,y.binaries,y.datas,name='RetroDisc',strip=False,upx=False)
app = BUNDLE(coll,name='RetroDisc.app',bundle_identifier='org.retrodisc.desktop',
    info_plist={'CFBundleShortVersionString':'1.0.0','NSHighResolutionCapable':True,
                'NSMicrophoneUsageDescription':'RetroDisc verarbeitet lokal ausgewählte Medien.'})
