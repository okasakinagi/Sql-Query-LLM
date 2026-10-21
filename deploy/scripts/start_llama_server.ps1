<#
.SYNOPSIS
    Start a local OpenAI-compatible LLM server with llama.cpp.

.DESCRIPTION
    Launches llama-server.exe in the background with GPU offloading and
    waits until the health endpoint reports "ok".

    All paths default to this repository's deploy/ directory, so the script
    works from any clone location. Override them with parameters if your
    files live elsewhere.

.EXAMPLE
    # Windows + NVIDIA GPU (recommended)
    powershell -ExecutionPolicy Bypass -File .\deploy\scripts\start_llama_server.ps1

.EXAMPLE
    # Point at an external model / runtime and use a different port
    .\deploy\scripts\start_llama_server.ps1 `
        -ModelPath "D:\models\qwen2.5-coder-7b-instruct-q4_k_m.gguf" `
        -ServerPath "D:\llama.cpp\llama-server.exe" -Port 8080

.EXAMPLE
    # CPU only (slow, for smoke tests)
    .\deploy\scripts\start_llama_server.ps1 -GpuLayers 0
#>
param(
    [string]$ModelPath,
    [string]$ServerPath,
    [int]$Port = 8080,
    [string]$ListenHost = "127.0.0.1",
    [int]$GpuLayers = 999,
    [int]$Ctx = 8192,
    [string]$Alias = "qwen2.5-coder-7b-instruct"
)

$ErrorActionPreference = "Stop"

# deploy/ is the parent of deploy/scripts/
$deployRoot = Split-Path -Parent $PSScriptRoot

if (-not $ModelPath) {
    $ModelPath = Join-Path $deployRoot "models\qwen2.5-coder-7b-instruct-q4_k_m.gguf"
}
if (-not $ServerPath) {
    $ServerPath = Join-Path $deployRoot "runtime\llama.cpp\llama-server.exe"
}

$logDir = Join-Path $deployRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdout = Join-Path $logDir "server.log"
$stderr = Join-Path $logDir "server.err.log"

if (-not (Test-Path $ServerPath)) {
    throw "llama-server.exe not found: $ServerPath`nSee deploy/README.md for download instructions."
}
if (-not (Test-Path $ModelPath)) {
    throw "Model file not found: $ModelPath`nSee deploy/README.md for download instructions."
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Warning "Port $Port is already in use by PID $($existing.OwningProcess). Stop it first or pick another -Port."
}

Write-Host "[1/2] Starting llama-server ..."
Write-Host "      model : $ModelPath"
Write-Host "      server: $ServerPath"
Write-Host "      gpu   : -ngl $GpuLayers  ctx=$Ctx  port=$Port"

$proc = Start-Process -FilePath $ServerPath -ArgumentList @(
    "-m", "`"$ModelPath`"",
    "-ngl", "$GpuLayers",
    "-c", "$Ctx",
    "--host", $ListenHost,
    "--port", "$Port",
    "--alias", $Alias
) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden

Write-Host "      PID=$($proc.Id)  logs=$logDir"

Write-Host "[2/2] Waiting for the model to load (up to 180s) ..."
$ready = $false
for ($i = 0; $i -lt 180; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-RestMethod -Uri "http://${ListenHost}:$Port/health" -TimeoutSec 2
        if ($r.status -eq "ok") { $ready = $true; break }
    }
    catch { }
}

if ($ready) {
    Write-Host ""
    Write-Host "OK - OpenAI compatible endpoint: http://${ListenHost}:$Port/v1"
    Write-Host "     model alias: $Alias | ctx: $Ctx"
    Write-Host "     set LLM_BASE_URL=http://${ListenHost}:$Port/v1 and LLM_MODEL=$Alias"
}
else {
    Write-Warning "Server did not become ready in time. Check $stderr"
}
