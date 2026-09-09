"""CPU restoration filters followed by the shared platform-aware encoder."""
import asyncio
import hashlib
import json
import re
import tempfile
import uuid
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Protocol
from src.models.restoration import RestorationAnalysis,RestorationPlan,RestorationOptions,SceneRestoration,RestorationSceneAnalysis
from src.config.presets import get_preset
from src.services.converter import Converter
from src.utils.subprocesses import create_hidden_subprocess,communicate_with_job


class RestorationProvider(Protocol):
    async def analyze(self,path,job=None) -> RestorationPlan: ...
    async def render(self,plan,preview=False,encoder='auto',job=None) -> RestorationPlan: ...


class Restoration:
    def __init__(self,library,ffmpeg,output_dir,temp_dir):
        self.library,self.ffmpeg=library,ffmpeg
        self.output_dir,self.temp_dir=Path(output_dir),Path(temp_dir)
        self.projects_dir=library.db_path.parent/'restoration-projects'

    async def _run(self,args,job=None,cwd=None,probe=False):
        exe=self.ffmpeg.ffprobe_path if probe else self.ffmpeg.ffmpeg_path
        proc=await create_hidden_subprocess(exe,*args,cwd=cwd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        out,err=await communicate_with_job(proc,job,max_output_bytes=2*1024*1024)
        if proc.returncode:
            raise RuntimeError(err.decode('utf-8',errors='replace')[-3000:])
        return out.decode('utf-8',errors='replace'),err.decode('utf-8',errors='replace')

    async def capabilities(self):
        text,_=await self._run(['-hide_banner','-filters'])
        names=set(re.findall(r'^\s*[.A-Z|]{2,3}\s+(\w+)\s',text,re.M))
        import importlib.util
        import shutil
        providers={name:{'available':False,'status':'unsupported','note':'Nicht als RestorationProvider integriert; keine Modelle installiert.'}
                   for name in ['qtgmc','realesrgan','basicvsr','rvrt','rife','vhs_decode']}
        if not importlib.util.find_spec('vapoursynth') or not shutil.which('vspipe'):
            providers['qtgmc']={'available':False,'status':'missing_runtime','note':'VapourSynth/vspipe fehlen; QTGMC-Plugins nicht geprüft.'}
        level='advanced' if {'vidstabdetect','vidstabtransform'}<=names else 'basic' if 'deshake' in names else 'none'
        return {'filters':sorted(names),'stabilization':{'available':level!='none','level':level},
            'providers':providers, 'archive':{'manifest_and_checksums':True,'ffv1_master':'probe_on_use','rf_capture':'unsupported'}}

    @staticmethod
    def field_order(stream,idet):
        tagged={'tt':'tff','bb':'bff','progressive':'progressive'}.get(stream.get('field_order'))
        total=sum(idet.values())
        if total>=10:
            dominant=max(idet,key=idet.get)
            if idet[dominant]/total>=0.8 and dominant in ('tff','bff','progressive'):
                if tagged and tagged!=dominant:
                    return 'unknown'
                return dominant
        return tagged or 'unknown'

    @staticmethod
    def frame_rate(stream):
        for key in ('avg_frame_rate','r_frame_rate'):
            try:
                rate=float(Fraction(str(stream.get(key,''))))
                if rate>0:return rate
            except (ValueError,ZeroDivisionError):
                continue
        raise ValueError('Keine gültige Bildrate ermittelbar; Quelle prüfen.')

    @staticmethod
    def preview_signature(plan):
        data={'source':plan.analysis.asset.path,'mtime':plan.analysis.source_mtime_ns,
              'size':plan.analysis.source_size,'preset':plan.preset,
              'options':plan.options.model_dump(),'scenes':[s.model_dump() for s in plan.scenes]}
        return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

    @classmethod
    def check_preview(cls,plan):
        if plan.preview and (plan.preview_signature!=cls.preview_signature(plan) or
                             len(plan.preview)!=2 or not all(Path(p).is_file() for p in plan.preview)):
            raise ValueError('Vorschau fehlt oder gehört zu einem anderen Plan. Bitte neue Vorschau erzeugen.')

    async def analyze(self,path,job=None):
        asset=await self.library.asset(path)
        if asset.kind!='video' or asset.duration<=0:
            raise ValueError('Eine Videodatei mit gültiger Dauer ist erforderlich.')
        before=Path(asset.path).stat()
        raw,_=await self._run(['-v','error','-show_streams','-show_format','-of','json',asset.path],probe=True,job=job)
        data=json.loads(raw);stream=next(s for s in data['streams'] if s['codec_type']=='video')
        seconds=min(8,asset.duration)
        _,stats=await self._run(['-hide_banner','-nostdin','-i',asset.path,'-t',str(seconds),'-an','-vf','idet,signalstats,metadata=mode=print','-f','null','-'],job)
        matches=re.findall(r'Multi frame detection:\s*TFF:\s*(\d+)\s*BFF:\s*(\d+)\s*Progressive:\s*(\d+)\s*Undetermined:\s*(\d+)',stats)
        idet=dict(zip(['tff','bff','progressive','unknown'],map(int,matches[-1]))) if matches else {}
        def averages(text,keys):
            result={}
            for key in keys:
                values=[float(v) for v in re.findall(r'lavfi.signalstats.'+key+r'=([\d.]+)',text)]
                if values:result[key]=sum(values)/len(values)
            return result
        _,residual=await self._run(['-hide_banner','-nostdin','-i',asset.path,'-t',str(min(3,seconds)),'-an','-filter_complex',
            '[0:v]split[a][b];[b]hqdn3d=1:2:2:3[c];[a][c]blend=all_mode=difference,signalstats,metadata=mode=print', '-f','null','-'],job)
        after=Path(asset.path).stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError('Quelle wurde während der Analyse verändert; erneut analysieren.')
        analysis=RestorationAnalysis(asset=asset,source_size=Path(asset.path).stat().st_size,source_mtime_ns=Path(asset.path).stat().st_mtime_ns,sample_seconds=seconds,field_order=self.field_order(stream,idet),
            fps=self.frame_rate(stream),sample_aspect_ratio=stream.get('sample_aspect_ratio','unknown'),
            display_aspect_ratio=stream.get('display_aspect_ratio','unknown'),pixel_format=stream.get('pix_fmt','unknown'),
            color_space=stream.get('color_space','unknown'),color_range=stream.get('color_range','unknown'),
            bitrate=int(stream['bit_rate']) if stream.get('bit_rate','').isdigit() else None,
            levels=averages(stats,['YMIN','YMAX','YAVG','SATAVG']),noise_proxy=averages(residual,['YAVG','UAVG','VAVG']),idet=idet,
            uncertain=['Rauschproxy enthält auch Textur/Bewegung; keine reine Rauschmessung.',
                'Verwacklung, Blockartefakte, Unschärfe, Flicker und Audiostörungen nicht zuverlässig klassifiziert.',
                'Nur kurzer Anfangsausschnitt gemessen; Vorschau und Field Order prüfen.'])
        options=RestorationOptions(deinterlace=analysis.field_order in ('tff','bff'),
            field_order=analysis.field_order if analysis.field_order in ('tff','bff') else 'auto')
        caps=await self.capabilities()
        plan=RestorationPlan(analysis=analysis,options=options,capabilities=caps,notes=['Erhalten vor Erfinden. Stabilisierung und Audiofilter nur nach bewusster Auswahl.'])
        if analysis.field_order=='unknown':plan.notes.append('Field Order unklar: vor Deinterlacing manuell prüfen/setzen.')
        self.save(plan)
        return plan

    @staticmethod
    def filters(plan):
        o=plan.options
        chain=[]
        if o.deinterlace:chain.append(f'{o.deinterlacer}=mode=send_field:parity={o.field_order}:deint=all')
        strengths={'natural':'0.7:1.5:1:2','balanced':'1.5:3:2:4','strong':'3:5:4:6'}
        if o.denoise:
            if plan.scenes:
                for scene in plan.scenes:
                    if scene.options.denoise:
                        value=':'.join(map(str,scene.denoise_strength)) if scene.denoise_strength else strengths[plan.preset]
                        chain.append(f"hqdn3d={value}:enable='gte(t,{scene.start})*lt(t,{scene.end})'")
            else:chain.append('hqdn3d='+strengths[plan.preset])
        if o.color:chain.append('eq=contrast=1.01:brightness=0:gamma=1:saturation=1.01')
        if o.sharpen:
            if plan.scenes:
                for scene in plan.scenes:
                    if scene.options.sharpen:
                        chain.append(f"unsharp=5:5:{scene.sharpen_amount}:5:5:0:enable='gte(t,{scene.start})*lt(t,{scene.end})'")
            else:chain.append('unsharp=5:5:'+{'natural':'0.15','balanced':'0.25','strong':'0.35'}[plan.preset]+':5:5:0')
        if o.size!='original':
            w,h={'720p':(1280,720),'1080p':(1920,1080)}[o.size]
            # dar includes anamorphic PAL SAR. Pad to a square-pixel canvas.
            chain += [f'scale=w=trunc(min({w}\\,{h}*dar)/2)*2:h=trunc(min({h}\\,{w}/dar)/2)*2:flags=lanczos',
                      'setsar=1',f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2']
        return chain

    @staticmethod
    def checksum(path):
        digest=hashlib.sha256()
        with Path(path).open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        return digest.hexdigest()

    def save(self,plan):
        plan=RestorationPlan.model_validate(plan.model_dump())
        self.projects_dir.mkdir(parents=True,exist_ok=True)
        target=self.projects_dir/(plan.id+'.json')
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=self.projects_dir,delete=False) as f:
            temp=Path(f.name);f.write(plan.model_dump_json(indent=2))
        try:temp.replace(target)
        finally:temp.unlink(missing_ok=True)
        return target

    def load(self,project_id):
        if not re.fullmatch('[a-f0-9]{32}',project_id):raise ValueError('Ungültige Projekt-ID.')
        return RestorationPlan.model_validate_json((self.projects_dir/(project_id+'.json')).read_text(encoding='utf-8'))

    async def render(self,plan,preview=False,encoder='auto',job=None):
        plan=RestorationPlan.model_validate(plan.model_dump())
        if not preview:self.check_preview(plan)
        source=Path(plan.analysis.asset.path)
        if not source.is_file():raise FileNotFoundError(f'Quelle fehlt: {source}')
        stat=source.stat()
        if plan.analysis.source_mtime_ns and (stat.st_mtime_ns!=plan.analysis.source_mtime_ns or stat.st_size!=plan.analysis.source_size):
            raise ValueError('Quelle wurde verändert; erneut analysieren.')
        actual=await self.library.asset(source)
        if actual.id!=plan.analysis.asset.id or actual.duration!=plan.analysis.asset.duration:
            raise ValueError('Quelle wurde verändert; erneut analysieren.')
        chain=self.filters(plan);caps=await self.capabilities()
        required={f.split('=')[0] for f in chain}
        if not required<=set(caps['filters']):raise ValueError('FFmpeg-Filter fehlen: '+', '.join(required-set(caps['filters'])))
        if plan.options.stabilize and not caps['stabilization']['available']:raise ValueError('Kein Stabilisierungsfilter verfügbar.')
        if plan.options.stabilize and caps['stabilization'].get('level')=='basic':
            chain.insert(int(plan.options.deinterlace),'deshake=rx=16:ry=16:edge=mirror')
        self.temp_dir.mkdir(parents=True,exist_ok=True)
        folder=self.temp_dir/'restoration-previews' if preview else self.output_dir
        folder.mkdir(parents=True,exist_ok=True)
        output=folder/f'Restored_{plan.id[:8]}_{uuid.uuid4().hex[:8]}.mp4'
        original=folder/(output.stem+'_original.mp4')
        if output.resolve()==source.resolve():raise ValueError('Original darf nicht überschrieben werden.')
        if output.exists() or original.exists():raise FileExistsError('Ausgabename existiert bereits; erneut starten.')
        limit=['-t',str(min(6,actual.duration))] if preview else []
        source_hash=await asyncio.to_thread(self.checksum,source)
        try:
            with tempfile.TemporaryDirectory(prefix='restoration-',dir=self.temp_dir) as work:
                work=Path(work);input_path=source
                if plan.options.stabilize and caps['stabilization'].get('level')!='basic':
                    deinterlace=chain.pop(0) if plan.options.deinterlace else None
                    detect=([deinterlace] if deinterlace else [])+['vidstabdetect=shakiness=3:accuracy=9:result=transforms.trf']
                    await self._run(['-hide_banner','-nostdin','-i',str(source),*limit,'-an','-vf',','.join(detect),'-f','null','-'],job,cwd=work)
                    transform=([deinterlace] if deinterlace else [])+['vidstabtransform=input=transforms.trf:smoothing=5:optzoom=0:zoom=0:crop=keep']
                    input_path=work/'stabilized.mkv'
                    await self._run(['-hide_banner','-nostdin','-i',str(source),*limit,'-vf',','.join(transform),'-c:v','ffv1','-c:a','copy',str(input_path)],job,cwd=work)
                extra=['-preset','medium','-crf','20',*limit]
                if chain:extra+=['-vf',','.join(chain)]
                if plan.options.audio and actual.audio_codec:extra+=['-af','highpass=f=60,afftdn=nf=-30']
                preset=replace(get_preset('mp4_h264_720p'),resolution=None,fps=None,extra_args=extra,
                    video_bitrate='6M' if plan.options.size=='1080p' else '3M',audio_codec='aac' if actual.audio_codec else None)
                await Converter(self.ffmpeg).convert_file(input_path,preset,output,hwaccel=encoder,job=job)
                info=await self.ffmpeg.probe(output)
                expected=min(6,actual.duration) if preview else actual.duration
                if not info.video_streams or abs(info.duration_seconds-expected)>.25 or bool(info.audio_streams)!=bool(actual.audio_codec):
                    raise ValueError('Restaurationsausgabe hat unerwartete Dauer/Streams.')
                if preview:
                    clean=replace(preset,resolution=None,extra_args=['-preset','medium','-crf','20',*limit])
                    await Converter(self.ffmpeg).convert_file(source,clean,original,hwaccel=encoder)
                    plan.preview=[str(original),str(output)]
                    plan.preview_signature=self.preview_signature(plan)
                else:
                    await self.library.asset(output)
                    plan.outputs.append(str(output))
                    plan.source_sha256=await asyncio.to_thread(self.checksum,source)
                    plan.output_sha256[str(output)]=await asyncio.to_thread(self.checksum,output)
                after=source.stat()
                if (stat.st_size,stat.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                    raise ValueError('Quelle wurde während der Verarbeitung verändert; erneut analysieren.')
                if await asyncio.to_thread(self.checksum,source)!=source_hash:
                    raise ValueError('Quellprüfsumme verändert; Ergebnis verworfen.')
                plan.filters=list(chain)
                if plan.options.stabilize and caps['stabilization'].get('level')!='basic':plan.filters.insert(int(plan.options.deinterlace),'vidstabtransform (smoothing=5, no autozoom)')
                version,_=await self._run(['-version']);plan.tool_version=version.splitlines()[0]
                if not preview:
                    plan.report=self.build_report(plan,actual,info,source_hash,output,plan.output_sha256[str(output)])
                self.save(plan)
                if job and not preview:
                    job.output_path=output;job.params['output_paths']=[str(output)]
                return plan
        except BaseException:
            output.unlink(missing_ok=True);original.unlink(missing_ok=True)
            raise

    async def analyze_scenes(self,plan,job=None):
        """Bounded low-resolution scan, then short measurements per merged interval."""
        plan=RestorationPlan.model_validate(plan.model_dump())
        source=Path(plan.analysis.asset.path)
        if not source.is_file():raise FileNotFoundError('Quelle fehlt.')
        duration=plan.analysis.asset.duration
        _,text=await self._run(['-hide_banner','-nostdin','-i',str(source),'-an','-vf',
            "scale=160:-2,select='gt(scene,0.3)',showinfo",'-f','null','-'],job)
        cuts=sorted(set(float(x) for x in re.findall(r'pts_time:([\d.]+)',text)))
        # Minimum interval grows for long tapes; never hundreds of tiny scenes.
        minimum=max(3,duration/30)
        boundaries=[0.0]
        for cut in cuts:
            if cut-boundaries[-1]>=minimum and duration-cut>=minimum and len(boundaries)<30:
                boundaries.append(cut)
        boundaries.append(duration)
        scenes=[]
        for start,end in zip(boundaries,boundaries[1:]):
            _,stats=await self._run(['-hide_banner','-nostdin','-ss',str(start),'-i',str(source),
                '-t',str(min(3,end-start)),'-an','-vf','scale=320:-2,signalstats,metadata=mode=print','-f','null','-'],job)
            def average(key):
                values=[float(x) for x in re.findall(r'lavfi.signalstats\.'+key+r'=([\d.]+)',stats)]
                return sum(values)/len(values) if values else None
            brightness,low,high,movement=map(average,['YAVG','YLOW','YHIGH','YDIF'])
            dark=brightness is not None and brightness<55
            # YDIF is motion/change, deliberately not advertised as noise.
            metrics=RestorationSceneAnalysis(brightness=brightness,contrast=high-low if high is not None and low is not None else None,
                movement=movement,dark=dark)
            strength=(1.2,2.8,1.5,3.0) if dark else (0.7,1.5,1.0,2.0)
            if movement is not None and movement>8:strength=(strength[0],strength[1],0.5,1.0)
            scenes.append(SceneRestoration(start=start,end=end,options=plan.options.model_copy(deep=True),
                metrics=metrics,denoise_strength=strength,sharpen_amount=0.1 if dark else 0.15))
        plan.scenes=scenes
        plan.notes.append('Adaptive Denoise/Schärfung: kurze Messung pro Abschnitt; keine sichere Rausch-/Verwacklungsklassifikation.')
        self.save(plan)
        return plan

    @staticmethod
    def build_report(plan,actual,info,source_hash,output,output_hash):
        """Reproducible RestorationReport (Mission 3). Measured facts only, no quality score."""
        a=plan.analysis;o=plan.options
        video=info.video_streams[0] if info.video_streams else None
        audio=info.audio_streams[0] if info.audio_streams else None
        scan={'tff':'interlaced','bff':'interlaced','progressive':'progressive'}.get(a.field_order,'unknown')
        stab=plan.capabilities.get('stabilization',{}) if isinstance(plan.capabilities,dict) else {}
        return {
            'source':{'filename':Path(a.asset.path).name,'resolution':[actual.width,actual.height],
                'aspect_ratio':a.display_aspect_ratio,'sample_aspect_ratio':a.sample_aspect_ratio,'fps':a.fps,
                'field_order':a.field_order,'scan':scan,'duration':actual.duration,
                'video_codec':actual.video_codec,'audio_codec':actual.audio_codec,
                'pixel_format':a.pixel_format,'color_space':a.color_space,'bitrate':a.bitrate},
            'analysis':{'scenes':len(plan.scenes),
                'dark_scenes':sum(1 for s in plan.scenes if s.metrics and s.metrics.dark),
                'noise_proxy':a.noise_proxy,  # Proxy inkl. Textur/Bewegung, kein reiner Rauschwert.
                'stabilization_available':stab.get('level','none'),
                'stabilization_applied':bool(o.stabilize and stab.get('available')),
                'selected_preset':plan.preset,'uncertain':a.uncertain},
            'processing':{'deinterlace':o.deinterlacer if o.deinterlace else False,
                'field_order':o.field_order if o.deinterlace else None,
                'denoise':o.denoise,'chroma_denoise':o.denoise,  # hqdn3d filtert Luma und Chroma getrennt.
                'stabilization':(stab.get('level') if o.stabilize and stab.get('available') else 'off'),
                'color':o.color,'sharpen':o.sharpen,'upscale':o.size,'audio_restoration':o.audio,
                'scene_adaptive':bool(plan.scenes),'filters':list(plan.filters)},
            'result':{'resolution':[video.width,video.height] if video else None,
                'fps':video.fps if video else None,'video_codec':video.codec if video else None,
                'audio_codec':audio.codec if audio else None,'duration':info.duration_seconds,
                'filesize':output.stat().st_size,'path':str(output)},
            'integrity':{'source_sha256':source_hash,'output_sha256':output_hash,'source_unchanged':True},
        }

    @staticmethod
    def collect_sources(paths):
        """Expand files and folders to a de-duplicated, ordered list of video files."""
        from src.services.converter import Converter
        found=[]
        for raw in paths:
            item=Path(raw)
            if item.is_dir():
                found+=sorted(f for f in item.iterdir() if f.is_file() and f.suffix.lower() in Converter.VIDEO_EXTENSIONS)
            else:
                found.append(item)
        seen=set();ordered=[]
        for f in found:
            key=str(f.resolve()) if f.exists() else str(f)
            if key not in seen:seen.add(key);ordered.append(f)
        return ordered

    async def batch(self,paths,*,adaptive=False,preset=None,size=None,audio=None,encoder='auto',job=None,on_item=None):
        """Analyse -> optional Szenen -> Render pro Datei. Ein Fehler stoppt die Queue nicht (Mission 7).

        Gibt je Datei einen Statuseintrag zurück; Originale werden nie überschrieben
        (Render legt eindeutige Ausgabenamen an und lehnt vorhandene Ziele ab).
        """
        sources=self.collect_sources(paths)
        results=[]
        for index,source in enumerate(sources):
            entry={'index':index,'source':str(source),'status':'pending','project':None,'output':None,'report':None,'error':None}
            try:
                if not source.is_file():raise FileNotFoundError(f'Datei fehlt: {source}')
                plan=await self.analyze(source,job=job)
                if preset is not None:plan.preset=preset
                if size is not None:plan.options.size=size
                if audio is not None:plan.options.audio=audio
                if adaptive:plan=await self.analyze_scenes(plan,job=job)
                plan=await self.render(plan,preview=False,encoder=encoder,job=job)
                entry.update(status='done',project=plan.id,scenes=len(plan.scenes),
                    output=plan.outputs[-1] if plan.outputs else None,report=plan.report)
            except Exception as exc:
                entry.update(status='error',error=str(exc))
            results.append(entry)
            if on_item:on_item(index,entry,len(sources))
        return results

    async def archive(self,plan,job=None):
        """Lossless technical master, no restoration filters; never prioritise in Recent."""
        from datetime import datetime,timezone
        plan=RestorationPlan.model_validate(plan.model_dump())
        source=Path(plan.analysis.asset.path)
        if not source.is_file():raise FileNotFoundError('Archivquelle fehlt.')
        before=await asyncio.to_thread(self.checksum,source)
        self.output_dir.mkdir(parents=True,exist_ok=True)
        output=self.output_dir/f'Archive_{plan.id[:8]}_{uuid.uuid4().hex}.mkv'
        manifest=output.with_suffix('.json')
        # -n is required even for unpredictable unique names.
        try:
            encoders,_=await self._run(['-hide_banner','-encoders'],job)
            if not re.search(r'\bffv1\s',encoders):raise ValueError('FFV1-Encoder fehlt.')
            await self._run(['-hide_banner','-nostdin','-n','-i',str(source),'-map','0:v:0','-map','0:a?',
                '-map_metadata','-1','-c:v','ffv1','-level','3','-g','1','-slicecrc','1',
                '-c:a','pcm_s24le',str(output)],job)
            raw,_=await self._run(['-v','error','-show_streams','-show_format','-of','json',str(output)],job,probe=True)
            data=json.loads(raw);video=next(x for x in data['streams'] if x['codec_type']=='video')
            if video['codec_name']!='ffv1' or abs(float(data['format']['duration'])-plan.analysis.asset.duration)>.25:
                raise ValueError('Archivmaster hat unerwarteten Codec/Dauer.')
            await self._run(['-v','error','-xerror','-i',str(output),'-f','null','-'],job)
            if await asyncio.to_thread(self.checksum,source)!=before:raise ValueError('Archivquelle wurde verändert.')
            version,_=await self._run(['-version'])
            metadata={'source_file':source.name,'source_sha256':before,'archive_file':output.name,
                'archive_sha256':await asyncio.to_thread(self.checksum,output),'created_at':datetime.now(timezone.utc).isoformat(),
                'duration':float(data['format']['duration']),'video_codec':'ffv1',
                'audio_codec':[x['codec_name'] for x in data['streams'] if x['codec_type']=='audio'],
                'resolution':[video['width'],video['height']],'frame_rate':video.get('avg_frame_rate'),
                'field_order':video.get('field_order','unknown'),'aspect_ratio':video.get('display_aspect_ratio'),
                'ffmpeg_version':version.splitlines()[0],'retrodisc_version':self._version()}
            with manifest.open('x',encoding='utf-8') as f:json.dump(metadata,f,ensure_ascii=False,indent=2)
            plan.archives.append({'path':str(output),'manifest':str(manifest),'metadata':metadata})
            self.save(plan)
            return plan
        except BaseException:
            output.unlink(missing_ok=True);manifest.unlink(missing_ok=True)
            raise

    @staticmethod
    def _version():
        from importlib.metadata import version,PackageNotFoundError
        try:return version('retrodisc')
        except PackageNotFoundError:return 'development'
