# Discipline

One owner for the working rules the skills share. `audit-fix` and `backlog-plan`
both read this file before working a step; neither restates these rules in full,
because two copies of one rule is how the rules themselves drifted — the guard/fix
commit split was refined in one skill and contradicted by the stale copy in the
other, in the same session that fixed the identical defect in the product three
times.

Each rule carries the case that produced it, so the next reader can judge whether
their situation is the same one.

## 1. Prove it fails first

A guard that has never been seen to fail is not yet a guard. Write the assertion,
run it against the unfixed code, and show the failure before implementing.

```
.venv/Scripts/python.exe scripts/prove_fail.py tests/test_x.py::test_y
```

Runs the test against the parent commit's source with the current test file.
`PROVEN` (exit 0) means it failed there and the guard is real; `NOT PROVEN`
(exit 1) means the parent already satisfied it. Quote the output in the fix
commit. `CANNOT ANSWER` (exit 2) is neither — a dirty tree, a bad node id, or a
runner that aborted, and it is not a licence to proceed as though the guard
were proven.

*Case:* UX-09's first test passed against the broken code — `time.sleep` in a sync
route handler blocked the browser and serialised the race it was meant to create.
Implementing behind it would have shipped a fix with evidence that proved nothing.
The script exists because that check was four manual steps and got skipped: three
of four consecutive rounds left a High finding invisible to the guard beside it.

## 2. Measure, don't infer

If the step claims to widen coverage, report the count before and after. If it
claims to close a leak, show the leak. "This should now cover…" is not a result.

*Case:* the a11y sweep's reveal was measured at 8 of 17 categories opened; the fix
measured 17 of 17. Without the numbers, the `n-zero` filter's cost had been
invisible for the sweep's whole life.

## 3. Enumerate consumers before changing anything

Before applying a change, grep for every call site, template, audience, renderer
or module that implements the same rule — do not work from the list a report or a
plan happened to name. Fix all of them, or state explicitly which are deferred and
why. Where a rule has many consumers, prefer a test that enumerates them from a
registry or file list over a hard-coded list — a hard-coded list of three is how a
partial fix passes.

*Case:* four separate rounds fixed a subset and reported success — the provenance
tag in `_expert_section` but not `_finding_line`; the vendor leak in the run
template but not comparison; `page_coverage` in three of seven modules, the other
four carrying 82% of the weight.

## 4. Evidence, not structure

A claim that something is guarded must come from what the guard does when it runs,
never from reading its configuration. A route in `ROUTES` is not evidence the
sweep paints anything there; a selector in a test is not evidence it matched. If
the harness cannot report what it covered, the coverage is unverified — treat it
as unguarded, and rank making the harness report above the work it protects. Do
not inherit a coverage claim from a previous plan; a premise repeated without
being rechecked is the least trustworthy kind.

*Case:* the anatomy route was "covered" for the sweep's entire life while nine of
seventeen category panels had never been painted, and the facts panels never
rendered at all.

When two defensible orderings conflict — a sequencing rule against an audit's own
remediation order, a guard-first instinct against a predicted cost — prefer the
one backed by **observed failures** over the one backed by predicted costs.
Rework is recoverable and bounded; the regressions are the ones already shipped.

*Case:* the audit sequenced the blocked-state work before the routes guard to
avoid rework; the only two regressions the loop ever shipped both landed on
unguarded dashboard screens. Guard first won, by measurement rather than by
taste.

## 5. A check's evidence must be able to disagree with it

The general form of rules 1–4, and the most repeated defect in this repository —
in the product and in its tests alike. A check drawing its evidence from the thing
it checks can only ever pass.

*Cases:* G7's evidence set was built from the same rows the narrative came from,
so a fabricated figure generated cleanly. Sweep selectors captured empty strings
and the assertions held. The two-page fixture could not express the defects its
guards were written against, so two regressions shipped with green tests standing
beside them. A route delay that blocked the browser removed the race it existed
to create.

## 6. Never commit red — and red is not the only bad state

A red suite blocks the commit. So does a suite that produced **no result** —
collection aborted, the runner errored, every test errored at setup. That is not
a pass and not a failure; it means the suite told you nothing, and nothing about
the code may be inferred from it. Never weaken, skip, or delete a test to reach
green: a test failing because it asserted the old wrong behaviour is a judgement
call for the operator, not a cleanup.

**A red that will not reproduce — the carve-out.** *Rewritten 2026-09-06 by
the operator's answer to `QUESTIONS.md` Q-48. What it replaced needed a green
re-run of the whole suite and membership of a filed class; both halves are
measured below and both failed.*

A red may stand aside — as a round's **step-5 baseline** or at **verify**, on
the same terms — only where the round shows all three of these and writes
each one into the commit body:

1. **It does not reproduce.** Run the failing node alone against the
   unchanged tree. It passes. This is the whole test, and it is the one that
   separates a real defect from the class: a defect the diff caused fails
   alone, every time, for a reason you can state.
2. **The diff cannot reach it.** A file-level argument naming what the commit
   touches and why none of it is on any path the node exercises — not a
   feeling that the two are unrelated.
3. **The round names the class it is claiming, and says whether it suspects
   its own diff.** Any reason to suspect it, and the round stops. That
   clause is unchanged and is the part of rule 6 that was always load-bearing.

Quote the failing run's path under `.claude/run/` and the serial re-run's
result. A carve-out with only two of the three is not a carve-out.

**Why reproduction and not a register.** Filing by node cannot work, and this
is measured rather than argued. Round 116 found that bounding an
authorisation to named survivors cannot reach a population that grows each
time somebody runs the suite. Brief v16a's AT-a then ran the pinned suite
four times over one unchanged tree — a diff of three untracked additions, a
module nothing imported — and got **nine distinct failing nodes with not one
repeated**, all rendered browser guards, all green serially (`37 passed in
377.61s` plus `4 passed in 13.55s`). One sitting added eight names to a row
that had three. A register that grows eight nodes a night is a list of every
rendered test in the repository, and `KI-60`, `KI-61` and `KI-62` declining
membership on "no cause established" is a distinction none of those nine
could have been sorted by either.

**Why not a green re-run.** It was the unreliable half. Those four runs went
442.38 → 624.18 → 939.38 → 936.22s against the 444.07s the 29-run capture
set records as the quiet arm's maximum, and **none was green**; what
eventually produced a green (`3068 passed in 465.39s`) was the machine
quietening, not anything about the tree. Each attempt cost eight to sixteen
minutes. Round 149 had already recorded 0 of 2 on one tree. So the procedure
every earlier option leaned on is a coin flip whose bias is the machine's
load, and rounds 145, 147, 148 and 149 each threw away finished, verified
work waiting for it.

**Why the suite is still worth trusting under this rule, which is the
objection that matters.** A carve-out decided by the round rather than by a
list can be used to wave a real defect through. It cannot be used
*accidentally*, because a real defect reproduces. The case is on the record:
the fifth run of that same sitting came back red on two nodes, one of them
`test_the_built_bundle_is_not_older_than_its_source` — a genuine defect, a
`part_page.tsx` edit committed with a stale bundle. It failed alone, it kept
failing alone, and it stopped only when the bundle was rebuilt, while the
class node beside it would not reproduce at all. Clause 1 is exactly the
difference between those two reds, and it costs seconds.

**What this does not license.** It is not permission to skip the suite, to
narrow it, or to treat an unexplained red as noise because it is
inconvenient. A no-result is still not a pass. A node that reproduces alone
still stops the round however unrelated it looks — that is a defect until
someone explains it. And the honest cost of the change is stated rather than
hidden: the judgement moves from a list to the round's own argument, and the
round making it is the one least able to see its own diff. Clause 1 is the
mitigation, and it is checkable by anyone afterwards, which a feeling is
not.

**What checks that any of this happened.** Until round 132 nothing did, in
either direction — WF-98, report 132. `scripts/run-suite.ps1` leaves every run
on disk under `.claude/run/`, so the reds are recorded whether or not a commit
mentions them, and:

```
.venv\Scripts\python.exe scripts/check_carveout.py --since <commit>
```

puts the two records side by side. Exit 0 and `clean` means every red and every
no-result has its path quoted somewhere in the record — a commit body, a
register, or an audit report — and names a node the register files. Exit 1
lists the runs that do not, in two separate groups because these are two
separate conditions. Measured on its first run: of 47 captured runs, 14 red and
2 no-result, **7 of those 16 quoted nowhere in the repository**, and 6 reds
naming no node KI-22 or KI-51 files.

**An unquoted red is a question, not a verdict.** Some are rounds that stopped
and recorded the failure by node id rather than by path, which is the record
being thin rather than the rule being broken. The script never says which
commit invoked the carve-out — no matcher over commit prose can, and two were
measured and rejected before it was written; its docstring carries both counts.

Membership is a judgement per red, and the register does not settle it. The node
`test_a_recalled_brief_states_the_total_it_was_drawn_from` was filed under KI-51
through sixteen instances and was a deterministic ephemeral-port collision all
along, fixed in round 127; a re-run cleared it only by re-rolling the port. Ask
what the failure was, not where it is filed.

**The carve-out reaches a verifying run on the same terms.** Not looser ones:
the same three clauses, the same quoted paths, and the same stop the moment
the round has any reason to suspect its own diff. Any red that reproduces
alone still blocks the commit, and a no-result is still not a green.

*Before 2026-09-06 this paragraph extended a green-re-run carve-out bounded
by a filed class. Q-48 replaced the mechanism, not the scope: verify was
already covered and still is.*

What this costs is worth stating, because the round taking it is the one least
able to see it: at verify the tree carries that round's own change, so a green
re-run can in principle paper over an intermittency the change itself
introduced. The carve-out is a permission and not an instruction — a round with
any reason to suspect its own diff says so and stops. The operator took that
risk in preference to the alternative: at roughly one red in three, a stall at
verify leaves the work done and the tree dirty, which refuses the next
preflight in turn.

*Case:* pytest's temp-directory abort returned neither green nor red, and the
distinction had to be reasoned out from first principles twice before it became a
rule.

*Case for the carve-out:* rounds 100, relay 090 and relay 100 committed against a
green re-run and said so; rounds 109 and 115 stopped on the red. Both readings
were defensible because this file did not say which, and the question halted four
rounds while the handling was decided per round. `QUESTIONS.md` Q-39, answered
*only where the cause is known load-related* by the operator, 2026-09-01.

*Case for extending it to verify:* relay 123's single suite run was a verifying
one and came back red on `test_a_brief_whose_figures_all_lapse_still_accounts_for_them`
carrying KI-51's recorded `.expert-report` timeout signature; the re-run of the
unchanged tree returned `2391 passed`. It reached its commit only because that
commit was receipt registers alone — a round that had changed `clauditseo/` would
have had nowhere to go. `QUESTIONS.md` Q-42, answered *extend the carve-out to
verify, on the same terms* by the operator, 2026-09-01. That answer settles the
re-run and nothing about what a commit must run: it did not exempt a
register-only commit from the suite, and the option that would have was the one
not taken.

## 7. Guard and fix: separate commits only when the guard stands alone

A guard that widens coverage and thereby uncovers pre-existing defects passes by
itself — commit it first, repairs after, independently revertable. A guard that
reproduces the defect being fixed in the same step cannot pass until the fix
lands; it is the fix's evidence, not an independent net — commit them together.
Splitting that kind leaves HEAD red for one commit, which refuses preflight at
that SHA and poisons bisect. Where this rule and rule 6 appear to conflict, this
is the case they conflict on, and rule 6 wins.

*Case:* UX-09's guard and fix were split on instruction and HEAD was red for one
commit — named in the round summary rather than left for someone to find.

## 8. A commit contains one step's work

Stage only the files this step touched, named explicitly — never `git add .`. The
tree may carry unrelated edits: backlog entries, notes, another session's work in
flight. They are separate concerns and must not ride along. If a bookkeeping file
already holds unrelated uncommitted edits, offer its update as its own commit.

*Case:* `rm reports/out/seed-*.md` matching live deliverables, twice, is what an
untargeted operation on a shared surface costs.

## 9. A corrected premise: stop or continue by what it changes

Stop when the correction changes **what the cluster is** — the entries are not
closable this way, the blocker is elsewhere, the work belongs to a different
file. A corrected plan beats a completed wrong one. Continue when the cluster
stands and only the mechanism was wrong, **and** the correction was derived from
an observed failure rather than guessed — then record the correction and the dead
end in the code, where the next person will hit the same wall. One more attempt
on a hunch is what this rule exists to stop; a fix the failure handed you is not
that.

*Case for stopping:* the picker was blamed for panels that never rendered because
the fixture stored no evidence — two runs went into the wrong screen. *Case for
continuing:* fill-first ordering failed with a message that named the working
order; stopping to ask would have left a red tree and learned nothing.

## 10. Commands handed to the operator are PowerShell 5.1

`&&` is not a statement separator there. Each command on its own line; a
single-quoted here-string for any multi-line commit body:

```powershell
git add path/to/file.py
$msg = @'
subject line

body
'@
git commit -m $msg
```

## 11. A green baseline is evidence only if the gate's command produced it

Run the suite the way the gate runs it: the same flags, character for
character, and the same kind of entry point. A pass from a neighbouring
invocation is not the gate's answer to a different question — it is no answer,
because the difference between the two is exactly what it cannot see.

Where the environment forces a difference — a local virtualenv path against a
PATH lookup on a runner — name the difference and keep everything else
identical. A flag added to make a run succeed locally (`--basetemp`, `-p`, a
narrowed path) makes it a diagnostic, not a baseline. Say which one you have.

*Case:* `python -m pytest` puts the working directory on `sys.path`; bare
`pytest` does not. `242d94a` had to make `tests/` a package so the gate's
invocation could resolve `tests.conftest` — a divergence no local run using
the other entry point could have surfaced, and one that is invisible until CI
is the thing that finds it. The corollary bit in the same session: copying the
gate's `-q` removed the `N passed` line under `xdist`, so a baseline recorded
by reading a count would have had no count to read.

## 12. A signal is evidence only if it was observed where the operator sees it

A passing suite proves the code. It does not prove the running instance. Where
a round changes something the operator encounters — a screen, an endpoint, a
served asset — the observable signal named for that round must be checked
against the running product after a rebuild and a restart, and the served value
recorded verbatim.

Rule 11 is the sibling of this one for baselines: there, a green result is only
the gate's answer if the gate's command produced it. Here, a signal is only the
operator's answer if it was read from what the operator is served.

*Case:* round 021 (`f043135`) added a `bundle` field to `/api/health` so a
stale UI could be detected. 884 passed, committed, verification recorded.
Forty-seven minutes later the served endpoint returned
`{"status":"ok","version":"0.14.0","engine_version":"0.7.0"}` — no `bundle`
field, because the `pythonw` process listening on 8020 had started at 13:01:50,
before the commit existed. After `scripts\restart-service.ps1` it returned
`…,"bundle":"dQp5Q1ak"`, matching the built `index-dQp5Q1ak.js`.

So the round that fixed staleness shipped a staleness gate that could not fire,
because the endpoint reporting the value was itself stale — the same defect one
layer out, and the round's own verification could not see it. This is the
second half of what round 021 found; the first half was `restart-service.ps1`
never rebuilding the dashboard, with `dist` measured 746 minutes older than
`admin.tsx`.

## 13. An action that changes the running product is recorded before the next round

Rule 12's other half. Once the running product is where a claim is settled, it
becomes evidence — and evidence that anyone can change without leaving a trace
in git. A restart, a rebuild, a service install, a database reset or restore,
an environment-variable change, a hand-applied migration, a process killed:
anything done outside a commit that alters what the running product does gets a
row in `OPERATOR_ACTIONS.md`, with the time, what changed as an observed
before-and-after, and the evidence.

This binds the loop and the operator equally. The loop restarts the service in
step 5 of most rounds; those are actions too, and a file that only records
other people's is a file that makes the loop's own effects invisible.

**Directed work records that it is underway, too.** Work you are asked for in
chat — an investigation, a backlog capture, a repair — is none of the four
kinds a skill wraps, so nothing used to say it was happening:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 `
  -Claim -Kind fix -Subject CI -Phase working -Start (Get-Date -Format o)
```

`investigation`, `backlog` and `fix` are **notes**: they record without holding.
A note never blocks a round, never needs clearing, and is displaced by the next
real claim — so directed work, which has no skill to guarantee an ending, cannot
leave a lock behind. Exit `3` means a live round or relay holds the marker and
the note was not recorded; the work is not blocked, only unrecorded.

The reason is relay 020's: a round's restart and a hand restart are
indistinguishable by process tree, and the marker is the only discriminator. An
absent marker is the signature of the unattributed anomaly, so directed work
that records nothing manufactures false instances of it — two are already in
`OPERATOR_ACTIONS.md`, for F-03 and F-02.

**Nothing enforces this**, and that is worth knowing rather than assuming
otherwise: no skill wraps directed work, and the measured precedent is that an
instruction without one gets skipped — F-01, F-02 and F-03 were all built
without a marker. Treat the record as best-effort, and a gap in it as a gap
rather than as evidence nothing ran.

Record it even when nothing appeared to change. A restart that moved no version
is what later rules out the restart as the cause of a difference.

*Case:* round 024's Critical was that the served process reported
`engine_version 0.7.0` against a tree at `0.8.0`, returning `resolved: 352`
with no `not_rechecked` key — the round-022 Critical still in front of the
operator after two rounds of fixing it. A hand-run `restart-service.ps1` at
approximately 18:05 moved the endpoint to `0.8.0`, which was the right thing to
do and destroyed the finding's evidence in the same motion. Round 025 met a
different world, retired the finding as fixed, and could only *infer* the
restart from the version moving. It said so plainly — "fixed by a restart with
no code change, so the guard that should have prevented it is still absent" —
but `critical: 2 -> 1` across those two rounds is not progress, and nothing but
the auditor's own care stopped it reading as progress.

## 14. A command recommended to a future run is written in the form that run can act on

Where a skill tells a *later* run what to do next, it names the invocation that
later run can carry out unattended. For the planner that is `/backlog-plan
--auto N`, not the bare form. `N` is a ceiling and never a target; do not write
one above 1 — a run that wants more asks for it in its own NEXT UP, which the
planner's ending already knows how to do.

This binds recommendations only. Where a human types the command, the bare form
is unchanged and remains the right thing to type when they want to see the plan
before anything moves.

**The reason, which is the part that stops this being undone.** `/backlog-plan`
bare ends by offering to carry out the NEXT ACTION and stopping — "the operator
seeing the plan before anything moves is the point of this command; removing
that would make it a different tool" (`backlog-plan/SKILL.md:316-318`). That
gate was real while the operator drove every invocation. It is not real any
more. The watcher carries out `NEXT_UP.md` after any round, on the success path
as well as after a stop (the watcher, `CodeDash/watcher/watch.ps1`; `fed3356` in
the archived `_relay` history). A bare plan commits its
timing row and a fresh `NEXT_UP.md`, and the next cycle — about a minute later —
reads that file and works whatever it names. So the loop acts on the plan
either way; the bare form does not preserve the review, it only costs an extra
invocation to reach the same place while looking like caution. A gate with
nobody standing at it is worse than no gate, because it is claimed in the
instructions.

**`--auto` is not the relaxed mode.** It is stricter than a round: six stop
conditions, a mandatory re-plan between clusters — "a run that follows its
opening list is batch mode, and batch mode is what produced two consecutive
audit rounds with identical counts" — and feature clusters refused outright on
the ground that every feature trips a stop condition on arrival. Those are what
make this decision safe. Weakening any of them to make an unattended run go
further inverts the decision rather than implementing it.

**The rejected alternative: the watcher appending `--auto` itself.** It must not.
A scheduler that edits the instructions it was told to follow cannot be trusted
to have followed them, and the whole value of `NEXT_UP.md` is that it is the
round's reasoning rather than the scheduler's. The form is decided by the run
that writes the advice, not by the process that reads it.

*Case:* the three sites in `audit-fix/SKILL.md` that recommend a plan were bare
for eight rounds' worth of NEXT UPs — 027, 028, 029, 032, 033, 036, 041 and 043.
Exactly one of those plans ever ran, after 036 (`c3b229b`, 3.5 minutes). Seven
recommendations produced nothing. Decided 18 Aug 2026, recorded here rather than
in the skill so a later round meeting "prefer `--auto`" without the reason does
not read it as impatience and revert it.

## 15. The pinned suite is run in the foreground and blocked on

Every time a round runs the pinned suite, it runs it as a **foreground,
blocking** invocation and waits for it to return, however long that takes. Do
not background it (`run_in_background=true` in Bash, `Start-Process`, `Start-Job`,
`&` shell suffix), do not poll for its result, and do not exit with a "the
monitor will report when the suite finishes" message.

*Case, measured 19 August 2026 three times in one day:* rounds F-05 (17:18),
backlog-plan (19:59) and round-060 (22:27) each computed a coherent fix cluster,
ran the suite in the background, polled a few times, gave up, and exited with
the tree dirty and the work uncommitted. The 22:27 log line was verbatim: "I've
been polling without progress. Stopping now — the monitor will report when the
suite finishes." Each stall left four to seven files uncommitted and required
operator recovery; two of the three tripped the two-consecutive-NO-OP safety
halt within an hour. The suite's completion is what gates the commit — every
one of those rounds would have committed successfully had it just waited.

**The trade the polling pattern makes is verification for speed and both times
today the trade lost.** Foreground execution takes the suite's runtime as a
lower bound on round duration, which is honest — the round is not complete
until the suite says so. Any patience-based polling gives up too early and
misclassifies a still-running suite as a suite that will never return.

A worker that finds itself needing to poll should instead re-run the pinned
command in the foreground and wait; if it appears already-running from a
prior invocation, wait on that one's completion via its own PID rather than
by tail-and-timeout on the output.
