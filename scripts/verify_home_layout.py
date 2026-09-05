#!/usr/bin/env python3
"""Measure the RetroDisc start screen and prove the five actions are visible.

The start screen must show **five** primary actions -- Disc kopieren,
Konvertieren, Brennen, Rippen, Download -- completely, at 100 %, 125 % and
150 % Windows scaling. "Completely" is not a matter of opinion, so this gate
measures it instead of describing it.

It measures in the engine the product actually ships. A real pywebview window
with the WebView2 control loads ``src/ui/app.html``, and the measurement runs
inside that control -- not in a browser that merely resembles it. pywebview
exposes the control's DevTools endpoint through
``webview.settings['REMOTE_DEBUGGING_PORT']``, which is how the viewport and
the device pixel ratio are set per scenario and how the screenshots are taken.

Two things change with the Windows scaling, and both are covered:

* the **device pixel ratio**, set through ``Emulation.setDeviceMetricsOverride``
  so that 100 %, 125 % and 150 % are really rendered, including the sub-pixel
  rounding that can make a layout overflow by a pixel at 125 % while it is
  exact at 100 %;
* the **CSS viewport**. The pywebview WinForms backend sizes the window in
  physical pixels (``self.Size = Size(int(width * scale), int(height * scale))``),
  so on a screen large enough for the scaled window the viewport stays at
  roughly 884x601 CSS pixels for every scaling. Where the scaled window no
  longer fits the screen, Windows caps it and the viewport shrinks. Those
  capped cases are separate scenarios, as is the harsher model in which the
  window does not grow with the DPI at all. A layout that passes all of them
  is safe under either behaviour.

Exit code 0 means every measurement passed. Any finding exits non-zero and is
printed with the numbers that produced it.
"""
from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import re
import socket
import struct
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "src" / "ui" / "app.html"
REPORT_DIR = ROOT / "build" / "ui-layout"

EXPECTED_ACTIONS = [
    "Disc kopieren",
    "Konvertieren",
    "Brennen",
    "Rippen",
    "Download",
]

# The Windows scalings the product has to survive.
SCALINGS = (1.0, 1.25, 1.5)


class Scenario:
    """One CSS viewport the start screen has to survive."""

    def __init__(self, name: str, width: int, height: int, why: str,
                 scalings: tuple[float, ...] = SCALINGS):
        self.name = name
        self.width = width
        self.height = height
        self.why = why
        self.scalings = scalings

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


# 900x640 window minus the WinForms caption and borders (39 x 16 logical px)
# leaves 884x601 CSS pixels whenever the scaled window still fits the screen.
SCENARIOS = [
    Scenario("Normalfenster", 884, 601,
             "900x640-Fenster; auf einem ausreichend grossen Bildschirm bei "
             "jeder Skalierung derselbe CSS-Viewport"),
    Scenario("Mindestfenster", 844, 521,
             "min_size 860x560: die kleinste Groesse, auf die der Nutzer das "
             "Fenster ziehen kann"),
    Scenario("Hoehenbegrenzt 1366x768", 884, 441,
             "150 % auf einem Notebook: die 960 phys. Fensterhoehe passt nicht "
             "mehr auf den Bildschirm und wird gekappt",
             scalings=(1.5,)),
    Scenario("Begrenzt 1280x720", 837, 409,
             "kleinster realistischer Bildschirm, Breite und Hoehe gekappt",
             scalings=(1.5,)),
    Scenario("Fenster waechst nicht mit der DPI", 589, 401,
             "haerteres Modell: das Fenster bliebe 900x640 phys., der "
             "CSS-Viewport schrumpft mit der Skalierung -- schaerfster Fall",
             scalings=(1.25, 1.5)),
]


# -- Minimal WebSocket client (RFC 6455, text frames only) ----------------
# The repository ships no WebSocket dependency and this gate must not add one,
# so the few frames the DevTools protocol needs are built here.

class WebSocket:
    def __init__(self, url: str, timeout: float = 60.0):
        parsed = urllib.parse.urlparse(url)
        port = parsed.port or 80
        self.sock = socket.create_connection((parsed.hostname, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("WebSocket-Handshake abgebrochen")
            buffer += chunk
        head, rest = buffer.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise RuntimeError(f"WebSocket-Handshake abgelehnt: {status!r}")
        self._buffer = rest

    def _read(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("WebSocket-Verbindung geschlossen")
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data

    def send(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv(self) -> str:
        chunks: list[bytes] = []
        while True:
            first, second = self._read(2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(length) if length else b""
            if opcode == 0x8:
                raise RuntimeError("WebSocket vom Steuerelement geschlossen")
            if opcode in (0x9, 0xA):  # ping / pong carry nothing we need
                continue
            chunks.append(payload)
            if fin:
                return b"".join(chunks).decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class DevTools:
    """The handful of DevTools calls this gate needs."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method,
                                 "params": params or {}}))
        while True:
            data = json.loads(self.ws.recv())
            if data.get("id") == self._id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})

    def evaluate(self, expression: str) -> object:
        result = self.call("Runtime.evaluate",
                           {"expression": expression, "returnByValue": True,
                            "awaitPromise": True})
        if "exceptionDetails" in result:
            raise RuntimeError(f"Auswertung warf: {result['exceptionDetails']}")
        return result["result"].get("value")


# -- The measurement itself, executed inside the page ---------------------

MEASURE_JS = r"""
(() => {
  const round = (value) => Math.round(value * 100) / 100;
  const doc = document.documentElement;
  const view = { w: doc.clientWidth, h: doc.clientHeight };
  const home = document.getElementById('homeview');
  const buttons = Array.from(document.querySelectorAll('#homeview .cbtn'));

  const describe = (element) => {
    const box = element.getBoundingClientRect();
    return {
      left: round(box.left), top: round(box.top),
      right: round(box.right), bottom: round(box.bottom),
      width: round(box.width), height: round(box.height),
    };
  };

  // A button counts as visible only if its own centre actually receives the
  // click. elementFromPoint catches anything painted on top of it.
  const hitOwnCentre = (element) => {
    const box = element.getBoundingClientRect();
    const x = box.left + box.width / 2, y = box.top + box.height / 2;
    if (x < 0 || y < 0 || x > view.w || y > view.h) return false;
    const hit = document.elementFromPoint(x, y);
    return !!hit && element.contains(hit);
  };

  const actions = buttons.map((button) => {
    const style = getComputedStyle(button);
    const label = button.querySelector('.cc-label');
    const icon = button.querySelector('.cc-ico');
    return {
      label: label ? label.textContent.trim() : '',
      flow: (button.getAttribute('onclick') || '').replace(/[^a-z]/g, ''),
      box: describe(button),
      icon: icon ? describe(icon) : null,
      display: style.display,
      visibility: style.visibility,
      hit: hitOwnCentre(button),
      labelClipped: label ? label.scrollWidth > label.clientWidth + 1 : true,
    };
  });

  const pills = Array.from(document.querySelectorAll('#homeview .sec-btn'))
    .map((pill) => ({ label: pill.textContent.trim(), box: describe(pill) }));

  return {
    view,
    dpr: window.devicePixelRatio,
    homeVisible: !!home && getComputedStyle(home).display !== 'none',
    bodyClass: document.body.className,
    actions,
    pills,
    scroll: {
      docWidth: doc.scrollWidth,
      homeScrollWidth: home ? home.scrollWidth : 0,
      homeScrollHeight: home ? home.scrollHeight : 0,
      homeClientWidth: home ? home.clientWidth : 0,
      homeClientHeight: home ? home.clientHeight : 0,
    },
  };
})()
"""


def judge(data: dict) -> list[str]:
    """Return the findings for one measurement. An empty list is a pass."""
    findings: list[str] = []
    view = data["view"]
    actions = data["actions"]
    epsilon = 0.5

    if not data["homeVisible"]:
        findings.append("Startseite (#homeview) ist nicht sichtbar")
    if "home-mode" not in data["bodyClass"]:
        findings.append(f"body steht nicht im home-mode: {data['bodyClass']!r}")

    labels = [action["label"] for action in actions]
    if labels != EXPECTED_ACTIONS:
        findings.append(
            f"Startseite zeigt {labels!r} statt der fuenf Aktionen {EXPECTED_ACTIONS!r}"
        )

    for action in actions:
        name = action["label"] or action["flow"] or "?"
        box = action["box"]
        if action["display"] == "none" or action["visibility"] == "hidden":
            findings.append(
                f"{name}: ausgeblendet ({action['display']}/{action['visibility']})"
            )
            continue
        if box["width"] <= 0 or box["height"] <= 0:
            findings.append(f"{name}: hat keine Flaeche ({box['width']}x{box['height']})")
        if box["left"] < -epsilon:
            findings.append(f"{name}: links abgeschnitten (left={box['left']})")
        if box["top"] < -epsilon:
            findings.append(f"{name}: oben abgeschnitten (top={box['top']})")
        if box["right"] > view["w"] + epsilon:
            findings.append(
                f"{name}: rechts abgeschnitten (right={box['right']} > Viewport {view['w']})"
            )
        if box["bottom"] > view["h"] + epsilon:
            findings.append(
                f"{name}: unten abgeschnitten (bottom={box['bottom']} > Viewport {view['h']})"
            )
        if not action["hit"]:
            findings.append(f"{name}: Mitte ist nicht anklickbar, etwas liegt darueber")
        if action["labelClipped"]:
            findings.append(f"{name}: Beschriftung ist abgeschnitten")
        icon = action["icon"]
        if not icon or icon["width"] <= 0 or icon["height"] <= 0:
            findings.append(f"{name}: Symbol wird nicht gezeichnet")

    # The five actions belong in one row. Overlap is only meaningful between
    # two buttons that share a row, so it is checked after the row check.
    tops = [action["box"]["top"] for action in actions if action["box"]["height"] > 0]
    if tops and (max(tops) - min(tops)) > 1.0:
        findings.append(f"Die Aktionen stehen nicht in einer Reihe (Oberkanten {tops})")
    else:
        ordered = sorted(actions, key=lambda action: action["box"]["left"])
        for left, right in zip(ordered, ordered[1:]):
            if right["box"]["left"] < left["box"]["right"] - epsilon:
                findings.append(
                    f"{left['label']} und {right['label']} ueberlappen "
                    f"({left['box']['right']} > {right['box']['left']})"
                )

    scroll = data["scroll"]
    if scroll["docWidth"] > view["w"] + 1:
        findings.append(
            f"Das Dokument scrollt waagerecht ({scroll['docWidth']} > {view['w']})"
        )
    if scroll["homeScrollWidth"] > scroll["homeClientWidth"] + 1:
        findings.append(
            f"Die Startseite scrollt waagerecht "
            f"({scroll['homeScrollWidth']} > {scroll['homeClientWidth']})"
        )
    if scroll["homeScrollHeight"] > scroll["homeClientHeight"] + 1:
        findings.append(
            f"Die Startseite passt nicht in die Hoehe "
            f"({scroll['homeScrollHeight']} > {scroll['homeClientHeight']})"
        )

    for pill in data["pills"]:
        box = pill["box"]
        if box["bottom"] > view["h"] + epsilon or box["right"] > view["w"] + epsilon:
            findings.append(f"Zusatzaktion {pill['label']!r} ragt aus dem Fenster")

    return findings


# -- Talking to the running WebView2 control ------------------------------

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def page_websocket_url(port: int, timeout: float = 60.0) -> str:
    """Return the DevTools WebSocket URL of the control's page target.

    Deliberately ``http.client`` and not ``urllib``: with proxy environment
    variables set, urllib routes even a 127.0.0.1 request through the proxy and
    times out instead of reaching the control.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        connection = None
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("GET", "/json/list")
            targets = json.loads(connection.getresponse().read())
            for target in targets:
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    return target["webSocketDebuggerUrl"]
            last_error = RuntimeError(f"kein page-Target: {targets!r}")
        except Exception as error:  # noqa: BLE001 - retried until the deadline
            last_error = error
        finally:
            if connection is not None:
                connection.close()
        time.sleep(0.25)
    raise RuntimeError(f"WebView2 meldete sich nicht auf Port {port}: {last_error}")


def wait_for_home(devtools: DevTools, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            ready = devtools.evaluate(
                "document.readyState === 'complete' && "
                "document.querySelectorAll('#homeview .cbtn').length > 0"
            )
        except Exception:  # noqa: BLE001 - the page may still be loading
            ready = False
        if ready:
            return
        time.sleep(0.25)
    raise RuntimeError("Die Startseite wurde nicht fertig geladen")


def settle(devtools: DevTools) -> None:
    devtools.evaluate(
        "new Promise((resolve) => requestAnimationFrame("
        "() => requestAnimationFrame(() => resolve(true))))"
    )


def measure(devtools: DevTools, screenshots: bool) -> list[dict]:
    results: list[dict] = []
    for scaling in SCALINGS:
        for scenario in SCENARIOS:
            if scaling not in scenario.scalings:
                continue
            devtools.call("Emulation.setDeviceMetricsOverride", {
                "width": scenario.width,
                "height": scenario.height,
                "deviceScaleFactor": scaling,
                "mobile": False,
            })
            settle(devtools)
            data = devtools.evaluate(MEASURE_JS)
            findings = judge(data)
            percent = int(round(scaling * 100))
            entry = {
                "scaling": f"{percent} %",
                "scenario": scenario.name,
                "why": scenario.why,
                "target": f"{scenario.width}x{scenario.height}",
                "measured_viewport": f"{data['view']['w']}x{data['view']['h']}",
                "measured_dpr": data.get("dpr"),
                "findings": findings,
                "detail": data,
            }
            if abs(data["dpr"] - scaling) > 0.001:
                entry["findings"].append(
                    f"Skalierung nicht wirksam: gemessene DPR {data['dpr']} "
                    f"statt {scaling}"
                )
            if screenshots:
                REPORT_DIR.mkdir(parents=True, exist_ok=True)
                shot = devtools.call("Page.captureScreenshot",
                                     {"format": "png", "captureBeyondViewport": False})
                target_file = REPORT_DIR / f"home-{percent}-{scenario.slug}.png"
                target_file.write_bytes(base64.b64decode(shot["data"]))
                entry["screenshot"] = str(target_file)
            results.append(entry)
    devtools.call("Emulation.clearDeviceMetricsOverride")
    return results


def report(results: list[dict]) -> int:
    for entry in results:
        status = "PASS" if not entry["findings"] else "FAIL"
        print(f"[{status}] {entry['scaling']} - {entry['scenario']}: Viewport "
              f"{entry['measured_viewport']} CSS, DPR {entry['measured_dpr']}")
        print(f"        {entry['why']}")
        if not entry["findings"]:
            boxes = [
                f"{action['label']} {action['box']['width']:.0f}x"
                f"{action['box']['height']:.0f}@{action['box']['left']:.0f}"
                for action in entry["detail"]["actions"]
            ]
            print("        " + ", ".join(boxes))
        for finding in entry["findings"]:
            print(f"        - {finding}")
        if entry.get("screenshot"):
            print(f"        Screenshot: {entry['screenshot']}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary = REPORT_DIR / "home-layout.json"
    summary.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                       encoding="utf-8")
    failed = sum(1 for entry in results if entry["findings"])
    print()
    print(f"Bericht: {summary}")
    if failed:
        print(f"ERGEBNIS: FAIL - {failed} von {len(results)} Messungen mit Befunden")
        return 1
    print(f"ERGEBNIS: PASS - {len(results)} Messungen ohne Befund")
    return 0


def run(screenshots: bool) -> int:
    if not APP_HTML.exists():
        raise SystemExit(f"{APP_HTML} fehlt")

    import webview

    port = free_port()
    webview.settings["REMOTE_DEBUGGING_PORT"] = port
    webview.settings["ALLOW_FILE_URLS"] = True

    window = webview.create_window(
        "RetroDisc Startseiten-Messung",
        url="file:///" + str(APP_HTML).replace("\\", "/"),
        width=900,
        height=640,
        text_select=False,
    )
    outcome: dict = {"code": 1, "error": None, "results": []}

    def controller() -> None:
        ws = None
        try:
            ws = WebSocket(page_websocket_url(port))
            devtools = DevTools(ws)
            devtools.call("Page.enable")
            devtools.call("Runtime.enable")
            wait_for_home(devtools)
            outcome["results"] = measure(devtools, screenshots)
        except Exception as error:  # noqa: BLE001 - reported, never swallowed
            outcome["error"] = error
        finally:
            if ws is not None:
                ws.close()
            window.destroy()

    webview.start(controller, private_mode=True)

    if outcome["error"] is not None:
        raise SystemExit(f"Messung fehlgeschlagen: {outcome['error']}")
    return report(outcome["results"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--screenshots", action="store_true",
        help="je Messung ein PNG nach build/ui-layout schreiben",
    )
    arguments = parser.parse_args()
    return run(arguments.screenshots)


if __name__ == "__main__":
    sys.exit(main())
