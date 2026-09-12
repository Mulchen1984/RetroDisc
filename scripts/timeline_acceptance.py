"""Real timeline/slideshow acceptance, isolated outputs; shared cross-platform renderer."""
import asyncio,json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.core.ffmpeg import FFmpeg
from src.services.library import MediaLibrary
from src.services.director import Director
from src.services.timeline import edit
from src.models.director import ProductionProject,Scene,AudioPlacement
from src.models.media import Job,JobType,JobState

async def main(folder):
    folder.mkdir(parents=True,exist_ok=True)
    ff=FFmpeg()
    def make(*args):subprocess.run([ff.ffmpeg_path,'-v','error','-n',*map(str,args)],check=True)
    video=folder/'Quelle ü.mp4';music=folder/'Musik.wav';images=[folder/'Foto 1.png',folder/'Foto 2.png']
    if not video.exists():make('-f','lavfi','-i','testsrc2=size=320x240:rate=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','6','-c:v','libx264','-c:a','aac',video)
    if not music.exists():make('-f','lavfi','-i','sine=frequency=220:sample_rate=48000','-t','8',music)
    for image,color in zip(images,['red','blue']):
        if not image.exists():make('-f','lavfi','-i',f'color=c={color}:s=400x300','-frames:v','1',image)
    lib=MediaLibrary(db_path=folder/'library.db',ffmpeg=ff);lib.thumb_dir=folder/'thumbs';lib.open()
    service=Director(lib,ff,SimpleNamespace(),folder/'out',folder/'audio',folder/'temp')
    assets=[await lib.asset(p) for p in [video,music,*images]]
    p=ProductionProject(prompt='Timeline acceptance',target_duration=6,assets=assets[:2],timeline=[Scene(asset_id=assets[0].id,start=0,end=6,position=0)])
    p=edit(p,'split',0,{'time':3});p=edit(p,'trim',0,{'start':1});p=edit(p,'transition',1,{'value':'dip_black'})
    p.music=[AudioPlacement(asset_id=assets[1].id,duration=p.duration)]
    slide=ProductionProject(prompt='Slideshow',target_duration=4,assets=assets[1:],
        timeline=[Scene(asset_id=a.id,start=0,end=2,position=i*2,transition='fade',zoom='subtle') for i,a in enumerate(assets[2:])],
        music=[AudioPlacement(asset_id=assets[1].id,duration=4)])
    results=[]
    for plan in [p,slide]:
        job=Job(job_type=JobType.DIRECTOR_RENDER)
        out=await service.render(plan,job=job)
        info=await ff.probe(out)
        make('-xerror','-i',out,'-f','null','-')
        job.state=JobState.DONE;lib.record_job_outputs(job)
        assert any(r['path']==str(out) for r in lib.recent_outputs())
        assert service.load(plan.id).outputs[-1]==str(out)
        assert abs(info.duration_seconds-plan.duration)<.2
        results.append({'prompt':plan.prompt,'output':str(out),'duration':info.duration_seconds,'audio':bool(info.audio_streams),'decode':True,'recent':True})
    (folder/'result.json').write_text(json.dumps(results,indent=2));print(json.dumps(results));lib.close()

if __name__=='__main__':asyncio.run(main(Path(sys.argv[1] if len(sys.argv)>1 else 'build/timeline-acceptance').resolve()))
