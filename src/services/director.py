"""Small local production coordinator: library assets → reviewable plan → FFmpeg."""
from __future__ import annotations
import asyncio
import json
import math
import os
import re
import tempfile
import uuid
import wave
from dataclasses import replace
from pathlib import Path

from src.config.presets import get_preset
from src.models.director import ProductionProject, Scene, PlanProposal, Voiceover, AudioPlacement
from src.services.converter import Converter
from src.services.editor_filters import tempo,join_graph,clip_filters
from src.services.subtitle import SubtitleGenerator
from src.services.voice import LocalVoice
from src.utils.subprocesses import (create_hidden_subprocess, communicate_with_job,
    commit_staged_output, staging_output_path)


class Director:
    def __init__(self, library, ffmpeg, assistant, output_dir, audio_dir, temp_dir):
        self.library, self.ffmpeg, self.assistant = library, ffmpeg, assistant
        self.output_dir, self.audio_dir, self.temp_dir = map(Path, (output_dir,audio_dir,temp_dir))
        self.projects_dir = library.db_path.parent / 'projects'

    async def capabilities(self):
        models=await self.assistant.available_models()
        tts=LocalVoice.capability()
        return {'whisper':SubtitleGenerator.capability(), 'tts':tts,
                'llm_models':models, 'preferred_model':next((m for m in ['llama3.2:3b','qwen2.5-coder:3b'] if m in models),''),
                'music_generation':False, 'sound_generation':False, 'dubbing':bool(models) and tts['available'],
                'note':'Rohschnitt ohne LLM möglich. Dubbing: lokaler Prototyp mit geprüftem Transkript. Keine Musikgenerierung/Voice-Cloning.'}

    async def transcribe(self, asset, model='base', language=None, job=None):
        capability=SubtitleGenerator.capability(model)
        if not capability['available']:
            raise RuntimeError('Whisper ist nicht installiert oder nicht einsatzbereit. '+capability.get('note','Keine Transkription erzeugt.'))
        if not asset.audio_codec:
            raise ValueError(f'Asset hat keine Audiospur: {asset.title}')
        self.temp_dir.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='director-transcript-',dir=self.temp_dir) as tmp:
            audio=Path(tmp)/'audio.wav'
            await self.ffmpeg.convert(asset.path,audio,audio_codec='pcm_s16le',sample_rate=16000,
                                      extra_args=['-vn','-ac','1'],job=job)
            result=await SubtitleGenerator(capability.get('model_path') or model).generate(audio,Path(tmp)/'transcript.json',format='json',language=language,job=job)
            data=json.loads(result.read_text(encoding='utf-8'))
            segments=data.get('segments',[])
            for s in segments:
                if not (math.isfinite(s['start']) and math.isfinite(s['end']) and 0 <= s['start'] < s['end'] <= asset.duration+0.2):
                    raise ValueError('Ungültige Whisper-Zeitsegmente.')
            for segment in segments:
                segment['language']=data.get('language') or language or 'und'
            transcript={'language':data.get('language'), 'text':data.get('text',''), 'segments':segments}
            self.library.attach_transcript(asset.path,transcript)
            return await self.library.asset(asset.path)

    async def select_time_ranges(self, asset, segments, target, wish='', model=''):
        """Mission 11: reuse the local LLM to choose highlight ranges; caller validates + falls back."""
        if model and model not in await self.assistant.available_models():
            raise RuntimeError('Lokales Modell nicht verfügbar; deterministischer Fallback.')
        if model:
            self.assistant.model = model
        payload = {'duration': asset.duration, 'target_seconds': target,
                   'wish': wish or 'Finde die interessantesten Abschnitte.',
                   'segments': [{'start': round(float(s), 2), 'end': round(float(e), 2), 'text': str(t)[:200]}
                                for s, e, t in segments[:200]]}
        return [(r['start'], r['end']) for r in await self.assistant.highlight_ranges(payload)]

    async def plan(self, prompt, paths, target_duration=0, model='', transcribe=False, whisper_model='base'):
        if not prompt.strip():
            raise ValueError('Bitte einen Produktionsauftrag eingeben.')
        unique=list(dict.fromkeys(paths))
        if not 1 <= len(unique) <= 20:
            raise ValueError('Bitte 1 bis 20 Medien auswählen.')
        assets=[await self.library.asset(path) for path in unique]
        if transcribe:
            assets=[await self.transcribe(a,whisper_model) if a.audio_codec else a for a in assets]
        videos=[a for a in assets if a.kind=='video' and a.duration > 0]
        if not videos:
            raise ValueError('Für einen Schnittplan wird mindestens ein Video benötigt.')
        match=re.search(r'(\d+(?:[.,]\d+)?)\s*[- ]?(?:Sekunden|seconds|Sek\b|s\b)',prompt,re.I)
        requested=target_duration or (float(match[1].replace(',','.')) if match else 60)
        if not 0 < requested <= 600:
            raise ValueError('Zieldauer muss zwischen 0 und 600 Sekunden liegen.')
        remaining=min(requested,sum(a.duration for a in videos))
        position=0.0
        timeline=[]
        words=set(re.findall(r'\w{4,}',prompt.lower()))
        for i,asset in enumerate(videos):
            length=min(asset.duration, remaining/(len(videos)-i))
            segments=(asset.transcript or {}).get('segments',[])
            scored=sorted(segments,key=lambda s:len(words & set(re.findall(r'\w{4,}',s.get('text','').lower()))),reverse=True)
            start=min(float(scored[0]['start']),max(0,asset.duration-length)) if scored else 0.0
            if scored and words & set(re.findall(r'\w{4,}',scored[0].get('text','').lower())):
                start=float(scored[0]['start'])
                length=min(length,float(scored[0]['end'])-start,asset.duration-start)
            if length > 0:
                timeline.append(Scene(asset_id=asset.id,start=start,end=start+length,position=position))
                position+=length
                remaining-=length
        project=ProductionProject(prompt=prompt,target_duration=requested,assets=assets,timeline=timeline,
            story=['Rohschnitt aus ausgewählten Quellen; inhaltliche Auswahl ohne LLM nur anhand vorhandener Transkriptwörter.'],
            notes=['Keine visuelle Szenenanalyse. Keine generierte Musik oder erfundenen Sprechertexte.'])
        if project.duration < requested-0.05:
            project.notes.append(f'Quellmaterial reicht nur für {project.duration:.2f}s; keine künstliche Wiederholung.')
        explicit_voice=re.search(r'Sprechertext\s*:\s*["„](.+?)["“]',prompt,re.I|re.S)
        if explicit_voice:
            project.voiceover=[Voiceover(text=explicit_voice[1],position=0)]
        if model:
            draft=project.model_dump()
            # Bound transcript context; full transcripts remain in the library/project.
            for asset in draft['assets']:
                transcript=asset.get('transcript') or {}
                segments=transcript.get('segments',[])
                ranked=sorted(segments,key=lambda seg:len(words & set(re.findall(r'\w{4,}',seg.get('text','').lower()))),reverse=True)
                asset['transcript']={'language':transcript.get('language'), 'segments':[
                    {**seg,'text':seg.get('text','')[:600]} for seg in ranked[:8]]} if segments else None
            draft.pop('outputs',None)
            draft.pop('generated_audio',None)
            if model not in await self.assistant.available_models():
                project.notes.append('Lokales Modell nicht verfügbar; deterministischer Fallback, kein Download.')
            else:
                # Exactly two attempts, including semantic validation against real assets.
                for attempt in range(2):
                    try:
                        self.assistant.model=model
                        proposal=await self.assistant.production_plan(draft)
                        edits=PlanProposal.model_validate(proposal).model_dump()
                        # Positions are derived from source cuts; never trust model arithmetic.
                        position=0.0
                        for scene in edits['timeline']:
                            scene['position']=position
                            position+=scene['end']-scene['start']
                        candidate=ProductionProject.model_validate(project.model_dump() | edits | {'planner':'ollama'})
                        if set(s.asset_id for s in candidate.timeline) != set(a.id for a in videos):
                            raise ValueError('Jedes ausgewählte Video muss im Plan vorkommen.')
                        if abs(candidate.duration-project.duration)>0.05:
                            raise ValueError(f'Timeline muss {project.duration:.2f} Sekunden lang sein.')
                        project=candidate
                        break
                    except Exception as exc:
                        draft['repair']={'error':str(exc)[:2000],
                            'instruction':'Einziger Reparaturversuch: gültigen vollständigen Plan liefern. Vorhandene Timeline als sichere Basis verwenden.'}
                        if attempt == 1:
                            project.notes.append('LLM-Plan nach zwei Versuchen ungültig: deterministischer Fallback. ' + str(exc)[:500])
        self.save(project)
        return project

    def save(self, project):
        project=ProductionProject.model_validate(project.model_dump())
        self.projects_dir.mkdir(parents=True,exist_ok=True)
        target=self.projects_dir/f'{project.id}.json'
        fd,name=tempfile.mkstemp(prefix='.project-',suffix='.json',dir=self.projects_dir)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                f.write(project.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(name,target)
        finally:
            Path(name).unlink(missing_ok=True)
        return target

    def load(self, project_id):
        if not re.fullmatch(r'[a-f0-9]{32}',project_id):
            raise ValueError('Ungültige Projekt-ID.')
        project=ProductionProject.model_validate_json((self.projects_dir/f'{project_id}.json').read_text(encoding='utf-8'))
        for asset in project.assets:
            warning=f'Quelldatei fehlt: {asset.path}'
            if not Path(asset.path).is_file() and warning not in project.notes:
                project.notes.append(warning)
        return project

    def list_projects(self):
        result=[]
        for path in sorted(self.projects_dir.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
            try:
                project=self.load(path.stem)
                result.append({'id':project.id,'title':project.title,'outputs':project.outputs})
            except (ValueError,OSError):
                continue
        return result

    async def _command(self,args,job,cwd=None):
        proc=await create_hidden_subprocess(self.ffmpeg.ffmpeg_path,'-hide_banner','-loglevel','error','-nostdin',*args,
            cwd=cwd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        _,err=await communicate_with_job(proc,job)
        if proc.returncode:
            from src.core.errors import EncodeError
            raise EncodeError('Editor-Rendering fehlgeschlagen. Filter, Quelle und Ausgabeverzeichnis prüfen.',detail=err.decode('utf-8',errors='replace'))

    @staticmethod
    def subtitle_segments(project, voice_lengths=()):
        # Spoken production text takes precedence over overlapping original subtitles.
        if voice_lengths:
            return [{'start':cue.position,'end':cue.position+length,'text':cue.text,'language':cue.language}
                    for cue,length in voice_lengths]
        assets={a.id:a for a in project.assets}
        segments=[]
        for scene in project.timeline:
            if scene.freeze_duration:continue
            for seg in (assets[scene.asset_id].transcript or {}).get('segments',[]):
                start=max(scene.start,float(seg['start']));end=min(scene.end,float(seg['end']))
                if end>start:
                    segments.append({'start':scene.position+(start-scene.start)/scene.speed,'end':scene.position+(end-scene.start)/scene.speed,'text':seg['text']})
        return sorted(segments,key=lambda seg:seg['start'])

    async def prepare_dubbing(self, project, provider):
        from src.services.translation import translate_dubbing
        if project.dubbing is None:
            raise ValueError('Kein Dubbing-Plan vorhanden.')
        translated=await translate_dubbing(project.dubbing,provider)
        result=ProductionProject.model_validate(project.model_dump())
        result.dubbing=translated
        self.save(result)
        return result

    async def render_dubbing(self, project, encoder='auto', job=None):
        # Reuse the normal cut/voice/mix renderer with a full-length source scene.
        project=ProductionProject.model_validate(project.model_dump())
        plan=project.dubbing
        if not plan or not plan.cues or any(not c.translated_text for c in plan.cues):
            raise ValueError('Dubbing benötigt geprüfte übersetzte Segmente.')
        asset=next(a for a in project.assets if a.id==plan.asset_id)
        working=project.model_dump() | {'dubbing':None,'target_duration':asset.duration,
            'timeline':[Scene(asset_id=asset.id,start=0,end=asset.duration,position=0).model_dump()],
            'original_audio':plan.original_audio,
            'voiceover':[Voiceover(text=c.translated_text,position=c.start,voice=c.voice,
                language=plan.target_language,max_duration=c.end-c.start).model_dump() for c in plan.cues]}
        rendered=ProductionProject.model_validate(working)
        try:
            output=await self.render(rendered,encoder,job)
            stored=self.load(project.id)
            project.outputs=stored.outputs
            project.generated_audio=stored.generated_audio
            project.subtitle_paths=stored.subtitle_paths
            return output
        finally:
            self.save(project)

    async def render(self, project, encoder='auto', job=None):
        project=ProductionProject.model_validate(project.model_dump())
        if project.dubbing is not None:
            raise ValueError('Dubbing ist als Plan gespeichert, aber noch nicht renderbar. Kein Übersetzungsprovider angebunden.')
        # Validate against current library metadata, not editable duration assertions.
        current=[await self.library.asset(a.path) for a in project.assets]
        if [a.id for a in current] != [a.id for a in project.assets]:
            raise ValueError('Asset-Referenzen stimmen nicht überein.')
        project=ProductionProject.model_validate(project.model_dump() | {'assets':[a.model_dump() for a in current]})
        assets={a.id:a for a in project.assets}
        self.temp_dir.mkdir(parents=True,exist_ok=True)
        self.output_dir.mkdir(parents=True,exist_ok=True)
        output=self.output_dir/f'Director_{project.id[:8]}_{uuid.uuid4().hex[:8]}.mp4'
        staging=staging_output_path(output)
        generated=[]
        subtitle=output.with_suffix('.srt')
        self.save(project)
        try:
            with tempfile.TemporaryDirectory(prefix='director-render-',dir=self.temp_dir) as tmp:
                work=Path(tmp)
                clips=[]
                audio_parts=[]
                for i,scene in enumerate(project.timeline):
                    asset=assets[scene.asset_id]
                    duration=scene.duration
                    input_path=asset.path
                    if asset.kind=='image':
                        input_path=work/f'image-{i}.mkv'
                        await self._command(['-loop','1','-i',asset.path,'-t',str(scene.end-scene.start),'-vf',
                            'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1',
                            '-r','30','-c:v','ffv1',str(input_path)],job)
                    visual='1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1'
                    if scene.zoom!='off':
                        step=0.0003 if scene.zoom=='subtle' else 0.0008
                        visual+=f",zoompan=z='min(1.12,1+on*{step})':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1280x720:fps=30"
                    local=scene.transition if isinstance(scene.transition,str) else scene.transition.type
                    if not scene.overlap and local!='cut':
                        fade=min(.35,duration/3) if isinstance(scene.transition,str) else scene.transition.duration
                        if local in ('fade','fade_from_black','dip_black'):visual+=f',fade=t=in:d={fade}'
                        if local in ('fade_to_black','dip_black'):visual+=f',fade=t=out:st={duration-fade}:d={fade}'
                    preset=replace(get_preset('mp4_h264_720p'),audio_codec=None,audio_bitrate=None,fps=30,
                        resolution=None,
                        extra_args=['-preset','medium','-crf','23','-t',str(duration),'-vf',
                            f'trim=start={0 if asset.kind=="image" else scene.start}:duration={scene.end-scene.start},setpts=(PTS-STARTPTS)/{scene.speed},'+
                            (f'select=eq(n\\,0),tpad=stop_mode=clone:stop_duration={duration},' if scene.freeze_duration else '')+
                            (','.join(clip_filters(scene))+',' if clip_filters(scene) else '')+'scale='+visual+(',drawbox=c=black:t=fill' if not scene.visible else ''),'-an'])
                    clip=await Converter(self.ffmpeg).convert_file(input_path,preset,work/f'{i}.mp4',hwaccel=encoder,job=job)
                    clips.append(clip)
                    audio=work/f'{i}.wav'
                    if asset.audio_codec and project.original_audio!='mute' and not scene.muted and not scene.freeze_duration:
                        await self.ffmpeg.convert(asset.path,audio,audio_codec='pcm_s16le',sample_rate=48000,
                            extra_args=['-t',str(duration),'-vn','-ac','2','-af',f'atrim=start={scene.start}:end={scene.end},asetpts=PTS-STARTPTS,'+tempo(scene.speed)+f',volume={scene.volume},afade=t=in:d={scene.audio_fade_in},afade=t=out:st={max(0,duration-scene.audio_fade_out)}:d={scene.audio_fade_out},apad'],job=job)
                    else:
                        with wave.open(str(audio),'wb') as stream:
                            stream.setparams((2,2,48000,0,'NONE','not compressed'))
                            remaining=round(duration*48000)
                            while remaining:
                                count=min(remaining,48000)
                                stream.writeframes(b'\0'*(count*4))
                                remaining-=count
                    audio_parts.append(audio)
                original=work/'original.wav'
                if any(s.overlap for s in project.timeline):
                    graph,v,a=join_graph(project.timeline)
                    inputs=[]
                    for clip,audio in zip(clips,audio_parts):inputs+=['-i',str(clip),'-i',str(audio)]
                    lossless=work/'transitions.mkv'
                    await self._command(inputs+['-filter_complex_threads','1','-filter_complex',';'.join(graph),
                        '-map',f'[{v}]','-an','-c:v','ffv1',str(lossless),'-map',f'[{a}]','-vn','-c:a','pcm_s16le',str(original)],job)
                    joined=await Converter(self.ffmpeg).convert_file(lossless,replace(get_preset('mp4_h264_720p'),resolution=None,audio_codec=None),work/'joined.mp4',hwaccel=encoder,job=job)
                else:
                    joined=await self.ffmpeg.merge(clips,work/'joined.mp4',job=job)
                    original=work/'original.wav'
                    with wave.open(str(original),'wb') as combined:
                        combined.setparams((2,2,48000,0,'NONE','not compressed'))
                        for part in audio_parts:
                            with wave.open(str(part),'rb') as stream:
                                while data:=stream.readframes(48000):
                                    combined.writeframes(data)
                joined=await self.compose(project,assets,joined,work,encoder,job)
                args=['-i',str(joined),'-i',str(original)]
                filters=[f'[1:a]volume={project.original_volume}[original]']
                labels=['[original]']
                voice_lengths=[]
                for i,cue in enumerate(project.voiceover if project.voiceover_enabled else []):
                    voice=self.audio_dir/f'Director_{project.id[:8]}_{uuid.uuid4().hex[:8]}.wav'
                    generated.append(voice)
                    await LocalVoice().synthesize(cue.text,voice,self.ffmpeg,cue.voice,job,language=cue.language)
                    info=await self.ffmpeg.probe(voice)
                    allowed=min(cue.max_duration or project.duration,project.duration-cue.position)
                    if info.duration_seconds > allowed:
                        factor=info.duration_seconds/allowed
                        if factor > 1.25:
                            raise ValueError('Sprachsegment ist zu lang; mehr als 25% Beschleunigung nötig. Übersetzung kürzen.')
                        fitted=work/f'voice-fit-{i}.wav'
                        await self.ffmpeg.convert(voice,fitted,audio_codec='pcm_s16le',sample_rate=48000,
                            extra_args=['-af',f'atempo={factor}','-ac','2'],job=job)
                        os.replace(fitted,voice)
                        info=await self.ffmpeg.probe(voice)
                    if cue.position+info.duration_seconds > project.duration+0.1:
                        raise ValueError('Sprechertext ist länger als die Timeline. Text kürzen oder Timeline verlängern.')
                    voice_lengths.append((cue,info.duration_seconds))
                    args+=['-i',str(voice)]
                    filters.append(f'[{i+2}:a]adelay={round(cue.position*1000)}:all=1[voice{i}]')
                    labels.append(f'[voice{i}]')
                if project.original_audio == 'duck' and generated:
                    intervals='+'.join(f'between(t,{cue.position},{cue.position+length})' for cue,length in voice_lengths)
                    filters[0]=f"[1:a]volume={project.original_volume},volume=0.2:enable='{intervals}'[original]"
                for i,track in enumerate(project.music+project.sound_effects+[AudioPlacement(asset_id=o.asset_id,position=o.start,start=o.source_start,duration=o.duration,volume=o.volume,duck=False) for o in project.overlays if not o.muted and o.volume and assets[o.asset_id].audio_codec]):
                    asset=assets[track.asset_id]
                    args+=['-i',asset.path]
                    length=track.duration
                    envelope=f'volume={track.volume},afade=t=in:d={min(track.fade_in,length)},afade=t=out:st={max(0,length-track.fade_out)}:d={min(track.fade_out,length)}'
                    duck=''
                    if track.duck and voice_lengths:
                        intervals='+'.join(f'between(t,{cue.position},{cue.position+seconds})' for cue,seconds in voice_lengths)
                        duck=f",volume=0.25:enable='{intervals}'"
                    filters.append(f'[{2+len(voice_lengths)+i}:a]atrim=start={track.start}:duration={length},asetpts=PTS-STARTPTS,{envelope},adelay={round(track.position*1000)}:all=1'+duck+f'[track{i}]')
                    labels.append(f'[track{i}]')
                filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0:duration=longest[mix]')
                args+=['-filter_complex',';'.join(filters),'-map','0:v:0','-map','[mix]',
                    '-c:v','copy','-c:a','aac','-b:a','192k','-t',str(project.duration),'-movflags','+faststart',str(staging)]
                await self._command(args,job)
                info=await self.ffmpeg.probe(staging)
                if not info.video_streams or not info.audio_streams or abs(info.duration_seconds-project.duration)>0.2:
                    raise ValueError('Render-Ausgabe hat falsche Streams oder Dauer.')
                commit_staged_output(staging,output)
            segments=self.subtitle_segments(project,voice_lengths) if project.voiceover_enabled else self.subtitle_segments(project.model_copy(update={'voiceover':[]}),[])
            if segments:
                subtitle.write_text(SubtitleGenerator()._to_srt(segments),encoding='utf-8')
                project.subtitle_paths.append(str(subtitle))
            project.outputs.append(str(output))
            project.generated_audio.extend(map(str,generated))
            await self.library.asset(output)
            for path in generated:
                await self.library.asset(path)
            self.save(project)
            if job:
                job.output_path=output
                job.params['output_paths']=[str(output),*map(str,generated)]
                job.params['project_id']=project.id
                job.params['subtitle_paths']=project.subtitle_paths
            return output
        except BaseException:
            staging.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            subtitle.unlink(missing_ok=True)
            # Only files created by this render attempt are removed.
            for path in generated:
                path.unlink(missing_ok=True)
            raise

    async def compose(self,project,assets,joined,work,encoder,job):
        overlays=[o for o in project.overlays if o.visible]
        texts=[t for t in project.text_clips if t.visible]
        if not overlays and not texts:return joined
        proc=await create_hidden_subprocess(self.ffmpeg.ffmpeg_path,'-hide_banner','-filters',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        out,_=await communicate_with_job(proc,job,max_output_bytes=1024*1024)
        names=set(re.findall(r'^\s*[.A-Z|]{2,3}\s+(\w+)\s',out.decode(),re.M))
        if texts and 'drawtext' not in names:raise ValueError('Texteinblendung nicht verfügbar: FFmpeg ohne drawtext/Font-Unterstützung.')
        if overlays and 'overlay' not in names:raise ValueError('Overlay-Filter nicht verfügbar.')
        args=['-i',str(joined)];graph=['[0:v]format=yuv420p[base]'];label='base'
        for i,o in enumerate(overlays):
            asset=assets[o.asset_id]
            if asset.kind=='image':args+=['-loop','1']
            args+=['-i',asset.path]
            graph.append(f'[{i+1}:v]trim=start={o.source_start}:duration={o.duration},setpts=PTS-STARTPTS+{o.start}/TB,scale={o.width}:{o.height},format=rgba,colorchannelmixer=aa={o.opacity}[overlay{i}]')
            graph.append(f'[{label}][overlay{i}]overlay=x={o.x}:y={o.y}:eof_action=pass:enable=\'between(t,{o.start},{o.start+o.duration})\'[layer{i}]')
            label=f'layer{i}'
        for i,t in enumerate(texts):
            (work/f'text{i}.txt').write_text(t.text,encoding='utf-8')
            x={'bottom_left':'40','bottom_right':'w-tw-40'}.get(t.position,{'left':'40','center':'(w-tw)/2','right':'w-tw-40'}[t.alignment])
            y={'top':'40','center':'(h-th)/2'}.get(t.position,'h-th-40')
            alpha=str(t.opacity)
            if t.fade_in:alpha+=f'*min(1,max(0,(t-{t.start})/{t.fade_in}))'
            if t.fade_out:alpha+=f'*min(1,max(0,({t.start+t.duration}-t)/{t.fade_out}))'
            graph.append(f"[{label}]drawtext=textfile=text{i}.txt:expansion=none:fontsize={t.font_size}:fontcolor=white:x={x}:y={y}:alpha='{alpha}':enable='between(t,{t.start},{t.start+t.duration})'[text{i}]")
            label=f'text{i}'
        raw=work/'composition.mkv'
        await self._command(args+['-filter_complex_threads','1','-filter_complex',';'.join(graph),'-map',f'[{label}]','-an','-t',str(project.duration),'-c:v','ffv1',str(raw)],job,cwd=work)
        return await Converter(self.ffmpeg).convert_file(raw,replace(get_preset('mp4_h264_720p'),resolution=None,audio_codec=None),work/'composition.mp4',hwaccel=encoder,job=job)
