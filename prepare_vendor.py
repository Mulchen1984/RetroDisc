# -*- coding: utf-8 -*-
"""Prepare the complete, offline Windows runtime used by ``build.py``.

Release builds must not depend on whatever happens to be the newest upstream
asset on build day. Every downloadable component therefore has an immutable
version/revision. Where a trustworthy digest is known, bytes are verified
before they can enter ``vendor/``.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR_DIR = ROOT / "vendor"

# BtbN keeps month-end assets for two years. This immutable historical release
# replaces the floating ``latest`` URL used previously.
FFMPEG_TAG = "autobuild-2026-08-31-13-27"
FFMPEG_ARCHIVE = "ffmpeg-N-126342-gf88b741dbf-win64-gpl.zip"
FFMPEG_URL = (
    f"https://github.com/BtbN/FFmpeg-Builds/releases/download/{FFMPEG_TAG}/"
    f"{FFMPEG_ARCHIVE}"
)
FFMPEG_SHA256 = "b4da332540eaebc6939181b59e267f163dd57407ef6596f7f3452845921d1d91"
FFMPEG_SOURCE_MARKER = VENDOR_DIR / "ffmpeg-source.json"

# yt-dlp muss mit YouTube Schritt halten: 2026.07.04 lieferte fuer die
# produktiven Formatmuster reproduzierbar "HTTP Error 403: Forbidden",
# 2026.08.19 laedt dieselbe URL mit demselben Muster fehlerfrei. Der Pin ist
# Absicht (nachvollziehbare Builds), muss aber regelmaessig angehoben und der
# Download danach real geprueft werden.
YTDLP_VERSION = "2026.08.19"
YTDLP_URL = (
    f"https://github.com/yt-dlp/yt-dlp/releases/download/{YTDLP_VERSION}/"
    "yt-dlp.exe"
)
YTDLP_SHA256 = "66674953fe251b89f4d08c5f0e35e0728679bd67ab3d7d05c0562af101dd3e7a"

DVDSTYLER_VERSION = "3.2.1"
DVDSTYLER_URL = (
    "https://sourceforge.net/projects/dvdstyler/files/dvdstyler/3.2.1/"
    "DVDStyler-3.2.1-win64.exe/download"
)
DVDSTYLER_SHA256 = "99b74055e9b5cceae29b153158563e454905531c966f3cdbe98ea390a6a0e713"
DVD_REQUIRED_SHA256 = {
    "dvd+rw-mediainfo.exe": "a6d16c77239fd80e25633390dce3a343e4e5cd579fd4996914e0833748191985",
    "dvdauthor.exe": "01d9351e8ac01b35cb28ddca4a7930da29003614f5121384a6f5dd07e268459c",
    "growisofs.exe": "56e5ab9e5fdb166dec30fed339444929ef544dc93b00acb6a31efc802142fd24",
    "mkisofs.exe": "cbb635d157f0959889fb8212e46ea64554ec2e8c9d3ccf9b88523f618062551a",
}

WHISPER_REPO = "Systran/faster-whisper-base"
WHISPER_REVISION = "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"
WHISPER_REQUIRED_SHA256 = {
    "config.json": "56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a",
    "model.bin": "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9",
    "tokenizer.json": "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab",
    "vocabulary.txt": "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913",
}


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest for *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matches_hash(path: Path, expected: str) -> bool:
    return path.is_file() and sha256_file(path) == expected.lower()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _relative_files(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def _required_files_match(root: Path, expected: dict[str, str]) -> bool:
    return root.is_dir() and all(
        _matches_hash(root / relative, digest)
        for relative, digest in expected.items()
    )


def _tree_matches(
    root: Path,
    expected: dict[str, str],
    *,
    allowed_extra: set[str] | frozenset[str] = frozenset(),
) -> bool:
    """Match both hashes and the complete file set.

    Directories from ``retrodisc_final.spec`` are bundled recursively, so an
    unverified extra DLL or executable must make the readiness check fail.
    """
    if not _required_files_match(root, expected):
        return False
    return _relative_files(root) == set(expected) | set(allowed_extra)


def _file_manifest(root: Path, *, exclude: set[str] | frozenset[str] = frozenset()) -> dict[str, str]:
    return {
        relative: sha256_file(root / relative)
        for relative in sorted(_relative_files(root) - set(exclude))
    }


def _manifest_tree_matches(
    root: Path,
    marker_name: str,
    expected_metadata: dict[str, str],
) -> bool:
    marker_path = root / marker_name
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    files = marker.pop("files", None)
    if marker != expected_metadata or not isinstance(files, dict) or not files:
        return False
    if not all(
        isinstance(relative, str)
        and _is_sha256(digest)
        for relative, digest in files.items()
    ):
        return False
    return _tree_matches(root, files, allowed_extra={marker_name})


def download_with_progress(
    url: str,
    dest: Path,
    label: str,
    expected_sha256: str | None = None,
) -> None:
    """Download atomically and reject bytes that do not match a known digest."""
    print(f"  Lade {label}...")
    print(f"  URL: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".download")
    partial.unlink(missing_ok=True)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "RetroDisc-Builder/1.0"}
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            chunk_size = 1024 * 256  # 256 KB chunks

            with partial.open("wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)

                    if total > 0:
                        pct = done / total * 100
                        bar_len = 40
                        filled = int(bar_len * done / total)
                        bar = "#" * filled + "." * (bar_len - filled)
                        mb = done / 1024 / 1024
                        total_mb = total / 1024 / 1024
                        print(
                            f"\r  [{bar}] {pct:.0f}% ({mb:.1f}/{total_mb:.1f} MB)",
                            end="", flush=True
                        )

        if expected_sha256 is not None:
            actual = sha256_file(partial)
            if actual != expected_sha256.lower():
                raise RuntimeError(
                    f"{label}: SHA-256 stimmt nicht: {actual} "
                    f"(erwartet {expected_sha256})"
                )
        os.replace(partial, dest)
        print(f"\r  OK: {label} heruntergeladen ({done/1024/1024:.1f} MB)")

    except (OSError, RuntimeError, urllib.error.URLError) as e:
        partial.unlink(missing_ok=True)
        print(f"\n  FEHLER: Download fehlgeschlagen oder ungültig: {e}")
        raise


def extract_ffmpeg(zip_path: Path) -> None:
    """Extract and transactionally install the verified FFmpeg pair."""
    print("  Extrahiere aus ZIP...")
    names = ("ffmpeg.exe", "ffprobe.exe")
    with tempfile.TemporaryDirectory(prefix="retrodisc-ffmpeg-", dir=VENDOR_DIR) as raw:
        staging = Path(raw) / "staging"
        staging.mkdir()

        with zipfile.ZipFile(zip_path) as zf:
            members = zf.namelist()
            normalized_members = [
                (member, member.replace("\\", "/")) for member in members
            ]
            for target_name in names:
                found = next(
                    (
                        member
                        for member, normalized in normalized_members
                        if Path(normalized).name == target_name
                        and "/bin/" in f"/{normalized}"
                    ),
                    None,
                )
                if found is None:
                    found = next(
                        (
                            member
                            for member, normalized in normalized_members
                            if Path(normalized).name == target_name
                        ),
                        None,
                    )
                if found is None:
                    raise FileNotFoundError(f"{target_name} nicht im FFmpeg-ZIP")
                dest = staging / target_name
                with zf.open(found) as src, dest.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                if dest.stat().st_size < 10 * 1024 * 1024:
                    raise RuntimeError(f"{target_name} ist unplausibel klein")
                print(
                    f"  OK: {target_name} extrahiert "
                    f"({dest.stat().st_size / 1024 / 1024:.1f} MB)"
                )

        marker_name = FFMPEG_SOURCE_MARKER.name
        (staging / marker_name).write_text(
            json.dumps(
                {
                    "tag": FFMPEG_TAG,
                    "archive": FFMPEG_ARCHIVE,
                    "url": FFMPEG_URL,
                    "sha256": FFMPEG_SHA256,
                    "files": _file_manifest(staging),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _replace_files(staging, VENDOR_DIR, (*names, marker_name))


def _replace_files(staging: Path, target_root: Path, names: tuple[str, ...]) -> None:
    """Install a file set transactionally and restore the prior set on error."""
    backup = staging.parent / "previous"
    backup.mkdir()
    installed: list[Path] = []
    moved_to_backup: list[tuple[Path, Path]] = []
    try:
        for name in names:
            target = target_root / name
            if target.exists():
                saved = backup / name
                target.replace(saved)
                moved_to_backup.append((saved, target))
        for name in names:
            source = staging / name
            target = target_root / name
            source.replace(target)
            installed.append(target)
    except BaseException:
        for target in reversed(installed):
            target.unlink(missing_ok=True)
        for saved, target in reversed(moved_to_backup):
            if saved.exists():
                saved.replace(target)
        raise


def _replace_directory(staging: Path, target: Path) -> None:
    """Replace a vendor tree while retaining the old tree until staging is valid."""
    backup = target.with_name(target.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    if target.exists():
        target.replace(backup)
    try:
        staging.replace(target)
    except BaseException:
        if backup.exists() and not target.exists():
            backup.replace(target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def ffmpeg_is_ready() -> bool:
    try:
        marker = json.loads(FFMPEG_SOURCE_MARKER.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    files = marker.pop("files", None)
    if marker != {
        "tag": FFMPEG_TAG,
        "archive": FFMPEG_ARCHIVE,
        "url": FFMPEG_URL,
        "sha256": FFMPEG_SHA256,
    }:
        return False
    expected_names = {"ffmpeg.exe", "ffprobe.exe"}
    if not isinstance(files, dict) or set(files) != expected_names:
        return False
    return all(
        _is_sha256(files[name])
        and (VENDOR_DIR / name).is_file()
        and (VENDOR_DIR / name).stat().st_size >= 10 * 1024 * 1024
        and _matches_hash(VENDOR_DIR / name, files[name])
        for name in expected_names
    )


def ytdlp_is_ready() -> bool:
    return _matches_hash(VENDOR_DIR / "yt-dlp.exe", YTDLP_SHA256)


def dvdtools_are_ready() -> bool:
    root = VENDOR_DIR / "dvdtools"
    return _required_files_match(root, DVD_REQUIRED_SHA256) and _manifest_tree_matches(
        root,
        "RETRODISC_SOURCE.json",
        {
            "version": DVDSTYLER_VERSION,
            "url": DVDSTYLER_URL,
            "installer_sha256": DVDSTYLER_SHA256,
        },
    )


def whisper_is_ready() -> bool:
    return _tree_matches(
        VENDOR_DIR / "whisper-base",
        WHISPER_REQUIRED_SHA256,
        allowed_extra={"RETRODISC_SOURCE.json"},
    )


def prepare_ffmpeg() -> None:
    if ffmpeg_is_ready():
        return
    archive = VENDOR_DIR / FFMPEG_ARCHIVE
    try:
        download_with_progress(
            FFMPEG_URL,
            archive,
            "FFmpeg-Bundle",
            FFMPEG_SHA256,
        )
        extract_ffmpeg(archive)
    finally:
        archive.unlink(missing_ok=True)


def prepare_ytdlp() -> None:
    if not ytdlp_is_ready():
        download_with_progress(
            YTDLP_URL,
            VENDOR_DIR / "yt-dlp.exe",
            f"yt-dlp {YTDLP_VERSION}",
            YTDLP_SHA256,
        )


def prepare_dvdtools() -> None:
    """Install pinned DVDStyler silently, then vendor its complete CLI runtime."""
    if dvdtools_are_ready():
        return
    with tempfile.TemporaryDirectory(prefix="retrodisc-dvd-", dir=VENDOR_DIR) as raw:
        workspace = Path(raw)
        installer = workspace / f"DVDStyler-{DVDSTYLER_VERSION}-win64.exe"
        install_root = workspace / "installed"
        staging = workspace / "dvdtools"
        install_root.mkdir()
        staging.mkdir()
        download_with_progress(
            DVDSTYLER_URL,
            installer,
            f"DVDStyler {DVDSTYLER_VERSION}",
            DVDSTYLER_SHA256,
        )

        result = subprocess.run(
            [
                str(installer),
                "/SP-",
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={install_root}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).decode("utf-8", errors="replace")
            raise RuntimeError(
                f"DVDStyler-Entpackung fehlgeschlagen ({result.returncode}): {detail}"
            )

        source_root = next(
            (
                candidate
                for candidate in (install_root, install_root / "bin")
                if all((candidate / name).is_file() for name in DVD_REQUIRED_SHA256)
            ),
            None,
        )
        if source_root is None:
            raise RuntimeError("DVDStyler enthält die erwarteten DVD-CLI-Werkzeuge nicht")

        for item in source_root.iterdir():
            if item.name.lower().startswith("unins"):
                continue
            target = staging / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        if not _required_files_match(staging, DVD_REQUIRED_SHA256):
            raise RuntimeError("DVDStyler-Runtime stimmt nicht mit dem geprüften Pin überein")
        (staging / "RETRODISC_SOURCE.json").write_text(
            json.dumps(
                {
                    "version": DVDSTYLER_VERSION,
                    "url": DVDSTYLER_URL,
                    "installer_sha256": DVDSTYLER_SHA256,
                    "files": _file_manifest(staging),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _replace_directory(staging, VENDOR_DIR / "dvdtools")


def prepare_whisper() -> None:
    """Materialise the exact audited CTranslate2 base-model revision."""
    if whisper_is_ready():
        return
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface-hub fehlt; installiere zuerst requirements.txt"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="retrodisc-whisper-", dir=VENDOR_DIR) as raw:
        staging = Path(raw) / "whisper-base"
        snapshot_download(
            repo_id=WHISPER_REPO,
            revision=WHISPER_REVISION,
            local_dir=str(staging),
            allow_patterns=sorted(WHISPER_REQUIRED_SHA256),
        )
        shutil.rmtree(staging / ".cache", ignore_errors=True)
        if not _tree_matches(staging, WHISPER_REQUIRED_SHA256):
            raise RuntimeError("Whisper-Modell stimmt nicht mit der geprüften Revision überein")
        (staging / "RETRODISC_SOURCE.json").write_text(
            json.dumps(
                {"repository": WHISPER_REPO, "revision": WHISPER_REVISION},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _replace_directory(staging, VENDOR_DIR / "whisper-base")


def check_vendor() -> bool:
    """Report whether every runtime that the final spec bundles is present."""
    checks = {
        "FFmpeg/FFprobe": ffmpeg_is_ready(),
        "yt-dlp": ytdlp_is_ready(),
        "DVD-Werkzeuge": dvdtools_are_ready(),
        "Faster-Whisper Base-Modell": whisper_is_ready(),
    }
    for label, ready in checks.items():
        print(f"  {'OK' if ready else 'FEHLT/UNGÜLTIG'}: {label}")
    return all(checks.values())


def main() -> int:
    print("\n  RetroDisc - vollständige Offline-Runtime vorbereiten")
    print("  " + "=" * 52)
    VENDOR_DIR.mkdir(exist_ok=True)
    prepare_ffmpeg()
    prepare_ytdlp()
    prepare_dvdtools()
    prepare_whisper()
    if not check_vendor():
        print("\n  FEHLER: Vendor-Runtime ist unvollständig oder ungeprüft.")
        return 1
    print("\n  OK: Vollständige, gepinnte Vendor-Runtime ist bereit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
