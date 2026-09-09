"""Director plans, asset reuse and optional capabilities without model downloads."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from src.models.director import ProductionProject
from src.models.media import MediaFile,MediaType,VideoStream,AudioStream,Job,JobType,JobState
from src.services.director import Director
from src.services.library import MediaLibrary
from src.services.subtitle import SubtitleGenerator
from src.services.voice import LocalVoice


@pytest.fixture
def studio(tmp_path):
    async def probe(path):
        return MediaFile(path=Path(path),media_type=MediaType.VIDEO,container='mov,mp4',duration_seconds=10,
            file_size_bytes=1,video_streams=[VideoStream(0,'h264',1280,720,30)],
            audio_streams=[AudioStream(1,'aac',2,48000)])
    ff=SimpleNamespace(probe=AsyncMock(side_effect=probe),convert=AsyncMock())
    lib=MediaLibrary(db_path=tmp_path/'library.db',ffmpeg=ff)
    lib.open()
    assistant=SimpleNamespace(available_models=AsyncMock(return_value=['local']),production_plan=AsyncMock())
    director=Director(lib,ff,assistant,tmp_path/'Output',tmp_path/'Audio',tmp_path/'Temp')
    paths=[]
    for name in ['a 日本.mp4','b.mp4']:
        p=tmp_path/name
        p.write_bytes(b'x')
        paths.append(str(p))
    yield director,paths
    lib.close()


@pytest.mark.asyncio
async def test_plan_multiple_assets_and_project_reload(studio):
    director,paths=studio
    project=await director.plan('Erstelle einen 6-Sekunden-Clip.',paths)
    assert len(project.timeline)==2 and project.duration==6
    assert project.timeline[1].position==3
    assert director.load(project.id)==project
    assert director.list_projects()[0]['id']==project.id
    assert project.music==[] and project.voiceover==[]


@pytest.mark.asyncio
async def test_assets_reuse_probe_and_preserve_transcript_timing(studio):
    director,paths=studio
    first=await director.library.asset(paths[0])
    data={'language':'de','segments':[{'start':5.2,'end':8.1,'text':'Hormus Nachrichten'}]}
    director.library.attach_transcript(paths[0],data)
    asset=await director.library.asset(paths[0])
    assert director.ffmpeg.probe.await_count==1
    assert asset.transcript==data and asset.id==first.id
    project=await director.plan('Hormus Nachrichten',paths,4)
    assert project.timeline[0].start==5.2
    mtime=Path(paths[0]).stat().st_mtime
    os.utime(paths[0],(mtime+2,mtime+2))
    assert (await director.library.asset(paths[0])).transcript is None


@pytest.mark.asyncio
async def test_asset_origin_survives_recent_eviction(studio):
    director,paths=studio
    director.library.record_job_outputs(Job(job_type=JobType.DOWNLOAD,state=JobState.DONE,output_path=Path(paths[0])))
    assert (await director.library.asset(paths[0])).origin=='download'
    with director.library._conn:
        director.library._conn.execute('DELETE FROM recent_outputs')
    assert (await director.library.asset(paths[0])).origin=='download'


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['end','position','asset_id','transition'])
async def test_invalid_timeline_rejected(studio,mutation):
    director,paths=studio
    data=(await director.plan('Clip',paths,6)).model_dump()
    data['timeline'][0][mutation]={'end':999,'position':1,'asset_id':'invented','transition':'dissolve'}[mutation]
    with pytest.raises(ValidationError):
        ProductionProject.model_validate(data)


@pytest.mark.asyncio
async def test_renderer_revalidates_edited_asset_duration(studio):
    director,paths=studio
    data=(await director.plan('Clip',paths,15)).model_dump()
    data['assets'][0]['duration']=99
    data['target_duration']=100
    data['timeline']=[{'asset_id':data['assets'][0]['id'],'start':0,'end':90,'position':0}]
    project=ProductionProject.model_validate(data)
    with pytest.raises(ValidationError):
        await director.render(project)
    director.ffmpeg.convert.assert_not_called()


@pytest.mark.asyncio
async def test_llm_cannot_inject_assets_or_unsupported_tracks(studio):
    director,paths=studio
    director.assistant.production_plan.return_value={'assets':[]}
    fallback=await director.plan('Clip',paths,6,model='local')
    assert fallback.planner=='metadata'
    assert director.assistant.production_plan.await_count==2
    director.assistant.production_plan.return_value={'title':'Lokaler Schnitt','story':['Review required'], 'timeline':[s.model_dump() for s in fallback.timeline]}
    project=await director.plan('Clip',paths,6,model='local')
    assert project.planner=='ollama' and project.title=='Lokaler Schnitt'
    data=project.model_dump() | {'music':[{'generated':'fake'}]}
    with pytest.raises(ValidationError):
        ProductionProject.model_validate(data)


@pytest.mark.asyncio
async def test_missing_whisper_is_honest_and_never_starts_audio_work(studio):
    director,paths=studio
    asset=await director.library.asset(paths[0])
    with patch.object(SubtitleGenerator,'capability',return_value={'available':False}):
        with pytest.raises(RuntimeError,match='nicht installiert'):
            await director.transcribe(asset)
    director.ffmpeg.convert.assert_not_called()


@pytest.mark.asyncio
async def test_transcription_reuses_generator_json_and_attaches_segments(studio):
    director,paths=studio
    asset=await director.library.asset(paths[0])
    async def generate(source,output,**kwargs):
        assert kwargs['format']=='json'
        Path(output).write_text(json.dumps({'language':'de','segments':[{'start':1.2,'end':5.8,'text':'Echter Zeitbereich'}]}))
        return Path(output)
    with patch.object(SubtitleGenerator,'capability',return_value={'available':True}), patch.object(SubtitleGenerator,'generate',side_effect=generate):
        result=await director.transcribe(asset)
    assert result.transcript['segments'][0]['start']==1.2
    assert result.transcript['segments'][0]['end']==5.8
    assert not list(director.temp_dir.iterdir())


@pytest.mark.asyncio
async def test_missing_models_and_fake_voice_cloning_are_not_advertised(studio):
    director,paths=studio
    director.assistant.available_models.return_value=[]
    project=await director.plan('Clip',paths,6,model='missing')
    assert project.planner=='metadata'
    director.assistant.production_plan.assert_not_called()
    caps=await director.capabilities()
    assert not caps['music_generation'] and not caps['dubbing'] and not caps['tts']['voice_cloning']


def test_project_id_cannot_escape_storage(studio):
    director,_=studio
    with pytest.raises(ValueError):
        director.load('../../settings')


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [None, [], {'timeline':[]}, {'assets':[]}, '```json {} ```'])
async def test_invalid_llm_exactly_one_repair_then_fallback(studio,bad):
    director,paths=studio
    director.assistant.production_plan.return_value=bad
    project=await director.plan('8-Sekunden-Clip',paths,model='local')
    assert project.planner=='metadata' and project.duration==8
    assert len(project.timeline)==2 and project.original_audio=='duck'
    assert director.assistant.production_plan.await_count==2
    assert 'Fallback' in project.notes[-1]
    assert director.load(project.id).timeline==project.timeline


@pytest.mark.asyncio
async def test_llm_repair_uses_real_bounds(studio):
    director,paths=studio
    baseline=await director.plan('8-Sekunden-Clip',paths)
    good={'title':'Repariert','story':['Ruhig, dann Spannung'],
          'timeline':[s.model_dump() for s in baseline.timeline],
          'voiceover':[{'text':'Die Lage bleibt angespannt.','position':0}], 'atmosphere':'Düster, Musik nur gewünscht'}
    bad=json.loads(json.dumps(good));bad['timeline'][0]['end']=999
    director.assistant.production_plan.side_effect=[bad,good]
    project=await director.plan('8-Sekunden-Clip',paths,model='local')
    assert project.planner=='ollama' and project.duration==8
    assert director.assistant.production_plan.await_count==2
    assert 'repair' in director.assistant.production_plan.call_args.args[0]
    assert director.load(project.id).voiceover==project.voiceover
    Path(paths[0]).unlink()
    assert any('Quelldatei fehlt' in n for n in director.load(project.id).notes)


def test_native_voice_discovery_prefers_installed_german(monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr('src.services.voice.sys.platform','darwin')
    monkeypatch.setattr('src.services.voice.shutil.which',lambda name:'/native/say')
    run=Mock(return_value=SimpleNamespace(stdout='Alex en_US # Hello\nAnna de_DE # Hallo\n'))
    monkeypatch.setattr('src.services.voice.run_hidden',run)
    caps=LocalVoice.capability()
    assert caps['preferred_voice']=='Anna' and len(caps['voices'])==2
    run.return_value.stdout='Markus de_DE # Hallo\n'
    assert LocalVoice.capability()['preferred_voice']=='Markus'


@pytest.mark.asyncio
async def test_llm_source_positions_are_derived_not_trusted(studio):
    director,paths=studio
    baseline=await director.plan('8 Sekunden',paths)
    proposal={'title':'Clip','story':[], 'timeline':[s.model_dump() for s in baseline.timeline]}
    proposal['timeline'][1]['position']=99
    director.assistant.production_plan.return_value=proposal
    result=await director.plan('8 Sekunden',paths,model='local')
    assert result.planner=='ollama' and result.timeline[1].position==4
    assert director.assistant.production_plan.await_count==1


@pytest.mark.asyncio
async def test_fallback_preserves_explicit_voice_without_inventing_speech(studio):
    director,paths=studio
    director.assistant.production_plan.side_effect=RuntimeError('unreachable')
    result=await director.plan('8 Sekunden. Sprechertext: "Die Lage bleibt angespannt."',paths,model='local')
    assert result.planner=='metadata' and result.voiceover[0].text=='Die Lage bleibt angespannt.'
    assert director.assistant.production_plan.await_count==2


@pytest.mark.asyncio
async def test_ollama_request_uses_schema_and_rejects_empty_json(studio,monkeypatch):
    import httpx
    from src.services.assistant import Assistant, AssistantError
    director,paths=studio
    draft=(await director.plan('8 Sekunden',paths)).model_dump()
    calls=[]
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':''}})
    client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(httpx,'AsyncClient',lambda:client)
    with pytest.raises(AssistantError,match='keinen Produktionsplan'):
        await Assistant(model='local').production_plan(draft)
    assert calls[0]['format']['additionalProperties'] is False
    assert calls[0]['format']['$defs']['Scene']['properties']['asset_id']['enum']==[a['id'] for a in draft['assets']]
    assert calls[0]['stream'] is False


@pytest.mark.asyncio
async def test_missing_requested_voice_uses_installed_german(tmp_path):
    from unittest.mock import Mock
    ff=SimpleNamespace(convert=AsyncMock(return_value=tmp_path/'out.wav'))
    proc=SimpleNamespace(returncode=0)
    caps={'available':True,'voices':[{'name':'Markus','language':'de_DE'}], 'preferred_voice':'Markus'}
    with patch.object(LocalVoice,'capability',return_value=caps), \
         patch('src.services.voice.create_hidden_subprocess',new_callable=AsyncMock,return_value=proc) as launch, \
         patch('src.services.voice.communicate_with_job',new_callable=AsyncMock,return_value=(b'',b'')):
        await LocalVoice().synthesize('Hallo',tmp_path/'out.wav',ff,voice='Not installed')
    assert launch.call_args.args[-2:]==('-v','Markus')


@pytest.mark.asyncio
async def test_dubbing_persistence_and_provider_boundary(studio):
    from src.models.director import DubbingPlan,DubbingCue
    from src.services.translation import translate_dubbing
    director,paths=studio
    project=await director.plan('8 Sekunden',paths)
    dubbing=DubbingPlan(asset_id=project.assets[0].id,source_language='de',target_language='en',
        cues=[DubbingCue(start=1,end=2,source_text='Hallo',speaker='A',voice='Alex')])
    with pytest.raises(RuntimeError,match='Kein lokaler'):
        await translate_dubbing(dubbing,None)
    provider=SimpleNamespace(translate=AsyncMock(return_value=['Hello']))
    translated=await translate_dubbing(dubbing,provider)
    assert translated.cues[0].start==1 and translated.cues[0].end==2
    assert dubbing.cues[0].translated_text is None
    project.dubbing=translated
    director.save(project)
    assert director.load(project.id).dubbing==translated
    with pytest.raises(ValueError,match='noch nicht renderbar'):
        await director.render(project)
    provider.translate.return_value=[]
    with pytest.raises(ValueError,match='Segmente'):
        await translate_dubbing(dubbing,provider)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,voice', [('keep',True),('duck',True),('mute',True),('duck',False)])
async def test_render_audio_modes_and_output_registration(studio,mode,voice):
    import wave
    from src.models.director import Voiceover
    director,paths=studio
    project=await director.plan('8 Sekunden',paths)
    project.original_audio=mode
    if voice:
        project.voiceover=[Voiceover(text='Hallo',position=1)]
    real_probe=director.ffmpeg.probe.side_effect
    async def probe(path):
        result=await real_probe(path)
        if str(path) not in paths:
            result.duration_seconds=1 if Path(path).suffix=='.wav' else 8
        return result
    director.ffmpeg.probe.side_effect=probe
    async def audio(source,target,**kwargs):
        with wave.open(str(target),'wb') as f:
            f.setparams((2,2,48000,0,'NONE','not compressed'))
            f.writeframes(b'\0'*48000*4)
        return target
    director.ffmpeg.convert.side_effect=audio
    director.ffmpeg.merge=AsyncMock(return_value=director.temp_dir/'joined.mp4')
    async def command(args,job):
        Path(args[-1]).write_bytes(b'rendered')
    director._command=AsyncMock(side_effect=command)
    async def synth(text,path,*args,**kwargs):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'voice')
        return path
    job=Job(job_type=JobType.DIRECTOR_RENDER)
    with patch('src.services.director.Converter.convert_file',new_callable=AsyncMock,return_value=Path('clip.mp4')), \
         patch.object(LocalVoice,'synthesize',side_effect=synth):
        output=await director.render(project,job=job)
    args=director._command.call_args.args[0]
    filters=args[args.index('-filter_complex')+1]
    assert ('volume=0.2' in filters)==(mode=='duck' and voice)
    if mode=='duck' and voice:
        assert 'between(t,1.0,2.0)' in filters
    assert director.ffmpeg.convert.await_count==(0 if mode=='mute' else 2)
    assert output.exists() and job.output_path==output
    loaded=director.load(project.id)
    assert loaded.outputs[-1]==str(output)
    assert len(loaded.generated_audio)==int(voice)


def test_whisper_package_model_and_configuration_are_distinct(tmp_path,monkeypatch):
    monkeypatch.setattr('importlib.util.find_spec',lambda name:None)
    assert SubtitleGenerator.capability()['status']=='package_missing'
    monkeypatch.setattr('importlib.util.find_spec',lambda name:object() if name=='faster_whisper' else None)
    assert SubtitleGenerator.capability(str(tmp_path/'absent'))['status']=='model_missing'
    assert SubtitleGenerator.capability('')['status']=='not_configured'
    (tmp_path/'model.bin').write_bytes(b'model')
    assert SubtitleGenerator.capability(str(tmp_path))['status']=='available'


@pytest.mark.asyncio
async def test_transcript_context_is_bounded_and_topic_cut_stays_in_segment(studio):
    director,paths=studio
    segments=[{'start':i/10,'end':i/10+.05,'text':'irrelevant '*200} for i in range(80)]
    segments.append({'start':8,'end':9,'text':'Die Energiepreise steigen','language':'de'})
    director.library.attach_transcript(paths[0],{'language':'de','text':'Huge document','segments':segments})
    baseline=await director.plan('Energiepreise',paths,6)
    assert baseline.timeline[0].start==8 and baseline.timeline[0].end==9
    director.assistant.production_plan.side_effect=RuntimeError('offline')
    await director.plan('Energiepreise',paths,6,model='local')
    context=director.assistant.production_plan.call_args.args[0]['assets'][0]['transcript']
    assert len(context['segments'])==8 and context['segments'][0]['start']==8
    assert 'text' not in context
    assert all(len(s['text'])<=600 for s in context['segments'])


def test_subtitle_timing_uses_cut_offsets_and_existing_writer(studio):
    from src.models.director import MediaAsset,Scene,Voiceover
    asset=MediaAsset(id='a',path='a.mp4',kind='video',duration=10,
        transcript={'segments':[{'start':3,'end':7,'text':'Grüße 日本'}]})
    p=ProductionProject(prompt='test',target_duration=3,assets=[asset],timeline=[Scene(asset_id='a',start=4,end=7,position=0)])
    segments=Director.subtitle_segments(p)
    assert segments==[{'start':0.,'end':3.,'text':'Grüße 日本'}]
    srt=SubtitleGenerator()._to_srt(segments)
    assert '00:00:00,000 --> 00:00:03,000' in srt and 'Grüße 日本' in srt


def test_windows_tts_never_uses_say(monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr('src.services.voice.sys.platform','win32')
    run=Mock(side_effect=AssertionError('Apple call on Windows'))
    monkeypatch.setattr('src.services.voice.run_hidden',run)
    assert not LocalVoice.capability()['available']
    run.assert_not_called()


@pytest.mark.asyncio
async def test_render_failure_cleans_owned_files_and_keeps_project(studio):
    director,paths=studio
    project=await director.plan('8 Sekunden',paths)
    with patch('src.services.director.Converter.convert_file',new_callable=AsyncMock,side_effect=RuntimeError('encoder failed')):
        with pytest.raises(RuntimeError,match='encoder failed'):
            await director.render(project)
    assert not list(director.output_dir.glob('*.mp4'))
    assert not list(director.temp_dir.iterdir())
    assert director.load(project.id).outputs==[]


@pytest.mark.asyncio
async def test_translation_provider_validates_schema_and_local_host(monkeypatch):
    import httpx
    from src.services.assistant import Assistant
    from src.services.translation import LocalOllamaTranslationProvider
    with pytest.raises(ValueError,match='lokalen'):
        LocalOllamaTranslationProvider(Assistant(host='https://example.com'))
    assistant=Assistant(model='local');assistant.available_models=AsyncMock(return_value=['local'])
    seen=[]
    def handle(request):
        body=json.loads(request.content);seen.append(body)
        return httpx.Response(200,json={'message':{'content':json.dumps({'texts':['Hello']})}})
    client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(httpx,'AsyncClient',lambda:client)
    assert await LocalOllamaTranslationProvider(assistant).translate(['Hallo'],'de','en')==['Hello']
    assert seen[0]['format']['properties']['texts']['minItems']==1
    assert seen[0]['format']['additionalProperties'] is False


@pytest.mark.asyncio
async def test_dubbing_reuses_render_and_restores_editable_project(studio):
    from src.models.director import DubbingPlan,DubbingCue
    director,paths=studio
    project=await director.plan('8 Sekunden',paths)
    project.dubbing=DubbingPlan(asset_id=project.assets[0].id,source_language='de',target_language='en',
        cues=[DubbingCue(start=1,end=3,source_text='Hallo',translated_text='Hello')])
    async def render(working,*args):
        assert working.dubbing is None
        assert working.voiceover[0].language=='en' and working.voiceover[0].max_duration==2
        assert working.voiceover[0].position==1 and working.original_audio=='duck'
        working.outputs.append('render.mp4');working.subtitle_paths.append('render.srt')
        director.save(working)
        return Path('render.mp4')
    director.render=AsyncMock(side_effect=render)
    await director.render_dubbing(project)
    loaded=director.load(project.id)
    assert loaded.dubbing==project.dubbing
    assert loaded.outputs==['render.mp4'] and loaded.subtitle_paths==['render.srt']


@pytest.mark.asyncio
async def test_missing_source_and_audio_are_clear(studio):
    director,paths=studio
    asset=await director.library.asset(paths[0]);asset.audio_codec=None
    with patch.object(SubtitleGenerator,'capability',return_value={'available':True}):
        with pytest.raises(ValueError,match='keine Audiospur'):
            await director.transcribe(asset)
    project=await director.plan('8 Sekunden',paths)
    Path(paths[0]).unlink()
    with pytest.raises(FileNotFoundError):
        await director.render(project)
    director.ffmpeg.convert.assert_not_called()
