param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectJson
)

$project = Get-Content -Raw $ProjectJson | ConvertFrom-Json
$timeline = $project.render.ffconcat_path
$audio = $project.inputs.audio_path
$output = $project.render.final_video_path
$outputDir = Split-Path -Parent $output

New-Item -ItemType Directory -Force $outputDir | Out-Null

ffmpeg -y `
  -f concat -safe 0 -i $timeline `
  -i $audio `
  -filter:v "pad=ceil(iw/2)*2:ceil(ih/2)*2:color=black,fps=30,format=yuv420p" `
  -c:v libx264 -preset medium -crf 18 `
  -c:a aac -b:a 192k `
  -movflags +faststart `
  -shortest `
  $output

Get-Item $output | Select-Object FullName,Length,LastWriteTime
