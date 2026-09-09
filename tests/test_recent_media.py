"""Recent job outputs use the existing SQLite library and real shipped UI functions."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.media import Job, JobState, JobType
from src.services.library import MediaLibrary
from retrodisc_launcher import RetroDiscBridge


@pytest.fixture
def bridge(tmp_path):
    lib = MediaLibrary(db_path=tmp_path / 'library.db')
    lib.open()
    b = object.__new__(RetroDiscBridge)
    b.library = lib
    b.settings = SimpleNamespace(sound=SimpleNamespace(play_on_complete=False),
                                 directories=SimpleNamespace(temp_dir=tmp_path / 'processing'))
    b._emit = lambda *args: None
    yield b
    lib.close()


def complete(bridge, tmp_path, filename, kind=JobType.DOWNLOAD, state=JobState.DONE):
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'media')
    job = Job(job_type=kind, output_path=path, state=state)
    bridge._on_complete(job)
    return path


def test_download_convert_burn_and_rip_share_outputs(bridge, tmp_path):
    video = complete(bridge, tmp_path, 'download.mkv')
    row = json.loads(bridge.get_recent_media())[0]
    assert row['path'] == str(video) and row['can_convert'] and row['can_burn']
    assert row['operation'] == 'download'
    converted = complete(bridge, tmp_path, 'converted.mp4', JobType.CONVERT)
    assert json.loads(bridge.get_recent_media())[0]['path'] == str(converted)
    ripped = complete(bridge, tmp_path, 'rip.webm', JobType.RIP_DVD)
    row = json.loads(bridge.get_recent_media())[0]
    assert row['path'] == str(ripped) and row['operation'] == 'rip'
    assert row['can_convert'] and row['can_burn']


def test_audio_extraction_is_recorded_but_never_proposed_for_dvd(bridge, tmp_path):
    video, audio = tmp_path / 'video.mkv', tmp_path / 'audio.mp3'
    video.write_bytes(b'video')
    audio.write_bytes(b'audio')
    job = Job(job_type=JobType.DOWNLOAD, state=JobState.DONE, output_path=video,
              params={'output_paths':[str(video),str(audio)]})
    bridge._on_complete(job)
    rows = json.loads(bridge.get_recent_media())
    assert len(rows) == 2
    a = next(r for r in rows if r['type']=='audio')
    assert a['operation']=='extract_audio' and a['can_convert'] and not a['can_burn']


@pytest.mark.parametrize('state',[JobState.FAILED,JobState.CANCELLED,JobState.RUNNING])
def test_unsuccessful_outputs_never_registered(bridge, tmp_path, state):
    complete(bridge,tmp_path,'failed.mp4',state=state)
    assert json.loads(bridge.get_recent_media()) == []


def test_internal_missing_partial_files_and_restart_pruning(bridge,tmp_path):
    for filename in ['processing/work.mp4','.retrodisc-dl-test/work.mp4','video.mp4.part','.video.retrodisc-abc.mp4']:
        complete(bridge,tmp_path,filename)
    bridge._on_complete(Job(state=JobState.DONE,output_path=tmp_path/'missing.mp4'))
    assert bridge.library.recent_outputs()==[]
    keep=complete(bridge,tmp_path,'keep.mp4')
    remove=complete(bridge,tmp_path,'remove.mp4')
    bridge.library.close()
    remove.unlink()
    bridge.library.open()
    assert [r['path'] for r in bridge.library.recent_outputs()]==[str(keep)]


def test_history_is_bounded_deduplicated_and_persistent(bridge,tmp_path):
    for i in range(12):
        complete(bridge,tmp_path,f'{i}.mp4')
    complete(bridge,tmp_path,'11.mp4')
    bridge.library.close()
    bridge.library.open()
    rows=bridge.library.recent_outputs()
    assert len(rows)==10 and rows[0]['filename']=='11.mp4'
    assert all(r['created_at'] for r in rows)


def test_unsupported_video_can_be_converted_before_burning(bridge,tmp_path):
    complete(bridge,tmp_path,'video.ogv')
    row=json.loads(bridge.get_recent_media())[0]
    assert row['can_convert'] and not row['can_burn']
    complete(bridge,tmp_path,'disc.iso')
    row=json.loads(bridge.get_recent_media())[0]
    assert not row['can_convert'] and not row['can_burn']


@pytest.mark.skipif(not shutil.which('node'),reason='Node required for shipped UI functions')
def test_ui_handoffs_manual_selection_audio_and_escaping(tmp_path):
    html=Path('src/ui/app.html').read_text()
    functions=html[html.index('async function refreshRecentMedia()'):html.index('async function loadEncoderOptions()')]
    helpers='\n'.join(re.search(r'function '+name+r'\(s\)\{[^\n]+\}',html).group() for name in ['escHtml','escAttr'])
    script=tmp_path/'recent.js'
    helpers += '\n' + html[html.index('function revealOutputButton('):html.index('async function openOutputFolder(')]
    script.write_text(helpers+'\n'+functions+'''\n
const assert=require('node:assert/strict');
const title='日本 <img src=x onerror="fail()"> & film';
const video={path:'/Movies/'+title+'.mkv',filename:title+'.mkv',type:'video',operation:'download',can_convert:true,can_burn:true};
const audio={path:'/Music/audio.mp3',filename:'audio.mp3',type:'audio',operation:'extract_audio',can_convert:true,can_burn:false};
let rows=[audio,video];
const elements={'presetSel':{value:'video'},'recent-convert':{style:{}},'recent-burn':{style:{}}};
const document={getElementById:id=>elements[id]};
const S={files:[{path:'/manual.mp4'}],selFile:0,presets:[{id:'video',media_type:'video'},{id:'audio',media_type:'audio'}]};
function api(){return {get_recent_media:async()=>JSON.stringify(rows)}}
function renderFiles(){}
function showTab(name){S.tab=name}
function setStat(message){S.status=message}
async function loadPresetsFromBackend(){}
function onPresetChange(){}
(async()=>{
 await refreshRecentMedia();
 assert.equal(S.files[0].path,'/manual.mp4');
 assert.equal(recentCandidate('convert').path,video.path);
 assert.equal(recentCandidate('burn').path,video.path);
 assert.ok(elements['recent-convert'].innerHTML.includes('&lt;img'));
 assert.ok(!elements['recent-convert'].innerHTML.includes('<img'));
 assert.ok(elements['recent-convert'].innerHTML.includes('overflow-wrap:anywhere'));
 assert.ok(elements['recent-convert'].innerHTML.includes('openOutputFolder(this.dataset.path)'));
 assert.ok(elements['recent-convert'].innerHTML.includes(escAttr(video.path)));
 await useRecentMedia({dataset:{path:video.path,target:'convert'}});
 assert.equal(S.files[0].path,video.path);
 assert.equal(S.tab,'convert');
 elements.presetSel.value='audio';renderRecentMedia();
 assert.equal(recentCandidate('convert').path,audio.path);
 const converted={...video,path:'/Movies/converted.mp4',filename:'converted.mp4',operation:'convert'};
 rows=[converted,...rows];await refreshRecentMedia();
 assert.equal(recentCandidate('burn').path,converted.path);
 await useRecentMedia({dataset:{path:converted.path,target:'burn'}});
 assert.deepEqual(S.files.map(f=>f.path),[converted.path]);
 assert.equal(S.tab,'burn');
 rows=[];await useRecentMedia({dataset:{path:video.path,target:'convert'}});
 assert.equal(S.files[0].path,converted.path);
 assert.ok(S.status.includes('nicht mehr verfügbar'));
 rows=[{...video,can_burn:false}];await refreshRecentMedia();
 assert.ok(elements['recent-burn'].innerHTML.includes('Vor dem Brennen konvertieren'));
 await useRecentMedia({dataset:{path:video.path,target:'convert',convertFirst:'true'}});
 assert.equal(elements.presetSel.value,'mp4_h264_1080p');
})().catch(e=>{console.error(e);process.exit(1)});
''')
    subprocess.run(['node',str(script)],check=True,capture_output=True,text=True,timeout=10)


@pytest.mark.asyncio
async def test_real_pipeline_completion_registers_only_success(bridge,tmp_path):
    import asyncio
    from src.core.pipeline import Pipeline
    pipeline=Pipeline(play_sound=False)
    pipeline.on_job_complete=bridge._on_complete
    done=asyncio.Event()
    pipeline.on_queue_empty=done.set
    async def handler(job):
        job.output_path=tmp_path/f'{job.id}.mp4'
        job.output_path.write_bytes(b'produced')
        if job.params.get('fail'):
            raise RuntimeError('failed after writing partial output')
    success=Job(job_type=JobType.CONVERT)
    failure=Job(job_type=JobType.CONVERT,params={'fail':True})
    await pipeline.submit(success,handler)
    await pipeline.submit(failure,handler)
    runner=asyncio.create_task(pipeline.start())
    try:
        await asyncio.wait_for(done.wait(),timeout=5)
        assert [r['path'] for r in bridge.library.recent_outputs()]==[str(success.output_path)]
    finally:
        await pipeline.shutdown()
        await runner
