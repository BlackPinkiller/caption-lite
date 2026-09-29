param(
    [switch]$Multilingual,
    [switch]$LongContext
)

$ErrorActionPreference = 'Stop'
if ($Multilingual -and $LongContext) {
    throw 'Choose either -Multilingual or -LongContext'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$modelName = if ($Multilingual) {
    'sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-560ms-int8-2026-06-11'
} elseif ($LongContext) {
    'sherpa-onnx-nemotron-speech-streaming-en-0.6b-1120ms-int8-2026-04-25'
} else {
    'sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25'
}
$expectedBytes = if ($Multilingual) {
    475271763
} elseif ($LongContext) {
    463945058
} else {
    463945051
}
$expectedSha256 = if ($Multilingual) {
    'c6bf5e0df765f9d5b43bc9e0536d4b4b3e7d40bdf5ecf13e45f134c51c05ae3a'
} elseif ($LongContext) {
    '840c48deed02d4a5975716e7b12dc0a8b1ba620776c6366f7e5677d8907edd73'
} else {
    '78e2b79fcf7271553a74402a76b771b09ea40117a39566a79f52235b23db6358'
}
$destination = Join-Path $projectRoot (Join-Path 'models' $modelName)
$parent = Split-Path -Parent $destination
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$archive = Join-Path $parent "$modelName.tar.bz2"
$url = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/' +
       "$modelName.tar.bz2"
curl.exe -L --fail --retry 3 --output $archive $url
if ($LASTEXITCODE -ne 0) { throw 'Nemotron model download failed' }
$actualBytes = (Get-Item -LiteralPath $archive).Length
if ($actualBytes -ne $expectedBytes) {
    throw "Nemotron model size mismatch: expected $expectedBytes, got $actualBytes"
}
$actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $expectedSha256) {
    throw 'Nemotron model checksum mismatch'
}
tar.exe -xjf $archive -C $parent
if ($LASTEXITCODE -ne 0) { throw 'Nemotron model extraction failed' }
$extracted = Join-Path $parent $modelName
if (-not (Test-Path -LiteralPath (Join-Path $extracted 'encoder.int8.onnx'))) {
    throw "Expected model files were not found in $extracted"
}
Remove-Item -LiteralPath $archive -Force
Write-Host "Nemotron model ready at $destination"
