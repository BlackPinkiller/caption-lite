$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $projectRoot '.venv'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the Python environment' }
}

& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Unable to update pip' }
& $python -m pip install -r (Join-Path $projectRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Unable to install dependencies' }

Write-Host "Environment ready: $python"
Write-Host 'Next: .\tools\download-nemotron-model.ps1'
Write-Host 'Run:  .\tools\run.ps1'
