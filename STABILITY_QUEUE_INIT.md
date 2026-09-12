# Stabilitätsblock: Queue-Initialisierungs-Timeout (2026-09-11)

Separater Auftrag, getrennt vom abgeschlossenen UI-Modernisierungsblock
(siehe `UI_MODERNIZATION_PLAN.md`). Betrifft ausschließlich
`retrodisc_launcher.py`. Keine UI-, Encoder-, FFmpeg- oder Datenmodell-Änderung.

## Ausgangsbefund

Voller `pytest -q` vor diesem Block: **776 passed / 19 skipped / 10 failed /
19 errors** (Baseline unverändert seit Block 1). Alle 10 FAILED + alle 19
ERROR lagen ausschließlich in `tests/test_disc_copy_flow.py` und
`tests/test_disc_flows.py`, jeweils mit identischem Traceback:

```
tests/test_disc_flows.py:170: in create
    bridge = RetroDiscBridge()
retrodisc_launcher.py:315: in __init__
    self.conversion_queue = self._async(self._init_conversion_queue()).result(timeout=5)
...
TimeoutError
```

## Root Cause (reproduziert vor jeder Änderung)

`RetroDiscBridge.__init__` startet einen Hintergrund-Thread, der
`self._loop.run_forever()` ausführt, und wartet danach synchron via
`self._async(coro).result(timeout=5)` auf `_init_conversion_queue()`
(Konstruktion der neuen `ConversionQueue`, inkl. SQLite-Connect).

Die Fixture `disc_bridge` in `tests/test_disc_flows.py` (verwendet auch von
`tests/test_disc_copy_flow.py` über `copy_runtime`) patcht bewusst
`threading.Thread` durch eine No-Op-Attrappe:

```python
monkeypatch.setattr(
    launcher, "threading",
    SimpleNamespace(Thread=lambda **kwargs: SimpleNamespace(start=lambda: None)),
)
```

Docstring der Fixture: *"Run the production constructor with isolated
settings and no worker/DB."* — zum Zeitpunkt, als diese Fixture geschrieben
wurde, brauchte `__init__` den Hintergrund-Thread noch nicht. Die spätere
(fremde, unabhängig entstandene) Erweiterung um `conversion_queue` hat diese
Annahme stillschweigend gebrochen: `__init__` wartet jetzt **immer** auf
etwas, das nur der echte Hintergrund-Thread erledigen kann.

Mit der Attrappe startet **kein** echter Thread → `self._loop.run_forever()`
läuft nie → die auf `self._loop` dispatchte Coroutine `_init_conversion_queue()`
wird nie ausgeführt → `.result(timeout=5)` läuft *garantiert und
deterministisch* nach 5 s in `TimeoutError`. Kein Flackern, keine Ressourcen-
Erschöpfung durch viele Testläufe — ein einzelner, reproduzierbarer Bug.

**Isolierter Beweis** (ohne pytest, direkter Nachbau der Fixture):

```
Constructing RetroDiscBridge() with faked threading.Thread ...
FAILED after 5.01s: TimeoutError
Real thread count alive: 1
RuntimeWarning: coroutine 'RetroDiscBridge._init_conversion_queue' was never awaited
```

Die Warnung belegt zweifelsfrei: die Coroutine wurde nie ausgeführt, nicht
nur langsam.

**Warum nicht einfach den Timeout erhöhen:** Ohne laufenden Thread wird die
Coroutine *nie* ausgeführt — jeder endliche Timeout schlägt irgendwann fehl,
ein unendlicher Timeout würde `__init__` für immer blockieren. Das Timeout
ist nicht das Problem, sondern nur der Ort, an dem das eigentliche Problem
(fehlende Thread-Ausführung) sichtbar wird.

## Warum die Konstruktion ursprünglich überhaupt über `self._loop` lief

`ConversionQueue.__init__` selbst ist vollständig synchron (kein `await`);
sie hätte direkt aufgerufen werden können. Der Grund für den Umweg über
`self._async(...)`: die dort erzeugte SQLite-Connection (`JobQueue(db_path)`)
darf laut SQLite nur aus dem Thread heraus benutzt werden, in dem sie erzeugt
wurde. Alle späteren Operationen (`submit`, `rows`, `cancel`, `retry`,
`shutdown`) laufen ebenfalls über `self._async(...)` auf `self._loop` — die
Connection muss also von Anfang an auf **demselben** Thread entstehen, sonst
entsteht der in diesem Repo bereits an anderer Stelle beobachtete Fehler
`SQLite objects created in a thread can only be used in that same thread`.
Ein simples "direkt in `__init__` aufrufen" hätte den Timeout beseitigt, aber
diesen Cross-Thread-Bug in der echten Anwendung eingeführt — deshalb nicht
gewählt.

## Minimaler Fix

`self.conversion_queue` wird in `__init__` nur noch mit `None` initialisiert
(keine Wartezeit, keine Thread-Abhängigkeit). Die eigentliche Konstruktion
erfolgt **lazy**, weiterhin über `self._async(...)` (also weiterhin garantiert
auf `self._loop`, Thread-Affinität der SQLite-Connection bleibt gewahrt),
beim ersten echten Bedarf:

```python
async def _ensure_conversion_queue(self):
    if self.conversion_queue is None:
        from src.services.pipeline.conversion_queue import ConversionQueue
        self.conversion_queue = ConversionQueue(...)
    return self.conversion_queue

async def _submit_conversion_job(self, job):
    queue = await self._ensure_conversion_queue()
    return await queue.submit(job)
```

`_submit_job` ruft jetzt `_submit_conversion_job` statt direkt
`self.conversion_queue.submit`; `retry_job` bekommt eine Absicherung für den
Fall, dass noch nie ein Job eingereiht wurde (`conversion_queue is None`).
`list_jobs`, `cancel_job`, `shutdown` waren bereits mit
`getattr(self, 'conversion_queue', None)` abgesichert und brauchten keine
Änderung — sie verhalten sich korrekt, solange die Queue noch nicht existiert.

In echter Nutzung ändert sich für den Anwender nichts: der Hintergrund-Thread
läuft dort tatsächlich, und die Queue entsteht beim ersten Konvertierungs-Job
statt beim Programmstart — spart sogar unnötiges Anlegen von `pipeline.db`,
wenn nie eine persistente Konvertierung läuft.

## Ergebnis

| | vorher | nachher |
|---|---|---|
| `pytest -q` gesamt | 776 passed / 19 skipped / 10 failed / 19 errors, 157 s | **804 passed / 19 skipped / 1 failed / 0 errors, 16 s** |
| `test_disc_copy_flow.py` + `test_disc_flows.py` | 10 failed / 19 errors | 0 failed / 0 errors |

Die Laufzeit sank von 157 s auf 16 s — zusätzlicher, unabhängiger Beleg dafür,
dass die tatsächliche Blockierung beseitigt wurde und nicht nur ein Symptom
verschoben wurde.

## Verbleibender 1 Fehler — technisch erklärt, nicht behoben

`tests/test_job_submission.py::test_every_queueing_bridge_method_returns_a_usable_job`

Fixture `queued_bridge` nutzt **echtes** Threading (keine Attrappe) — dieser
Test war vom oben beschriebenen Bug nie betroffen. Bewiesen durch identischen
Fehlertext vor und nach diesem Fix:

```
AssertionError: convert_file did not park a job under <job_id>
assert None is not None
```

Ursache: `convert_file`-Jobs mit `preset_name` werden (bereits vor diesem
Block, fremde WIP) über `conversion_queue` statt über `self.pipeline`
eingereiht. Der Test prüft aber pauschal `queued_bridge.pipeline.get_job(job_id)`
für alle Queueing-Methoden — für `convert_file` ist das seit Einführung der
persistenten Queue nicht mehr die richtige Quelle. Das ist eine
Design-/Business-Entscheidung (soll `convert_file` weiterhin in
`self.pipeline` sichtbar sein, oder muss der Test auf `conversion_queue`
umgestellt werden?), keine Nebenwirkung dieses Stabilitätsblocks. Absichtlich
nicht angefasst: sowohl die Testerwartung als auch das Routing sind fremde
Pipeline-WIP-Entscheidungen außerhalb des beauftragten Rahmens.

## Nicht verändert

UI (`src/ui/app.html`), Encoder-/FFmpeg-Logik, Datenmodelle,
`src/services/pipeline/conversion_queue.py`, `src/services/pipeline/queue.py`,
`src/services/pipeline/scheduler.py`. Kein Commit, kein Push.
