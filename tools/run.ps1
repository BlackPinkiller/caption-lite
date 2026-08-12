$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Environment missing. Run .\tools\setup.ps1 first.'
}
& $python (Join-Path $projectRoot 'main.py')
