param([Parameter(Mandatory, Position = 0)][string]$Path)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\windows-signature.ps1"
if ($env:DUCKBOT_SIGNER_THUMBPRINT -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Set the approved DUCKBOT_SIGNER_THUMBPRINT first.' }
if ([string]::IsNullOrWhiteSpace($env:DUCKBOT_SIGNER_NAME)) { throw 'Set DUCKBOT_SIGNER_NAME to the exact verified publisher.' }
$file = (Get-Item -LiteralPath $Path).FullName
$certificate = Get-Item "Cert:\CurrentUser\My\$env:DUCKBOT_SIGNER_THUMBPRINT" -ErrorAction Stop
if (!$certificate.HasPrivateKey) { throw 'The signing provider has not made this key available.' }
if ($certificate.NotAfter -le (Get-Date)) { throw 'The signing certificate has expired.' }
$tool = Find-DuckbotSignTool
# /sha1 identifies the approved certificate; file/timestamp digests are SHA-256.
# The private key stays with the configured hardware token or cloud KSP.
& $tool sign /s My /sha1 $env:DUCKBOT_SIGNER_THUMBPRINT /fd SHA256 `
    /tr http://timestamp.digicert.com /td SHA256 $file | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Signing failed; do not publish this file.' }
Assert-DuckbotSignature -Path $file -Thumbprint $env:DUCKBOT_SIGNER_THUMBPRINT -Publisher $env:DUCKBOT_SIGNER_NAME | Out-Null
