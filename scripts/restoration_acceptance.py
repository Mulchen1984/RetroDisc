#!/usr/bin/env python3
"""Real-FFmpeg acceptance for scene-adaptive restoration and the FFV1 archive master.

Selbstständiger Nachweis (keine Mocks) für die Missionen 1–5, 23, 24, 26:

  * erzeugt lokale Testmedien mit FFmpeg (PAL 576i TFF/BFF, progressives SD,
    30 s Video mit Bewegung + dunklen/hellen Abschnitten, Sprach-Audio),
  * fährt Analyse -> Szenenanalyse -> szenenadaptiven Render -> Report,
  * fährt Archivmaster (FFV1 + verlustloses Audio) + Manifest,
  * dekodiert jede Ausgabe vollständig (ffmpeg -xerror -f null) und prüft
    Dauer/Streams via ffprobe,
  * belegt, dass die Quell-SHA256 unverändert bleibt,
  * misst die Laufzeit (Mission 26).

Aufruf:  python3 scripts/restoration_acceptance.py [arbeitsverzeichnis]
Exit 0 = alle Prüfungen bestanden. Ausgabe ist als Journal-Beleg gedacht.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.ffmpeg import FFmpeg
from src.models.director import MediaAsset
from src.services.restoration import Restoration

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class ProbeLibrary:
    """Minimal library over real ffprobe: only .asset() and .db_path are used."""

    def __init__(self, db_path: Path, ffmpeg: FFmpeg):
        self.db_path = Path(db_path)
        self._ffmpeg = ffmpeg

    async def asset(self, path) -> MediaAsset:
        path = Path(path).resolve()
        info = await self._ffmpeg.probe(path)
        video = info.video_streams[0] if info.video_streams else None
        audio = info.audio_streams[0] if info.audio_streams else None
        return MediaAsset(
            id=hashlib.sha256(str(path).encode()).hexdigest()[:16],
            path=str(path),
            kind="video" if video else "audio",
            duration=info.duration_seconds,
            container=info.container,
            video_codec=video.codec if video else None,
            audio_codec=audio.codec if audio else None,
            width=video.width if video else None,
            height=video.height if video else None,
        )


def run_ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *args], check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decodes_fully(path: Path) -> bool:
    """Full decode of every packet; -xerror turns any decode error into failure."""
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
    )
    return result.returncode == 0 and not result.stderr.strip()


def probe_json(path: Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


# ── Testmedien (Mission 23) ────────────────────────────────────────────────

def make_interlaced(path: Path, parity: str, seconds: int = 4) -> None:
    """PAL 576i mit echter Halbbildstruktur + Ton; parity = 'tff' | 'bff'."""
    scan = "tff" if parity == "tff" else "bff"
    order = "tt" if parity == "tff" else "bb"
    run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=size=720x576:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", str(seconds),
        "-vf", f"interlace=scan={scan}:lowpass=1,setfield={scan}",
        "-c:v", "ffv1", "-field_order", order,
        "-c:a", "pcm_s16le", "-shortest", "-y", str(path),
    )


def make_progressive(path: Path, seconds: int = 4) -> None:
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", str(seconds),
        "-c:v", "ffv1", "-c:a", "pcm_s16le", "-shortest", "-y", str(path),
    )


def make_scene_video(path: Path, work: Path, segment: int = 10) -> None:
    """30 s SD-Video: dunkel/statisch -> hell/farbig -> heller/hohe Bewegung.

    Harte Schnitte erzeugen echte Szenengrenzen für select='gt(scene,...)',
    die Segmente unterscheiden sich messbar in Helligkeit und Bewegung.
    """
    segs = []
    sources = [
        # dunkel, wenig Bewegung
        "color=c=0x0d0d0d:s=640x480:r=25,noise=alls=6:allf=t",
        # hell, mittlere Bewegung
        "testsrc2=s=640x480:r=25",
        # hell, hohe Bewegung/Detail
        "mandelbrot=s=640x480:rate=25",
    ]
    for index, source in enumerate(sources):
        seg = work / f"seg{index}.mkv"
        run_ffmpeg("-f", "lavfi", "-i", source, "-t", str(segment),
                   "-pix_fmt", "yuv420p", "-c:v", "ffv1", "-y", str(seg))
        segs.append(seg)
    concat = work / "scene_concat.txt"
    concat.write_text("".join(f"file '{s.resolve()}'\n" for s in segs), encoding="utf-8")
    # Ton mit Pausen für spätere Silence-Tests (Mission 12) gleich mitliefern.
    run_ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat),
               "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000",
               "-map", "0:v", "-map", "1:a", "-t", str(segment * len(sources)),
               "-c:v", "ffv1", "-c:a", "pcm_s16le", "-y", str(path))


# ── Prüf-Läufe ──────────────────────────────────────────────────────────────

async def restore_case(name: str, source: Path, restoration: Restoration,
                       adaptive: bool, size: str) -> dict:
    report: dict = {"case": name, "source": source.name}
    source_before = sha256(source)
    started = time.monotonic()
    plan = await restoration.analyze(source)
    plan.options.size = size
    report["field_order"] = plan.analysis.field_order
    report["deinterlace"] = plan.options.deinterlace
    report["fps"] = plan.analysis.fps
    if adaptive:
        plan = await restoration.analyze_scenes(plan)
        report["scenes"] = len(plan.scenes)
        report["dark_scenes"] = sum(1 for s in plan.scenes if s.metrics and s.metrics.dark)
        report["scene_denoise"] = [s.denoise_strength for s in plan.scenes]
    chain = Restoration.filters(plan)
    report["filter_chain"] = chain
    report["scene_enabled_filters"] = sum(1 for f in chain if "enable=" in f)
    # Kein Preview-Gate für Direktrender im Test.
    plan = await restoration.render(plan, preview=False, encoder="auto")
    report["render_seconds"] = round(time.monotonic() - started, 2)
    output = Path(plan.outputs[-1])
    info = probe_json(output)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    report["output"] = {
        "path": output.name,
        "resolution": [video["width"], video["height"]],
        "codec": video["codec_name"],
        "duration": round(float(info["format"]["duration"]), 2),
        "size_bytes": output.stat().st_size,
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
        "decodes_fully": decodes_fully(output),
    }
    report["report_keys"] = sorted(plan.report.keys())
    report["report_result"] = plan.report.get("result", {})
    report["source_sha_unchanged"] = sha256(source) == source_before
    report["source_sha256"] = source_before
    report["output_sha256"] = plan.output_sha256.get(str(output))
    return report


async def archive_case(source: Path, restoration: Restoration) -> dict:
    report: dict = {"case": "archive_master", "source": source.name}
    before = sha256(source)
    started = time.monotonic()
    plan = await restoration.analyze(source)
    plan = await restoration.archive(plan)
    report["archive_seconds"] = round(time.monotonic() - started, 2)
    archive = plan.archives[-1]
    output = Path(archive["path"])
    manifest = Path(archive["manifest"])
    info = probe_json(output)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    report["archive_codec"] = video["codec_name"]
    report["audio_codecs"] = [s["codec_name"] for s in info["streams"] if s["codec_type"] == "audio"]
    report["decodes_fully"] = decodes_fully(output)
    report["manifest_exists"] = manifest.is_file()
    report["manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
    report["manifest_sha_matches"] = report["manifest"]["archive_sha256"] == sha256(output)
    report["source_sha_unchanged"] = sha256(source) == before
    return report


async def main() -> int:
    if not FFMPEG or not FFPROBE:
        print("SKIP: ffmpeg/ffprobe nicht gefunden")
        return 0
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="retrodisc-accept-"))
    base.mkdir(parents=True, exist_ok=True)
    media = base / "media"; media.mkdir(exist_ok=True)
    work = base / "work"; work.mkdir(exist_ok=True)
    out = base / "out"; temp = base / "temp"

    print(f"# Restoration-Acceptance  ffmpeg={Path(FFMPEG).name}  base={base}")
    ver = subprocess.run([FFMPEG, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    print(f"# {ver}")

    print("## Testmedien erzeugen (Mission 23)")
    tff = media / "pal_576i_tff.mkv"; make_interlaced(tff, "tff")
    bff = media / "pal_576i_bff.mkv"; make_interlaced(bff, "bff")
    prog = media / "sd_progressive.mkv"; make_progressive(prog)
    scene = media / "scene_30s.mkv"; make_scene_video(scene, work)
    for path in (tff, bff, prog, scene):
        print(f"  - {path.name}  {path.stat().st_size} bytes  decode_ok={decodes_fully(path)}")

    ffmpeg = FFmpeg()
    library = ProbeLibrary(base / "library.db", ffmpeg)
    restoration = Restoration(library, ffmpeg, out, temp)

    caps = await restoration.capabilities()
    print("## Capabilities")
    print(f"  - stabilization: {caps['stabilization']}")
    print(f"  - ffv1_master:   {caps['archive']}")
    print(f"  - providers:     {{name: available}} = "
          + json.dumps({k: v['available'] for k, v in caps['providers'].items()}))

    results = []
    print("## Restoration-Läufe")
    results.append(await restore_case("PAL 576i TFF -> 720p (adaptiv)", tff, restoration, adaptive=True, size="720p"))
    results.append(await restore_case("PAL 576i BFF -> 720p", bff, restoration, adaptive=False, size="720p"))
    results.append(await restore_case("Progressive SD -> original", prog, restoration, adaptive=False, size="original"))
    results.append(await restore_case("Szenen 30s -> 720p (adaptiv)", scene, restoration, adaptive=True, size="720p"))

    print("## Archivmaster (Missionen 4+5)")
    archive = await archive_case(scene, restoration)
    results.append(archive)

    print("## Batch-Restauration mit defekter Datei (Mission 7)")
    broken = media / "kaputt.mkv"; broken.write_bytes(b"not a video")
    batch = await restoration.batch([tff, broken, prog], size="720p")
    batch_report = {"case": "batch", "count": len(batch),
                    "statuses": [b["status"] for b in batch],
                    "done": sum(1 for b in batch if b["status"] == "done"),
                    "errors": sum(1 for b in batch if b["status"] == "error"),
                    "outputs_decode": [decodes_fully(Path(b["output"])) for b in batch if b["output"]],
                    "error_did_not_stop_queue": batch[0]["status"] == "done" and batch[2]["status"] == "done"}
    results.append(batch_report)

    print("\n===== ERGEBNIS (JSON) =====")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))

    # Akzeptanzkriterien
    ok = True
    for item in results:
        if item["case"] == "batch":
            checks = [item["done"] == 2, item["errors"] == 1,
                      item["error_did_not_stop_queue"], all(item["outputs_decode"])]
        elif item["case"] == "archive_master":
            checks = [item["archive_codec"] == "ffv1", item["decodes_fully"],
                      item["manifest_exists"], item["manifest_sha_matches"], item["source_sha_unchanged"]]
        else:
            o = item["output"]
            checks = [o["decodes_fully"], o["codec"] in ("h264", "hevc"),
                      o["has_audio"], item["source_sha_unchanged"],
                      "result" in item["report_keys"], "integrity" in item["report_keys"],
                      "analysis" in item["report_keys"], "processing" in item["report_keys"]]
        status = "PASS" if all(checks) else "FAIL"
        if not all(checks):
            ok = False
        print(f"[{status}] {item['case']}")

    print("\nGESAMT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
