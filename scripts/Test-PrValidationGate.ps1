#requires -Version 7.0
param([string]$Root=(Split-Path $PSScriptRoot -Parent),[int]$MaxTotalSeconds=600,[int]$ChildTimeoutSeconds=90)
$ErrorActionPreference='Stop'
Push-Location (Join-Path $Root 'source')
try {
  & npm.cmd run build
  if($LASTEXITCODE -ne 0){throw 'Reading build failed'}
  & npm.cmd run qa:reading
  if($LASTEXITCODE -ne 0){throw 'Reading data QA failed'}
  & python tools/verify_reading_site.py
  if($LASTEXITCODE -ne 0){throw 'Source and link QA failed'}
  & python tools/verify_game_images.py
  if($LASTEXITCODE -ne 0){throw 'Game image source QA failed'}
  Write-Output 'RESULT: PASS'
} finally {Pop-Location}
