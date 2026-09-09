# Final Release Readiness — 2026-09-09

| Gate | Status |
|---|---|
| MACOS LOCAL BUILD | PASS |
| MACOS APP START / WEBVIEW / BRIDGE | PASS |
| MACOS WHISPER (external tiny, offline) | PASS |
| MACOS HANDOFFS | PASS: real Convert → Recent → Convert/Burn/Director |
| MACOS RELOCATION | PASS (previous audited build; no relocation logic changed) |
| MACOS AD-HOC SIGNATURE | PASS |
| MACOS GATEKEEPER | REJECTED EXPECTED (previous assessed ad-hoc build) |
| MACOS DEVELOPER ID | NOT CONFIGURED: zero valid visible signing identities |
| MACOS NOTARIZATION | NOT CONFIGURED, no submission |
| WINDOWS STATIC PACKAGE | PASS: declarations/import closure inspected and tested |
| WINDOWS REAL BUILD | NOT TESTED: no Windows build host |
| WINDOWS CAPTION BURN | NOT TESTED: Windows vendor executables absent locally |
| MACOS CAPTION BURN | CAPABILITY_UNAVAILABLE: no subtitles/libass filter |
| WINDOWS TTS | UNAVAILABLE: no Windows provider implemented |
| TEST SUITE | PASS: 487 passed / 19 skipped / 0 failed |
| LOCAL DEVELOPMENT | YES |
| PUBLIC DISTRIBUTION | NO |

## Final artifact

`release/macos/RetroDisc.app`, ignored by Git. Main executable SHA-256:
`f4b6c5fc5162aaf95bb496537b13a7f9e017998c08f912c8ad03e3d7f69cc186`. Size: 253.74 MiB, 266068718 bytes
of regular files, excluding symlink duplicates. Largest components and named
runtime totals: `bundle-size.json`. Whisper uses ctranslate2 plus ONNX VAD; the
two largest ONNX runtime files are about 39/32 MiB. FFmpeg is dynamically linked;
the executable size alone does not include its bundled codec libraries.

Full hashes/dependency audit: `build/macos-release/final-bundle-audit.json`.
121 Mach-O files: no external Homebrew/developer libraries; deep strict codesign
verification PASS. App was rebuilt with the unchanged macOS build architecture
for the small audit fixes, then package ASR and real WebView/handoffs rechecked.

Logs/evidence: `final-package.json`, `final-package.srt`, `final-webview.json`,
`final-webview.log`, `final-build.log`, `final-audit-tests.log` in
`build/macos-release`. These contain local artifact paths and remain ignored.

## Windows package / vendor audit

Existing `retrodisc_final.spec` retained: WinForms/EdgeChromium, yt-dlp, FFmpeg,
FFprobe, subtitle/ASR and all new shared `src` services/models/package-check via
`collect_submodules("src")`. Mandatory faster-whisper, ctranslate2, tokenizers,
Hugging Face, AV and NumPy now fail the build if absent or uncollectable instead
of merely warning and emitting an incomplete package.

Pinned vendor definition in `prepare_vendor.py`:
`ffmpeg-N-126342-gf88b741dbf-win64-gpl.zip`, release
`autobuild-2026-08-31-13-27`, SHA-256
`b4da332540eaebc6939181b59e267f163dd57407ef6596f7f3452845921d1d91`.
No local Windows vendor EXEs: H.264, HEVC, subtitles/libass, NVENC, QSV, libvidstab
and FFprobe execution are all **NOT TESTED**, not inferred from the archive name.
Use `../windows/README.md` on Windows to capture exact capabilities and execute
the new platform-neutral caption-burn harness. GPU encoder listing alone does
not establish usable hardware.

Windows TTS remains unavailable; its capability no longer labels the absent
provider as “macOS say”. No Apple executable lookup happens on Windows.

## Paths / source audit

- Launcher data/log/tool paths use LOCALAPPDATA with user-home fallback.
- Windows settings now also honour redirected LOCALAPPDATA, preserving the
  existing USERPROFILE/AppData/Local fallback when unset. APPDATA (roaming) is
  deliberately not used for these local tool/data files.
- Python Path.home supplies USERPROFILE on Windows. tempfile follows the OS
  temp environment; configured media work paths retain existing settings logic.
- No hardcoded `/Users/`, `/opt/homebrew`, `/usr/bin/say`, Windows developer-home
  paths or `shell=True` found in the scoped runtime/launcher/spec source audit.
- Credential-literal heuristic: no findings (`source-security.json`). This is
  not a comprehensive security proof. No .env, private keys or passwords read.
- Package/webview checks remain explicit command-line branches; ordinary startup
  does not run acceptance rendering. Package check now requires frozen runtime,
  packaged UI files and ASR runtime, and verifies shared service imports/paths.

## Reproducibility / signing

Build/signing instructions: `../macos/README.md`, `../windows/README.md`.
Recorded Python environment: `macos-build-environment.txt`. Build dependencies
and FFmpeg remain external build prerequisites; runtime is bundled. No local
checkout path is encoded in the spec. Fresh-host/bit-identical reproduction has
not been claimed. No aggressive size optimization performed.

Apple flow prepared: inside-out codesign → notarytool → staple → spctl.
Windows flow prepared: Authenticode sign/verify → signed artifact tests/hashes.
No signing certificates created/imported/exported, no notarization attempted,
no Gatekeeper bypass. Public release requires real identity/notarization and
clean-platform acceptance; Windows additionally requires the actual build and
vendor/caption tests.

Startup estimate from existing accepted logs: 2.688 seconds from first launcher
log to main-UI loading, followed by successful real Bridge/Handoff calls. This
includes the intentional splash; it is **not** a measured process-start-to-ready
benchmark or a cold-start guarantee.

## Changed files in this audit block

- `retrodisc_final.spec`: fail-fast mandatory runtime collection.
- `src/config/settings.py`, `src/services/voice.py`: Windows path/capability fixes.
- `src/utils/package_check.py`: cross-platform frozen/UI/import/runtime checks.
- `scripts/caption_burn_acceptance.py`: real burn/probe/full-decode/visible-caption
  acceptance with honest unavailable result.
- `tests/test_release_final_audit.py`: four focused regressions/static guards.
- `pytest.ini`: exclude generated release trees from collection (upstream NumPy
  tests otherwise caused missing-hypothesis collection errors; no product tests
  removed and no test dependency installed to conceal it).
- `.gitignore`, `release/` documents/reports and release audit journal.

No commits, push or new branch; existing edits preserved.

Final gates: 487 passed, 19 skipped in 13.44s; verify_ui_bridge 0 findings, node syntax, compileall and git diff --check PASS.
