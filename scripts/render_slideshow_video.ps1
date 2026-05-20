$projectRoot = 'C:\Users\MIKE\Documents\Codex\YT'
$timeline = Join-Path $projectRoot 'edit\timeline.ffconcat'
$audio = Join-Path $projectRoot 'assets\audio\message@elevenLabsVoicerBot.mp3'
$outputDir = Join-Path $projectRoot 'deliverables\final_video'
$output = Join-Path $outputDir 'telegram_darknet_final.mp4'

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
