<#
.SYNOPSIS
    Stop the llama.cpp server started by start_llama_server.ps1.

.PARAMETER Port
    Port the server is listening on (default 8080).
#>
param(
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $conn) {
    Write-Host "No process is listening on port $Port."
    return
}

$pids = $conn.OwningProcess | Select-Object -Unique
foreach ($processId in $pids) {
    $p = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($p) {
        Write-Host "Stopping $($p.ProcessName) (PID $processId) ..."
        Stop-Process -Id $processId -Force
    }
}
Write-Host "Done."
