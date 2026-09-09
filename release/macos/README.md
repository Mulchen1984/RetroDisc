# macOS release staging

Artifacts in this directory are ignored. Reports are tracked in `../reports`.
Build the common launcher on macOS (same architecture as the target):

```sh
python3.11 -m venv .venv-build
.venv-build/bin/python -m pip install -r requirements.txt pyinstaller pywebview faster-whisper requests yt-dlp
# ffmpeg and ffprobe must already be installed and discoverable on the build PATH.
.venv-build/bin/python -m PyInstaller retrodisc_macos.spec --distpath release/macos --workpath build/macos --noconfirm
.venv-build/bin/python scripts/audit_macos_bundle.py release/macos/RetroDisc.app
```

For the audited dependency versions see `../reports/macos-build-environment.txt`.
This records the complete tested environment, including test tools; it is not a
minimal cross-platform lockfile. FFmpeg is resolved from the build PATH and its
linked libraries bundled. Record its version/hash for each build. Model data is
external. No developer home path is required. A clean-machine rebuild and
bit-for-bit reproducibility have not been claimed.

## Distribution signing — NOT CONFIGURED

No valid signing identities were visible during this audit. No certificate was
created, downloaded or exported. No notarization was submitted.

Once an authorized Apple Developer ID Application identity and a notarytool
Keychain profile have been configured outside the repository:

1. Start from a reviewed, frozen build. Inventory Mach-O files with the audit
   script. Sign nested libraries/helpers first, then the main executable, then
   the app envelope with the same identity. Do not use `--deep` as a substitute
   for correct inside-out signing. Review any required hardened-runtime
   entitlements on the actual ASR/WebView build; do not blanket-disable checks.
2. Per nested file, then app: `codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" <path>`.
3. `codesign --verify --deep --strict --verbose=2 release/macos/RetroDisc.app`
4. `ditto -c -k --keepParent release/macos/RetroDisc.app release/macos/RetroDisc.zip`
5. `xcrun notarytool submit release/macos/RetroDisc.zip --keychain-profile "$NOTARY_PROFILE" --wait`
6. Only after **Accepted**: `xcrun stapler staple release/macos/RetroDisc.app`.
7. `xcrun stapler validate release/macos/RetroDisc.app`
8. `spctl --assess --type execute --verbose=4 release/macos/RetroDisc.app`
9. Repeat package/WebView/Whisper tests against the signed artifact, then archive
   it again and record final hashes. Test on a clean Mac with Gatekeeper enabled.

These are preparation instructions, not evidence of signing/notarization.
Never store credentials, passwords, certificates or private keys in this repo.
No quarantine removal or Gatekeeper bypass is part of this workflow.
