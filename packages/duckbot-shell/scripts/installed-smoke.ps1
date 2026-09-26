$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$installer = @(Get-ChildItem "$repo\packages\duckbot-shell\src-tauri\target\release\bundle\nsis\*.exe")
if ($installer.Count -ne 1) { throw 'Expected exactly one NSIS installer' }
$destination = Join-Path $env:RUNNER_TEMP 'DuckbotInstalledSmoke'
$install = Start-Process -FilePath $installer[0].FullName -ArgumentList @('/S', "/D=$destination") -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Installer failed with exit $($install.ExitCode)" }
$hostBinary = Join-Path $destination 'duckbot-host.exe'
$shellBinary = Join-Path $destination 'duckbot-shell.exe'
if (!(Test-Path $hostBinary)) { throw 'Installed sidecar is missing from the resource root' }
if (!(Test-Path $shellBinary)) { throw 'Installed desktop executable is missing' }
$env:DUCKBOT_DATA_DIR = Join-Path $env:RUNNER_TEMP 'DuckbotInstalledSmokeData'
python "$repo\packages\duckbot-host\scripts_smoke.py" $hostBinary
if ($LASTEXITCODE -ne 0) { throw 'Installed privacy smoke failed' }
python "$repo\packages\duckbot-host\scripts_product_smoke.py" $hostBinary
if ($LASTEXITCODE -ne 0) { throw 'Installed task smoke failed' }
$startupError = Join-Path $env:RUNNER_TEMP 'DuckbotInstalledSmokeStartup.txt'
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
