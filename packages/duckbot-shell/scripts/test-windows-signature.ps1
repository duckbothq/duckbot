$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\windows-signature.ps1"

# Native Windows checks, using Microsoft's existing signed PowerShell executable.
# No test certificate is trusted, no signing key is created, and no fixture is shipped.
$fixture = Join-Path $PSHOME 'pwsh.exe'
$signature = Get-AuthenticodeSignature -LiteralPath $fixture
$thumbprint = $signature.SignerCertificate.Thumbprint
$publisher = $signature.SignerCertificate.GetNameInfo(
    [System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
$accepted = Assert-DuckbotSignature -Path $fixture -Thumbprint $thumbprint -Publisher $publisher
if ($accepted.sha256 -ne (Get-FileHash $fixture -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'The signature evidence has an incorrect file hash.'
}
$script:checks = 1
function Expect-Rejection {
    param([scriptblock]$Action, [string]$Message)
    $rejected = $false
    try { & $Action | Out-Null } catch {
        if ($_.Exception.Message -notlike "*$Message*") { throw }
        $rejected = $true
    }
    if (!$rejected) { throw "The release gate unexpectedly accepted: $Message" }
    $script:checks++
}
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('duckbot-signature-test-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    Expect-Rejection { Assert-DuckbotSignature $fixture ('0' * 40) $publisher } 'not the approved release certificate'
    Expect-Rejection { Assert-DuckbotSignature $fixture $thumbprint 'Another publisher' } 'publisher does not match'
    Expect-Rejection { Assert-DuckbotSignature $fixture 'not-a-thumbprint' $publisher } 'Thumbprint'
    $unsigned = Join-Path $temporary 'unsigned.ps1'
    'Write-Output "Never executed"' | Set-Content $unsigned
    Expect-Rejection { Assert-DuckbotSignature $unsigned $thumbprint $publisher } 'not trusted and valid'
    $tampered = Join-Path $temporary 'tampered.exe'
    $bytes = [IO.File]::ReadAllBytes($fixture)
    $bytes[0x28] = $bytes[0x28] -bxor 1
    [IO.File]::WriteAllBytes($tampered, $bytes)
    Expect-Rejection { Assert-DuckbotSignature $tampered $thumbprint $publisher } 'not trusted and valid'
    $repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
    $commit = (& git -C $repo rev-parse HEAD).Trim()
    $output = Join-Path $temporary 'must-not-be-published'
    Expect-Rejection {
        & "$PSScriptRoot\verify-windows-release.ps1" -InstallerPath $fixture `
            -Thumbprint ('0' * 40) -Publisher $publisher -SourceCommit $commit -OutputDirectory $output
    } 'not the approved release certificate'
    if (Test-Path $output) { throw 'Rejected candidate created release output.' }
    $errors = @()
    foreach ($file in Get-ChildItem "$PSScriptRoot\*.ps1") {
        $tokens = $null
        $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
        $errors += $parseErrors
    }
    if ($errors.Count) { throw ($errors | Out-String) }
    Write-Host "$script:checks native signature checks passed; all PowerShell files parsed."
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
