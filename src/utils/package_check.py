"""Explicit local bundle acceptance mode; never runs during normal startup."""
import asyncio
import json
import sys
import time
from pathlib import Path


def run(output, model=None, audio=None):
    import retrodisc_launcher as app
    from src.services.subtitle import SubtitleGenerator
    from src.utils.subprocesses import run_hidden
    bridge=app.RetroDiscBridge()
    result={'frozen':bool(getattr(sys,'frozen',False)), 'bundle':str(app.BUNDLE_DIR)}
    try:
        import importlib
        modules=('src.services.director','src.services.restoration','src.services.smart_edit',
                 'src.services.translation','src.services.voice','src.services.subtitle')
        result['imports']={name:bool(importlib.import_module(name)) for name in modules}
        result['ui_resources']={name:(app.BUNDLE_DIR/'src/ui'/name).is_file() for name in ('app.html','splash.html')}
        result['paths']=json.loads(bridge.get_path_status())
        result['tools']={}
        for name,path in app.check_tools().items():
            proc=run_hidden([path,'--version' if name=='ytdlp' else '-version'],capture_output=True,text=True,timeout=30)
            result['tools'][name]={'path':path,'returncode':proc.returncode,'version':proc.stdout.splitlines()[:1]}
        result['platform']=json.loads(bridge.get_platform_info())
        result['diagnostics']=json.loads(bridge.diagnostics())
        result['recent']=json.loads(bridge.get_recent_media())
        result['whisper_default']=SubtitleGenerator.capability()
        if model and audio:
            result['whisper_local']=SubtitleGenerator.capability(model)
            target=Path(output).with_suffix('.srt')
            asyncio.run(SubtitleGenerator(model=model,device='cpu').generate(audio,target,language='de'))
            result['srt']=target.read_text(encoding='utf-8')
        result['ok']=result['frozen'] and bool(result['whisper_default']['engines']) and all(result['ui_resources'].values()) and all(t['returncode']==0 for t in result['tools'].values()) and len(result['tools'])==3
    except Exception as exc:
        result.update(ok=False,error=repr(exc))
    finally:
        bridge.shutdown()
        Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['ok'] else 1


def webview_check(window,output):
    """Exercise the real injected JS API after splash navigation, no Computer Use."""
    result={}
    try:
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if window.evaluate_js("!!document.getElementById('tab-restore') && !!window.pywebview?.api"):
                break
            time.sleep(.25)
        else:raise RuntimeError('UI/Bridge not ready after 60 seconds')
        window.evaluate_js("""window.__packageResult=null;
            Promise.all([pywebview.api.get_platform_info(),pywebview.api.get_recent_media(),pywebview.api.get_encoder_options()])
            .then(x=>window.__packageResult={ok:true,platform:JSON.parse(x[0]),recent:JSON.parse(x[1]),encoders:JSON.parse(x[2]),
                panels:['tab-restore','tab-ai'].map(id=>!!document.getElementById(id))})
            .catch(e=>window.__packageResult={ok:false,error:String(e)});""")
        for _ in range(100):
            result=window.evaluate_js('window.__packageResult')
            if result:break
            time.sleep(.1)
        if not result:raise RuntimeError('JS bridge response timed out')
        if not result.get('ok'):raise RuntimeError('Bridge call failed')
        import uuid
        import retrodisc_launcher as app
        from src.utils.subprocesses import run_hidden
        folder=Path(output).parent
        source=folder/('Quelle ä '+uuid.uuid4().hex+'.mp4')
        target=folder/('Ausgabe ü '+uuid.uuid4().hex+'.mp4')
        ffmpeg=app.check_tools()['ffmpeg']
        run_hidden([ffmpeg,'-v','error','-n','-f','lavfi','-i','testsrc2=size=320x240:rate=25',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','libx264','-c:a','aac',str(source)],check=True,timeout=30)
        script="""window.__handoff=null;(async()=>{
            const path=TARGET;
            const submitted=JSON.parse(await pywebview.api.convert_file(SOURCE,'mp4_h264_720p',path,false,'auto'));
            if(submitted.error)throw new Error(submitted.error);
            let rows=[];
            for(let i=0;i<120;i++){
                rows=JSON.parse(await pywebview.api.get_recent_media());
                if(rows.some(r=>r.path===path))break;
                await new Promise(resolve=>setTimeout(resolve,250));
            }
            const row=rows.find(r=>r.path===path);
            if(!row)throw new Error('Converted output missing from Recent Media');
            await useRecentMedia({dataset:{path,target:'convert'}});
            const convert=S.files[0]?.path===path;
            await useRecentMedia({dataset:{path,target:'burn'}});
            const burn=row.can_burn && S.files[0]?.path===path;
            const assets=JSON.parse(await pywebview.api.director_assets(JSON.stringify([path])));
            window.__handoff={ok:convert&&burn&&assets[0]?.path===path,convert,burn,director:assets[0]?.path===path,path};
        })().catch(e=>window.__handoff={ok:false,error:String(e)});"""
        script=script.replace('TARGET',json.dumps(str(target))).replace('SOURCE',json.dumps(str(source)))
        window.evaluate_js(script)
        handoff=None
        for _ in range(160):
            handoff=window.evaluate_js('window.__handoff')
            if handoff:break
            time.sleep(.25)
        result['handoffs']=handoff
        if not handoff or not handoff.get('ok'):result['ok']=False
        if target.exists():
            run_hidden([ffmpeg,'-v','error','-xerror','-i',str(target),'-f','null','-'],check=True,timeout=30)
            result['decode']=True

    except Exception as exc:result={'ok':False,'error':repr(exc)}
    finally:
        Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        window.destroy()
