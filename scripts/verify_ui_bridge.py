#!/usr/bin/env python3
"""Verify the productive UI -> RetroDiscApi -> RetroDiscBridge call chain.

Earlier audits ran this comparison from a throwaway ``.audit_tmp/compare.py``
that no longer exists, so the gate was not reproducible. This script is the
committed replacement.

It checks and exits non-zero if any of these fails:

1. every method the UI calls on the pywebview bridge exists on
   ``retrodisc_launcher.RetroDiscApi`` -- the object actually handed to
   PyWebView, not ``src/ui/desktop.py``, which the packaged EXE does not use,
2. every ``RetroDiscApi`` method forwards to an existing ``RetroDiscBridge``
   method,
3. the argument count the UI passes fits the proxy signature, and the proxy
   call fits the bridge signature.

It also writes the extracted inline JavaScript to ``build/ui-audit/inline.js``
so ``node --check`` runs against exactly what the UI ships.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "src" / "ui" / "app.html"
LAUNCHER = ROOT / "retrodisc_launcher.py"

SCRIPT_BLOCK = re.compile(
    r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE
)
API_VAR = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*api\(\)")
QUOTES = ("\"", "'", "`")


def extract_inline_js(html: str) -> str:
    """Return the concatenated body of every inline <script> block."""
    parts = []
    for match in SCRIPT_BLOCK.finditer(html):
        if "src=" in match.group("attrs").lower():
            continue
        parts.append(match.group("body"))
    return "\n;\n".join(parts)


def split_call_args(text: str, open_index: int) -> list[str] | None:
    """Split the argument list of a call whose ``(`` sits at ``open_index``.

    Returns the top-level argument sources, or ``None`` when the call is not
    balanced inside ``text``. Unparsable calls are reported, never ignored.
    """
    depth = 0
    args: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = open_index
    length = len(text)
    while i < length:
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                current.append(text[i : i + 2])
                i += 2
                continue
            if ch == quote:
                quote = None
            current.append(ch)
            i += 1
            continue
        if ch in QUOTES:
            quote = ch
            current.append(ch)
            i += 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = length if end == -1 else end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = length if end == -1 else end + 2
            continue
        if ch in "([{":
            depth += 1
            if depth == 1:
                i += 1
                continue
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append("".join(current).strip())
                if len(args) == 1 and args[0] == "":
                    return []
                return args
        elif ch == "," and depth == 1:
            args.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    return None


def find_ui_calls(js: str) -> tuple[list[dict], list[str]]:
    """Collect every bridge method call the UI performs."""
    receivers = set(API_VAR.findall(js))
    receivers.add("window.pywebview.api")
    calls: list[dict] = []
    unparsed: list[str] = []
    for receiver in sorted(receivers):
        pattern = re.compile(re.escape(receiver) + r"\s*\.\s*([A-Za-z_$][\w$]*)\s*\(")
        for match in pattern.finditer(js):
            method = match.group(1)
            line = js.count("\n", 0, match.start()) + 1
            args = split_call_args(js, match.end() - 1)
            if args is None:
                unparsed.append(f"{receiver}.{method} (inline.js:{line})")
                continue
            calls.append({"method": method, "argc": len(args), "line": line})
    return calls, unparsed


def method_arity(node: ast.FunctionDef) -> tuple[int, int | None]:
    """Return (minimum, maximum) callable argument count, excluding ``self``."""
    args = node.args
    positional = args.posonlyargs + args.args
    if positional and positional[0].arg in {"self", "cls"}:
        positional = positional[1:]
    maximum: int | None = len(positional)
    if args.vararg is not None:
        maximum = None
    required = max(len(positional) - len(args.defaults), 0)
    return required, maximum


def class_methods(tree: ast.Module, class_name: str) -> dict[str, tuple[int, int | None]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name: method_arity(item)
                for item in node.body
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
            }
    raise SystemExit(f"class {class_name} not found in {LAUNCHER}")


def proxy_targets(tree: ast.Module) -> dict[str, str]:
    """Map each RetroDiscApi method to the bridge method it forwards to."""
    targets: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "RetroDiscApi"):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name.startswith("_"):
                continue
            for call in ast.walk(item):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Attribute)
                    and call.func.value.attr == "_bridge"
                ):
                    targets[item.name] = call.func.attr
                    break
    return targets


def fits(argc: int, arity: tuple[int, int | None]) -> bool:
    minimum, maximum = arity
    if argc < minimum:
        return False
    return maximum is None or argc <= maximum


def report(title: str, rows: Iterable[str]) -> int:
    rows = list(rows)
    if rows:
        print(f"\nFAIL {title} ({len(rows)}):")
        for row in rows:
            print(f"  - {row}")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="RetroDisc UI/bridge contract gate")
    parser.add_argument(
        "--emit-js",
        type=Path,
        default=ROOT / "build" / "ui-audit" / "inline.js",
        help="where to write the extracted inline JavaScript for node --check",
    )
    parser.add_argument("--json", action="store_true", help="print a machine-readable summary")
    args = parser.parse_args()

    js = extract_inline_js(APP_HTML.read_text(encoding="utf-8"))
    args.emit_js.parent.mkdir(parents=True, exist_ok=True)
    args.emit_js.write_text(js, encoding="utf-8")

    calls, unparsed = find_ui_calls(js)
    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    api = class_methods(tree, "RetroDiscApi")
    bridge = class_methods(tree, "RetroDiscBridge")
    targets = proxy_targets(tree)

    missing_proxy = sorted(
        {
            f"UI calls {c['method']}() -- no RetroDiscApi method"
            for c in calls
            if c["method"] not in api
        }
    )
    ui_arity = sorted(
        {
            f"UI calls {c['method']}() with {c['argc']} arg(s) at inline.js:{c['line']}; "
            f"proxy accepts {api[c['method']]}"
            for c in calls
            if c["method"] in api and not fits(c["argc"], api[c["method"]])
        }
    )
    no_target = sorted(
        f"RetroDiscApi.{name}() forwards to no bridge method"
        for name in api
        if name not in targets
    )
    missing_bridge = sorted(
        f"RetroDiscApi.{name}() -> RetroDiscBridge.{target}() which does not exist"
        for name, target in targets.items()
        if target not in bridge
    )
    proxy_arity = sorted(
        f"RetroDiscApi.{name}{api[name]} -> RetroDiscBridge.{target}{bridge[target]}: "
        "proxy accepts calls the bridge would reject"
        for name, target in targets.items()
        if target in bridge
        and api[name][1] is not None
        and not (fits(api[name][0], bridge[target]) and fits(api[name][1], bridge[target]))
    )

    summary = {
        "ui_call_sites": len(calls),
        "ui_methods": len({c["method"] for c in calls}),
        "proxy_methods": len(api),
        "bridge_methods": len(bridge),
        "missing_proxy": len(missing_proxy),
        "ui_arity_mismatch": len(ui_arity),
        "proxy_without_target": len(no_target),
        "missing_bridge_target": len(missing_bridge),
        "proxy_arity_mismatch": len(proxy_arity),
        "unparsed_calls": len(unparsed),
        "inline_js": str(args.emit_js),
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"UI call sites            : {summary['ui_call_sites']}")
        print(f"distinct UI methods      : {summary['ui_methods']}")
        print(f"RetroDiscApi methods     : {summary['proxy_methods']}")
        print(f"RetroDiscBridge methods  : {summary['bridge_methods']}")
        print(f"extracted inline JS      : {args.emit_js}")

    failures = 0
    failures += report("UI call without proxy method", missing_proxy)
    failures += report("UI call arity mismatch", ui_arity)
    failures += report("proxy without bridge target", no_target)
    failures += report("proxy target missing on bridge", missing_bridge)
    failures += report("proxy/bridge arity mismatch", proxy_arity)
    failures += report("unparsable UI call", unparsed)

    if failures:
        print(f"\nRESULT: FAIL ({failures} finding(s))")
        return 1
    print("\nRESULT: PASS (0 findings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
