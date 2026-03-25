<#
.SYNOPSIS
    Build ONyX Client portable distribution (no installer required).
    Pipeline: PyInstaller → copy daemon into client folder → sign → zip

.PARAMETER Version
    Version string embedded in the output archive, e.g. "0.3.0"

.PARAMETER CertThumbprint
    SHA1 thumbprint of a certificate in Cert:\CurrentUser\My or Cert:\LocalMachine\My.
    Use generate-cert.ps1 to create a self-signed one.

.PARAMETER CertFile
    Path to a .pfx certificate file (alternative to CertThumbprint).

.PARAMETER CertPassword
    Password for the .pfx file.

.PARAMETER TimestampUrl
    RFC 3161 timestamp server URL.
    Default: http://timestamp.digicert.com

.PARAMETER SkipSigning
    Build without code signing (development/testing without a cert).

.EXAMPLE
    # Quick build, no signing
    .\build-portable.ps1 -Version "0.3.0" -SkipSigning

    # With self-signed cert from generate-cert.ps1
    .\build-portable.ps1 -Version "0.3.0" -CertFile ".\onyx-codesign.pfx" -CertPassword "secret"
#>

param(
    [Parameter(Mandatory)]
    [string]$Version,

    [string]$CertThumbprint  = "",
    [string]$CertFile        = "",
    [string]$CertPassword    = "",
    [string]$TimestampUrl    = "http://timestamp.digicert.com",
    [switch]$SkipSigning
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ClientDir   = $PSScriptRoot
$DistDir     = Join-Path $ClientDir "dist"
$PortableDir = Join-Path $ClientDir "dist-portable"

# ── Locate signtool ───────────────────────────────────────────────────────────

function Find-Signtool {
    $sdkBin = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (Test-Path $sdkBin) {
        $found = Get-ChildItem "$sdkBin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
                 Sort-Object Name -Descending | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$Signtool = Find-Signtool
$DoSign   = (-not $SkipSigning) -and ($CertThumbprint -ne "" -or $CertFile -ne "")

if ($DoSign -and -not $Signtool) {
    Write-Error "signtool.exe not found. Install Windows 10 SDK or pass -SkipSigning."
}

# ── Helper: sign file(s) ──────────────────────────────────────────────────────

function Sign-Files {
    param([string[]]$Files)

    if (-not $DoSign) {
        Write-Host "  [signing skipped]" -ForegroundColor DarkGray
        return
    }

    $args = @("sign", "/fd", "sha256", "/td", "sha256", "/tr", $TimestampUrl)

    if ($CertFile -ne "") {
        $args += "/f", (Resolve-Path $CertFile).Path
        if ($CertPassword -ne "") { $args += "/p", $CertPassword }
    } else {
        $args += "/sha1", $CertThumbprint
    }

    foreach ($f in $Files) {
        if (-not (Test-Path $f)) { Write-Warning "  not found, skipping: $f"; continue }
        Write-Host "  signing: $(Split-Path $f -Leaf)"
        & $Signtool @args $f
        if ($LASTEXITCODE -ne 0) { throw "signtool failed: $f" }
    }
}

# ── Step 1: PyInstaller ───────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== Step 1: PyInstaller ===" -ForegroundColor Cyan
Push-Location $ClientDir

Write-Host "  Building ONyXClient (GUI, COLLECT mode)..."
python -m PyInstaller --noconfirm ONyXClient.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: ONyXClient.spec" }

Write-Host "  Building ONyXClientDaemon (onefile)..."
python -m PyInstaller --noconfirm ONyXClientDaemon.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: ONyXClientDaemon.spec" }

Pop-Location

# ── Step 2: Assemble portable folder ─────────────────────────────────────────
#   dist/ONyXClient/ is the portable root.
#   The daemon must sit next to ONyXClient.exe so the client can find and
#   launch it automatically on first run.

Write-Host ""
Write-Host "=== Step 2: Assemble portable folder ===" -ForegroundColor Cyan

$ClientExe  = Join-Path $DistDir "ONyXClient\ONyXClient.exe"
$DaemonExe  = Join-Path $DistDir "ONyXClientDaemon.exe"
$DaemonDst  = Join-Path $DistDir "ONyXClient\ONyXClientDaemon.exe"

if (-not (Test-Path $DaemonExe)) {
    throw "Daemon binary not found: $DaemonExe"
}

Write-Host "  Copying ONyXClientDaemon.exe → ONyXClient\"
Copy-Item $DaemonExe $DaemonDst -Force

# ── Step 3: Sign ──────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== Step 3: Sign executables ===" -ForegroundColor Cyan

Sign-Files @($ClientExe, $DaemonDst)

$BinExes = Get-ChildItem (Join-Path $DistDir "ONyXClient\_internal\bin\*.exe") `
               -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
if ($BinExes) {
    Write-Host "  signing bundled VPN binaries..."
    Sign-Files $BinExes
}

# ── Step 4: Zip ───────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== Step 4: Create zip archive ===" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $PortableDir | Out-Null

$ZipName = "ONyXClient-$Version-portable.zip"
$ZipPath = Join-Path $PortableDir $ZipName

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

$SourceDir = Join-Path $DistDir "ONyXClient"
Compress-Archive -Path "$SourceDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "  Archive: $ZipPath  ($([Math]::Round((Get-Item $ZipPath).Length / 1MB, 1)) MB)"

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host "  Output  : $ZipPath"
Write-Host "  Usage   : Extract zip anywhere, run ONyXClient.exe"
Write-Host "            On first connect UAC will appear once to launch the daemon."
if ($DoSign) {
    $certLabel = if ($CertFile -ne "") { (Split-Path $CertFile -Leaf) } else { "thumbprint $CertThumbprint" }
    Write-Host "  Signed  : $certLabel"
} else {
    Write-Host "  Signed  : NO  (pass -CertFile / -CertThumbprint to enable)" -ForegroundColor Yellow
}
