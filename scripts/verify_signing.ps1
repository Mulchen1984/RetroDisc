param(
    [string[]]$Paths = @(
        "dist\RetroDisc.exe",
        "Output\RetroDisc_Setup_1.0.0.exe"
    )
)

$ErrorActionPreference = "Stop"
$failed = $false

foreach ($path in $Paths) {
    if (-not (Test-Path $path)) {
        Write-Error "Missing release artifact: $path"
        $failed = $true
        continue
    }

    $sig = Get-AuthenticodeSignature -FilePath $path
    $subject = if ($sig.SignerCertificate) { $sig.SignerCertificate.Subject } else { "<none>" }
    $thumbprint = if ($sig.SignerCertificate) { $sig.SignerCertificate.Thumbprint } else { "<none>" }

    Write-Host "$path"
    Write-Host "  Status:     $($sig.Status)"
    Write-Host "  Subject:    $subject"
    Write-Host "  Thumbprint: $thumbprint"

    if ($sig.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        $failed = $true
    }
}

if ($failed) {
    Write-Error "One or more shipped executables are missing a valid Authenticode signature."
    exit 1
}

Write-Host "PASS: all shipped executables have a valid Authenticode signature."
exit 0
