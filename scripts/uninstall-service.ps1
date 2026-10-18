# Remove the ClauditSEO scheduled task and stop the running server.
# ASCII-only: see the note in install-service.ps1.
param([string]$TaskName = "ClauditSEO server")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed scheduled task '$TaskName'"
} else {
    Write-Host "no scheduled task named '$TaskName'"
}

Get-Process python, pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$root*" } |
    ForEach-Object {
        Write-Host "stopping server (pid $($_.Id))"
        Stop-Process -Id $_.Id -Force
    }
