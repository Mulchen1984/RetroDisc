# Windows release staging

Use the existing Windows `build.py` / `retrodisc_final.spec`, not the macOS spec.
Follow `CLAUDE.md` for the approved Windows interpreter and existing build gates.
`prepare_vendor.py` verifies pinned vendor downloads before packaging.

After building on Windows:

```powershell
.\dist\RetroDisc.exe --package-check .\release\reports\windows-package.json
.\dist\RetroDisc.exe --package-check .\release\reports\windows-asr.json --model <local-model-directory> --audio <local-speech.wav>
.\dist\RetroDisc.exe --webview-check .\release\reports\windows-webview.json
python scripts/caption_burn_acceptance.py --ffmpeg vendor/ffmpeg.exe --ffprobe vendor/ffprobe.exe --work build/caption-windows
vendor\ffmpeg.exe -hide_banner -encoders
vendor\ffmpeg.exe -hide_banner -filters
vendor\ffprobe.exe -version
```

Save raw encoder/filter output and vendor hashes with the release report.
Encoder listing proves compiled support, not available GPU hardware. Actual
NVENC/QSV renders require corresponding Windows hardware/drivers. Caption test
returns PASS only after real burn-in, stream/duration and full-decode checks;
otherwise CAPABILITY_UNAVAILABLE if libass is absent. A Windows EXE is not run
or represented as tested on macOS.

## Authenticode — NOT CONFIGURED / NOT TESTED HERE

Use an authorized code-signing certificate already provisioned in the Windows
certificate store or hardware-backed signing service. No certificate generation,
export or credential storage is part of this repository.

After selecting a trusted timestamp URL and certificate thumbprint externally:

```powershell
signtool sign /sha1 $env:SIGNING_THUMBPRINT /fd SHA256 /tr $env:TIMESTAMP_URL /td SHA256 .\dist\RetroDisc.exe
signtool verify /pa /all /v .\dist\RetroDisc.exe
```

Sign and verify the installer as well. Generate portable archives and their
hashes after signing. Verify the exact signed artifacts on a clean Windows host
with existing Smart App Control / Defender policy intact. This audit does not
claim Windows signing, installer acceptance or hardware tests.
