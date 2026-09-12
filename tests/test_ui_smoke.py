"""WebView-freier JS-Smoke: die neuen Panel-Funktionen laufen ohne Runtime-Fehler.

Führt die tatsächlich ausgelieferten app.html-Funktionen unter Node mit einem
minimalen DOM/Bridge-Mock aus (wie test_drive_detection_ui) und prüft, dass die
Smart-Edit-/Short-/Batch-/Archiv-Panels ohne JS-Exception initialisieren und die
Caption-Capability korrekt in beiden Zuständen auf die UI wirkt.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

UI = (Path(__file__).resolve().parents[1] / "src/ui/app.html").read_text(encoding="utf-8")


def function(name):
    match = re.search(r"(?:async )?function " + name + r"\([^)]*\)\s*\{.*?^\}", UI, re.S | re.M)
    assert match, f"Funktion nicht gefunden/extrahierbar: {name}"
    return match.group(0)


def run_js(code):
    node = shutil.which("node")
    assert node, "Node wird für den echten UI-Smoke benötigt"
    result = subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# Gemeinsamer Harness: DOM-Knoten merken sich innerHTML/textContent/value/options.
HARNESS = r"""
const store = {};
function node(id){
  if(!store[id]) store[id] = {id, innerHTML:'', textContent:'', value:'', style:{}, disabled:false,
                              dataset:{}, options:[], checked:false};
  return store[id];
}
// Select-Knoten mit Optionen vorbelegen
store['shortCaptions'] = {id:'shortCaptions', value:'off', options:[
  {value:'off',disabled:false},{value:'normal',disabled:false},{value:'modern',disabled:false}], style:{}};
const document = { getElementById:id=>node(id) };
const S = {};
function escHtml(s){return String(s==null?'':s);}
function escAttr(s){return String(s==null?'':s);}
function revealOutputButton(p){return '<button></button>';}
function finalOutputPaths(r){return [...new Set([...(r.output_paths||[]), r.output].filter(Boolean))];}
function openFlow(){}
let CAPS = {silence_detection:true, captions:true, hardware_encode:['h264_videotoolbox'],
            reframe:{subject_tracker:{level:'unavailable'}}};
const api = () => ({
  smart_edit_capabilities: async () => JSON.stringify(CAPS),
});
"""


def test_short_panel_initialises_and_gates_captions_by_capability():
    code = HARNESS + function("loadShortUI") + function("applyCaptionCapability") + """
(async()=>{
  // libass vorhanden -> Burn-Optionen aktiv, kein Hinweis
  CAPS.captions = true;
  await loadShortUI();
  const withAss = {caps: node('shortCaps').textContent,
                   note: node('shortCaptionNote').textContent,
                   modernDisabled: store['shortCaptions'].options[2].disabled,
                   shortCaptions: S.shortCaptions};
  // libass fehlt -> Burn-Optionen deaktiviert + Hinweis, Auswahl auf 'off'
  CAPS.captions = false;
  store['shortCaptions'].value = 'modern';
  await loadShortUI();
  const noAss = {note: node('shortCaptionNote').textContent,
                 modernDisabled: store['shortCaptions'].options[2].disabled,
                 value: store['shortCaptions'].value,
                 shortCaptions: S.shortCaptions};
  console.log(JSON.stringify({withAss, noAss}));
})().catch(e=>{console.error('JSERR:', e && e.stack); process.exit(1);});
"""
    result = run_js(code)
    assert result["withAss"]["shortCaptions"] is True
    assert result["withAss"]["modernDisabled"] is False
    assert result["withAss"]["note"] == ""
    assert "Untertitel einbrennen: verfügbar" in result["withAss"]["caps"]
    assert result["noAss"]["shortCaptions"] is False
    assert result["noAss"]["modernDisabled"] is True
    assert result["noAss"]["value"] == "off"            # burn-Auswahl auf 'off' zurückgesetzt
    assert "nicht verfügbar" in result["noAss"]["note"]


def test_short_result_and_batch_and_archive_render_without_errors():
    code = HARNESS + UI[UI.index("const FEEDBACK_META ="):UI.index("function animBurnDone")] + function("shortShowResult") + function("batchRenderList") + \
        function("batchOnDone") + function("archiveShowResult") + """
(async()=>{
  shortShowResult(['/out/Short_ab.mp4']);
  S.batchFiles = [{path:'/a.mp4', label:'a.mp4', status:'Wartet'},
                  {path:'/b.mkv', label:'b.mkv', status:'Wartet'}];
  batchRenderList();
  batchOnDone({batch_summary:{total:2, done:1, errors:1}, output:'/out/x.mp4', output_paths:['/out/x.mp4']});
  archiveShowResult({path:'/out/Archive.mkv', manifest:'/out/Archive.json',
                     metadata:{video_codec:'ffv1', archive_sha256:'abc', source_sha256:'def'}});
  console.log(JSON.stringify({
    shortResult: node('shortResult').innerHTML,
    shortHandoff: node('shortHandoff').innerHTML,
    batchList: node('batchList').innerHTML,
    batchResult: node('batchResult').innerHTML,
    archiveResult: node('archiveResult').innerHTML
  }));
})().catch(e=>{console.error('JSERR:', e && e.stack); process.exit(1);});
"""
    result = run_js(code)
    assert "Short_ab.mp4" in result["shortResult"]
    assert "Konvertieren" in result["shortHandoff"] and "KI-Regisseur" in result["shortHandoff"]
    assert "a.mp4" in result["batchList"] and "b.mkv" in result["batchList"]
    assert "1 erfolgreich, 1 fehlgeschlagen von 2" in result["batchResult"]
    assert "ffv1" in result["archiveResult"] and "Archivmaster erstellt" in result["archiveResult"]


def test_timeline_undo_redo_buttons_gate_on_history():
    code = HARNESS + """
const timelineHistory={undo:[],redo:[],id:'x'};
store['directorPlan']={id:'directorPlan',value:'{"a":1}'};
store['timelineUndoBtn']={id:'timelineUndoBtn',disabled:true};
store['timelineRedoBtn']={id:'timelineRedoBtn',disabled:true};
function directorSummarizePlan(){}
""" + re.search(r"^let timelineEditQueue=.*$", UI, re.M).group(0) + function("timelineUpdateButtons") + function("timelineApply") + function("timelineUndo") + """
(async()=>{
  const snap=()=>({undo:node('timelineUndoBtn').disabled, redo:node('timelineRedoBtn').disabled});
  timelineUpdateButtons();
  const initial=snap();                 // beide leer -> beide disabled
  timelineApply({b:2});
  const afterEdit=snap();               // undo verfügbar, redo nicht
  await timelineUndo(false);
  const afterUndo=snap();               // undo leer -> disabled, redo verfügbar
  await timelineUndo(true);
  const afterRedo=snap();               // wieder undo verfügbar
  console.log(JSON.stringify({initial,afterEdit,afterUndo,afterRedo}));
})().catch(e=>{console.error('JSERR:', e && e.stack); process.exit(1);});
"""
    r = run_js(code)
    assert r["initial"] == {"undo": True, "redo": True}
    assert r["afterEdit"] == {"undo": False, "redo": True}      # undo aktiv, redo deaktiviert
    assert r["afterUndo"] == {"undo": True, "redo": False}      # redo aktiv, undo deaktiviert
    assert r["afterRedo"] == {"undo": False, "redo": True}


def test_waveform_slice_and_svg_stay_in_sync_with_clip():
    code = function("slicePeaks") + function("waveformSvg") + """
const wf={has_audio:true,duration:10,peaks:Array.from({length:100},(_,i)=>i/100)};
const full=slicePeaks(wf,0,10);
const trimmed=slicePeaks(wf,2.5,5);              // Trim -> Teilfenster
const firstHalf=slicePeaks(wf,0,5);              // Split-Teil A
const secondHalf=slicePeaks(wf,5,10);            // Split-Teil B
const none=slicePeaks({has_audio:false,duration:0,peaks:[]},0,5);
const svg=waveformSvg(trimmed);
console.log(JSON.stringify({
  fullLen:full.length, trimmed:{len:trimmed.length,first:trimmed[0],last:trimmed[trimmed.length-1]},
  splitLens:[firstHalf.length,secondHalf.length], noneLen:none.length,
  svgHasRects:/<rect/.test(svg), svgEmptyForNone:waveformSvg(none)===''
}));
"""
    r = run_js(code)
    assert r["fullLen"] == 100
    assert r["trimmed"]["len"] == 25 and abs(r["trimmed"]["first"] - 0.25) < 1e-9   # Fenster [2.5,5]
    assert r["splitLens"] == [50, 50]              # Split teilt die Wellenform korrekt
    assert r["noneLen"] == 0 and r["svgEmptyForNone"]   # kein Audio -> leer
    assert r["svgHasRects"]                         # echte Balken gerendert


def test_feedback_states_escape_text_and_preserve_long_details():
    helper = UI[UI.index("const FEEDBACK_META ="):UI.index("function animBurnDone")]
    escape = re.search(r"^function escHtml\(s\).*?$", UI, re.M).group(0)
    result = run_js(HARNESS + escape + helper + r"""
const states = ['info','success','warning','error','loading'];
const rows = states.map(kind => {
  renderFeedback('result',kind,'<img src=x onerror=alert(1)> Grüße 日本');
  return {kind, classes:node('result').className, html:node('result').innerHTML};
});
const text = 'Sehr lange Fehlermeldung: ' + 'ä'.repeat(200) + '\nWeitere Details <script>';
renderFeedback('result','error',text);
const details = node('result').innerHTML;
renderFeedback('result','info','');
console.log(JSON.stringify({rows,details,cleared:node('result').innerHTML}));
""")
    for row in result['rows']:
        assert row['classes'] == 'feedback feedback-' + row['kind']
        assert '<img' not in row['html']
        assert '&lt;img' in row['html']
        assert 'Grüße 日本' in row['html']
    assert '<details' in result['details']
    assert 'ä' * 200 in result['details']
    assert '&lt;script&gt;' in result['details']
    assert result['cleared'] == ''
