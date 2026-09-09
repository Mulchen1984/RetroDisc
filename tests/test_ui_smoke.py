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
    code = HARNESS + function("shortShowResult") + function("batchRenderList") + \
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
""" + function("timelineUpdateButtons") + function("timelineApply") + function("timelineUndo") + """
(async()=>{
  const snap=()=>({undo:node('timelineUndoBtn').disabled, redo:node('timelineRedoBtn').disabled});
  timelineUpdateButtons();
  const initial=snap();                 // beide leer -> beide disabled
  timelineApply({b:2});
  const afterEdit=snap();               // undo verfügbar, redo nicht
  timelineUndo(false);
  const afterUndo=snap();               // undo leer -> disabled, redo verfügbar
  timelineUndo(true);
  const afterRedo=snap();               // wieder undo verfügbar
  console.log(JSON.stringify({initial,afterEdit,afterUndo,afterRedo}));
})().catch(e=>{console.error('JSERR:', e && e.stack); process.exit(1);});
"""
    r = run_js(code)
    assert r["initial"] == {"undo": True, "redo": True}
    assert r["afterEdit"] == {"undo": False, "redo": True}      # undo aktiv, redo deaktiviert
    assert r["afterUndo"] == {"undo": True, "redo": False}      # redo aktiv, undo deaktiviert
    assert r["afterRedo"] == {"undo": False, "redo": True}
