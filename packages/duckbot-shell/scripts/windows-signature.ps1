# Shared Windows release checks. No certificate is imported or added to a trust store.
Set-StrictMode -Version Latest

function Find-DuckbotSignTool {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $sdk = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $tools = @(Get-ChildItem "$sdk\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending)
    if (!$tools.Count) { throw 'Install the Windows SDK signing tools first.' }
    return $tools[0].FullName
}

function Assert-DuckbotSignature {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{40}$')][string]$Thumbprint,
        [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Publisher
    )
    $file = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($file.PSIsContainer) { throw 'Expected one signed file.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne 'Valid') { throw "Signature is not trusted and valid: $($file.Name) ($($signature.Status))." }
    if ($signature.SignatureType -ne 'Authenticode') { throw 'An embedded Authenticode signature is required.' }
    $certificate = $signature.SignerCertificate
    if ($certificate.Thumbprint -ne $Thumbprint) { throw 'The signing certificate is not the approved release certificate.' }
    $name = $certificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
    if ($name -cne $Publisher) { throw 'The certificate publisher does not match the approved publisher.' }
    if ($certificate.Subject -eq $certificate.Issuer) { throw 'Self-signed certificates cannot pass the public release gate.' }
    $eku = @($certificate.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.37' } |
        ForEach-Object { $_.EnhancedKeyUsages } | ForEach-Object { $_.Value })
    if ('1.3.6.1.5.5.7.3.3' -notin $eku) { throw 'The certificate is not a code-signing certificate.' }
    if (!$signature.TimeStamperCertificate) { throw 'A trusted timestamp is required.' }
    $tool = Find-DuckbotSignTool
    & $tool verify /pa /all /tw $file.FullName | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Windows SignTool rejected the signature or timestamp.' }
    return [pscustomobject]@{
        file = $file.Name
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        bytes = $file.Length
        publisher = $name
        certificateThumbprint = $certificate.Thumbprint
        timestampAuthority = $signature.TimeStamperCertificate.Subject
    }
}
