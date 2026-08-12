$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Environment missing. Run .\tools\setup.ps1 first.'
}

Push-Location $projectRoot
try {
    & $python -m PyInstaller --noconfirm --clean RealtimeSubtitle.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    Copy-Item -LiteralPath 'config.example.json' -Destination 'dist\config.example.json' -Force
    Write-Host "Built: $projectRoot\dist\RealtimeSubtitle.exe"
} finally {
    Pop-Location
}
