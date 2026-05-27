param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectJson,
    [string]$ScenePlanJson = "",
    [string]$Workdir = "",
    [int]$Start = 1,
    [int]$End = 0,
    [string]$AspectRatio = "16:9",
    [double]$PollSeconds = 10,
    [int]$MaxPolls = 180,
    [int]$Concurrency = 4,
    [int]$TaskRetries = 1,
    [int]$StopAfterConsecutiveFailures = 5,
    [switch]$StopOnError,
    [switch]$Detached,
    [switch]$PrintOnly,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

function Test-VeoApiKey {
    if ($env:VEO_NONSTOP_API_KEY -and $env:VEO_NONSTOP_API_KEY.Trim()) {
        return $true
    }

    $envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
    if (-not (Test-Path $envPath)) {
        return $false
    }

    $line = Select-String -Path $envPath -Pattern "^VEO_NONSTOP_API_KEY=" -SimpleMatch:$false | Select-Object -First 1
    return [bool]$line
}

$projectPath = [System.IO.Path]::GetFullPath($ProjectJson)
if (-not (Test-Path $projectPath)) {
    throw "Project json not found: $projectPath"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$runnerPath = Join-Path $repoRoot "scripts\run_veononstop_standard_scene_plan.py"
if (-not (Test-Path $runnerPath)) {
    throw "Runner script not found: $runnerPath"
}

$project = Get-Content $projectPath -Raw | ConvertFrom-Json

if (-not $ScenePlanJson) {
    $ScenePlanJson = $project.animation.scene_plan_source_path
    if (-not $ScenePlanJson) {
        $ScenePlanJson = $project.scene_plan.scene_plan_path
    }
}

if (-not $Workdir) {
    $Workdir = $project.animation.standard_run_dir
    if (-not $Workdir) {
        $runManifestPath = [string]$project.animation.run_manifest_path
        if (-not $runManifestPath) {
            throw "animation.run_manifest_path is missing in project json."
        }
        $Workdir = Split-Path -Parent $runManifestPath
    }
}

$scenePlanPath = [System.IO.Path]::GetFullPath($ScenePlanJson)
$workdirPath = [System.IO.Path]::GetFullPath($Workdir)
New-Item -ItemType Directory -Force -Path $workdirPath | Out-Null

if (-not (Test-Path $scenePlanPath)) {
    throw "Scene plan json not found: $scenePlanPath"
}

if (-not (Test-VeoApiKey)) {
    throw "VEO_NONSTOP_API_KEY was not found in the environment or in C:\Users\MIKE\Documents\Codex\YT\.env"
}

$argList = @(
    $runnerPath,
    "--scene-plan-json", $scenePlanPath,
    "--workdir", $workdirPath,
    "--start", "$Start",
    "--aspect-ratio", $AspectRatio,
    "--poll-seconds", "$PollSeconds",
    "--max-polls", "$MaxPolls",
    "--concurrency", "$Concurrency",
    "--task-retries", "$TaskRetries",
    "--stop-after-consecutive-failures", "$StopAfterConsecutiveFailures"
)

if ($End -gt 0) {
    $argList += @("--end", "$End")
}

if ($StopOnError) {
    $argList += "--stop-on-error"
}

$commandPreview = @($PythonExe) + $argList
$commandText = $commandPreview -join " "
$commandPath = Join-Path $workdirPath "launcher_command.txt"
$stdoutPath = Join-Path $workdirPath "launcher_stdout.log"
$stderrPath = Join-Path $workdirPath "launcher_stderr.log"

Set-Content -Path $commandPath -Value $commandText -Encoding UTF8

Write-Host "Project: $projectPath"
Write-Host "Scene plan: $scenePlanPath"
Write-Host "Workdir: $workdirPath"
Write-Host "Command: $commandText"

if ($PrintOnly) {
    return
}

if ($Detached) {
    $process = Start-Process -FilePath $PythonExe -ArgumentList $argList -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    Write-Host "Started detached veononstop standard run. PID: $($process.Id)"
    Write-Host "Stdout: $stdoutPath"
    Write-Host "Stderr: $stderrPath"
    return
}

& $PythonExe @argList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
