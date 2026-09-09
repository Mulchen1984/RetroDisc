"""Local cross-platform FFmpeg/libass acceptance. No downloads or fake capability."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path


def run(ffmpeg,ffprobe,folder):
    def command(exe,*args):
        return subprocess.run([exe,*map(str,args)],capture_output=True,text=True,check=True,timeout=120)
    filters=command(ffmpeg,'-hide_banner','-filters').stdout
    names=set(re.findall(r'^\s*[.A-Z|]{2,3}\s+(\w+)\s',filters,re.M))
    if 'subtitles' not in names:
        return {'status':'CAPABILITY_UNAVAILABLE','reason':'FFmpeg has no subtitles/libass filter'}
    Path(folder).mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='caption-',dir=folder) as tmp:
        work=Path(tmp)
        command(ffmpeg,'-v','error','-n','-f','lavfi','-i','color=c=black:s=320x240:r=25',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','2',
                '-c:v','libx264','-c:a','aac',work/'source.mp4')
        (work/'caption.srt').write_text('1\n00:00:00,000 --> 00:00:01,900\nGrüße & Straße\nUnicode: ÄÖÜ ß\n',encoding='utf-8')
        # Relative filter input avoids drive-letter and quote escaping differences.
        subprocess.run([ffmpeg,'-v','error','-n','-i','source.mp4','-vf','subtitles=caption.srt',
                        '-c:v','libx264','-c:a','copy','output.mp4'],cwd=work,check=True,capture_output=True,timeout=120)
        info=json.loads(command(ffprobe,'-v','error','-show_streams','-show_format','-of','json',work/'output.mp4').stdout)
        command(ffmpeg,'-v','error','-xerror','-i',work/'output.mp4','-f','null','-')
        frame=subprocess.run([ffmpeg,'-v','error','-ss','0.5','-i',str(work/'output.mp4'),
                              '-frames:v','1','-pix_fmt','gray','-f','rawvideo','-'],capture_output=True,check=True,timeout=30).stdout
        if not frame or max(frame)-min(frame)<50:raise AssertionError('Caption produced no visible contrast on black fixture')
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        assert video['width']==320 and video['height']==240
        assert any(s['codec_type']=='audio' for s in info['streams'])
        assert abs(float(info['format']['duration'])-2)<.15
        return {'status':'PASS','codec':video['codec_name'],'decode':True,'visible_caption':True,'audio':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--ffmpeg',default='ffmpeg');parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--work',type=Path,default=Path('build/caption-acceptance'))
    args=parser.parse_args()
    print(json.dumps(run(args.ffmpeg,args.ffprobe,args.work),indent=2))
