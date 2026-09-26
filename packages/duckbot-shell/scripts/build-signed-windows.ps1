# Run on a prepared Windows signing machine after installing the build dependencies
# and configuring the certificate issuer's hardware/cloud key provider.
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\windows-signature.ps1"
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
if ($env:DUCKBOT_SIGNER_THUMBPRINT -notmatch '^[A-Fa-f0-9]{40}$' -or
    [string]::IsNullOrWhiteSpace($env:DUCKBOT_SIGNER_NAME)) {
    throw 'Configure the approved publisher name and certificate thumbprint before building.'
}
$certificate = Get-Item "Cert:\CurrentUser\My\$env:DUCKBOT_SIGNER_THUMBPRINT" -ErrorAction Stop
if (!$certificate.HasPrivateKey) { throw 'A working hardware/cloud signing key is required.' }
$changes = @(& git -C $repo status --porcelain)
if ($LASTEXITCODE -ne 0 -or $changes.Count) { throw 'Build public releases only from a clean source checkout.' }
$sourceCommit = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the release source.' }
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('duckbot-signing-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    Push-Location "$repo\packages\duckbot-host"
    try {
        pyinstaller --noconfirm --clean duckbot-host.spec
        if ($LASTEXITCODE -ne 0) { throw 'Sidecar build failed.' }
    } finally { Pop-Location }
    $hostBinary = "$repo\packages\duckbot-host\dist\duckbot-host.exe"
    & "$PSScriptRoot\sign-windows.ps1" $hostBinary
    New-Item -ItemType Directory -Force "$repo\packages\duckbot-shell\src-tauri\resources" | Out-Null
    Copy-Item -LiteralPath $hostBinary "$repo\packages\duckbot-shell\src-tauri\resources\duckbot-host.exe" -Force
    $signScript = (Join-Path $PSScriptRoot 'sign-windows.ps1').Replace('\', '/')
    $configuration = Join-Path $temporary 'signing.json'
    @{ bundle = @{ windows = @{ signCommand = "pwsh -NoProfile -File `"$signScript`" `"%1`"" } } } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configuration -Encoding utf8
    Push-Location "$repo\packages\duckbot-shell"
    try {
        npx --yes '@tauri-apps/cli@^2' build --config $configuration
        if ($LASTEXITCODE -ne 0) { throw 'Signed desktop build failed.' }
    } finally { Pop-Location }
    $installers = @(Get-ChildItem "$repo\packages\duckbot-shell\src-tauri\target\release\bundle\nsis\*.exe")
    if ($installers.Count -ne 1) { throw 'Expected exactly one newly built installer.' }
    & "$PSScriptRoot\verify-windows-release.ps1" -InstallerPath $installers[0].FullName `
        -Thumbprint $env:DUCKBOT_SIGNER_THUMBPRINT -Publisher $env:DUCKBOT_SIGNER_NAME `
        -SourceCommit $sourceCommit -OutputDirectory "$repo\dist\windows-release"
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
