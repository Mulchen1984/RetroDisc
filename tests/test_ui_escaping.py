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
