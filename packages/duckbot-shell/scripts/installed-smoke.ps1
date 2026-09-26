param(
  [string]$InstallerPath,
  [switch]$RequireSignature,
  [string]$SignerThumbprint,
  [string]$Publisher,
  [switch]$ReturnSignatureEvidence
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$installer = @(if ($InstallerPath) { Get-Item -LiteralPath $InstallerPath } else {
  Get-ChildItem "$repo\packages\duckbot-shell\src-tauri\target\release\bundle\nsis\*.exe"
})
if ($installer.Count -ne 1) { throw 'Expected exactly one NSIS installer' }
if ($RequireSignature) {
  . "$PSScriptRoot\windows-signature.ps1"
  Assert-DuckbotSignature -Path $installer[0].FullName -Thumbprint $SignerThumbprint -Publisher $Publisher | Out-Null
}
$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$destination = Join-Path $temporaryRoot ('DuckbotInstalledSmoke-' + [guid]::NewGuid())
$install = Start-Process -FilePath $installer[0].FullName -ArgumentList @('/S', "/D=$destination") -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Installer failed with exit $($install.ExitCode)" }
$hostBinary = Join-Path $destination 'duckbot-host.exe'
$shellBinary = Join-Path $destination 'duckbot-shell.exe'
if (!(Test-Path $hostBinary)) { throw 'Installed sidecar is missing from the resource root' }
if (!(Test-Path $shellBinary)) { throw 'Installed desktop executable is missing' }
$payloadEvidence = @()
if ($RequireSignature) {
  $payloadEvidence += Assert-DuckbotSignature -Path $hostBinary -Thumbprint $SignerThumbprint -Publisher $Publisher
  $payloadEvidence += Assert-DuckbotSignature -Path $shellBinary -Thumbprint $SignerThumbprint -Publisher $Publisher
}
$env:DUCKBOT_DATA_DIR = Join-Path $temporaryRoot ('DuckbotInstalledSmokeData-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $env:DUCKBOT_DATA_DIR | Out-Null
python "$repo\packages\duckbot-host\scripts_smoke.py" $hostBinary | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Installed privacy smoke failed' }
python "$repo\packages\duckbot-host\scripts_product_smoke.py" $hostBinary | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Installed task smoke failed' }
$startupError = Join-Path $env:DUCKBOT_DATA_DIR 'startup-error.txt'
$desktop = Start-Process -FilePath $shellBinary -PassThru -RedirectStandardError $startupError
try {
  # Tauri creates its window before setup finishes spawning and handshaking the
  # frozen host. A window handle alone does not mean setup has finished.
  $deadline = (Get-Date).AddSeconds(30)
  $readySince = $null
  do {
    Start-Sleep -Milliseconds 500
    $desktop.Refresh()
    if ($desktop.HasExited) { throw "Installed desktop exited during startup: $($desktop.ExitCode)" }
    $child = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($desktop.Id)" |
      Where-Object { $_.Name -eq 'duckbot-host.exe' -and $_.ExecutablePath -eq $hostBinary })
    if ($desktop.MainWindowHandle -ne 0 -and $child.Count -gt 0) {
      if ($null -eq $readySince) { $readySince = Get-Date }
      if (((Get-Date) - $readySince).TotalSeconds -ge 3) { break }
    } else {
      $readySince = $null
    }
  } while ((Get-Date) -lt $deadline)
  if ($desktop.MainWindowHandle -eq 0) { throw 'Installed desktop did not open a window' }
  if ($null -eq $readySince -or ((Get-Date) - $readySince).TotalSeconds -lt 3) {
    throw 'Installed desktop did not keep its installed local service running'
  }
  Write-Host 'Installed desktop opened its window and started the installed sidecar.'
} catch {
  if (Test-Path $startupError) { Get-Content $startupError }
  throw
} finally {
  Stop-Process -Id $desktop.Id -Force -ErrorAction SilentlyContinue
}
if ($ReturnSignatureEvidence) { $payloadEvidence }
