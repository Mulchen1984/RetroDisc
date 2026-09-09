"""Local native speech adapter. No voice cloning or model installation is implied."""
import asyncio
import shutil
import re
import sys
import tempfile
from pathlib import Path
from src.utils.subprocesses import create_hidden_subprocess, communicate_with_job, run_hidden


class LocalVoice:
    @staticmethod
    def capability():
        available=sys.platform == 'darwin' and bool(shutil.which('say'))
        voices=[]
        if available:
            try:
                result=run_hidden([shutil.which('say'),'-v','?'],capture_output=True,text=True,check=True,timeout=5)
                for line in result.stdout.splitlines():
                    match=re.match(r'(.+?)\s+([a-z]{2}_[A-Z]{2})\s+#',line)
                    if match:
                        voices.append({'name':match[1].strip(),'language':match[2]})
            except Exception as exc:
                return {'available':False,'engine':'macOS say','voice_cloning':False,'voices':[], 'note':str(exc)}
        preferred=next((v['name'] for v in voices if v['name']=='Anna' and v['language'].startswith('de_')),None)
        preferred=preferred or next((v['name'] for v in voices if v['language'].startswith('de_')),'')
        return {'available':available, 'engine':'macOS say' if sys.platform=='darwin' else 'unavailable', 'voice_cloning':False,
                'voices':voices,'preferred_voice':preferred}

    async def synthesize(self, text, output, ffmpeg, voice='', job=None, language='de'):
        caps=self.capability()
        if not caps['available']:
            raise RuntimeError('Keine lokale TTS-Engine verfügbar; Voice-Cloning wird nicht unterstützt.')
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.voice-', dir=output.parent) as temp:
            folder=Path(temp)
            (folder/'text.txt').write_text(text, encoding='utf-8')
            cmd=[shutil.which('say'),'-f',str(folder/'text.txt'),'-o',str(folder/'voice.aiff')]
            if voice not in {v['name'] for v in caps.get('voices',[])}:
                voice=next((v['name'] for v in caps.get('voices',[]) if v['language'].startswith(language.split('-')[0]+'_')),caps.get('preferred_voice',''))
            if voice:
                cmd += ['-v',voice]
            proc=await create_hidden_subprocess(*cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            _, error=await asyncio.wait_for(communicate_with_job(proc,job),timeout=120)
            if proc.returncode:
                raise RuntimeError(error.decode('utf-8',errors='replace'))
            return await ffmpeg.convert(folder/'voice.aiff',output,audio_codec='pcm_s16le',
                sample_rate=48000,extra_args=['-vn','-ac','2'],job=job)
