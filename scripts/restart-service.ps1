# Restart the ClauditSEO scheduled task so it picks up code changes.
# Start-ScheduledTask on an already-running task is a no-op, which silently
# leaves the old code serving. Always stop first.
# ASCII-only: see the note in install-service.ps1.
param([string]$TaskName = "ClauditSEO server", [int]$Port = 8020,
      [switch]$Rebuild, [switch]$CheckOnly, [switch]$Force)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# Is the process that is serving older than the Python it is meant to be
# serving? Reported, never refused: a stale module is the reason to restart,
# so refusing would be refusing to do the one thing this script is for. The
# dashboard check below does refuse, because there the fix is a build this
# script does not perform.
#
# -CheckOnly answers the question without restarting, which is the part that
# was missing. This script only ever compared dashboard\src against
# dashboard\dist and named clauditseo nowhere, so nothing on the machine could
# say whether the running product held the current Python. It could not: the
# process serving on 2026-08-16 was created at 19:50:27 and d26b51b rewrote
# clauditseo/secrets.py at 20:27:54, thirty-seven minutes later, and the gap
# was found by an audit rather than by anything here.
# The server's own processes: the ones whose command line is `-m clauditseo
# serve`. It was every python under the repo root, and the stop below killed
# that whole set - which is also the .venv python a test suite, a CLI audit or
# a second session's worktree runs under. Measured 2026-09-14: a full suite
# started seconds before a restart died with an empty output file.
function Get-ServerProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like "$root*" -and $_.CommandLine -match '-m\s+clauditseo\s+serve' } |
        ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
}

function Get-ServerStaleness {
    $proc = Get-ServerProcesses | Sort-Object StartTime | Select-Object -First 1
    if (-not $proc) { return [pscustomobject]@{ Running = $false } }

    $watch = Join-Path $root "clauditseo"
    $newest = Get-ChildItem -Path $watch -Recurse -File -Filter *.py |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1

    [pscustomobject]@{
        Running   = $true
        Pid       = $proc.Id
        Started   = $proc.StartTime
        NewestPy  = $newest.FullName.Substring($root.Length + 1)
        Modified  = $newest.LastWriteTime
        Stale     = ($newest.LastWriteTime -gt $proc.StartTime)
    }
}

if ($CheckOnly) {
    # Exit codes, and 1 is deliberately not among them:
    #   0  the running process holds the current Python
    #   2  STALE - it does not
    #   3  nothing is serving at all
    #   1  the script did not run
    #
    # 1 is what PowerShell returns when execution policy refuses the file, and
    # this script used to return 1 for STALE as well. A caller could not tell
    # "your product is out of date" from "I never ran", and both are one line
    # of output nobody reads in a pipeline. Measured on this machine: with the
    # inherited PSExecutionPolicyPreference stripped, a bare
    # `powershell -NoProfile -File` exits 1 without executing a statement.
    #
    # "Nothing serving" was exit 0 - success - which is the same class of
    # error one step worse: no server at all reported as a healthy one.
    $s = Get-ServerStaleness
    if (-not $s.Running) { Write-Host "no server process is running"; exit 3 }
    $when = $s.Started.ToString("yyyy-MM-dd HH:mm:ss")
    $mod = $s.Modified.ToString("yyyy-MM-dd HH:mm:ss")
    if ($s.Stale) {
        Write-Host ("STALE: pid $($s.Pid) started $when, but $($s.NewestPy) " +
                    "was modified $mod. The running product does not hold it.")
        exit 2
    }
    Write-Host ("current: pid $($s.Pid) started $when, newest Python " +
                "$($s.NewestPy) modified $mod")
    exit 0
}

$before = Get-ServerStaleness

# An audit in flight dies with the process that runs it. Refused unless
# -Force, and the refusal names the runs, so the operator's own scan is never
# ended by a restart nobody told them about (operator, 2026-09-14).
if ($before.Running -and -not $Force) {
    try {
        $sites = Invoke-RestMethod "http://localhost:$Port/api/sites" -TimeoutSec 10
        $busy = @()
        foreach ($site in $sites) {
            $detail = Invoke-RestMethod "http://localhost:$Port/api/sites/$($site.id)" -TimeoutSec 20
            $busy += @($detail.runs | Where-Object { $_.status -in @("pending", "running") } |
                       ForEach-Object { "$($site.domain) run $($_.id.Substring(0, 8)) ($($_.status))" })
        }
        if ($busy.Count -gt 0) {
            throw ("Refusing to restart: an audit is in flight and would die with the server - " +
                   ($busy -join "; ") + ". Wait for it, or re-run with -Force.")
        }
    } catch [System.Net.WebException] {
        Write-Host "could not ask the server what is running ($($_.Exception.Message)); restarting anyway"
    }
}

if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    throw "No task named '$TaskName'. Run scripts\install-service.ps1 first."
}

# The server mounts dashboard/dist with StaticFiles, and this script exists to
# "pick up code changes" - but it never rebuilt, and only dev.ps1 runs
# npm run build. So every dashboard fix reached the operator only if they
# happened to rebuild by hand. Measured once at twelve hours: a bundle dated
# 00:08 serving a fix that landed at 12:41, with nothing on any screen or
# endpoint saying so.
#
# dashboard/dist is gitignored and both packaging scripts are `git archive
# HEAD`, so the archive never contains a build - dist belongs to this machine,
# which is why the check belongs here and not in package.ps1.
$dist = Join-Path $root "dashboard\dist\index.html"
$src  = Join-Path $root "dashboard\src"
# The bundle's sources are not all under dashboard\src. `glossary.tsx` imports
# `../../clauditseo/glossary.json` - the registry item 166 made the single
# source of every legend, disclosure and report appendix - so editing a
# definition changed the bundle's content while leaving every watched file
# untouched. Measured 2026-09-16: four registry entries were added, the script
# reported nothing stale, restarted, and served the old bundle; the screen
# showed the new words only after a hand-run `vite build`. Anything the bundle
# imports from outside src belongs in this list.
$watchedForBundle = @($src, (Join-Path $root "clauditseo\glossary.json")) |
                    Where-Object { Test-Path $_ }
if ($watchedForBundle) {
    $newest = Get-ChildItem -Path $watchedForBundle -Recurse -File |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $built = if (Test-Path $dist) { (Get-Item $dist).LastWriteTime } else { $null }
    if ($null -eq $built -or $built -lt $newest.LastWriteTime) {
        $why = if ($null -eq $built) { "no build exists" }
               else { "the build is older than $($newest.Name)" }
        if ($Rebuild) {
            Write-Host "dashboard: $why - rebuilding"
            Push-Location (Join-Path $root "dashboard")
            try {
                npm run build
                if ($LASTEXITCODE -ne 0) { throw "npm run build failed ($LASTEXITCODE)." }
            } finally { Pop-Location }
        } else {
            # Refusing rather than restarting. Serving a stale bundle is the
            # failure this check exists to stop, and doing it quietly is what
            # made it survive: the operator sees a restart succeed and reads
            # that as their change being live.
            throw ("Refusing to restart: $why, so the server would serve a " +
                   "dashboard that predates the source. Run " +
                   "``npm run build`` in dashboard\, or re-run this with " +
                   "-Rebuild.")
        }
    }
}

if ($before.Running -and $before.Stale) {
    # Said out loud so the OPERATOR_ACTIONS.md row can quote what was stale.
    # DISCIPLINE rule 13 exists because a restart that silently closes a gap
    # also destroys the evidence that the gap was there.
    Write-Host ("was stale: pid $($before.Pid) started " +
                "$($before.Started.ToString('yyyy-MM-dd HH:mm:ss')), " +
                "$($before.NewestPy) modified " +
                "$($before.Modified.ToString('yyyy-MM-dd HH:mm:ss'))")
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
# Stop-ScheduledTask does not always reap the child process. Only the server's
# own processes are stopped - see Get-ServerProcesses.
Get-ServerProcesses | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 2

Start-ScheduledTask -TaskName $TaskName
for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 1
    try {
        $health = (Invoke-WebRequest -UseBasicParsing "http://localhost:$Port/api/health" `
                   -TimeoutSec 3).Content
        Write-Host "restarted: $health"
        exit 0
    } catch { }
}
throw "The task restarted but the server did not respond on port $Port."
