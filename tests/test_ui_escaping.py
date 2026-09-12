"""Regression guards for dynamic HTML attributes in the desktop UI.

The structural guards below pin down *where* interpolated values may appear.
They cannot prove that ``escAttr`` escapes correctly, because a reordered
``.replace()`` chain -- escaping ``&`` last instead of first -- would
double-encode every output while leaving each asserted substring in place.
``test_esc_attr_output_is_correct_for_real_input`` therefore executes the
shipped helper with Node and compares real output.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).parents[1] / "src" / "ui" / "app.html"
NODE = shutil.which("node")


def _html() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


def _esc_attr_source(html: str) -> str:
    match = re.search(r"function escAttr\(s\)\{[^\n]+\}", html)
    assert match, "escAttr helper is missing"
    return match.group(0)


def test_esc_attr_performs_html_attribute_escaping():
    html = _html()
    match = re.search(r"function escAttr\(s\)\{(?P<body>[^\n]+)\}", html)
    assert match, "escAttr helper is missing"

    body = match.group("body")
    assert "String(s ?? '')" in body
    for escaped in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert escaped in body
    assert "\\\\'" not in body
    assert "\\\\\"" not in body


def test_dynamic_paths_and_titles_are_passed_via_dataset():
    html = _html()

    # Interpolated values must never be placed inside quoted inline-JS
    # arguments; entity escaping belongs in data attributes instead.
    assert not re.search(r'onclick="[^"]*\$\{escAttr\(', html)

    assert 'data-url="${escAttr(r.url)}" data-title="${escAttr(r.title)}"' in html
    assert 'onclick="dlResultFromButton(event,this)"' in html
    assert "button.dataset.url" in html
    assert "button.dataset.title" in html

    assert 'data-path="${escAttr(f.path||f.filename)}" onclick="showMediaInfo(this.dataset.path)"' in html
    assert 'onclick="addLibFileToQueue(event,this)"' in html
    assert 'data-path="${escAttr(path)}" onclick="addLibFileToQueueDirect(this.dataset.path)"' in html
    assert "addLibFileToQueueDirect(button.dataset.path)" in html


# Erwartete Ausgabe des ausgelieferten escAttr für echte Eingaben.
# Die Einzelzeichenfälle sind die entscheidenden: Wird "&" nicht zuerst
# ersetzt, liefert "<" das doppelt kodierte "&amp;lt;" statt "&lt;".
ESC_ATTR_CASES = {
    "": "",
    "plain": "plain",
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
    "a&b&c": "a&amp;b&amp;c",
    "&amp;": "&amp;amp;",
    '" onclick="steal()': "&quot; onclick=&quot;steal()",
    "<img src=x onerror=alert(1)>": "&lt;img src=x onerror=alert(1)&gt;",
    "C:\\Musik\\Grüße & 日本.mp3": "C:\\Musik\\Grüße &amp; 日本.mp3",
}


@pytest.mark.skipif(NODE is None, reason="node is required to execute the shipped escAttr")
def test_esc_attr_output_is_correct_for_real_input(tmp_path):
    """Run the shipped escAttr and compare its real output.

    Nullish input must collapse to the empty string, every special character
    must be entity-encoded exactly once, and no output may be double-encoded.
    """
    inputs = list(ESC_ATTR_CASES)
    script = tmp_path / "esc_attr_check.js"
    script.write_text(
        _esc_attr_source(_html())
        + "\nconst cases = "
        + json.dumps(inputs)
        + ";\nconst out = cases.map(escAttr);"
        + "\nout.push(escAttr(null), escAttr(undefined));"
        + "\nprocess.stdout.write(JSON.stringify(out));\n",
        encoding="utf-8",
    )

    result = subprocess.run([NODE, str(script)], capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")

    produced = json.loads(result.stdout.decode("utf-8"))
    assert produced[len(inputs) :] == ["", ""], "null/undefined must escape to the empty string"
    assert dict(zip(inputs, produced)) == ESC_ATTR_CASES


@pytest.mark.skipif(NODE is None, reason="node is required to execute queue rendering")
def test_queue_escapes_titles_and_labels_long_result_paths(tmp_path):
    html = _html()
    render = html[html.index('function renderJobs() {'):html.index('async function confirmCopyMedium(')]
    render += '\n' + html[html.index('function revealOutputButton('):html.index('async function openOutputFolder(')]
    esc_html = re.search(r'function escHtml\(s\)\{[^\n]+\}', html).group(0)
    title = '\"><img src=x onerror=alert(1)> & 日本'
    paths = ['/Movies/' + 'long/' * 70 + title + '.webm', '/Music/' + title + '.mp3']
    script = tmp_path / 'queue.js'
    script.write_text(_esc_attr_source(html) + '\n' + esc_html + '\n' + render + '\n'
        + 'const target={innerHTML:""}; const document={getElementById:()=>target};\n'
        + 'const S={jobs:' + json.dumps([{'id':'test', 'name':title, 'state':'done', 'outputPaths':paths}]) + '};\n'
        + 'renderJobs(); process.stdout.write(target.innerHTML);', encoding='utf-8')
    result = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=10, check=True)
    assert '<img' not in result.stdout
    assert '&lt;img' in result.stdout
    assert '<b>Video:</b>' in result.stdout and '<b>Audio:</b>' in result.stdout
    assert 'long/' * 70 in result.stdout
    assert 'overflow-wrap:anywhere' in result.stdout


@pytest.mark.skipif(NODE is None, reason="Node required")
def test_final_output_buttons_pass_exact_path_and_report_errors(tmp_path):
    html = _html()
    functions = html[html.index('function finalOutputPaths('):html.index('// ── Startup', html.index('function finalOutputPaths('))]
    script = tmp_path / 'reveal.js'
    script.write_text(_esc_attr_source(html) + '\n' + functions + r'''
const assert = require('node:assert/strict');
Object.defineProperty(globalThis,'navigator',{value:{platform:'MacIntel'},configurable:true});
const path = '/actual output/Grüße & 日本 \".mp4';
let received, status, failure = false;
function api(){return {open_output_folder:async p=>{received=p;return JSON.stringify(failure?{error:'Finder fehlgeschlagen'}:{ok:true})}}}
function setStat(s){status=s}
function alert(){}
(async()=>{
 assert.deepEqual(finalOutputPaths({output:path}),[path]);
 assert.deepEqual(finalOutputPaths({output:path,output_paths:[path,'/second.mp3']}),[path,'/second.mp3']);
 assert.ok(revealOutputButton(path).includes('Im Finder öffnen'));
 assert.ok(revealOutputButton(path).includes('openOutputFolder(this.dataset.path)'));
 assert.ok(revealOutputButton(path).includes('&amp;'));
 await openOutputFolder(path); assert.equal(received,path);
 failure=true; await openOutputFolder(path); assert.equal(status,'Finder fehlgeschlagen');
})().catch(e=>{console.error(e);process.exit(1)});
''')
    subprocess.run([NODE, str(script)], check=True, capture_output=True, text=True, timeout=10)


@pytest.mark.skipif(NODE is None, reason='Node required')
def test_director_outputs_reuse_safe_workflow_buttons(tmp_path):
    html=_html()
    functions=html[html.index('function directorSummarizePlan('):html.index('async function directorRenderPlan(')]
    functions+='\n'+html[html.index('function revealOutputButton('):html.index('async function openOutputFolder(')]
    helpers=_esc_attr_source(html)+'\n'+re.search(r'function escHtml\(s\)\{[^\n]+\}',html).group()
    script=tmp_path/'director-ui.js'
    script.write_text(helpers+'\n'+functions+r'''
const assert=require('node:assert/strict');
const nodes={directorOutputs:{},directorPlan:{value:JSON.stringify({voiceover:[{voice:'Anna'}]})},directorAudio:{value:'keep'},directorVoice:{value:''}};
const document={getElementById:id=>nodes[id]};
directorShowOutputs(['/Movies/<img onerror="bad"> & 日本.mp4','/Music/voice.wav']);
const out=nodes.directorOutputs.innerHTML;
assert.ok(out.includes('&lt;img'));
assert.ok(!out.includes('<img'));
assert.equal((out.match(/data-target="burn"/g)||[]).length,1);
assert.equal((out.match(/data-target="convert"/g)||[]).length,2);
assert.ok(out.includes('useRecentMedia(this)'));
assert.ok(out.includes('openOutputFolder(this.dataset.path)'));
directorEditAudio();
assert.equal(JSON.parse(nodes.directorPlan.value).voiceover[0].voice,'Anna');
assert.equal(JSON.parse(nodes.directorPlan.value).original_audio,'keep');
''')
    subprocess.run([NODE,str(script)],check=True,capture_output=True,text=True,timeout=10)


@pytest.mark.skipif(NODE is None, reason='Node required')
def test_director_plan_summary_shows_sources_and_fallback_as_text(tmp_path):
    html=_html()
    source=html[html.index('function directorSummarizePlan('):html.index('async function directorTranslatePlan(')]
    steps_source=html[html.index('function directorUpdateSteps('):html.index('function directorShowOutputs(')]
    script=tmp_path/'plan-summary.js'
    script.write_text(r'''
function escHtml(s){return String(s);}
const S={directorAssets:[]};
'''+steps_source+source+r'''
const assert=require('node:assert/strict');
const summary={};const plan={title:'<img src=x>',target_duration:8,planner:'metadata',story:['Storyline'],notes:['LLM Fallback'],assets:[{id:'a',title:'Quelle',path:'/Video/日本.mp4'}],timeline:[{asset_id:'a',start:12.4,end:18.8,position:0}],voiceover:[{position:0,text:'Hallo'}]};
const document={getElementById:id=>id==='directorPlanSummary'?summary:{value:JSON.stringify(plan)}};
directorSummarizePlan();
assert.ok(summary.textContent.includes('Von: 00:12.4'));
assert.ok(summary.textContent.includes('/Video/日本.mp4'));
assert.ok(summary.textContent.includes('LLM Fallback'));
assert.ok(summary.textContent.includes('Voiceover 00:00.0: Hallo'));
assert.equal(summary.innerHTML,undefined);
''')
    subprocess.run([NODE,str(script)],check=True,capture_output=True,text=True,timeout=10)
