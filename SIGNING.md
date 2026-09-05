# RetroDisc Code Signing

RetroDisc release artifacts must be Authenticode-signed before public distribution.

## Trusted release signing

Use a trusted Windows code-signing certificate from a public CA or a managed signing service. Do not commit certificates, private keys, PFX files, passwords, tokens, or other signing credentials to this repository.

Recommended flow:

1. Build release artifacts from a clean working tree.
2. Sign `dist/RetroDisc.exe` and `Output/RetroDisc_Setup_1.0.0.exe` with SHA-256 and an RFC 3161 timestamp.
3. Verify the Authenticode status of every shipped executable.
4. Rebuild or refresh the portable ZIP only after the signed EXE exists so the ZIP contains the signed bytes.
5. Run the full release gates again against the signed artifacts and record their final hashes.

Example with SignTool when a certificate is available in the Windows certificate store:

```powershell
signtool sign /sha1 <CERT_THUMBPRINT> /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\RetroDisc.exe
signtool sign /sha1 <CERT_THUMBPRINT> /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 Output\RetroDisc_Setup_1.0.0.exe
```

Example with a PFX file kept outside the repository:

```powershell
signtool sign /f C:\secure\retrodisc-code-signing.pfx /p $env:RETRODISC_SIGN_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\RetroDisc.exe
signtool sign /f C:\secure\retrodisc-code-signing.pfx /p $env:RETRODISC_SIGN_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 Output\RetroDisc_Setup_1.0.0.exe
```

Verify:

```powershell
Get-AuthenticodeSignature .\dist\RetroDisc.exe | Format-List Status,StatusMessage,SignerCertificate,TimeStamperCertificate
Get-AuthenticodeSignature .\Output\RetroDisc_Setup_1.0.0.exe | Format-List Status,StatusMessage,SignerCertificate,TimeStamperCertificate
```

A self-signed certificate is acceptable only for local development/testing and does not make a public release trusted by Windows SmartScreen.
