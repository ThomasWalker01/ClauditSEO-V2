---
name: backlog-plan
description: Read BACKLOG.md, the newest audit report and the promoted invariants,
  then propose an order of work — clustered by location, cross-referenced against
  open findings, with guards sequenced before the screens they protect.
argument-hint: "[a cluster or file to plan in detail] [--auto N]"
disable-model-invocation: true
---

Propose an order of work across the operator's backlog and the auditor's findings.

$ARGUMENTS

**Planning changes nothing: no code, no files, no commits — until the operator
says `go` or the invocation carries `--auto`.** The sections after Output govern
what happens then.

## Before reading anything — claim the marker and start the clock

```powershell
$start = Get-Date -Format o
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Claim -Kind plan -Phase planning -Start $start
```

A plan runs for tens of minutes and left no trace of having cost anything, so
the operator could account for roughly a quarter of a week's spend. `-Claim`
reads and writes in one call and **exits 2 if an `/audit-fix` round, a relay
item or another plan holds the marker** — two writers in one tree abort each
other. If it prints `BUSY`, stop and say what holds it; do not clear a marker
you did not write. A marker over 90 minutes old is treated as abandoned and
discarded, so a dead session does not block planning forever.

Set `-Phase working` when a `--auto` run starts changing files, so a reader can
tell a plan being written from a cluster being worked.

**`-Kind plan` beside it is no longer required, and the reason is worth
keeping.** This paragraph used to insist on it: `round-marker.ps1` assigned
`$myKind = $Kind` unconditionally against a `round` parameter default, so a
bare `-Phase working` reclassified a live plan as a round and, through
`$iAmNote`, could turn a note into an exclusive lock. Three consecutive plans
caught it by hand and the workaround they used became the instruction — which
left the defect standing behind a habit. Round 089 closed it as CQ-64: a kind
that was not supplied is now inherited from the marker on disk, exactly as the
subject always was, and `tests/test_a_phase_update_keeps_the_kind_it_found.py`
holds it. Passing `-Kind plan` is still correct and still wins; it is simply
not load-bearing any more.

## Read first

1. `BACKLOG.md` — every Open entry, and the **Rules promoted to invariants**.
2. The highest-numbered report in `audits/` — Phase 1 findings and Phase 2
   remediation, including its severities and its own sequencing notes.
3. `.claude/agents/auditor.md`, PROJECT CONTEXT — the design invariants, so a
   cluster can be named by the rule it violates rather than by its symptoms.
4. `KNOWN_ISSUES.md` — so a plan does not propose work that depends on a runtime
   fact still recorded as open.
5. `FEATURES.md` — every entry not marked **BUILT**. The one skill whose job is
   to see everything at once was blind to a fifth queue, so four entries that
   needed one shared mechanism would have been worked as four unrelated pieces,
   each rebuilding the same plumbing.
6. `audits/DISPOSITIONS.md` — what has already been **decided** about findings
   old enough to have earned a decision. Two jobs, pulling opposite ways.
   *Subtractive:* a finding with a row here is not open, so re-planning it as
   untouched work spends a cluster on a question already answered — read it
   before clustering, not after. *Additive:* an obligation this register is
   **overdue** on is a cluster candidate in its own right, ranked like any
   other, because the ten-round rule requires an outcome recorded here before
   a round selects any lever, and a gate that has stopped firing is not a gate.
   Report 044's WF-43 is what that costs: four consecutive rounds carried the
   obligation and skipped it, and the one skill positioned to see a register
   going stale was the one skill that never opened it.

Six sources, and they are not six of the same kind — say which you are holding
before you correlate them.

**Four are queues, produced independently.** The auditor finds where the product
contradicts itself (`audits/`), the operator finds where it is correct but
unhelpful (`BACKLOG.md`) and where it cannot do the thing at all
(`FEATURES.md`), and `KNOWN_ISSUES.md` holds what neither can derive from
source. **`auditor.md` is not a queue** but the rule set the other four are
judged against. **`DISPOSITIONS.md` is not a queue either**: it records what was
already settled about entries in the first one. Your job is to correlate them,
not to add to them.

## Every register the loop keeps, and whether this skill reads it

Twice a register has been added to the system and not to the list above —
`FEATURES.md` at `12f93e9`, `DISPOSITIONS.md` here — and both times the omission
was found by an auditor rather than by anyone maintaining the planner. This
table exists so the third one is caught when it is added. **A register added to
the loop is a row added here**, with the answer argued either way; a register
absent from this table is the defect repeating.

| Register | What it holds | Read? | Why, or why not |
| --- | --- | --- | --- |
| `BACKLOG.md` | where the product is correct but unhelpful | **yes** — source 1 | half the correlation, and the source of the promoted invariants |
| `audits/NNN-*.md` | where the product contradicts itself | **yes** — source 2, newest only | older reports are superseded records and a round may not edit one; the newest carries the live findings |
| `audits/DISPOSITIONS.md` | outcomes decided for aged findings | **yes** — source 6 | tells you what not to re-plan, and whether the gate itself is overdue |
| `KNOWN_ISSUES.md` | runtime facts not derivable from source | **yes** — source 4 | a plan must not rest on a runtime premise still recorded as open |
| `FEATURES.md` | capability the product has never had | **yes** — source 5 | its own section: no severity, so it cannot be ranked against a High |
| `.claude/agents/auditor.md` | the design invariants | **yes** — source 3 | lets a cluster be named by the rule it breaks rather than by its symptoms |
| `.claude/DISCIPLINE.md` | the rules binding the work | **yes**, twice | under *Evidence, not structure* before planning, and again before working a cluster — read, never recalled |
| `QUESTIONS.md` | the operator decisions the loop is waiting on | **yes** | an `open` row gates whatever its `gates:` names, so a cluster resting on one cannot be planned; an `answered` row is not a question but work, and is the cheapest work in the queue because the deciding is already done |
| `OPERATOR_ACTIONS.md` | changes to the running product made outside a commit | **no**, by decision | it holds no work, only why a runtime fact moved without a commit. Read it the moment a cluster's premise rests on a runtime observation, and say that you did: a finding retired by a restart is a premise that has already moved once |
| `data/server-starts.jsonl` | every start of the served process, written by the product itself | **no**, and never directly | it is the completeness check *on the row above*, not a source of work. Where a cluster's premise rests on `OPERATOR_ACTIONS.md`, run `scripts/check_restarts.py --since <commit>`: a start with no row there means the register you are about to trust is short by one restart. WF-47, first raised report 046 — for eighty-four reports the product wrote this file and nothing read it |
| `TIMINGS.md` | wall clock per round and per directed item | **no**, by decision | it answers "is the loop getting slower", which is the operator's question between rounds. Ranking clusters by it would rank by what work costs rather than by what it closes. This skill **writes** one row and does not read the column back |
| `NEXT_UP.md` | the single next command | **no**, and it must not | this skill writes that file. Planning from its own last output is how a plan walks a list instead of re-deriving one — the batch-mode failure `--auto` already refuses |
| `CHANGELOG.md` | what shipped, for a reader outside the loop | **no** | it records what closed, and a closure is already visible as the entry's absence from the queue it left |
| `.claude/run/round.json` | who currently holds the tree | **yes**, only via `-Claim` | a marker is checked and taken in one call at the top of this file; parsing it by hand is the ordering defect round 028 found |
| `_relay/{inbox,outbox,done}` | the operator's directed items | **no**, and deliberately | outside the repo, one instruction at a time rather than a queue to sequence, and `/relay` gates it so it is not worked unattended. A relay item that ought to be planned is one the operator restates in `BACKLOG.md` |

`tests/test_loop_instructions.py` keeps a `REGISTER_FILES` tuple, and it is not
this list — that one selects files whose **tables** are shape-checked, so it
omits registers that carry no table and includes ones this skill does not read.
Neither list is derived from the other; do not treat agreement between them as
guaranteed.

## How to cluster

Group by **where the work lands**, not by severity or by entry order. A cluster is
a file, a screen, or a shared component that several entries route through.

For each cluster report:

- the entries it closes, backlog and audit IDs together
- the file or component
- whether the entries share one root cause or merely one location — these need
  different fixes, and saying "same file" when it is really "same bug in two
  places" hides the one-owner opportunity
- the invariant it violates, if any

**A cluster spanning two screens with one root is the strongest item on the list**,
because one shared component closes both and the second location is the evidence
that it is a rule rather than a preference. Say so when you find one.

## Clustering features, which is not the same job

`FEATURES.md` entries are **absent capability, not present behaviour**, so they
carry no severity and cannot be ranked against a High. They get their own
section, labelled so nobody mistakes one for a lever: `/audit-fix` never
selects from that file, and DISCIPLINE rule 1 does not apply to any of them —
a feature gets an ordinary test asserting new behaviour, red until built, not a
guard proven to fail first.

**Cluster on shared mechanism, never on shared screen.** Two features touching
one panel but needing different plumbing are two pieces of work that will
collide in a single commit; four needing the same plumbing are one piece plus
four thin call sites. **State the mechanism each cluster shares**, in a
sentence, so the claim can be argued with rather than merely asserted.

The rule has been tested once, and it earned its wording. F-02 and F-03 were
grouped from their titles as "act on the thing in front of me, scoped". Built,
that held exactly: F-03 added a `scope` parameter to `advise_url` and F-02's
per-finding path reused it, so the second was call sites rather than plumbing.
F-05 and F-06 read as the same idea and are not — F-05 needs a probe executor
and somewhere to record its answer, F-06 needs a narrower engine unit that
`anatomy.py:213` says cannot currently be asked for. Same sentence, three
mechanisms. Grouping those by their intent would have produced one cluster that
was really three, which is the failure this rule exists to prevent.

**Sequence within a cluster so attribution survives.** The shared mechanism is
its own change with its own tests; each call site is a commit after it. Four
features in one commit throws away the ability to say which one broke
something — the same reason `/audit-fix` takes one lever per round.

## Sequencing rules

Order the clusters, and state the reason for each position.

1. **Guards before the screens they protect.** If a cluster's file sits outside a
   test that would catch regressions there — a route missing from the rendered
   accessibility sweep, a template outside a parametrised matrix, a module absent
   from an enumerating test — that guard is its own first item. Working the
   densest screen in the product with no net is how a fix ships a regression.
2. **Shared components before their call sites**, so the call sites inherit one
   answer instead of each deciding.
3. **Small independent items early** where they close both a backlog entry and an
   open finding — the cheapest evidence that the queues agree.
4. **Anything gated on an unanswered question, last**, and name the question.
   Read `QUESTIONS.md` at the repo root (and the newest audit's OPEN QUESTIONS):
   a cluster whose fix depends on an `open` row is not ready to start, and says
   which row. An `answered` row is the opposite — it is the most ready work in
   the repo, because the operator has just unblocked it: rank what it gates
   first, carry the answer into the cluster as a settled fact, and have the
   cluster set the row to `acted` with its commit.

## Evidence, not structure

Read `.claude/DISCIPLINE.md` before planning — rules 4 and 5 govern every
coverage claim this plan makes. In short: a claim that something is guarded must
come from what the guard reports when it runs, never from its configuration, and
never inherited from a previous plan. Unverified coverage is treated as
unguarded, and a harness that cannot report its own coverage is itself a
finding, ranked above the work it protects.

## Also report

- **Entries that are not what they appear — and route them.** A backlog entry
  describing a defect belongs in the auditor's queue; one describing a capability
  that exists but is unlabelled is discoverability, not a missing affordance, and
  takes a different fix. Naming these is not enough: say which queue each belongs
  in and **draft the entry**, ready to paste. An observation reported as
  "currently in no queue" and left there is an observation you have just lost.
  Anything visible only against real data — a stored row, a live run — goes to
  `KNOWN_ISSUES.md` with the observed values as its evidence, so the next audit
  verifies it at source.
- **Themes that have reached three** across the whole file, not only among recent
  entries, and propose the rule in the form it would take as an invariant.

  Then **recommend**, and give the reason. The test is whether the auditor could
  find violations of it by reading source: a rule stated as what the code must do
  ("an unbounded list must be bounded by a filter or pagination") is checkable; a
  rule stated as how the product should feel ("views should stay usable at real
  scale") is not, and will produce noise rather than findings. Where a theme is
  real but phrased unenforceably, say so and offer the enforceable rewording.

  Recommending is not promoting. Still wait for a yes — a rule promoted from
  three instances that only look alike gives the auditor a false invariant, and a
  wrong invariant is worse than none.
- **Stale notes.** An entry whose reasoning cites evidence that no longer holds —
  a count that has since been reset, a file that has since been split — should be
  flagged for correction, not quietly relied on.
- **What you are deliberately leaving out**, and why. A plan that silently drops
  entries reads as complete when it is not.

## Output

A short ordered list of clusters, each with: what it closes, where it lands, why
it sits at that position, and the first concrete step. No essay. The operator
should be able to start the top item without asking a follow-up question.

**Two lists, side by side — not one ranking with features interleaved.**
Defect clusters are ordered by the rules above. Feature clusters are ordered
among themselves, under their own heading, and the trade between them is left
explicit rather than resolved.

Decided this way because the alternative makes the operator's decision for
them and hides that it was made. A feature has no severity, so interleaving it
with Highs means inventing a rank and presenting it as derived — this file
already refuses that everywhere else, and the choice between hardening the
machine and shipping capability is exactly the judgement the operator keeps.
Say what the trade is in one sentence: what the top feature cluster would cost
and what the top defect cluster would close. Then stop, and let them pick.

End with **NEXT ACTION**: the complete instruction for the top cluster's first
step, written so it can be worked immediately.

It must advance the work, not inspect it. `sed -n '50,75p' some_file.py` is not a
next action — it is a request to look at something, and it leaves the operator to
compose the real instruction themselves, which is the job this command exists to
do. Reading is part of doing the step, so put it inside the instruction.

The instruction states: **the premise it rests on and how that premise was
verified**, what to change, what to write the test for first, what observable
signal confirms it worked, and what to leave alone. An unstated premise is the
one that turns out to be false during the work — naming it is what lets it be
challenged before an hour is spent on it. If anything must
be decided before it can start, that decision **is** the next action — state the
options and what each costs, rather than an instruction that will stall.

## `--auto N` — work a bounded run

**`--auto` never takes a feature cluster.** It plans them and stops there.

This is not caution, it is the skill's own stop conditions applied honestly.
`--auto` must stop at "a **guard that was never observed to fail** before it
was implemented" and at "the **observable signal** named in the NEXT ACTION was
not checked". A feature has neither by definition — `FEATURES.md` says outright
that DISCIPLINE rule 1 does not apply, because the behaviour does not exist and
a guard for it would assert something the code has never attempted. So every
feature would trip a stop condition on arrival, and an `--auto` run that took
one would have to soften the very rule that makes unattended work safe. A
planner that quietly relaxed its own stop condition to keep going is worse than
one that stops.

If the top item is a feature cluster, `--auto` reports it as the next action
and ends the run. That is a completed run, not a shortfall.

If the invocation carries `--auto N`, work up to **N** clusters without asking
between them, then stop and report. Everything else in this file still applies:
the plan is produced first, the NEXT ACTION is worked exactly as written, and the
discipline below is not relaxed because nobody is watching.

**Re-plan between every cluster.** Do not walk the list you printed at the start.
Re-read `BACKLOG.md`, the newest audit and the invariants, and re-cluster, because
finishing one cluster changes the others — a fix can reveal a working
implementation that makes a later cluster trivial, or invalidate the premise a
later cluster rested on. A run that follows its opening list is batch mode, and
batch mode is what produced two consecutive audit rounds with identical counts.

**Stop immediately — before starting another cluster — at the first of:**

- a cluster that is **gated** on an unanswered question;
- a **corrected premise that changes what the cluster is** — see below;
- a **red suite**, or a suite that produced no result at all;
- a **guard that was never observed to fail** before it was implemented;
- the **observable signal** named in the NEXT ACTION was not checked, or was
  checked and did not appear;
- anything that needs a decision only the operator can make.

**Not every correction is a stop.** The test is whether it changes *what the
cluster is* or only *how the step is done*.

Stop when the cluster itself was wrong: the entries it claimed to close are not
closable that way, the blocker is somewhere else entirely, the work belongs to a
different file. That is a corrected plan, and it is worth more than a completed
wrong one — the picker was blamed for panels that never rendered because the
fixture stored no evidence, and two runs went into the wrong screen before that
surfaced.

Continue when the cluster stands and only the mechanism was wrong — but only if
the correction is **derived from an observed failure**, not guessed at. A
sequence that had nothing to wait on, a navigation that was a no-op, a closure
rebinding a name it should have mutated: each announced itself, each pointed at
its own fix, and stopping to ask about any of them would have left a red tree
and learned nothing. Record the correction and the dead end **in the code**,
where the next person will meet the same wall, and report it in the summary. A
dead end explained is the most useful comment in a test file.

The distinction is not a licence to keep trying. One more attempt on a hunch is
the thing this rule exists to stop; a fix the failure handed you is not that.

Stopping early is a success, not a shortfall. Report which condition fired, what
was completed, and what the operator now has to decide. `N` is a ceiling, never a
target — do not reach for it by picking easier clusters than the plan ordered, and
do not soften a stop condition to keep going.

**How an `--auto` run works a cluster — stated here because no later section
will state it.** Do not fall through into `## Then offer to do it, and stop`.
That section's first line excludes `--auto`, so a run that arrives there has no
instruction left that tells it to act and stops at the offer, having planned and
changed nothing. Five consecutive `--auto 1` dispatches did exactly that on
20 August 2026 — KI-47 in `KNOWN_ISSUES.md`: 29.3 minutes, ten commits, no
`fix:` commit, and the regex the work was for still shipped. So this command's
unattended ending is written out here rather than borrowed from the attended
one:

1. Produce the plan and the **NEXT ACTION** exactly as `## Output` requires.
2. **Work that NEXT ACTION immediately, as written.** There is no offer and no
   `go`, because there is nobody to ask — the reply bullets in the next section
   have no meaning in an unattended run.
3. While working it, follow `.claude/DISCIPLINE.md` — read it now, not from
   memory. The rules that bind here: prove the guard fails first (1), measure
   rather than infer (2), one step's files per commit (8), guard/fix split only
   when the guard stands alone (7), and the corrected-premise test (9) for
   whether to stop or carry on.
4. Then follow **`## After the work`** in full — report, close the entries,
   commit, record the timing, write `NEXT_UP.md`, clear the marker. That section
   applies to every ending of this command, attended or not.
5. Re-plan, per the rule above, and repeat until `N` clusters are done or a stop
   condition fires.

An `--auto` run that ends with a plan, a `TIMINGS.md` row and no fix has not
completed a cluster — it has reproduced KI-47.

Without `--auto`, work exactly one cluster and only after a `go`.

## Then offer to do it, and stop

This section applies when `--auto` was **not** given. An `--auto` run has its own
ending, above, and must not arrive here — reaching this point unattended is the
KI-47 failure, not a stop condition.

After the NEXT ACTION, offer to carry it out, in one line, and **stop there**.
Do not begin without a reply. The operator seeing the plan before anything moves
is the point of this command; removing that would make it a different tool.

- **`go`** → work the NEXT ACTION exactly as written. Not a variation of it, not
  the cluster underneath it, not the tidy-up noticed on the way.
- **a cluster named instead** → plan that one in detail and offer again.
- **a question** → answer it and offer again. A question is not consent.
- **anything else** → treat as no.

When working it, follow `.claude/DISCIPLINE.md` — read it now, not from memory.
The rules that bind here: prove the guard fails first (1), measure rather than
infer (2), one step's files per commit (8), guard/fix split only when the guard
stands alone (7), and the corrected-premise test (9) for whether to stop or
carry on.

## After the work

Report, in this order: the files touched, the measurement before and after, and
the suite result as a count rather than as "green".

**Close the entries.** Move every backlog entry this step resolved into
**Resolved** in `BACKLOG.md`, naming the commit that closed it. An entry left in
Open after its fix has landed makes the queue grow monotonically and quietly
inflates the counts that drive promotion. This bookkeeping is part of the step,
not a separate chore.

If `BACKLOG.md` already carries **unrelated** uncommitted edits, do not stage it
alongside the code — say so, and offer the backlog update as its own commit. The
rule is that a commit contains one step's work, not that the backlog is untouchable.

**Then commit, and stop before pushing.** Stage only the files this step touched,
named explicitly — never `git add .`. The guard/fix commit split follows the rule
above: separate only when the guard stands on its own.

**Record what it cost, then clear the marker — on every ending**, including a
plan that changed nothing and a run that stopped on a decision. A plan that
produced only a plan still spent the time, and that is the number missing from
the operator's budget today. Append through `scripts\timings-append.ps1`,
never by free-hand Edit — the helper finds `## Other work` by heading and
refuses a row whose cell count does not match the table's header. Free-hand
appends have landed past the file's end twice (`b90f568` → `8537598`,
`bdb3390` → `04359e9`) and both went red at HEAD:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\timings-append.ps1 `
  -Section 'Other work' `
  -Row '| plan |  | <YYYY-MM-DD> | <min> | <work> | <what it was for> |'
```

The row shape, for reference:

```
| plan | | <YYYY-MM-DD> | <min> | <work> | <what it was for> |
```

`ref` is blank — a plan has no subject. `min` is wall clock from the `$start`
held at the top. `work` is derived from the paths any commit touched, by the
rule under *What `work` says* in `TIMINGS.md`; a plan that committed nothing
has no paths, so state what the planning was against and say it is a statement
rather than a measurement. Stage `TIMINGS.md` with the run's own commit where
there is one, and alone where there is not — a timing row left uncommitted
refuses the next preflight.

After staging and BEFORE `git commit`, run the width guard as a preflight:

```
.venv\Scripts\pytest.exe tests/test_loop_instructions.py::test_every_table_row_matches_its_header_width -q
```

If red, `git restore --staged TIMINGS.md`, repair the row, re-stage. Never
commit a row that lands under the wrong header.

Then `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Clear`, on every exit path. A marker cleared
only when a plan succeeds becomes a permanent "plan in progress" the first time
one is abandoned.

**End every run — completed, stopped, or refused — with NEXT UP**: the single
command or instruction the operator should run next, ready to paste. Derive it
from state, not habit:

- work completed and committed, more clusters remain → `/backlog-plan --auto 1`
  (or plain, if the next cluster needs a decision the plan already knows about).
  **Never write `--auto N` above 1 into NEXT_UP** — DISCIPLINE rule 14: `N` is
  a ceiling, never a target. The operator can always pass a higher `--auto`
  interactively; an unattended dispatch reads a bundled number as licence and
  round-060 was measured proof — the two clusters landed as one commit rather
  than one per round, breaking per-round attribution;
- the run stopped on a decision → `/backlog-plan --auto 1`, with the question
  verbatim as the first line of `reason` and the options and costs after it,
  and the question added to `QUESTIONS.md` as an `open` row (or its existing
  row named) so it waits where the operator looks.
  `command` always holds an invocation: the watcher dispatches whatever sits
  there as typed, and a question there is a prose prompt the worker can only
  talk to — it scores NO-OP, two NO-OPs halt the loop, and at 02:04 on
  2026-08-23 that is exactly what happened. The planner is the right
  invocation because it reads the backlog and the dispositions, so it ranks
  around the gated rows instead of walking into them;
- this run closed audit findings or promoted an invariant → `/audit-fix
  standard 1`, and say which trigger fired;
- the tree is dirty with this run's own bookkeeping → the one-file commit, as a
  PowerShell block, then the next command after it.

One NEXT UP, not a menu. If two are defensible, pick by DISCIPLINE rule 4's
tiebreak and say why in one sentence.

**Write it to `NEXT_UP.md` and commit that file alone**, as the last act of the
run, exactly as `audit-fix` does — the format and the reasoning live in that
file's own header. Update the `yaml` block: `command`, `reason`, `produced_by`
(`/backlog-plan` and the arguments), `at_commit`, `newest_report`, `written`.

This applies to every ending, including a run that refused to commit or stopped
on a decision. When the run stopped on a decision, `command` still holds an
invocation — `/backlog-plan --auto 1` — and the question goes verbatim at the
top of `reason`, with the options and their costs under it. An earlier form of
this rule said to write the question into `command`, on the premise that a
person would read it; DISCIPLINE rule 14 names the actual reader, the watcher,
which can carry out an invocation and can do nothing with a question. The
question is not lost by being in `reason`: it is a row in `QUESTIONS.md`
(add it if it is not — that file, not the report, is where the operator is
shown it and answers it), and the watcher now refuses a prose slot and logs
what it held.

A plan's NEXT UP is usually better-informed than a round's, because this
command reads the backlog and the dispositions as well as the newest report.
That is the whole reason it must outlive the session: the better-reasoned
answer was the one that used to disappear.

**Refuse to commit** under DISCIPLINE rule 6 — red suite, no-result suite, an
unproven guard, or an unchecked signal — and say which is blocking rather than
committing anyway. Commands handed to the operator follow rule 10 (PowerShell
5.1, here-strings for multi-line messages).
