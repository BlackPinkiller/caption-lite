param([switch]$Multilingual)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$modelName = if ($Multilingual) {
    'sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-560ms-int8-2026-06-11'
} else {
    'sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25'
}
$destination = Join-Path $projectRoot (Join-Path 'models' $modelName)
$parent = Split-Path -Parent $destination
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$archive = Join-Path $parent "$modelName.tar.bz2"
$url = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/' +
       "$modelName.tar.bz2"
curl.exe -L --fail --retry 3 --output $archive $url
if ($LASTEXITCODE -ne 0) { throw 'Nemotron model download failed' }
tar.exe -xjf $archive -C $parent
if ($LASTEXITCODE -ne 0) { throw 'Nemotron model extraction failed' }
$extracted = Join-Path $parent $modelName
if (-not (Test-Path -LiteralPath (Join-Path $extracted 'encoder.int8.onnx'))) {
    throw "Expected model files were not found in $extracted"
}
Remove-Item -LiteralPath $archive -Force
Write-Host "Nemotron model ready at $destination"
