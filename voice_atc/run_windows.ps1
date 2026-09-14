# Native Windows run — more reliable for Tab5 on LAN than Docker Desktop port publish
# Usage (PowerShell):
#   cd D:\WSL\home\esp32_flight_radar\voice_atc
#   .\run_windows.ps1

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host 'Stopping Docker voice-atc (free port 18650)...'
try { docker stop voice-atc 2>$null | Out-Null } catch { }

if (-not (Test-Path .\.venv-win\Scripts\python.exe)) {
  Write-Host 'Creating .venv-win ...'
  py -3 -m venv .venv-win
  .\.venv-win\Scripts\python.exe -m pip install -U pip
  .\.venv-win\Scripts\pip.exe install -r requirements.txt
}

Get-Content .\.env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
  $k, $v = $_.Split('=', 2)
  if ($k -and $null -ne $v) { Set-Item -Path "Env:$k" -Value $v }
}

$env:VOICE_ATC_HOST = '0.0.0.0'
$env:VOICE_ATC_PORT = '18650'

Write-Host 'Listening on http://0.0.0.0:18650  (Tab5: http://192.168.12.59:18650)'
& .\.venv-win\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 18650
