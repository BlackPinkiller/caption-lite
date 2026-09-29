$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Environment missing. Run .\tools\setup.ps1 first.'
}

Push-Location $projectRoot
$originalPath = $env:PATH
try {
    & $python 'tools\verify_environment.py'
    if ($LASTEXITCODE -ne 0) { throw 'Build environment does not match the lock file' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed' }
    # Native DLL discovery must not pick up another application's runtimes from
    # PATH (for example, a private ucrtbase.dll can prevent QtCore from loading).
    $env:PATH = @(
        (Split-Path -Parent $python)
        (Join-Path $env:SystemRoot 'System32')
        $env:SystemRoot
    ) -join [IO.Path]::PathSeparator
    & $python -m PyInstaller --noconfirm --clean RealtimeSubtitle.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    Copy-Item -LiteralPath 'config.example.json' -Destination 'dist\config.example.json' -Force
    & $python 'tools\package_release.py'
    if ($LASTEXITCODE -ne 0) { throw 'Distribution package validation failed' }
    Write-Host "Built: $projectRoot\dist\RealtimeSubtitle.exe"
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
