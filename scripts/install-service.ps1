# Register ClauditSEO as a per-user scheduled task so the server survives
# terminal restarts, editor restarts and logging out. Anything launched from a
# shell belongs to that shell's process tree and dies with it, which is why a
# plain background launch keeps disappearing.
#
# Starts at logon, restarts itself if it crashes, and starts immediately.
# Remove it with scripts\uninstall-service.ps1.
#
# Note: this file is deliberately ASCII-only. Windows PowerShell 5.1 reads
# .ps1 as ANSI unless there is a BOM, so a stray em dash breaks parsing.

param(
    [string]$TaskName = "ClauditSEO server",
    [int]$Port = 8020
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $python)) {
    # pythonw runs without a console window; fall back if it is absent.
    $python = Join-Path $root ".venv\Scripts\python.exe"
}
if (-not (Test-Path $python)) {
    throw "No virtualenv found at $root\.venv. Run scripts\dev.ps1 first."
}

# Stop anything already serving, so the task owns the database file alone.
Get-Process python, pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$root*" } |
    ForEach-Object {
        Write-Host "stopping existing server (pid $($_.Id))"
        Stop-Process -Id $_.Id -Force
    }

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "replacing existing task '$TaskName'"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute $python `
    -Argument "-m clauditseo serve" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Serves the ClauditSEO dashboard and API on port $Port." | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "registered and started '$TaskName'"

for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 1
    try {
        $health = (Invoke-WebRequest -UseBasicParsing "http://localhost:$Port/api/health" `
                   -TimeoutSec 3).Content
        Write-Host "server responding: $health"

        # The staleness check exists and, until now, nothing called it at the
        # moment that mattered. A task registered -AtLogOn starts whatever
        # source was on disk at logon and then serves it indefinitely, so the
        # gap opens silently and is found by an audit. Answered here, where a
        # human is watching the output.
        #
        # Advisory, not fatal: the server IS up, and refusing to finish an
        # install because the source moved during it would be the wrong call.
        # Exit code 2 is "stale", 3 is "nothing serving", and 1 would mean the
        # check itself did not run.
        & powershell -NoProfile -ExecutionPolicy Bypass -File `
            (Join-Path $PSScriptRoot 'restart-service.ps1') -CheckOnly
        if ($LASTEXITCODE -eq 2) {
            Write-Warning ("The server is up but does not hold the current " +
                           "source. Run restart-service.ps1 before trusting " +
                           "what it serves.")
        } elseif ($LASTEXITCODE -eq 1) {
            Write-Warning ("The staleness check did not run. Whether the " +
                           "server holds current source is unknown, which is " +
                           "not the same as it being fine.")
        }

        Write-Host "ClauditSEO is at http://localhost:$Port and restarts at every logon."
        exit 0
    } catch { }
}
throw "The task was registered but the server did not respond on port $Port."
