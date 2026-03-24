<#
.SYNOPSIS
    Generate a self-signed code-signing certificate for testing/internal use.

    Produces:
      onyx-codesign.pfx  — private key + cert (used by build.ps1)
      onyx-codesign.cer  — public cert only (deploy to trusted stores on user machines)

    The certificate is also added to Cert:\CurrentUser\My so signtool can find it
    by thumbprint.

.PARAMETER SubjectName
    CN field. Default: "ONyX Client"

.PARAMETER Password
    Password for the exported .pfx file.

.PARAMETER ValidYears
    Certificate validity in years. Default: 5.

.PARAMETER PfxPath
    Output path for .pfx. Default: .\onyx-codesign.pfx

.PARAMETER CerPath
    Output path for .cer. Default: .\onyx-codesign.cer

.EXAMPLE
    .\generate-cert.ps1 -Password "MySecret123"

.NOTES
    To trust this certificate on a machine (suppress SmartScreen / UAC warnings):
      Run as admin on each target machine:
        Import-Certificate -FilePath onyx-codesign.cer -CertStoreLocation Cert:\LocalMachine\TrustedPublisher
        Import-Certificate -FilePath onyx-codesign.cer -CertStoreLocation Cert:\LocalMachine\Root
      Or deploy via GPO in a domain environment.
#>

param(
    [string]$SubjectName = "ONyX Client",
    [Parameter(Mandatory)]
    [string]$Password,
    [int]$ValidYears     = 5,
    [string]$PfxPath     = ".\onyx-codesign.pfx",
    [string]$CerPath     = ".\onyx-codesign.cer"
)

$ErrorActionPreference = "Stop"

Write-Host "Generating self-signed code-signing certificate..." -ForegroundColor Cyan
Write-Host "  Subject : CN=$SubjectName"
Write-Host "  Valid   : $ValidYears years"

$cert = New-SelfSignedCertificate `
    -Subject          "CN=$SubjectName" `
    -Type             CodeSigningCert `
    -KeyUsage         DigitalSignature `
    -KeyAlgorithm     RSA `
    -KeyLength        4096 `
    -HashAlgorithm    SHA256 `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter         (Get-Date).AddYears($ValidYears)

Write-Host "  Thumbprint: $($cert.Thumbprint)" -ForegroundColor Green

# Export .pfx (private key — keep safe, do not share)
$SecurePass = ConvertTo-SecureString -String $Password -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath $PfxPath -Password $SecurePass | Out-Null

# Export .cer (public key only — safe to distribute to user machines)
Export-Certificate -Cert $cert -FilePath $CerPath | Out-Null

Write-Host ""
Write-Host "Files written:" -ForegroundColor Green
Write-Host "  $((Resolve-Path $PfxPath).Path)  [private — do not share]"
Write-Host "  $((Resolve-Path $CerPath).Path)   [public — distribute to user machines]"

Write-Host ""
Write-Host "Build signed installer:" -ForegroundColor Cyan
Write-Host "  .\build.ps1 -Version ""0.3.0"" -CertFile ""$PfxPath"" -CertPassword ""$Password"""

Write-Host ""
Write-Host "Trust on a user machine (run as admin — or via GPO):" -ForegroundColor Cyan
Write-Host "  Import-Certificate -FilePath ""$CerPath"" -CertStoreLocation Cert:\LocalMachine\TrustedPublisher"
Write-Host "  Import-Certificate -FilePath ""$CerPath"" -CertStoreLocation Cert:\LocalMachine\Root"
