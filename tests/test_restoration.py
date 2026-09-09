"""Restoration filter ordering, conservative analysis, persistence and safety."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from src.models.director import MediaAsset
from src.models.restoration import RestorationAnalysis,RestorationPlan,RestorationOptions,SceneRestoration
from src.services.restoration import Restoration


def plan(order='tff'):
    a=RestorationAnalysis(asset=MediaAsset(id='source',path='source.mkv',kind='video',duration=4,width=720,height=576),
        sample_seconds=4,field_order=order,fps=25,sample_aspect_ratio='16:15',display_aspect_ratio='4:3',pixel_format='yuv420p',color_space='bt470bg',color_range='tv')
    return RestorationPlan(analysis=a,options=RestorationOptions(deinterlace=order!='progressive',field_order=order if order!='progressive' else 'auto',size='720p'))

@pytest.mark.parametrize('order',['tff','bff'])
def test_pal_deinterlace_preserves_fields_and_anamorphic_aspect(order):
    p=plan(order);filters=Restoration.filters(p)
    assert filters[0]==f'bwdif=mode=send_field:parity={order}:deint=all'
    assert filters.index(next(f for f in filters if f.startswith('hqdn3d')))<filters.index(next(f for f in filters if f.startswith('unsharp')))
    assert 'dar' in filters[-3] and filters[-2]=='setsar=1'
    assert filters[-1]=='pad=1280:720:(ow-iw)/2:(oh-ih)/2'


def test_progressive_not_deinterlaced_and_original_sar_preserved():
    p=plan('progressive');p.options.size='original'
    filters=Restoration.filters(p)
    assert not any(f.startswith(('bwdif','yadif','scale','setsar','fps')) for f in filters)

@pytest.mark.parametrize('preset,luma,chroma',[('natural',.7,1.5),('balanced',1.5,3),('strong',3,5)])
def test_noise_presets_separate_luma_chroma(preset,luma,chroma):
    p=plan();p.preset=preset
    f=next(f for f in Restoration.filters(p) if f.startswith('hqdn3d'))
    values=list(map(float,f.split('=')[1].split(':')))
    assert values[:2]==[luma,chroma]
    p.options.denoise=False
    assert not any(f.startswith('hqdn3d') for f in Restoration.filters(p))


def test_conflicting_field_order_is_not_guessed():
    assert Restoration.field_order({'field_order':'tt'},{'bff':50,'tff':0})=='unknown'
    assert Restoration.field_order({}, {'tff':50,'progressive':1})=='tff'
    assert Restoration.field_order({}, {})=='unknown'


def test_save_load_and_scene_provider_boundary(tmp_path):
    service=Restoration(SimpleNamespace(db_path=tmp_path/'library.db'),None,tmp_path/'out',tmp_path/'temp')
    p=plan();p.source_sha256='abc';p.filters=Restoration.filters(p)
    service.save(p)
    assert service.load(p.id)==p
    with pytest.raises(ValueError):service.load('../../settings')
    with pytest.raises(ValidationError):SceneRestoration(start=2,end=1,options=RestorationOptions())
    with pytest.raises(ValidationError):RestorationOptions(size='4K')
    with pytest.raises(ValidationError):RestorationPlan.model_validate(p.model_dump()|{'provider':'fake_ai'})


@pytest.mark.asyncio
async def test_source_deleted_fails_without_output(tmp_path):
    service=Restoration(SimpleNamespace(db_path=tmp_path/'library.db'),None,tmp_path/'out',tmp_path/'temp')
    with pytest.raises(FileNotFoundError,match='Quelle fehlt'):
        await service.render(plan())
    assert not (tmp_path/'out').exists()


@pytest.mark.asyncio
async def test_capabilities_understand_current_and_older_ffmpeg_flags(tmp_path):
    service=Restoration(SimpleNamespace(db_path=tmp_path/'library.db'),None,tmp_path/'out',tmp_path/'temp')
    service._run=AsyncMock(return_value=(' TS bwdif V->V\n T.. hqdn3d V->V\n ... vidstabdetect V->V\n ... vidstabtransform V->V',''))
    caps=await service.capabilities()
    assert caps['stabilization']['available']
    assert {'bwdif','hqdn3d'}<=set(caps['filters'])
    assert all(not p['available'] for p in caps['providers'].values())


def test_ui_uses_existing_recent_handoffs_and_has_real_handlers():
    html=Path('src/ui/app.html').read_text()
    assert 'id="tab-restore"' in html
    assert 'restoration_process(p,preview)' in html
    assert 'restoration_play(' in html
    assert "restore:'Restaurierung'" in html
    assert 'strong">Stark – möglicher Detailverlust' in html


@pytest.mark.asyncio
async def test_analyzer_reads_last_idet_report(tmp_path):
    source=tmp_path/'source.mkv';source.write_bytes(b'source')
    asset=MediaAsset(id='source',path=str(source),kind='video',duration=4,width=720,height=576)
    lib=SimpleNamespace(db_path=tmp_path/'lib.db',asset=AsyncMock(return_value=asset))
    service=Restoration(lib,None,tmp_path/'out',tmp_path/'temp')
    raw=json.dumps({'streams':[{'codec_type':'video','avg_frame_rate':'25/1','field_order':'unknown'}]})
    stats='Multi frame detection: TFF: 0 BFF: 0 Progressive: 0 Undetermined: 0\nMulti frame detection: TFF: 100 BFF: 0 Progressive: 0 Undetermined: 0\nlavfi.signalstats.YAVG=70'
    service._run=AsyncMock(side_effect=[(raw,''),('',stats),('','lavfi.signalstats.YAVG=1'),(' TS bwdif V->V','')])
    result=await service.analyze(source)
    assert result.analysis.field_order=='tff' and result.options.deinterlace
    assert result.analysis.levels['YAVG']==70
    assert result.analysis.source_size==6


@pytest.mark.asyncio
async def test_existing_output_is_never_deleted(tmp_path,monkeypatch):
    source=tmp_path/'source.mkv';source.write_bytes(b'original')
    p=plan();p.analysis.asset.path=str(source)
    lib=SimpleNamespace(db_path=tmp_path/'lib.db',asset=AsyncMock(return_value=p.analysis.asset))
    service=Restoration(lib,None,tmp_path/'out',tmp_path/'temp')
    service.capabilities=AsyncMock(return_value={'filters':['bwdif','hqdn3d','eq','unsharp','scale','setsar','pad'],'stabilization':{'available':False}})
    monkeypatch.setattr('src.services.restoration.uuid.uuid4',lambda:SimpleNamespace(hex='0'*32))
    service.output_dir.mkdir();output=service.output_dir/f'Restored_{p.id[:8]}_00000000.mp4';output.write_bytes(b'keep')
    with pytest.raises(FileExistsError):await service.render(p)
    assert output.read_bytes()==b'keep' and source.read_bytes()==b'original'


@pytest.mark.parametrize('platform',['darwin','win32'])
def test_preview_uses_native_player_on_each_platform(tmp_path,monkeypatch,platform):
    import os,sys
    from unittest.mock import Mock
    from retrodisc_launcher import RetroDiscBridge,RetroDiscApi
    video=tmp_path/'Preview 日本.mp4';video.write_bytes(b'preview')
    bridge=object.__new__(RetroDiscBridge)
    bridge._restoration_service=lambda:SimpleNamespace(load=lambda _:SimpleNamespace(preview=[str(video),str(video)]))
    api=object.__new__(RetroDiscApi);api._bridge=bridge
    monkeypatch.setattr(sys,'platform',platform)
    run=Mock();startfile=Mock()
    monkeypatch.setattr('src.utils.subprocesses.run_hidden',run)
    monkeypatch.setattr(os,'startfile',startfile,raising=False)
    assert json.loads(api.restoration_play('project',1))=={'ok':True}
    if platform=='darwin':run.assert_called_once_with(['open',str(video)],check=True,timeout=10);startfile.assert_not_called()
    else:startfile.assert_called_once_with(str(video));run.assert_not_called()


@pytest.mark.parametrize('stream,expected',[
    ({'avg_frame_rate':'0/0','r_frame_rate':'25/1'},25),
    ({'avg_frame_rate':'N/A','r_frame_rate':'30000/1001'},30000/1001),
    ({'avg_frame_rate':'50/1','r_frame_rate':'25/1'},50),
])
def test_frame_rate_fallback_is_real_metadata(stream,expected):
    assert Restoration.frame_rate(stream)==expected


def test_unknown_frame_rate_reports_clear_error():
    with pytest.raises(ValueError,match='Bildrate'):
        Restoration.frame_rate({'avg_frame_rate':'0/0','r_frame_rate':'0/0'})


def test_preview_must_match_plan_and_exist(tmp_path):
    p=plan()
    previews=[tmp_path/'original.mp4',tmp_path/'restored.mp4']
    for path in previews:path.write_bytes(b'preview')
    p.preview=list(map(str,previews));p.preview_signature=Restoration.preview_signature(p)
    Restoration.check_preview(p)
    p.notes.append('Unrelated review note')
    Restoration.check_preview(p)
    p.preset='strong'
    with pytest.raises(ValueError,match='neue Vorschau'):Restoration.check_preview(p)
    p.preset='natural';previews[1].unlink()
    with pytest.raises(ValueError,match='Vorschau'):Restoration.check_preview(p)


def test_build_report_covers_mission3_sections(tmp_path):
    p=plan();p.preset='balanced'
    p.analysis.asset.path=str(tmp_path/'clip.mkv');p.analysis.noise_proxy={'YAVG':2.0}
    p.scenes=[SceneRestoration(start=0,end=2,options=p.options.model_copy(deep=True),denoise_strength=(1.2,2.8,1.5,3.0))]
    p.filters=Restoration.filters(p)
    actual=SimpleNamespace(width=720,height=576,duration=4.0,video_codec='mpeg2video',audio_codec='pcm_s16le')
    info=SimpleNamespace(video_streams=[SimpleNamespace(codec='h264',width=1280,height=720,fps=25.0)],
        audio_streams=[SimpleNamespace(codec='aac')],duration_seconds=4.0)
    out=tmp_path/'out.mp4';out.write_bytes(b'0'*1234)
    report=Restoration.build_report(p,actual,info,'src_hash',out,'out_hash')
    assert set(report)=={'source','analysis','processing','result','integrity'}
    assert report['source']['filename']=='clip.mkv' and report['source']['scan']=='interlaced'
    assert report['source']['video_codec']=='mpeg2video' and report['source']['audio_codec']=='pcm_s16le'
    assert report['analysis']['scenes']==1 and report['analysis']['selected_preset']=='balanced'
    assert report['processing']['deinterlace']=='bwdif' and report['processing']['scene_adaptive'] is True
    assert report['processing']['upscale']=='720p'
    assert report['result']['resolution']==[1280,720] and report['result']['filesize']==1234
    assert report['result']['video_codec']=='h264' and report['result']['audio_codec']=='aac'
    assert report['integrity']=={'source_sha256':'src_hash','output_sha256':'out_hash','source_unchanged':True}
    # No invented quality score anywhere.
    assert not any('score' in k or 'percent' in k or 'quality' in k for section in report.values() for k in section)


def test_collect_sources_expands_folder_dedups_and_filters(tmp_path):
    (tmp_path/'a.mp4').write_bytes(b'a');(tmp_path/'b.mkv').write_bytes(b'b')
    (tmp_path/'note.txt').write_bytes(b'x')
    folder=tmp_path/'more';folder.mkdir();(folder/'c.mov').write_bytes(b'c')
    sources=Restoration.collect_sources([tmp_path/'a.mp4',folder,tmp_path/'a.mp4'])
    names=[s.name for s in sources]
    assert names==['a.mp4','c.mov']  # folder expanded, non-video skipped, duplicate a.mp4 dropped


@pytest.mark.asyncio
async def test_batch_error_does_not_stop_queue(tmp_path):
    service=Restoration(SimpleNamespace(db_path=tmp_path/'library.db'),None,tmp_path/'out',tmp_path/'temp')
    for name in ('good1.mp4','bad.mp4','good2.mp4'):(tmp_path/name).write_bytes(b'v')
    scenes_called=[]
    async def fake_analyze(path,job=None):
        if 'bad' in str(path):raise RuntimeError('kaputt')
        p=plan('progressive');p.analysis.asset.path=str(path);return p
    async def fake_scenes(pl,job=None):scenes_called.append(pl);return pl
    async def fake_render(pl,preview=False,encoder='auto',job=None):
        pl.outputs.append(str(tmp_path/'out'/(Path(pl.analysis.asset.path).stem+'.mp4')))
        pl.report={'result':{'path':pl.outputs[-1]}};return pl
    service.analyze,service.analyze_scenes,service.render=fake_analyze,fake_scenes,fake_render
    seen=[]
    results=await service.batch([tmp_path/'good1.mp4',tmp_path/'bad.mp4',tmp_path/'good2.mp4'],
        adaptive=True,size='720p',on_item=lambda i,e,n:seen.append(e['status']))
    assert [r['status'] for r in results]==['done','error','done']
    assert results[1]['error']=='kaputt' and results[1]['output'] is None
    assert results[0]['output'] and results[2]['output']
    assert len(scenes_called)==2  # adaptive scene analysis ran for both good files, skipped the failed one
    assert seen==['done','error','done']  # progress callback fired per file


@pytest.mark.asyncio
async def test_source_change_during_analysis_requires_new_analysis(tmp_path):
    source=tmp_path/'source.mkv';source.write_bytes(b'original')
    asset=MediaAsset(id='source',path=str(source),kind='video',duration=4,width=720,height=576)
    lib=SimpleNamespace(db_path=tmp_path/'lib.db',asset=AsyncMock(return_value=asset))
    service=Restoration(lib,None,tmp_path/'out',tmp_path/'temp')
    calls=0
    async def run(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==1:
            return json.dumps({'streams':[{'codec_type':'video','avg_frame_rate':'25/1'}]}),''
        if calls==3:source.write_bytes(b'changed source')
        return '',''
    service._run=run
    with pytest.raises(ValueError,match='während der Analyse verändert'):
        await service.analyze(source)
    assert not service.projects_dir.exists()
