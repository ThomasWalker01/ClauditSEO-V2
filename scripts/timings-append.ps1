# Append one row to a named table inside TIMINGS.md.
#
# The problem this script exists to end.
#
# Every loop skill's step reads "Append one row to the `## Other work` table".
# The model reads that as "append to a file" and appends past the end. Whatever
# the last section of TIMINGS.md happens to be catches the row instead — it was
# `## Verification crawls` and its 7-cell header when this was written, and is
# `## Golden accuracy runs` and its 8-cell header since relay 087 — and a
# 6-cell plan row landing under either takes
# `test_every_table_row_matches_its_header_width[TIMINGS.md]` red at HEAD.
# Naming the section here rather than the count, because the count moves.
# Recurred twice already:
#   b90f568 → 8537598 (first repair)
#   bdb3390 → 04359e9 (second repair)
#
# This script takes -Section and -Row, finds the table under `## <Section>` by
# its delimiter row, walks to that table's last body row, and inserts the new
# row after it. Free-hand appending against the file's end is what fails; a
# scripted append against a table's end cannot.
#
# Two hard refusals, both to fail loud rather than to smuggle a bad row in:
#   1. The section heading must exist and have a delimited table under it.
#   2. The row's cell count must match the table's header width. `_cells` is
#      the same GFM rule the width guard uses (an escaped `\|` is one char,
#      not a boundary), so the numbers here agree with the ones the test would
#      report post-hoc.
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Section,
  [Parameter(Mandatory)][string]$Row,
  [string]$Path = 'TIMINGS.md'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Path)) {
  Write-Error "TIMINGS append: $Path not found"; exit 2
}

# The rounds table lives under a prose heading. Skills refer to it as `Rounds`
# both here and in commit messages; the actual heading text is verbose, so an
# alias saves the caller from copy-pasting it. `Other work` and `Verification
# crawls` are their own headings and pass through.
if ($Section -eq 'Rounds') { $Section = 'The two lever columns, and why there are two' }

# GFM cell count. `\|` is one character inside a cell, not a boundary — the
# same rule tests/test_loop_instructions.py enforces so the two agree.
function Get-CellCount([string]$line) {
  $trim = $line.TrimEnd()
  # replace escaped pipes with a placeholder, count remaining `|`, subtract 1
  # (leading and trailing pipes give N+1 delimiters for N cells).
  $stripped = $trim -replace '\\\|', 'X'
  return ($stripped.ToCharArray() | Where-Object { $_ -eq '|' }).Count - 1
}

$lines = [IO.File]::ReadAllLines($Path)
$headingRe = "^\s*##\s+$([regex]::Escape($Section))\s*$"

$secStart = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
  if ($lines[$i] -match $headingRe) { $secStart = $i; break }
}
if ($secStart -lt 0) {
  Write-Error "TIMINGS append: no section '## $Section' in $Path"; exit 3
}

# Section ends at the next `## ` heading, or EOF.
$secEnd = $lines.Count
for ($i = $secStart + 1; $i -lt $lines.Count; $i++) {
  if ($lines[$i] -match '^\s*##\s') { $secEnd = $i; break }
}

# Find the first delimiter row (--- --- ---) inside the section — its width
# is authoritative for every row of this table.
$delimIdx = -1; $width = 0
for ($i = $secStart + 1; $i -lt $secEnd; $i++) {
  if ($lines[$i] -match '^\s*\|\s*-{3,}' -and $i -gt 0 -and $lines[$i-1] -match '\|') {
    $delimIdx = $i
    $width = Get-CellCount $lines[$i]
    break
  }
}
if ($delimIdx -lt 0) {
  Write-Error "TIMINGS append: no table under '## $Section' (no --- row found)"; exit 4
}

$rowCells = Get-CellCount $Row
if ($rowCells -ne $width) {
  Write-Error ("TIMINGS append: row has $rowCells cells, `## $Section` table needs $width " +
               "(header at line $($delimIdx))")
  exit 5
}

# Walk from the delimiter forward, tracking the LAST contiguous body row of
# this specific table. A blank line ends a table per GFM; a heading ends the
# section. `_ENDS_A_TABLE` in the width guard uses the same rule.
$lastBody = $delimIdx
for ($i = $delimIdx + 1; $i -lt $secEnd; $i++) {
  $ln = $lines[$i]
  if ($ln -match '^\s*(#|```|~~~|$)') { break }
  if ($ln.TrimStart().StartsWith('|')) { $lastBody = $i } else { break }
}

# Insert the new row immediately after the last body row.
$before = @(); $after = @()
if ($lastBody -ge 0) { $before = $lines[0..$lastBody] }
if ($lastBody + 1 -lt $lines.Count) { $after = $lines[($lastBody + 1)..($lines.Count - 1)] }
$new = @($before) + @($Row) + @($after)

# Preserve the file's original line terminator. TIMINGS.md is CRLF on Windows.
$raw = [IO.File]::ReadAllText($Path)
$eol = if ($raw -match "`r`n") { "`r`n" } else { "`n" }
$trailing = if ($raw.EndsWith($eol)) { $eol } else { '' }
[IO.File]::WriteAllText($Path, ($new -join $eol) + $trailing)

Write-Host ("TIMINGS append: inserted at line $($lastBody + 2) " +
            "under '## $Section' ($width-col)")
