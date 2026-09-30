<#
.SYNOPSIS
  Record that an /audit-fix round is running, and which phase it is in.

.DESCRIPTION
  A round's own liveness was state that existed nowhere outside the session
  running it. `ROUND_START` was held in memory, the tree stays clean for the
  whole audit phase, and no commit lands until after the report - so for
  fifteen to twenty minutes nothing anywhere said a round was underway. A
  second operator session, or a status dashboard, could only conclude that the
  previous round was the current state and recommend starting another.

  Written to `.claude/run/round.json`, which `.gitignore` covers.

  **Gitignored inside the repo rather than outside it.** Ignored files do not
  appear in `git status --porcelain`, so preflight - which refuses to start on
  a dirty tree - cannot see it; that was the binding constraint. Keeping it
  repo-relative also means no absolute machine path is baked into a committed
  skill, which is what putting it beside `_relay\` would have required.

  **The auditor does not read it**, and is told so in `auditor.md` alongside
  `TIMINGS.md` and `NEXT_UP.md`. It carries a start timestamp, and the reason
  the timings exclusion exists applies unchanged: an auditor that can compute
  how long it has been running has been handed a pace to keep.

.PARAMETER Phase
  preflight | auditing | deciding | applying-lever | verifying | committing.
  Setting a new phase stamps `phase_start`, so elapsed time can be compared
  against the right median rather than against the whole round.

.PARAMETER Clear
  Remove the marker. Every exit path runs this - including the ones that stop
  early, because a marker only removed on the happy path becomes a permanent
  "a round is running" that blocks the next one.

.PARAMETER Read
  Print the current marker, or nothing if there is none. Preflight uses this.

.NOTES
  No liveness beacon is written, and no expected duration. A crashed session
  leaves a marker behind, so a reader must decide staleness for itself:
  compare `phase_start` against the matching column in TIMINGS.md. That
  judgement is deliberately left outside the round - `audit-fix` step 0 is
  explicit that the history is printed once and then ignored, and a round that
  computed its own time budget would be holding the pace the skill forbids.
#>
[CmdletBinding()]
param(
    [string]$Phase,
    [int]$Round,
    [string]$Depth,
    [int]$MaxRounds,
    [string]$Start,
    # What kind of work is underway, and which one. A reader needs to know
    # that relay 014 is running, not merely that something is. 'round' is the
    # default so every existing -Round call keeps working unchanged.
    # round | plan | relay | feature each have a skill wrapped around them, and
    # that skill guarantees the clear on every exit path. They HOLD the marker.
    #
    # investigation | backlog | fix are operator-directed work with no skill.
    # Nothing wraps them and nothing guarantees an ending, so they RECORD
    # without holding: a note never blocks anyone and never needs clearing,
    # which is why it is safe without a skill. See NOTE_KINDS below.
    [ValidateSet('round','plan','relay','feature',
                 'investigation','backlog','fix')]
    [string]$Kind = 'round',
    [string]$Subject,
    # Take the marker only if nobody else holds it. Exits 1 on a live foreign
    # marker instead of overwriting. This is the fix for the ordering defect
    # round 028 found: the round wrote at step 0 and read at preflight, so it
    # could never see anyone else's marker. Claiming reads and writes in one
    # call, so two writers cannot both believe they hold it.
    [switch]$Claim,
    # A marker older than this is treated as abandoned rather than live. The
    # alternative is a permanent "F-01 in progress" the first time an action
    # is interrupted, which turns the gate into one nobody can pass.
    [int]$StaleMinutes = 90,
    [switch]$Clear,
    [switch]$Read
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root '.claude\run'
$file = Join-Path $dir 'round.json'

if ($Clear) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Output "round marker cleared"
    } else {
        Write-Output "no round marker to clear"
    }
    exit 0
}

if ($Read) {
    if (Test-Path $file) { Get-Content $file -Raw }
    else { Write-Output "" }
    exit 0
}

if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$now = Get-Date -Format o
$existing = $null
if (Test-Path $file) {
    try { $existing = Get-Content $file -Raw | ConvertFrom-Json } catch { $existing = $null }
}

# Who this call is for, decided before any collision test. -Round is the old
# spelling and still means kind 'round' with the number as its subject.
#
# CQ-64: a kind that was NOT supplied is inherited on a plain update, the same
# discipline `Pick` applies to five other fields and `$mySubject` applies
# immediately below. This was `$myKind = $Kind` unconditionally, and `-Kind`
# has a parameter default of 'round' - so `-Phase working` after a plan had
# claimed the marker preserved the subject, the round, the depth and the start
# and silently relabelled the work a round. `$iAmNote` derives from it, so the
# same call turned a note from `exclusive: false` to `true`: a lock no skill
# is obliged to clear. Observed in `data/server-starts.jsonl` at report 048 -
# `"kind": "round", "subject": "", "round": 0` beside
# `"completed_seconds": {"planning": 239}`, a phase only /backlog-plan sets.
#
# `Pick` cannot do this. Its test is truthiness and `$Kind` is always truthy,
# so it would answer 'round' on every call. Only `$PSBoundParameters` tells a
# supplied kind from a defaulted one.
#
# `-Claim` deliberately does not inherit. A claim may displace a stale marker
# or a note, and wearing the kind of what it replaced would name the wrong
# work - the same defect arriving from the other side.
$myKind =
    if ($PSBoundParameters.ContainsKey('Kind')) { $Kind }
    elseif (-not $Claim -and $existing -and
            $existing.PSObject.Properties['kind'] -and $existing.kind) { $existing.kind }
    else { $Kind }
$mySubject = $Subject
if (-not $mySubject) {
    if ($Round) { $mySubject = "$Round" }
    elseif ($existing -and $existing.PSObject.Properties['subject']) { $mySubject = $existing.subject }
    else { $mySubject = '' }
}

# Kinds with no skill to clear them. They record that directed work was
# underway and deliberately hold nothing: a note cannot block a round, so a
# session that simply moves on cannot leave a lock behind. That is the whole
# reason these are safe to add without a skill wrapped around them.
#
# The distinction they preserve: "no marker" still means exactly one thing -
# nothing was underway - which is what relay 020's restart discriminator
# depends on. Before this, directed work produced an absent marker, so a
# restart during it was indistinguishable from the unattributed anomaly 020
# was built to detect. Two such restarts are already in OPERATOR_ACTIONS.md,
# for F-03 and F-02, attributable only because the rows were written by hand.
$NoteKinds = @('investigation', 'backlog', 'fix')
$iAmNote = $NoteKinds -contains $myKind

if ($Claim) {
    if ($existing) {
        $heldKind = if ($existing.PSObject.Properties['kind']) { $existing.kind } else { 'round' }
        $heldSubject = if ($existing.PSObject.Properties['subject']) { $existing.subject } else { "$($existing.round)" }
        $heldExclusive = if ($existing.PSObject.Properties['exclusive']) { [bool]$existing.exclusive } else { $true }
        $heldLabel = if ($heldSubject) { "$heldKind $heldSubject" } else { $heldKind }
        $mine = ($heldKind -eq $myKind -and $heldSubject -eq $mySubject)
        $age = New-TimeSpan -Start ([datetime]$existing.updated) -End ([datetime]$now)
        # Stale is decided by the clock, not by a rule about who may run: an
        # abandoned marker is not a live action, and refusing forever because
        # a session died is the failure this threshold exists to prevent.
        $fresh = $age.TotalMinutes -lt $StaleMinutes

        if (-not $mine) {
            if (-not $fresh) {
                Write-Output ("stale marker discarded: $heldLabel, " +
                              "last updated $($existing.updated), over $StaleMinutes min old")
                $existing = $null
            }
            elseif ($heldExclusive -and $iAmNote) {
                # A note must never displace a live holder: overwriting a
                # round's marker would destroy the phase accounting it has
                # been banking all round. Its own code, because "a round is
                # running so I did not record" is not "somebody else holds
                # what you wanted" (2) and not "the script did not run" (1).
                Write-Output ("NOT RECORDED: $heldLabel holds the marker and is live " +
                              "(phase '$($existing.phase)', updated $($existing.updated)). " +
                              "A note does not displace a holder; the work is not " +
                              "blocked, only unrecorded.")
                exit 3
            }
            elseif ($heldExclusive) {
                Write-Output ("BUSY: $heldLabel is in phase '$($existing.phase)', " +
                              "updated $($existing.updated) ($([int]$age.TotalMinutes) min ago). " +
                              "Two writers in one tree abort each other.")
                exit 2
            }
            else {
                # A note was never a lock, so anything may replace it - but
                # say what was replaced rather than losing it silently.
                Write-Output "displaced note: $heldLabel"
                $existing = $null
            }
        }
    }
}

function Pick($supplied, $name, $fallback) {
    if ($supplied) { return $supplied }
    if ($existing -and $existing.PSObject.Properties[$name]) { return $existing.$name }
    return $fallback
}

$phaseName = Pick $Phase 'phase' 'unknown'

# What each finished phase cost, carried forward. Without this a phase's
# duration existed only between its start and the next transition, and then
# nothing held it: TIMINGS.md gets the per-phase figures only in the row a
# round writes when it finishes, so a round that died mid-way lost the phases
# it HAD completed. A reader could say "auditing, 1.6 min in phase" and could
# not say what preflight took.
#
# SECONDS, and the field says so. Minutes to one decimal was the first
# attempt and it recorded 0 for every phase shorter than three seconds - a
# zero asserting a phase took no time, which is the exact objection
# TIMINGS.md's own backfill note raises against writing 0.0 where a value was
# never captured. Seconds cannot produce that reading for anything a phase
# realistically takes.
#
# The unit is in the field name because "frame is provenance" is a promoted
# invariant here: a number's unit travels with the value. A reader converts
# with /60 to compare against TIMINGS.md's minutes.
#
# A phase entered twice accumulates rather than overwrites - the honest answer
# to "how long was this round auditing" when it audited, applied a lever, and
# audited again.
$completed = [ordered]@{}
if ($existing -and $existing.PSObject.Properties['completed_seconds'] -and $existing.completed_seconds) {
    foreach ($p in $existing.completed_seconds.PSObject.Properties) {
        $completed[$p.Name] = $p.Value
    }
}

# Stamp phase_start only when the phase actually changes, so an update that
# re-states the same phase does not reset the clock a reader is measuring.
$phaseStart = $now
if ($existing -and $existing.PSObject.Properties['phase'] -and $existing.phase -eq $phaseName) {
    $phaseStart = $existing.phase_start
} elseif ($existing -and $existing.PSObject.Properties['phase'] -and $existing.phase) {
    $prev = $existing.phase
    $secs = [int][math]::Round(
        (New-TimeSpan -Start ([datetime]$existing.phase_start) -End ([datetime]$now)).TotalSeconds)
    if ($completed.Contains($prev)) {
        $completed[$prev] = [int]($completed[$prev] + $secs)
    } else {
        $completed[$prev] = $secs
    }
}

$marker = [ordered]@{
    kind        = $myKind
    subject     = $mySubject
    round       = [int](Pick $Round 'round' 0)
    depth       = Pick $Depth 'depth' 'standard'
    max_rounds  = [int](Pick $MaxRounds 'max_rounds' 0)
    exclusive   = (-not $iAmNote)
    phase       = $phaseName
    round_start = Pick $Start 'round_start' $now
    phase_start = $phaseStart
    completed_seconds = $completed
    updated     = $now
}

$marker | ConvertTo-Json -Depth 5 | Set-Content -Path $file -Encoding utf8
$label = if ($marker.subject) { "$($marker.kind) $($marker.subject)" } else { $marker.kind }
Write-Output "$label - $($marker.phase)"
# Explicit, because callers gate on it. Without this the script leaves
# $LASTEXITCODE at whatever the previous native command set, so a caller
# checking it after a successful -Claim can read a stale 1 and conclude the
# marker was held. Measured while wiring the second caller.
exit 0
