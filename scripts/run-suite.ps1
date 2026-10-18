<#
.SYNOPSIS
  Run the pinned suite verbatim and keep the whole run on disk.

.DESCRIPTION
  CQ-237 / `QUESTIONS.md` Q-36. The pinned suite is intermittently red -
  round 115 measured two reds in three runs of one unchanged tree - and across
  every round that has hit it, the answer to "which assertion fired" has never
  been recoverable. Q-36's own context records why: *"the runner's output was
  truncated before the assertion text and neither later run reproduced that
  node."* Rounds run the suite through a tool call, the failure section is cut
  off above the assertion, and the run is gone.

  This wrapper is the capture. It runs the profile's `suite_command` and tees
  the whole thing - stdout and stderr, merged at the OS level so nothing is
  reordered or dropped - to a timestamped file, then prints the path.

  It is a precondition of Q-36, not an answer to it. All five of Q-36's
  options need to know which assertion fires; none of them is "capture the
  output". Nothing here rearranges a clause, changes a flag, or decides who
  absorbs an intermittent.

  **It does not restate the command.** The flags are read out of
  `.claude/loop/PROFILE.md` at run time. A fourth hard-coded copy beside
  `ci.yml`, `PROFILE.md` and the three instruction files is precisely the
  drift `tests/test_loop_instructions.py::test_the_pinned_suite_command_is_stated_once`
  exists to refuse - and a wrapper running flags of its own would make every
  baseline taken through it worthless, which is rule 11's shape.

.PARAMETER ProfilePath
  The loop profile to read `suite_command:` from. Defaults to this repo's.
  Overridable so the guard can drive the wrapper against a deliberately red
  run without waiting five minutes for the real suite.

.PARAMETER LogDir
  Where the captured run is written. Defaults to `.claude/run/`, which
  `.gitignore` covers - so a capture cannot dirty the tree the next round's
  preflight is about to check.

.NOTES
  Exits with the suite's own status, so a caller can still tell red from
  green without parsing anything.
#>
[CmdletBinding()]
param(
  [string]$ProfilePath,
  [string]$LogDir
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not $ProfilePath) {
  $ProfilePath = Join-Path $repoRoot '.claude\loop\PROFILE.md'
}
if (-not $LogDir) {
  $LogDir = Join-Path $repoRoot '.claude\run'
}

if (-not (Test-Path $ProfilePath)) {
  Write-Error "no loop profile at $ProfilePath - nothing states the pinned command"
  exit 2
}

# The one `suite_command:` line, taken as written. Everything after the key is
# the command, including any trailing comment-looking text: the profile states
# it on one line and `test_the_pinned_suite_command_is_stated_once` checks that
# line against the gate, so trimming it here would be this wrapper inventing a
# reading of its own.
$line = Select-String -Path $ProfilePath -Pattern '^\s*suite_command:\s*(.+?)\s*$' |
        Select-Object -First 1
if (-not $line) {
  Write-Error "no `suite_command:` in $ProfilePath"
  exit 2
}
$command = $line.Matches[0].Groups[1].Value

if (-not (Test-Path $LogDir)) {
  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $LogDir "suite-$stamp.log"
$logPath = (New-Item -ItemType File -Path $logPath -Force).FullName

Write-Host "suite: $command"
Write-Host "log:   $logPath"

# Through `cmd /c` with an OS-level merge rather than PowerShell's `2>&1`.
# In Windows PowerShell 5.1 redirecting a native command's stderr wraps every
# line in an ErrorRecord and sets `$?` false even on exit 0 - which would turn
# the runner's own diagnostics into noise and lose the exit status this script
# exists to pass through faithfully.
#
# Written through a StreamWriter rather than `Tee-Object`, and the reason is
# measured rather than stylistic: `Tee-Object` in Windows PowerShell 5.1 has no
# `-Encoding` and writes UTF-16LE. The guard's first run against this wrapper
# captured the failing assertion correctly and still went red, because every
# character in the log was interleaved with a null byte and no tool reading it
# as UTF-8 could find the text. A capture nothing can read is the finding, not
# the fix. UTF8Encoding($false) - no BOM, for the same reason.
$writer = New-Object System.IO.StreamWriter(
  $logPath, $false, (New-Object System.Text.UTF8Encoding($false)))
try {
  & cmd.exe /c "$command 2>&1" | ForEach-Object {
    Write-Host $_
    $writer.WriteLine([string]$_)
  }
  $code = $LASTEXITCODE
} finally {
  $writer.Dispose()
}

Write-Host "log:   $logPath"
Write-Host "exit:  $code"
exit $code
