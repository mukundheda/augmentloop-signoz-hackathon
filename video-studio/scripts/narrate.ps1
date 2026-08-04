param(
  [Parameter(Mandatory = $true)]
  [string]$Text,
  [string]$Output = "../output/voiceover-raw.wav",
  [string]$Voice = "",
  [int]$Rate = 0
)

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

if ($Voice) {
  $synth.SelectVoice($Voice)
}

$synth.Rate = $Rate
$target = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Output))
$directory = [System.IO.Path]::GetDirectoryName($target)
[System.IO.Directory]::CreateDirectory($directory) | Out-Null

try {
  $synth.SetOutputToWaveFile($target)
  $synth.Speak($Text)
} finally {
  $synth.Dispose()
}

Write-Output "Created $target"
