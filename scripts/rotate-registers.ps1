#requires -Version 5.1
<#
.SYNOPSIS
  Rotate the aged tail of the pure-log receipt registers into a write-once
  archive - B-24, first tranche.

.DESCRIPTION
  The append-only registers grow without bound for every reader: the console's
  ingester, `git diff`, a human, and every loop session that opens one.
  Measured at relay 089 on this repo: `TIMINGS.md` 207,182 bytes,
  `OPERATOR_ACTIONS.md` 130,765 - and all of it re-read forever. Relay 089
  bounded what the AUDITOR reads; this script is the file-side complement the
  item split out as B-24: the aged tail moves to a fixed archive file, the
  live register keeps a recent window, and nothing is lost - git holds the
  whole history, so the archive is cold storage rather than the system of
  record.

  The policy, with its numbers stated as B-24 requires:

    OPERATOR_ACTIONS.md   whole table    rotate past the newest 40 rows
    TIMINGS.md            ## Other work  rotate past the newest 20 rows

  Either rotates only once the live file exceeds 64,000 bytes. Rows move
  verbatim, oldest first, appended to `<NAME>-archive.md` under the same
  table header, so every moved row keeps its cell width and its order.

  What is deliberately NOT rotated, so the next reader does not "fix" it:

    * The Rounds table of `TIMINGS.md` - the console's ingester
      (`codedash/ingest/timings.py`) parses it in full, and it is small.
    * `QUESTIONS.md` - it holds open rows the loop still acts on; rotating
      it needs an open-row predicate, which is B-24's remaining half.
    * `KNOWN_ISSUES.md` - a live register, not a log; its lever is the
      open-rows read bound that landed with kit 1.11.0.

  NOTHING CALLS THIS. It was wired into `/audit-fix` preflight as step 1b at
  round 114 and unwired at relay 115, when the operator answered `QUESTIONS.md`
  Q-33 with *drop it*. Run it by hand or not at all; do not re-wire it into a
  round without re-opening that question.

  The reason, so the next reader does not read the absence as an oversight.
  Two separate things killed it, and only the second is about this script.
  (1) The premise. Rotation was queued to bound the audit-phase read cost, and
  the measurement refutes the link: registers grew 12x (37 KB -> 451 KB,
  2026-08-17 -> 08-30) while `audit_min` grew 1.7x, and on 08-29 -> 08-30 they
  grew 1.5% while mean `audit_min` FELL 36%, to a three-week low, at the
  largest register size ever. What tracks the cost is the re-verification load
  (findings carried per report 124 -> 208, +68%, against `audit_min` +70%).
  (2) The guard. This script refuses both registers it targets, every time it
  runs, and the count only grows: 435 citations into `OPERATOR_ACTIONS.md` at
  round 114, 443 at relay 115, 414 of them in `audits/**` that no round may
  repair. That refusal is correct - it is what stops a silent 400x
  misaddressing - but a preflight step that can only refuse is a cost every
  round pays for nothing, which is what report 114 raised as WF-106.

  Idempotent: a file under threshold, or whose table is already within its
  window, is left byte-identical.

.PARAMETER RepoRoot
  The repo whose registers to rotate. Defaults to the working directory.
.PARAMETER DryRun
  Print the plan; write nothing.
#>
[CmdletBinding()]
param(
  [string]$RepoRoot = '.',
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

$ThresholdBytes = 64000
$Utf8 = New-Object System.Text.UTF8Encoding($false)

# `Sections` is tried in order, and the empty string means "the first table in
# the file". Two repos shaped the list: CodeDash's OPERATOR_ACTIONS.md opens
# straight onto its table, while ClauditSEO's carries four prose sections first
# and keeps the log under `## Actions`. Naming the section is what makes the
# choice deliberate in both instead of "whichever table came first".
#
# `RequiredColumn` is the refusal. A rotation that guesses wrong does not fail
# loudly - it silently moves rows out of the wrong table, in a register whose
# whole contract is that it is append-only. So the header of the table this
# finds must contain the named column, or the file is left alone.
$Policies = @(
  @{ File = 'OPERATOR_ACTIONS.md'; Sections = @('Actions', ''); Keep = 40
     RequiredColumn = 'when'
     Archive = 'OPERATOR_ACTIONS-archive.md'; Title = 'Operator actions' }
  @{ File = 'TIMINGS.md';          Sections = @('Other work'); Keep = 20
     RequiredColumn = 'kind'
     Archive = 'TIMINGS-archive.md';          Title = 'Round timings' }
)

# Find the table to rotate: the first GFM delimiter row after $Section's
# heading (or after line 0 when $Section is ''), its header on the line
# above, its body every `|`-led line below. Returns $null when absent -
# a register that has not grown a table yet is not an error.
function Find-Table {
  param([string[]]$Lines, [string]$Section)
  $start = 0
  if ($Section) {
    $headingRe = "^\s*##\s+$([regex]::Escape($Section))\s*$"
    $start = -1
    for ($i = 0; $i -lt $Lines.Count; $i++) {
      if ($Lines[$i] -match $headingRe) { $start = $i + 1; break }
    }
    if ($start -lt 0) { return $null }
  }
  $delim = -1
  for ($i = $start; $i -lt $Lines.Count; $i++) {
    if ($Lines[$i] -match '^\s*\|(\s*:?-{3,}:?\s*\|)+\s*$') { $delim = $i; break }
  }
  if ($delim -lt 1) { return $null }
  $end = $delim
  for ($i = $delim + 1; $i -lt $Lines.Count; $i++) {
    if ($Lines[$i] -match '^\s*\|') { $end = $i } else { break }
  }
  @{ Header = $delim - 1; Delim = $delim; BodyStart = $delim + 1; BodyEnd = $end }
}

# The refusal that matters most, and the one this script shipped without.
#
# An append-only register has STABLE LINE NUMBERS: rows are only ever added at
# the end, so `OPERATOR_ACTIONS.md:138` still names the same row a month later.
# The loop relies on that - reports, KNOWN_ISSUES rows, QUESTIONS rows and
# CHANGELOG entries all cite actions by line. Rotation removes rows from the
# HEAD of the table, so every one of those citations shifts by the number of
# rows moved, and nothing anywhere reports it: the citing text still parses,
# the cited file still exists, and the line it now names is a different action
# or past the end of the file.
#
# Measured when this was found, on the two repos the script had already been
# run against: ClauditSEO carried 433 such citations and CodeDash 19. On
# ClauditSEO, `OPERATOR_ACTIONS.md:138` named a real 2026-08-21 restart row
# before rotation and an empty line after it. Both rotations were reverted.
#
# So: count the citations first, and rotate nothing while any exist. The fix
# that lifts this is a line-preserving rotation - leave a one-line stub in
# place of each moved row, carrying the pointer to the archive - which is
# ClauditSEO's relay item 040 option B and is not built yet.
function Get-LineCitations {
  param([string]$RepoRoot, [string]$FileName)
  # Not a work tree - nothing is tracked, so nothing cites anything. Checked
  # before git is invoked at all: outside a repo `git grep` writes "not a git
  # repository" to stderr, and a guard whose refusal path is indistinguishable
  # from its own error message is not a guard.
  if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) { return @() }
  $name = [regex]::Escape($FileName)
  # Tracked files only: an untracked scratch file citing a line is not the
  # loop's evidence and must not block a rotation. stderr is folded in and
  # then filtered by shape, so a git that fails for any other reason
  # contributes no false citations and no crash.
  $out = & git -C $RepoRoot grep -ohE "$name`:[0-9]+" 2>&1
  @($out | ForEach-Object { "$_" } | Where-Object { $_ -match "^$name`:[0-9]+$" })
}

# The first section that yields a table whose header carries $RequiredColumn.
# Returns $null when no section does, which is the refusal described above.
function Resolve-Table {
  param([string[]]$Lines, [hashtable]$Policy)
  foreach ($section in $Policy.Sections) {
    $t = Find-Table -Lines $Lines -Section $section
    if ($null -eq $t) { continue }
    $cols = ($Lines[$t.Header] -split '\|') | ForEach-Object { $_.Trim().ToLower() }
    if ($cols -contains $Policy.RequiredColumn.ToLower()) {
      $t.Section = $section
      return $t
    }
  }
  return $null
}

function New-ArchiveHeader {
  param([hashtable]$Policy, [string]$Section, [string]$HeaderRow, [string]$DelimRow)
  $lines = @(
    "# $($Policy.Title) - archive"
    ''
    "Cold storage for ``$($Policy.File)``, written by ``scripts\rotate-registers.ps1``"
    '(B-24). Rows land here verbatim, oldest first, when the live register'
    'crosses the rotation threshold, and are never edited after that. The live'
    'file keeps the recent window its bounded readers need; git holds the whole'
    'history regardless - this file exists so no reader has to carry the tail.'
    ''
  )
  if ($Section) { $lines += @("## $Section", '') }
  $lines + @($HeaderRow, $DelimRow)
}

foreach ($p in $Policies) {
  $path = Join-Path $RepoRoot $p.File
  if (-not (Test-Path -LiteralPath $path)) {
    Write-Host "$($p.File): absent, nothing to rotate"
    continue
  }
  $cites = Get-LineCitations -RepoRoot $RepoRoot -FileName $p.File
  if ($cites.Count -gt 0) {
    Write-Host ("{0}: REFUSED - {1} line-number citation(s) point into it ({2} ...). Rotating would shift every one of them silently. See the header of this script; a line-preserving rotation is what lifts this." -f `
                $p.File, $cites.Count, (($cites | Select-Object -First 3) -join ', '))
    continue
  }
  $size = (Get-Item -LiteralPath $path).Length
  if ($size -le $ThresholdBytes) {
    Write-Host "$($p.File): $size bytes, under the $ThresholdBytes threshold"
    continue
  }
  $lines = [IO.File]::ReadAllLines($path)
  $t = Resolve-Table -Lines $lines -Policy $p
  if ($null -eq $t) {
    Write-Host ("{0}: no table under [{1}] carrying a '{2}' column - left alone" -f `
                $p.File, ($p.Sections -join ', '), $p.RequiredColumn)
    continue
  }
  $bodyCount = $t.BodyEnd - $t.BodyStart + 1
  $moveCount = $bodyCount - $p.Keep
  if ($moveCount -le 0) {
    Write-Host "$($p.File): $bodyCount rows already within the $($p.Keep)-row window"
    continue
  }
  $moved = $lines[$t.BodyStart..($t.BodyStart + $moveCount - 1)]
  $kept = @($lines[0..($t.BodyStart - 1)]) + @($lines[($t.BodyStart + $moveCount)..($lines.Count - 1)])

  $archivePath = Join-Path $RepoRoot $p.Archive
  if ($DryRun) {
    Write-Host ("DRYRUN {0}: would rotate {1} of {2} rows to {3}" -f $p.File, $moveCount, $bodyCount, $p.Archive)
    continue
  }
  if (Test-Path -LiteralPath $archivePath) {
    $archive = @([IO.File]::ReadAllLines($archivePath)) + @($moved)
  } else {
    $archive = @(New-ArchiveHeader -Policy $p -Section $t.Section -HeaderRow $lines[$t.Header] -DelimRow $lines[$t.Delim]) + @($moved)
  }
  # WriteAllLines ends every line, the last included, with CRLF on Windows -
  # the same shape the checkout already has under `* text=auto eol=lf`.
  [IO.File]::WriteAllLines($archivePath, [string[]]$archive, $Utf8)
  [IO.File]::WriteAllLines($path, [string[]]$kept, $Utf8)
  $newSize = (Get-Item -LiteralPath $path).Length
  Write-Host ("{0}: rotated {1} rows, {2} -> {3} bytes (archive {4})" -f $p.File, $moveCount, $size, $newSize, $p.Archive)
}
exit 0
