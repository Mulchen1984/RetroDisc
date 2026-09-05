param(
    [Parameter(Mandatory=$true)]
    [string]$CertThumbprint,

    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

function Resolve-SignTool {
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kitsRoot) {
        $candidate = Get-ChildItem $kitsRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "x64\signtool.exe" } |
            Where-Object { Test-Path $_ } |
            Select-Object -First 1
        if ($candidate) { return $candidate }
    }

    throw "signtool.exe was not found. Install the Windows SDK signing tools."
}

$signTool = Resolve-SignTool
$targets = @(
    "dist\RetroDisc.exe",
    "Output\RetroDisc_Setup_1.0.0.exe"
)

foreach ($target in $targets) {
    if (-not (Test-Path $target)) {
        throw "Missing release artifact: $target"
    }

    Write-Host "Signing $target ..."
    & $signTool sign /sha1 $CertThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $target
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool failed for $target with exit code $LASTEXITCODE"
    }
}

& "$PSScriptRoot\verify_signing.ps1" -Paths $targets
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "PASS: RetroDisc release executables are signed and verified."
