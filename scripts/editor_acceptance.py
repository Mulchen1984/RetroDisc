"""Real Director editor renders. Unsupported text is reported, never faked."""
import asyncio,json,subprocess,sys,hashlib
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.core.ffmpeg import FFmpeg
from src.services.library import MediaLibrary
from src.services.director import Director
from src.models.director import ProductionProject,Scene,OverlayClip,TextClip,AudioPlacement
from src.services.timeline import edit
from src.models.media import Job,JobType,JobState

async def main():
    root=Path('build/editor-acceptance').resolve();root.mkdir(parents=True,exist_ok=True)
    ff=FFmpeg()
    def command(*args):return subprocess.run([ff.ffmpeg_path,'-v','error',*map(str,args)],check=True,capture_output=True)
    sources=[root/'one.mp4',root/'two.mp4']
    for path,shape,fps in zip(sources,['320x240','480x270'],[25,30]):
        if not path.exists():command('-n','-f','lavfi','-i',f'testsrc2=size={shape}:rate={fps}','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','4','-c:v','libx264','-c:a','aac',path)
    image=root/'transparent.png'
    if not image.exists():command('-n','-f','lavfi','-i','color=red@0.5:s=80x80,format=rgba','-frames:v','1',image)
    lib=MediaLibrary(db_path=root/'library.db',ffmpeg=ff);lib.thumb_dir=root/'thumbs';lib.open()
    d=Director(lib,ff,SimpleNamespace(),root/'out',root/'audio',root/'tmp')
    assets=[await lib.asset(p) for p in [*sources,image]]
    base=ProductionProject(prompt='Editor acceptance',target_duration=12,assets=assets,timeline=[Scene(asset_id=a.id,start=0,end=3,position=i*3) for i,a in enumerate(assets[:2])])
    cases=[]
    for name in ['dissolve','wipe_left','wipe_right','slide_left','slide_right','zoom','blur','fade_black']:
        cases.append((name,edit(base,'transition',1,{'value':{'type':name,'duration':.5}})))
    overlay=base.model_copy(deep=True);overlay.overlays=[OverlayClip(asset_id=assets[2].id,start=0,duration=2,opacity=.6)]
    cases.append(('PNG overlay',overlay))
    pip=base.model_copy(deep=True);pip.overlays=[OverlayClip(asset_id=assets[1].id,start=1,duration=2,volume=.2)]
    cases.append(('PIP audio',pip))
    speed=edit(base,'speed',0,{'value':.5});speed=edit(speed,'freeze',0,{'time':1,'duration':2});cases.append(('Speed + Freeze',speed))
    for speed_value in [2,4]:cases.append((f'Speed {speed_value}',edit(base,'speed',0,{'value':speed_value})))
    for kind in ['fade_from_black','fade_to_black','dip_black']:
        cases.append((kind,edit(base,'transition',0,{'value':{'type':kind,'duration':.5}})))
    effects=edit(base,'effects',0,{'preset':'warm'})
    effects=edit(effects,'transform',0,{'crop':'1:1','rotate':90,'flip_horizontal':True})
    cases.append(('Effects + Transform',effects))
    result=[]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for name,plan in cases:
        job=Job(job_type=JobType.DIRECTOR_RENDER)
        out=await d.render(plan,job=job)
        info=await ff.probe(out);command('-xerror','-i',out,'-f','null','-')
        assert abs(info.duration_seconds-plan.duration)<.2 and info.audio_streams
        job.state=JobState.DONE;lib.record_job_outputs(job)
        assert any(r['path']==str(out) for r in lib.recent_outputs())
        result.append({'case':name,'duration':info.duration_seconds,'expected':plan.duration,'decode':True,'recent':True,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
        print(name,'PASS',flush=True)
    text=base.model_copy(deep=True);text.text_clips=[TextClip(text='Grüße & Titel',start=0,duration=2)]
    try:
        out=await d.render(text);command('-xerror','-i',out,'-f','null','-');result.append({'case':'Text','status':'PASS'})
    except ValueError as e:
        if 'drawtext' not in str(e):raise
        result.append({'case':'Text','status':'CAPABILITY_UNAVAILABLE','reason':str(e)})
    before=set((root/'out').iterdir())
    task=asyncio.create_task(d.render(base))
    await asyncio.sleep(.05)
    assert not task.done(), 'Cancel fixture completed before cancellation'
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass
    else:raise AssertionError('Render ignored cancellation')
    assert set((root/'out').iterdir())==before and not list((root/'tmp').iterdir())
    result.append({'case':'Cancel active render','status':'PASS','temporary_cleanup':True})
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    (root/'result.json').write_text(json.dumps(result,indent=2));lib.close()

if __name__=='__main__':asyncio.run(main())
