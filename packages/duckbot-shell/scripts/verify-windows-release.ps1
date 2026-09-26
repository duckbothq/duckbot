param(
    [Parameter(Mandatory)][string]$InstallerPath,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{40}$')][string]$Thumbprint,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Publisher,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\windows-signature.ps1"
$installer = Get-Item -LiteralPath $InstallerPath -ErrorAction Stop
if ($installer.Extension -ne '.exe') { throw 'Expected a Windows executable installer.' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new, empty release output location; previous evidence is never overwritten.' }
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$actualCommit = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $SourceCommit) { throw 'Acceptance checkout does not match the declared source commit.' }
$changes = @(& git -C $repo status --porcelain)
if ($LASTEXITCODE -ne 0 -or $changes.Count) { throw 'Acceptance requires a clean source checkout.' }
# Check trust BEFORE executing the installer. The same gate checks installed payloads
# before the smoke test executes them, then exercises the real installed application.
$installerEvidence = Assert-DuckbotSignature -Path $installer.FullName -Thumbprint $Thumbprint -Publisher $Publisher
$payloadEvidence = @(& "$PSScriptRoot\installed-smoke.ps1" -InstallerPath $installer.FullName `
    -RequireSignature -SignerThumbprint $Thumbprint -Publisher $Publisher -ReturnSignatureEvidence)
if ($payloadEvidence.Count -ne 2) { throw 'Expected signature evidence for both installed Duckbot executables.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
Copy-Item -LiteralPath $installer.FullName -Destination $OutputDirectory
$copied = Join-Path $OutputDirectory $installer.Name
if ((Get-FileHash -LiteralPath $copied -Algorithm SHA256).Hash.ToLowerInvariant() -ne $installerEvidence.sha256) {
    throw 'The release file changed during verification.'
}
@{
    schemaVersion = 1
    product = 'Duckbot Community'
    sourceCommit = $SourceCommit
    verifiedAt = (Get-Date).ToUniversalTime().ToString('o')
    installer = $installerEvidence
    installedPayloads = $payloadEvidence
    installationAndStartupPassed = $true
    # This is acceptance evidence, not a cryptographic reproducible-build attestation.
} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $OutputDirectory 'verification.json') -Encoding utf8
"$($installerEvidence.sha256)  $($installer.Name)" |
    Set-Content (Join-Path $OutputDirectory 'SHA256SUMS') -Encoding ascii
Write-Host 'Signed Windows candidate passed verification. No public upload was performed.'
