"""Regression: use final timeline positions/durations when attaching music."""
import json
import re
import subprocess
from pathlib import Path


def test_music_respects_speed_freeze_and_transition_overlap():
    ui = (Path(__file__).resolve().parents[1] / 'src/ui/app.html').read_text()
    function = re.search(r'async function timelineMusic\(\)\{.*?^\}', ui, re.S | re.M).group(0)
    code = '''
const plan={assets:[],timeline:[
  {start:0,end:4,position:0,speed:2},
  {start:0,end:4,position:1.5,speed:1},
  {start:1,end:4,position:5.5,freeze_duration:2}
]};
let saved, applied;
const S={directorAssets:[{id:'music',kind:'audio',duration:30}]};
const field={value:JSON.stringify(plan)};
const document={getElementById:()=>field};
const api=()=>({
  director_save:async text=>{saved=JSON.parse(text);return JSON.stringify({id:'project'});},
  director_load:async()=>JSON.stringify(saved)
});
function timelineApply(p){applied=p;}
''' + function + '''
(async()=>{
 await timelineMusic();
 console.log(JSON.stringify({duration:applied.music[0].duration,original:plan}));
})().catch(e=>{console.error(e);process.exit(1);});
'''
    result = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=10, check=True)
    output = json.loads(result.stdout)
    assert output['duration'] == 7.5
    assert 'music' not in output['original']
