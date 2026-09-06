"""Execute the shipped UI functions in Node with a minimal DOM/bridge."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

UI = (Path(__file__).resolve().parents[1] / "src/ui/app.html").read_text(encoding="utf-8")


def function(name):
    match = re.search(r"(?:async )?function " + name + r"\([^)]*\)\s*\{.*?^\}", UI, re.S | re.M)
    assert match, name
    return match.group(0)


def run_js(code):
    node = shutil.which("node")
    assert node, "Node is required to test the actual UI behavior"
    result = subprocess.run([node, "-e", code], capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("responses,force,expected", [
    ([{"drives": []}], False, 1),
    ([{"drives": [], "error": "probe failed"}, {"drives": []}], False, 2),
    ([{"drives": []}, {"drives": []}], True, 2),
])
def test_empty_drive_scan_cache_and_error_retry(responses, force, expected):
    code = """
let DRIVES_LOADED=false, COPY_DRIVES=[], calls=0;
const nodes={burnerArea:{},mediaArea:{}};
const document={getElementById:id=>nodes[id]};
const api=()=>({detect_burners:async()=>JSON.stringify(responses[calls++])});
""" + "const responses=" + json.dumps(responses) + ";" + function("loadBurners")
    code += "(async()=>{await loadBurners(false);await loadBurners(" + json.dumps(force) + ");console.log(JSON.stringify({calls}));})().catch(e=>{console.error(e);process.exit(1)});"
    assert run_js(code) == {"calls": expected}


def test_queue_exposes_medium_confirmation_and_calls_bridge():
    code = """
const S={jobs:[]};
const nodes={jlist:{},curjob:{style:{}},nojob:{style:{}},cjname:{},cjbar:{style:{}},cjpct:{},cjstatus:{}};
const document={getElementById:id=>nodes[id]};
let confirmed=[], alerts=[];
const updateJobBadge=()=>{};
const alert=text=>alerts.push(text);
const api=()=>({
 get_queue:async()=>JSON.stringify([{id:'copy123',name:'Disc copy',state:'running',progress:50,awaiting_copy_medium:true}]),
 confirm_copy_medium:async id=>{confirmed.push(id);return JSON.stringify({error:'Insert blank disc'});}
});
""" + "function escHtml(s){return String(s)}; function escAttr(s){return String(s)};" + function("refreshQueue") + function("renderJobs") + function("confirmCopyMedium")
    code += """
(async()=>{
 await refreshQueue();
 const before=nodes.jlist.innerHTML;
 await confirmCopyMedium('copy123');
 console.log(JSON.stringify({before,confirmed,alerts}));
})().catch(e=>{console.error(e);process.exit(1)});
"""
    result = run_js(code)
    assert "Quelldisc entfernen" in result["before"]
    assert "confirmCopyMedium('copy123')" in result["before"]
    assert result["confirmed"] == ["copy123"]
    assert result["alerts"] == ["Insert blank disc"]


def test_failed_forced_refresh_does_not_keep_old_cache():
    code = """
let DRIVES_LOADED=false, COPY_DRIVES=[], calls=0;
const document={getElementById:()=>({})};
const api=()=>({detect_burners:async()=>{
 calls++;
 if(calls===2) throw new Error('connection failed');
 return JSON.stringify({drives:[]});
}});
""" + function("loadBurners") + """
(async()=>{
 await loadBurners(false);
 await loadBurners(true);
 await loadBurners(false);
 console.log(JSON.stringify({calls}));
})().catch(e=>{console.error(e);process.exit(1)});
"""
    assert run_js(code) == {"calls": 3}
