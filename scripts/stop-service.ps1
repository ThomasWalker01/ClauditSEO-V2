# Stop the ClauditSEO server without unregistering the scheduled task, so the
# database and log file are released (for a backup, for example) and the task
# is still there to start again.
#
# Start it back up with scripts\restart-service.ps1.
# ASCII-only: see the note in install-service.ps1.
param([string]$TaskName = "ClauditSEO server")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host "stopped scheduled task '$TaskName'"
}

# Stop-ScheduledTask does not always reap the child process.
Get-Process python, pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$root*" } |
    ForEach-Object {
        Write-Host "stopping server process (pid $($_.Id))"
        Stop-Process -Id $_.Id -Force
    }
Start-Sleep -Seconds 2

if (Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue) {
    Write-Warning "something is still listening on port 8020"
} else {
    Write-Host "port 8020 free; database and log file are released"
}
