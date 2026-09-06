# RetroDisc Code Signing

RetroDisc release artifacts must be Authenticode-signed before distribution.

## The order is the whole point

Signing a finished ZIP or a finished installer signs the outer shell and leaves
the executable inside it unsigned. Windows reads the signature of the file it
actually runs, so a release must be produced in this order — and `build.py`
does exactly this, which is why there is no separate "sign the release"
script any more:

1. clean build of `dist/RetroDisc.exe`
2. sign `dist/RetroDisc.exe`
3. verify its Authenticode status; anything but `Valid` aborts the build
4. **only then** pack the portable ZIP, so it contains the signed bytes
5. build the installer, which embeds the already signed EXE
6. sign the installer and verify it
7. unpack the ZIP to a temporary directory and verify the **unpacked** EXE
8. install the installer into an isolated sandbox and verify the **installed**
   EXE

Steps 1–7 run inside `python build.py --clean --sign`. Step 8 runs in
`python scripts/verify_release_artifacts.py --require-signed`, which installs
and uninstalls for real in a sandbox with `USERPROFILE`, `APPDATA` and
`LOCALAPPDATA` redirected.

Never sign artifacts after the fact. If a signature is missing, rebuild.

## Signing stays optional

- Without a certificate, `python build.py --clean` still produces a working
  **development** build. It prints that the artifacts are unsigned.
- `--sign` is the release mode. It aborts if no certificate is configured, if
  signing fails, if the signed file does not verify as `Valid`, or if the EXE
  inside the ZIP is not `Valid`.
- `scripts/verify_release_artifacts.py --require-signed` turns every missing or
  invalid signature into a gate failure instead of a note, including the ZIP
  copy and the installed copy.

## Configuration

Credentials reach the build through the environment only. **Never commit a
PFX, a private key, a password or a token**; `.gitignore` blocks the usual
extensions, but the rule is the safeguard, not the file. Thumbprints are not
hard-coded anywhere in the build either — they are read from the environment at
build time.

Either a certificate from the Windows certificate store:

```powershell
$env:RETRODISC_SIGN_THUMBPRINT = "<thumbprint of your code-signing cert>"
```

or a PFX kept outside the repository:

```powershell
$env:RETRODISC_SIGN_PFX      = "C:\secure\retrodisc-code-signing.pfx"
$env:RETRODISC_SIGN_PASSWORD = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText
```

Optional, defaults to DigiCert's RFC 3161 endpoint:

```powershell
$env:RETRODISC_SIGN_TIMESTAMP_URL = "http://timestamp.digicert.com"
```

The password is passed to PowerShell through the process environment only. It
is never written into a script file or a command line.

Then:

```powershell
python build.py --clean --sign
python scripts\verify_release_artifacts.py --require-signed
```

To inspect a signature by hand:

```powershell
powershell -File scripts\verify_signing.ps1
Get-AuthenticodeSignature .\dist\RetroDisc.exe | Format-List Status,SignerCertificate,TimeStamperCertificate
```

## A development certificate is not a release certificate

`CN=RetroDisc Development` is a **local development certificate**. It makes
`Get-AuthenticodeSignature` report `Valid` on this machine because the issuing
root is trusted here, and it proves the signing pipeline works end to end. It
proves nothing about any other machine.

For public distribution RetroDisc still needs a **publicly trusted
code-signing certificate** from a public CA, or a managed signing service.
Reasons, stated plainly:

- On a machine that does not trust the issuing root, a development-signed file
  verifies as `UntrustedRoot`, not `Valid`. Distributing it is no better than
  distributing an unsigned build.
- Smart App Control checks its own policy and Microsoft's reputation service.
  A self-issued or locally trusted certificate is in neither, so SAC keeps
  blocking with CodeIntegrity event 3033/3077. In practice an EV or
  well-established OV certificate is what earns SmartScreen reputation.

So: the pipeline is finished and proven, and the remaining gap is procurement,
not code. Until a publicly trusted certificate is in place, builds signed with
the development certificate must not be handed to third parties.
