param(
  [string]$Video = "../output/system-check.mp4",
  [string]$Voice = "../output/voiceover-raw.wav",
  [string]$Output = "../output/system-check-mastered.mp4"
)

$videoPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Video))
$voicePath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Voice))
$outputPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Output))

ffmpeg -y `
  -i $videoPath `
  -i $voicePath `
  -filter_complex "[1:a]highpass=f=70,lowpass=f=10000,afftdn=nf=-25,dynaudnorm=f=150:g=7,loudnorm=I=-16:TP=-1.5:LRA=7,aresample=48000[voice]" `
  -map 0:v:0 `
  -map "[voice]" `
  -c:v copy `
  -c:a aac `
  -b:a 192k `
  -shortest `
  -movflags +faststart `
  $outputPath

if ($LASTEXITCODE -ne 0) {
  throw "FFmpeg mastering failed with exit code $LASTEXITCODE"
}

Write-Output "Created $outputPath"
