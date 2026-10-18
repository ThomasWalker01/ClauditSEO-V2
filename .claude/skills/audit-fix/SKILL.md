---
name: audit-fix
description: Run the independent auditor, save its report, apply one lever
  (the oldest carried High when the engineering cohort is non-empty; the sweep
  of two-or-more independent findings when they qualify; otherwise the report's
  first-ranked finding), verify against the test suite, and commit — repeating
  until the audit comes back CLEAN or a stop condition trips.
argument-hint: "[depth: triage|standard|deep] [max-rounds: N] — deep is audit-only unless a round count is given"
disable-model-invocation: true
---

Run an audit-and-fix loop over this repository.

Arguments: `$ARGUMENTS`
Parse as: first token = review depth (`triage` | `standard` | `deep`, default
`standard`), second token = maximum rounds (default `5`). Both optional.

**`deep` is audit-only unless a round count is given explicitly.** `/audit-fix
deep` audits, records, commits the report and stops without applying a lever;
`/audit-fix deep 1` behaves like any other round and applies one.

The reason is what `deep` costs. It stands up a probe server, drives the screens
and reproduces every High rather than reading it — the report *is* the
deliverable at that depth, and it routinely lands a lever larger than the room
left to work it. Round 013 produced a two-part change to the honesty gate on
client documents, with an expected-failure step, and stopped rather than start
it half-finished. Audit-only makes that the default rather than a judgement call
made when tired.

After an audit-only run, the lever is applied against the committed report in a
fresh session — the report writes out the probe, so nothing is re-derived.

## Step 0 — start the clock

Before preflight, before anything else:

1. Run `Get-Date -Format o` and hold the value as **ROUND_START**.
2. **Write the liveness marker**, so that a round in progress is visible to
   something other than this session:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Claim -Round <NNN> -Depth <depth> -MaxRounds <N> -Phase preflight -Start <ROUND_START>
   ```

   **`-Claim`, not a bare write.** A round is no longer the only writer: a
   plan, a relay item and feature work all take the same marker now. Claiming
   reads and writes in one call and exits 2 if somebody else holds it, which
   is what makes the preflight check below able to fire at all — round 028
   found that step 0 wrote before preflight read, so a round could never
   detect a foreign marker. Writing first and asking afterwards is the defect,
   and four writers make it certain rather than possible. If it prints `BUSY`,
   stop and say what holds it; do not clear a marker you did not write. One
   over 90 minutes old is discarded as abandoned automatically.

   Then set `-Phase` at each transition — `auditing`, `applying-lever`,
   `verifying` — and **clear it on every exit**, described at each of those
   steps below.

   Until this existed, a round's own start was state held in memory and
   nowhere else. The tree stays clean for the whole audit phase, the report is
   not written until the end, and no commit lands until after that — so for
   fifteen to twenty minutes nothing anywhere said a round was underway, and a
   second session reading repository state could only conclude the previous
   round was current and recommend starting another. That is a second writer
   in the tree, which aborts both.

   `.claude/run/round.json`, which `.gitignore` covers, so it cannot dirty the
   tree preflight is about to check.
3. Read `TIMINGS.md` if it exists. If it has **three or more** rows, print one
   line before starting:

   `History: last 5 rounds, median <M> min, range <lo>–<hi> min.`

   Print nothing at all if there are fewer than three rows — two samples is not
   a range, and printing one invites the reader to treat it as one.

**The history is printed once and then ignored.** Do not forecast this round's
duration from it. Do not compare against it while running. Never use elapsed
time as a reason to stop, to narrow a lever, to skip a verification step, or to
choose a smaller finding than the report ranked first.

The numbers exist to answer "is this loop getting slower" across rounds, which
is a question for the operator between rounds. Inside a round they are a pace to
keep, and a pace is exactly the pressure that produces a half-applied lever —
the failure this skill already has a capacity stop to prevent. A round that
takes three times the median because the lever was large is a good round.

## Preflight — do this once, before round 1

1. `git status --porcelain`. If the working tree is dirty, **stop** and tell the
   user. Do not stash, do not commit their work-in-progress. Per-round commits are
   only meaningful from a clean base.

   **One exception, and it is narrow.** If every dirty path is a receipt register
   — `TIMINGS.md`, `OPERATOR_ACTIONS.md`, `KNOWN_ISSUES.md`, `NEXT_UP.md`,
   `BACKLOG.md`, `CHANGELOG.md`, `QUESTIONS.md`, or one of their
   `-archive.md` counterparts — the dirt is bookkeeping that
   some run or the console wrote outside a commit (the console appends a rule-13
   row to `OPERATOR_ACTIONS.md` on every actuation, by the operator's decision).
   Commit those files alone, first — `receipts: <names> — written outside a run`
   — and continue the preflight from the clean base that leaves. Anything else
   dirty, stop as above.

   Then `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Read`. **If it returns a marker written by
   a round other than this one, stop and say so** — two rounds writing the
   same tree abort each other, and that is the failure the marker exists to
   make visible.

   A marker left by a session that died is not a live round, and this must not
   become a gate nobody can pass. Decide with evidence rather than a rule:
   compare its `phase_start` against the matching column in `TIMINGS.md`. A
   round three times the median deep into a phase is not running. Say which
   you concluded and why, then clear it with `-Clear` and start.
2. Record the starting commit SHA. You will report it at the end so the user can
   inspect or unwind the whole loop with one range.
3. Ensure `audits/` exists. Find the highest-numbered existing report to continue
   the sequence; if none, this is round 001.
4. Ensure `KNOWN_ISSUES.md` exists at the repo root. If it does not, create it with
   only the header and an empty table — do not populate it from your own guesses.
5. Run the baseline suite with **the `suite_command` in
   `.claude/loop/PROFILE.md`, verbatim** — do not derive one from
   `pyproject.toml`, and do not substitute another entry point. The profile
   states it once; `tests/test_loop_instructions.py` checks it against the
   gate. Its `suite_notes` say what must not be added or swapped.

   The flags are character-identical to the gate. `.github/workflows/ci.yml`
   runs `pytest -n auto --dist loadfile -ra` on `ubuntu-latest` and
   `windows-latest` after `pip install -e .[dev]`, so only the entry point
   differs — CI has no `.venv` and resolves `pytest` from PATH. **Match the
   flags exactly and match the entry-point kind**: a console-script `pytest`,
   never `python -m pytest`.

   Do not add `-q`. `pyproject.toml` sets `addopts = "-q"` already, so passing
   it again makes it `-qq` and suppresses the `N passed` line — which is what
   both this command and the gate did for fifteen rounds.

   The two are not interchangeable. `python -m pytest` puts the working
   directory on `sys.path` and bare `pytest` does not, so a suite can be green
   locally and fail collection on the gate. This repository has already paid
   for that once — `242d94a` made `tests/` a package so bare `pytest` could
   resolve `tests.conftest`. A baseline taken with the other entry point would
   not have found it.

   Record the baseline as the `N passed` line this prints, verbatim. If no such
   line appears, something is wrong with the invocation — that is the symptom
   `-qq` produced, and it is not a pass.

   **Run it through `scripts\run-suite.ps1`**, which runs that command
   verbatim -- it reads `suite_command` out of the profile at run time rather
   than carrying a copy -- and tees the whole run to a timestamped file under
   `.claude/run/`, which `.gitignore` covers:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-suite.ps1
   ```

   The wrapper is not a different command, and taking a baseline through it is
   not rule 11's shape: it states no flags of its own, and
   `tests/test_a_red_suite_run_leaves_its_assertion_text_readable.py` refuses
   one that does. What it adds is the run's *survival*. The pinned suite is
   intermittently red -- round 115 measured two reds in three runs of one
   unchanged tree -- and across every round that has hit it the answer to
   *which assertion fired* has never been recoverable, because the failure
   section is cut off above the assertion and the run is then gone.
   `QUESTIONS.md` Q-36 records exactly that. Quote the log's path when
   reporting a red or a no-result, so the next round can read the failure
   rather than re-run the coin flip.

   One further failure mode, which has bitten:

   - **A stale `pytest-current` symlink in the user temp root aborts the run**
     with `PermissionError: [WinError 5]` before any test executes. That is the
     no-result case below, not a failure, and it is not specific to either
     entry point. `--basetemp <fresh dir>` sidesteps it; adding that flag makes
     the command differ from the gate, so use it to diagnose and say so, never
     to record a baseline.

   **Then ask whether the record carries the reds that already happened**,
   because the instruction above is only as good as what rounds did with it:

   ```powershell
   .venv\Scripts\python.exe scripts\check_carveout.py --since <previous audit commit>
   ```

   Exit 0 and `clean` means every red and every no-result capture in
   `.claude/run/` has its path quoted somewhere in the record — a commit body,
   a register, or an audit report — and names a node the KI-22/KI-51 register
   files: rule 6's two mechanical conditions, checked from the logs rather
   than from anyone's account of them. Exit 1 lists the runs that do not, in
   two groups. **An unquoted red is a question, not a verdict**: some are
   rounds that stopped and recorded the failure by node id instead of by path.
   Read the commits around it before concluding a carve-out was taken, and say
   in the round summary that you did.

   WF-98, report 132. Rule 6 has required the path since relay 122 and the
   verify extension since round 131, and nothing compared the two records: on
   the first run, 7 of the 16 captures that owed a quoted path were quoted
   nowhere at all. This is a read, not a gate — it does not stop the round,
   and a red it names is not this round's to fix unless the round chooses it.

   A loop that uses tests as its ground truth cannot start without a result, and
   there are **two** distinct ways to lack one — stop on either, and say which:
   - **Red**: tests ran and some failed. Report the failures, and quote
     the `.claude/run/` log path. Whether the red may stand aside is
     DISCIPLINE rule 6's carve-out and not this step's to decide: it turns
     on whether the node reproduces when run alone, and it asks for three
     things in the commit body, not one.
   - **No result**: collection aborted, the runner errored, or every test errored
     at setup, so nothing actually executed. This is not a pass and not a
     failure — it means the suite told you nothing. Report the runner's own
     error and do not infer anything about the code from it.

6. Run `Get-Date -Format o` and hold it as **PREFLIGHT_DONE**. The baseline
   suite run is the bulk of this segment, which is why it is measured apart from
   the audit rather than folded into it.

## Each round

### Before step 1 — does this round owe an audit?

Not numbered, because the loop already has a `Step 0` and it means something
else. This is a gate on whether step 1 runs at all.

**A round audits when the newest report has something new to say, not because a
round is starting.** Before invoking the auditor, find the newest report in
`audits/` and ask the three questions below. An audit is owed if any one of them
answers yes:

1. **No report exists** — first run, or `audits/` holds none.
2. **The newest report is exhausted** — every finding it names has been closed,
   dispositioned, or was already selected as a lever by a previous round.
3. **The newest report is stale** by the test below — a changed path that
   survives the exclusion list is one an **open** finding of that report
   anchors to.

If none answers yes, **this round takes its lever from the newest report and does
not audit again.** Skip step 1 and step 2 — there is no new report to write or
commit — and go to step 3 with that report's `VERDICT`. Record `audit_min` as
`0.0` in `TIMINGS.md` and name the report the lever came from in the fix commit.
Where an audit **is** owed, name which of the three conditions owed it, in the
audit commit body at step 2.

**What this generalises, and the measurement that asked for it.** This gate
shipped scoped to one case — an unworked `deep` report — and the cost that
justified it was measured. Round 020 ran deep and audit-only at 25.5 minutes of
audit phase against a 13.3-minute median for standard rounds. Round 021 then
audited the same ground from scratch and took its lever from its own report.
Nothing was lost — 021 re-found all 57 of 020's findings — so the waste was never
the findings. It was the second audit.

That argument was never specific to `deep`. Over the twenty rounds ending at 070
the audit phase cost **356.3 minutes against 440.6 of fix** — 45% of all round
time — while the eight reports written in the last twenty hours read H:31±2
throughout and mostly re-confirmed each other. `/backlog-plan` is the existence
proof from the other side: it works from the newest report and never audits. So
the *input* widens to the newest report, deep or standard. The logic does not
change.

This does not reinstate the pressure that made audit-only the default. A `deep`
round still stops without applying anything; the difference is that the round
after it starts from the report rather than from another auditor invocation, so
the lever is worked with a fresh session's room, which is the whole reason the
report is committed on its own.

#### The open set, computed once and read by both of the conditions below

Conditions 2 and 3 ask about one set from opposite ends — condition 2 asks
whether it is empty, condition 3 asks whether a changed path anchors anything in
it — so it is derived here once rather than twice.

A finding in the newest report's Phase 1 findings table is **closed** when
either holds:

- a `Resolves:` trailer names it on a commit in
  `<the report's audit commit>..HEAD` — the loop's own record of what it
  selected and closed, and the evidence `TIMINGS.md`'s `levers` column is itself
  derived from, so reading the trailers also catches closures made by
  `/backlog-plan` and by relay items, which write no `levers` cell;
- it has an entry in `audits/DISPOSITIONS.md`.

Every other finding in that table is **open**.

**The range is a commit range and never a date.** `TIMINGS.md` records that the
auditor renumbers IDs every round, so `CQ-01` in two reports are two different
findings that share a label. The set is therefore only ever computed against the
*newest* report, and membership is decided over
`<the report's audit commit>..HEAD` — the same range condition 3's own
`git diff` already takes. "At or after that report" by calendar date is not
enough on its own: eight rounds share 2026-08-21, so a day cannot separate a
lever taken before a report from one taken after it, and reading an ID out of an
earlier round's numbering would close a finding nobody has touched.

Both registers are read for other reasons already, and both are evidence rather
than bookkeeping written for this gate. **Do not invent a third register to
answer this question.** If a case turns up that they cannot settle, that is an
operator decision: say so and stop, rather than adding a file whose only reader
is this paragraph.

#### Condition 2 — exhausted, decided from what the tree already carries

**A report is exhausted when its open set is empty.** Nothing further is derived
here — this condition and condition 3 read the one set above, so a finding
cannot be counted closed for exhaustion and still live for staleness.

Expect this condition to answer no for a long time. A report carries its
unclosed prior findings forward — report 070 names 172 distinct IDs — so
exhaustion is the empty-backlog case, not the ordinary one. It is written down
because the round that does reach it must audit, rather than draw a lever from a
report with nothing left in it to draw.

#### Condition 3 — stale, and what changed is whose anchors it reads

**A report is a valid lever source only while it still describes HEAD.** Commits
land between an audit and the round that works it — `320eb85` and `b18db32`
landed after round 024's audit. Before using one:

1. `git diff --stat <the report's audit commit>..HEAD` and state what changed.
2. Drop `TIMINGS.md`, `OPERATOR_ACTIONS.md`, `KNOWN_ISSUES.md`, `NEXT_UP.md`,
   `audits/` and `.claude/**` from that list before judging it.
3. Ask whether any *remaining* changed path is one an **open** finding of that
   report anchors to. The anchors of findings the loop has already closed since
   the report are not asked.

**Why those are excluded, since the unexcluded version cost a whole audit.**
The first five are the receipts every round is *required* to write, so a gate
that counted them would disqualify every report the moment the round that
produced it finished — the loop would make its own output stale. `.claude/**`
is the case that actually fired: round 024's report was deep, audit-only and
unworked; the only paths changed since its audit were `SKILL.md`, `ci.yml` and
`TIMINGS.md`; four of its findings anchor to `SKILL.md`; so the gate declared
it stale and round 025 re-audited from scratch — the exact outcome this block
exists to prevent, on the round that introduced it. Recorded as WF-19 across
reports 026 to 036 and narrowed here.

The exclusion is not "tooling does not matter". It is that a finding anchored
to an instruction file is a finding *about the instruction*, and the report's
account of the product is unaffected by editing it. Where a `.claude/**` change
would genuinely invalidate a finding this round intends to draw a lever from,
say so and audit — the list is a default, not a licence to skip the question.

`ci.yml` is deliberately **not** excluded: it is the gate, and a change to it
changes what green means.

If nothing remains, say so and use the report. If anything does, **the report is
stale for lever purposes**: audit normally and say which change made it stale. Do not let
"the newest report" quietly come to mean a report describing a tree that no
longer exists — that is rule 11's shape, and rule 11 was written because a
baseline taken against a different command is not a baseline.

**A plan committed between the report and the round will typically invalidate
it**, because a plan that fixes what the report found necessarily touches the
paths its findings anchor to — so pairing a deep with a plan spends the deep for
nothing a plain round would not have delivered. Measured once: report 051 was
deep, audit-only and unworked, and `/backlog-plan --auto 1` closed its Critical
in `ef7a150` before the next round started; the survivors of the exclusion list
were `clauditseo/api/app.py` and `tests/test_verify.py`, which are CQ-95's own
anchors, so round 052 audited from scratch at 19.4 minutes.

**What the staleness test compares, since this has already been misread.** It
asks whether a changed path is one *an open finding of the report anchors to* —
not whether product code changed. The delivery tooling is in audit scope, so a
report routinely anchors findings to `SKILL.md`, `DISPOSITIONS.md` and
`auditor.md`, and a diff touching only those can still make a report stale.

That paragraph is the comparison rule. Read it as it stands rather than
re-deriving it from the case below, which is how it was misread the first time.

On its first application it did exactly that. Round 024 was deep, audit-only
and unworked; the only paths changed since its audit were `SKILL.md`, `ci.yml`
and `TIMINGS.md`; and four of its findings — CQ-15 at `ci.yml:24,115`, CQ-36 at
`SKILL.md:273-285`, WF-15 at `:261-265`, WF-16 at `:216-221` — anchor to two of
those three. The gate declared the report stale and round 025 audited from
scratch, which is the outcome this block exists to avoid, on the round that
introduced it. Report 026 records that as WF-19 and remediation item 35 carries
the proposed narrowing.

**The narrowing that item carried, landed: open anchors, not all anchors.** The
test used to read the anchors of *every* finding the report names, including
ones the round had just closed. So a round that closed WF-89 at
`clauditseo/api/app.py:2128` staled report 072 on WF-89's own anchor — the
anchor of a finding that no longer has an account left to be wrong about —
while the report's account of every finding still open was as true after that
commit as before. A report describes HEAD for its open findings or it does not;
a closed finding's anchor is not evidence either way.

**The case that must still fire, stated so it is checked rather than assumed.**
A commit that closes WF-89 at `app.py:2128` and, in reaching it, also changes
the function an open finding anchors to — WF-84 at `app.py:1800-1802` — **stales
the report**, because WF-84 is open and its path changed. The test is on the
anchors of open findings, not on "the files the lever named": a lever that
reaches past its own finding is exactly what this gate exists to catch.
**Path is the grain, and do not refine to line ranges.** A path is what anchors
are written at, so the question is settled the moment `app.py` appears in the
surviving diff beside an open finding anchored there. Line matching would look
like more precision and would be the real weakening — it misses a finding whose
lines have moved, which they do on every commit that touches the file above
them.

**Do not weaken this test to make reports live longer.** A stale report is stale
for lever purposes; the remedy is to audit and say which change made it stale,
not to grow the exclusion list until nothing can make a report stale.

**Reading open anchors is not the weakening that paragraph forbids.** What is
forbidden is growing the *exclusion list* — the set of paths that never count.
The open-set narrowing changes no exclusion and takes nothing out of the receipt
set: `ci.yml` still counts, `SKILL.md` still counts, and `.claude/**` keeps
exactly the standing it has above. What changed is *whose* anchors a surviving
changed path is held against. Written next to the prohibition because the two
are easy to confuse, and confusing them is how the exclusion list would grow.

#### What this gate does not touch, stated rather than assumed

The **carried-cohort rule** (step 4) and the **ten-round dispositions gate**
both operate on the register and on the newest report, not on report freshness.
Widening what may serve as a lever source does not move either: a finding's age
is derived from evidence anchors across `audits/`, which this gate does not
write, and a round that skips its audit still reads `audits/DISPOSITIONS.md`
before selecting a lever. Said out loud because "the newest report is older
now" is exactly the shape of thing that quietly re-dates a cohort.

**The open set does not re-date the cohort either, and that is stated rather
than assumed.** It is read to decide whether an audit is owed and is written
nowhere, so no finding's age moves through it. Age still comes from evidence
anchors across `audits/`; a finding this gate counts closed keeps whatever age
the register gives it, and a carried finding that is open is precisely the
finding the cohort rule was already counting.

**CI attribution is unchanged**: one lever, one commit, one pinned suite per
round, all as they are. Only the redundant re-audit goes.

**What to expect, honestly.** Condition 3 will carry almost all of the
re-audits, and after a round that fixes product code it will usually fire, since
most fixes touch a path some finding anchors to. The saving is concentrated in
rounds whose surviving changed paths are ones no finding anchors to, and in the
deep case this block already served — which may be a small share of rounds. That
is a prediction, not a measurement, and the measurement that settles it is stated
in this change's own commit: audit-phase minutes per fix commit from
`TIMINGS.md`, the twenty rounds before this change against the rounds after,
against the 45% baseline above. If it does not move, the answer is **not** to
weaken condition 3; it is to put the staleness test itself to the operator.

**It did not move, it went to the operator, and the open set above is the
answer.** Rounds 071 and 072 are the whole measured run after `f153f6b`: both
audited, both on condition 3, at 20.8 and 17.1 audit minutes against 40.8 and
20.5 of fix — 38% of round time against the 45% baseline, on a sample of two,
which is a direction and not a result. The prediction held exactly as written,
so the sentence after it applied.

**Expect the narrowing to be small too, and do not credit it for a move it did
not cause.** Thirty-one of report 072's findings anchor to
`clauditseo/api/app.py`; the two levers taken since are two of them, CQ-147 and
WF-89, which leaves **twenty-nine open findings on that one path** — so report
072 is stale under the narrowed test as well, and counted rather than assumed. What the narrowing buys is the round whose *own*
closure was the only thing staling its report — not the tree dense with open
anchors, which is this tree. Before crediting a future move to this change, read
the levers: across a run of rounds in which every fix happened to touch an open
anchor the number should not move at all, and a move in that run came from
somewhere else.

**This gate runs on every invocation, whatever depth was named.** A depth
argument says how an audit is performed *if one happens*; it does not say that
one is owed. `/audit-fix standard 2` therefore checks this block first, exactly
as a bare `/audit-fix` would, and a round that takes an existing report's lever
spends its depth argument on the round *after* it.

One exception, and only one: **`deep` with no round count is a request for a
report, not for a lever.** The gate has nothing to offer it — there is no lever
to draw — so an audit-only `deep` run always audits. That is the sole case in
which naming a depth changes whether this block applies, and it is written down
here so nobody has to infer it from behaviour.

Nothing here changes what `deep` does. It remains audit-only without an explicit
round count, for the reason given at the top of this file.

### Before step 1 — `deep` only: is there a finding a fresh crawl would settle?

Rule 12 says a signal is evidence only if observed where the operator sees it.
Where a finding's **lifecycle** is the subject — `resolved`, `new`,
`not_rechecked`, `finding_states` — the running product has been checked against
runs crawled hours or days ago. Rounds 022, 025, 026 and the WF-03 round all
changed how findings move between buckets and all verified against stored runs.
A stored run cannot show whether a finding someone actually fixed now reads as
fixed.

This block sits **before** the audit, not after, because the point is that the
auditor gathers against data crawled this round. A crawl performed after the
report is written proves nothing about the report.

**`deep` and no other depth.** `standard` and `triage` never crawl. Audit-only
`deep` — no round count — still crawls, because the fresh data is for the audit
and the report is that round's deliverable.

**And only if step 1 is going to run.** If the gate above hands this round a
lever from the newest report, steps 1 and 2 are skipped — there is no audit for
fresh data to serve, so do not crawl. The two gates run in the order they are
written here: report first, crawl second.

#### 1. The pre-query, which will usually say no

Ask the stored data whether any finding is in a state a re-crawl would settle.
`current_state(conn, site_id)` (`clauditseo/persistence/runs.py:1820`) already
computes most of it. Qualifying states, each with the transition that makes it
qualify:

- **`fixed`** — a re-crawl either confirms it or moves it to `regressed`
  (`runs.py:704`).
- **`open` or `regressed` with `attempted_at` set** — a fix was attempted and
  the finding has not moved. This is `current_state`'s `awaiting`
  (`runs.py:1870-1872`).
- **`candidate`** — seen exactly once. A second sighting promotes it to `open`;
  absence drops it entirely (`runs.py:703,707`).
- **`open` on a page a *later* run did not fetch.** Read literally: this needs a
  later run that skipped the page. A site with one run has no later run and does
  **not** qualify here. Without that reading every finding on every single-run
  site qualifies forever, and a pre-query that cannot say no is not a gate.

**If none qualifies, do not crawl.** Say so with the counts and go to step 1.

Measured 17 August 2026, `twenty22.co` (site `de4f6723`, client `Twenty22`,
one run) stood at `fixed: 0`, `awaiting: 0`, no later run, `candidate: 6`. Only
the candidate clause carries it, and once those six settle the pre-query starts
saying no — which is the intended resting state, not a fault.

#### 2. What to invoke — and why not the CLI

**`POST /api/sites/{site_id}/verify`** (`clauditseo/api/app.py:1183`), with the
fingerprints the pre-query returned. **Not `clauditseo audit run`.**

The CLI cannot mark the run. `create_run` takes `kind` (`runs.py:50`) but
`cli.py:141` passes neither it nor `created_by`, so a CLI run is stored
`kind='audit', created_by=NULL` — indistinguishable from the operator's own
work, and load-bearing in three places that would each absorb it:

- `runs.py:271` — it becomes a **point on the site's score trend**.
- `runs.py:1351` — it increments the **"audits since" counter** on every
  existing deliverable for that site.
- `runs.py:1849` — it becomes **the latest run**, whose `finding_states` are the
  site's standing position for the fix loop.

The verify endpoint sets `kind="verify"` (`app.py:1221`), which all three
queries exclude. That is the answer to where these runs live: **in the same
database, marked, not in a separate client.** A separate client would split the
history the verification is checking against, which is the opposite of the point.

Three of the operator's parameters are satisfied by construction rather than by
remembering them: the endpoint derives its dimensions from the targeted findings
(`pages_for_findings`, `runs.py:731`) so it can never run the full default set;
it spends no model tokens, so analysts are off; and it fetches only the pages
behind those findings.

Before invoking, run the profile's `service_check_command`. This goes through
the running service, so rule 12's staleness problem applies to the crawl itself.

#### 3. A failed crawl is a no-result, not a red

This puts an external network dependency inside verification. The endpoint
distinguishes the cases for you, and they must not be collapsed:

- **502, detail `verification crawl failed: …`** (`app.py:1238`) — the crawl did
  not complete. Record the signal as **unmeasured** and say why. Never read a
  network failure as evidence a fix did not work, nor as evidence that it did.
  DISCIPLINE rule 6 already names this distinction; it applies here unchanged.
- **404 / 422** — the findings name no page to re-fetch, or came from an expert
  brief. Not a failure: the pre-query was too generous. Say which and carry on.
- **200 with `pages: 0`** — completed, fetched nothing. This is a no-result too.
  `pages` is the count of pages a check could actually read: 200 with an HTML
  body, via `eligible()` (`clauditseo/crawler/types.py`). The response also
  carries `pages_attempted`, and **a round must never read that one as a
  fetch** — a DNS failure leaves a page object, so three URLs that all fail to
  resolve return `pages_attempted: 3`. Where the two differ, the crawl
  partially failed and the difference is the diagnosis.

A no-result does not stop the round. It means the audit proceeds against stored
data, exactly as `standard` does, and the report says so.

#### 4. Record what it cost, and that it happened

Two files, both written by this session and neither by the auditor:

- **`TIMINGS.md`**, the `## Verification crawls` table — one row per crawl,
  including a crawl that returned no result. Its elapsed minutes are already
  inside that round's `total_min`; the table says how much of it was crawl.
- **`OPERATOR_ACTIONS.md`** — DISCIPLINE rule 13. A crawl writes rows to the
  live database, which is a change to the running product.

**The auditor does not do any of this.** Its grant is one file, the report, and
that is not widened here: it neither starts the crawl nor records it. The crawl
lands in `data/`, which `.gitignore` covers, so the hands-off check in step 1
stays clean.

### 1. Audit

Set the phase first: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Phase auditing`. This is the
longest phase and the one during which the tree stays clean, so it is the phase
a reader is most likely to be looking at.

Invoke the `auditor` subagent with the Agent tool. Give it exactly this and nothing
more — no summary of what you changed, no framing of what you think is wrong, no
suggestion of where to look:

- The review depth.
- The commit SHA of the previous round's audit commit, if any, so it can diff
  since then. First round: tell it to audit the whole codebase.
- The path to the previous round's report, if any, with this instruction verbatim:
  *"Treat every prior finding as a claim to re-verify against the current code, not
  as an established fact. A finding listed as fixed that is not actually fixed is a
  High finding. Account for every prior finding you do not carry forward, under
  exactly one of three words — **fixed**, **disproved**, or **not re-found** — and
  where a `prior` reference is ambiguous, or you fold two prior findings into one
  row, say so rather than choosing one."*

  **Why the three words, and why the auditor supplies them.** Findings cross
  rounds through this instruction and nowhere else. The lever comes from the
  current report; prior reports are read only to age candidates already in it.
  So a finding survives by being re-verified at every round, one hop at a time,
  and a single round that fails to re-find one drops it permanently — with
  nothing anywhere reporting that it happened.

  Measured across rounds 015–024 using each report's own `prior <ID>` claims,
  the chain has held: the one hop that can be checked exhaustively, deep round
  020 into 021, carried **57 of 57**, and the apparent drops at the other eight
  hops are the round's own lever landing or the auditor renumbering. So this is
  not a repair. Loss rate is zero and DISCIPLINE rule 4 forbids building
  machinery for it; what is missing is the ability to *notice*, which is why the
  requirement is a sentence in the report rather than a rule in the lever.

  **`not re-found` is the only one of the three that is a signal.** Fixed and
  disproved are the loop working. Not re-found is the chain breaking, and it is
  the evidence that would justify drawing candidates from older reports — a
  change that must not be written before it appears, because its only cheap
  matching rule is `file:line` comparison, and that has already produced a
  confident wrong answer. Diffing anchors between reports 020 and 021 says forty
  findings were lost. The true number is none.

  The ambiguity clause is part of the same reliability problem: a `prior`
  reference can fork. Reports 023 and 024 both carry a `UX-08` and both claim
  `prior UX-07`, so anything chaining by ID alone mis-tracks them and reports a
  drop that did not happen.
- The instruction to read `KNOWN_ISSUES.md` and `OPERATOR_ACTIONS.md` during
  its gather step, **each bounded** — `OPERATOR_ACTIONS.md` from the previous
  audit commit forward, as `auditor.md` step 4b bounds it; `KNOWN_ISSUES.md`
  its header prose and `## Open` section only. Say *bounded*; do not say
  *in full*.

  **Why the bound is stated here rather than left to the auditor's judgement.**
  Both files are registers the loop appends to and never truncates, so what
  they cost an audit rises every round while what they contribute does not.
  Measured on this repo on 2026-08-31: `OPERATOR_ACTIONS.md` is 340,775 bytes
  and `KNOWN_ISSUES.md` 127,975, of which the `## Resolved` section is 35,506
  — 28% of that second read is closed history before the window on the first
  is applied at all. Only an open row can be re-raised as a new finding, which
  is the job the read exists for; a closed row that has regressed is a genuine
  new finding, and reading its old text would invite writing the register's
  account instead of your own. The loop kit profiled the same two reads on
  CodeDash at 4.8% of the auditor's cumulative input over its rounds 001–012
  and 10.5% over 028–036; that figure is CodeDash's, not this repo's, and is
  quoted for the shape of the growth rather than as a measurement here.

  **`auditor.md` bounds only one of the two.** Its step 4b carries the
  `OPERATOR_ACTIONS.md` window; there is no step 4c here, so the subagent's own
  instructions say nothing about `KNOWN_ISSUES.md` and this dispatch is the
  only place that bound is stated. Do not drop it on the assumption that the
  subagent file already carries it.

  **It is not the dominant term, and the bound is not sold as one.** Most of
  the growth in an audit's input is elsewhere — more turns over a larger base
  context. A round that expects this to halve `audit_min` will be
  disappointed; round-to-round variance in that column is about 2x, which is
  wider than the saving.

  **What the bound must never touch.** It cuts what the auditor reads *for
  context*, never what it *re-checks*. Every prior finding is still re-verified
  one hop, as the paragraphs above require; neither register is where that
  chain runs.
- **The exact path to write its report to** — `audits/<NNN>-<YYYY-MM-DD>.md`,
  with NNN the round number — and the instruction that this is the only file it
  may create.

**Set the auditor's model by the depth**, as the Agent tool's `model`
override on that same call: `deep` runs on **opus**; `triage` and `standard`
run on **sonnet**. The deep audit is the thorough, audit-only pass and it stays
on the strongest tier. A standard round runs many times a day, sonnet costs
roughly a third of opus per token, and on this repo the audit almost never
returns CLEAN — so the cheaper tier carries nearly every audit, and the saving
is most of the audit budget rather than a rounding error. Measured on the two
paid runs of 2026-08-24: sonnet ~48k tokens at ~USD 0.096, opus ~60k at
~USD 0.302.

**Fail toward quality.** `auditor.md`'s frontmatter stays at `model: opus`, and
it is the default the dispatch falls to if the per-depth override is dropped,
mistyped, or unsupported. So the failure direction is toward the expensive
tier: a deep audit, or one that declares CLEAN, must never silently run on
sonnet. Do not "fix" a missing override by relaxing that default.

**Both halves of this are observed, not assumed** — every Agent-tool result
carries a `resolvedModel`, which is the harness's own record of what the
subagent actually ran on. Across the 151 recorded dispatches in this project
the `model` override took in 19 of 19 calls that passed one, and every auditor
dispatch that passed none resolved to whatever `auditor.md` said at that
moment: opus throughout, bar three runs on the evening of 2026-08-17 that sit
exactly between `86b0c56` (frontmatter set to sonnet) and `a540756` (set back
to opus). That is what makes the paragraph above a mechanism rather than a
hope, and it is checkable again the same way if either half is ever doubted.

**The CLEAN case is not settled here.** Whether a sonnet audit that returns
CLEAN must be re-confirmed on opus is an open operator decision, registered on
CodeDash by its relay item 079 and not yet answered. Until it is, the daily
deep — always opus — is the confirmation, and no round should treat a sonnet
CLEAN as more than it is.

Do not paste the code, the diff, or your own opinion into the prompt. The auditor
gathers its own evidence — that independence is the whole point, and pre-loading it
destroys the value of the separate context.

**When the auditor returns**, run `Get-Date -Format o` and hold it as
**AUDIT_DONE**.

**Then, before anything else, check that it kept its hands off.**
Run `git status --porcelain` and compare against the preflight baseline.

The auditor has no Write or Edit tools, but it does have Bash — so a redirect, a
`sed -i`, or a `git` write is technically reachable. Its instructions forbid them;
this is the check that the instruction held.

- **A tracked file changed** → stop the loop immediately. Report exactly which
  files, and revert with `git checkout -- <paths>`. Do not apply a fix on top of an
  audit that modified the thing it was judging, and do not treat the report as
  trustworthy — an auditor that edited source may have been reasoning about a state
  that no longer exists.
- **A new file other than the report** → treat as a tracked-file change. The
  auditor is granted exactly one write; anything else is a breach of the grant,
  not a convenience.
- **New untracked files under gitignored output paths** (`reports/out/`, `data/`,
  caches) → expected and fine. Reproducing a defect is legitimate audit work and is
  how round 001 produced its Critical finding. Note them in the round summary so the
  user can clear them, and carry on.

### 2. Record

The auditor has already written `audits/<NNN>-<YYYY-MM-DD>.md`. **Do not
transcribe it, reformat it, or reconcile anything in it** — including an internal
inconsistency in its own figures, which has happened and must survive to the
record rather than be tidied away by the session that commits it.

Confirm the file exists and is non-empty, read only its `VERDICT` block for step
3, and commit it alone:

```
audit: round <NNN> — <status>, <n> critical / <n> high / <n> medium

Scores: CQ=<n> WF=<n> UX=<n> UI=<n>
First lever: <finding IDs>
Carried: <k>/<m> prior findings — not re-found: <IDs, or none>
Audit owed: <which of the pre-step's three conditions owed this audit, and the
  report it was decided against — omit only when no report existed>
```

**`Audit owed:` exists because this commit's own existence is the only trace the
pre-step leaves when it says an audit is owed.** A round that takes a report's
lever names it in the fix commit and writes no audit commit at all; a round that
audits anyway writes one of these and, until this line existed, said nothing
about the report it passed over — so a reader could not tell "chose not to" from
"did not notice". One clause is enough: `report 051 stale — ef7a150 touched
CQ-95's anchors`, `report 070 exhausted`, or `deep, audit-only — no lever to
draw`. Round 052 is the case: it audited from scratch over an unworked deep 051
and its commit body does not mention 051, so which reason applied had to be
reconstructed from a diff afterwards rather than read.

Committing the report before the fix keeps an untouched record, and means a later
`git revert` of the fix does not also erase the reasoning behind it.

**Run the mechanical reconciliation first, then the diff below — two
independent measurements, per relay 029, not a replacement of either:**

```powershell
.venv\Scripts\python.exe scripts\reconcile_findings.py
```

Exit 0 with "nothing to compare" on a first-ever report; exit 0 with "clean"
if every prior finding is either still tracked or named in the current
report's own "not carried forward" table; exit 1, naming every ID, otherwise.
This exists because the diff below was a redundancy that never fired under
opus (report 038 individually re-verified all 124 carried findings) and fired
twice under sonnet, caught by hand, at real session cost, before this script
existed — see `scripts/reconcile_findings.py`'s own module docstring and
`tests/test_reconcile_findings.py`, proven against the real 038-to-039
transition it was built to catch. **If the script and the manual diff below
disagree, report the disagreement rather than trusting either alone** — the
same rule the marker cross-check in step 6 already follows for timings.

**Then check the report's anchors, which is a different question and has its
own script:**

```powershell
.venv\Scripts\python.exe scripts\check_anchors.py
```

Exit 0 with "clean"; exit 1 naming every Evidence-column anchor whose file is
missing or shorter than the line cited, and every path at ten or more reports
with no row in `audits/DISPOSITIONS.md`. Reconciliation asks whether a finding
was *dropped*; this asks whether the ones kept still have a reachable address.
Round 044 found five that did not, the oldest carried for fifteen reports, with
`auditor.md`'s "check the anchor resolves" instruction in place the whole time.

**A report is not edited to satisfy it.** This is the one check whose subject
is a file the round may not touch, which is why it is a script and not a
pytest — `tests/test_loop_instructions.py` records why `audits/**` is absent
from `REGISTER_FILES`. If it names an anchor, say so in the round summary and
carry it to `NEXT_UP.md`: the auditor runs the same script before returning, so
a survivor is a defect in that instruction rather than in the report. The
undispositioned half **is** a pytest as well, and there the remedy is a row.

**Fill the `Carried:` line from a diff, not from the report's own summary.**
Collect every finding ID in the previous report, and every `prior <ID>` claim in
this one; `m` is the first count, `k` the number of them claimed. Then check the
accounting the auditor was asked for:

- **A prior ID that is neither claimed nor accounted for** is the failure this
  line exists to catch. Name it in `not re-found`, and say so in the round
  summary — an unaccounted drop is worth more attention than most findings,
  because it is the only way the loop loses one silently.
- **Two rows claiming the same prior ID** is a fork. Record both; the count is
  not wrong, but any later comparison chaining by ID will be.
- `not re-found: none` is the expected result and must still be written. A line
  that only appears when something is wrong is a line nobody notices is missing.

This is a diff, not a judgement: do not decide for yourself whether a dropped
finding was really fixed. Only the auditor examined the current code, so only
the auditor can say which of the three words applies. Report what it said and
whether it said anything.

**A round that carries no lever from the previous round still does this.** An
audit-only round drops nothing by fixing anything, so an unaccounted ID there is
unambiguous — nothing closed it.

### 3. Decide

Parse the `VERDICT` block at the end of the report. Stop the loop, **without fixing
anything**, only if one of these holds:

- `status: CLEAN` — nothing above Low. The loop is done. Report success.
- **No progress**: this round's severity counts are identical to the previous
  round's **and** the first lever points at the same `file:line` evidence anchor.
  Compare the anchor, never the finding ID — the auditor renumbers IDs every
  round, so `CQ-01` in two consecutive reports is routinely two different
  findings. Identical counts alone are not a stall: a loop can close one finding
  and surface another of the same severity while genuinely converging, which is
  what rounds 007 and 008 did. If the counts are flat but the anchor moved, say
  so and continue.
- The report says a Critical finding can only be resolved by breaching a stated
  hard constraint. That is the user's decision, not yours.
- The report proposes a rewrite or re-platform. Stop and surface it.

`status: BLOCKING` is **not** a stop condition. A Critical finding is the strongest
reason to go on and fix something, not a reason to halt.

The maximum-rounds limit is **not** checked here. It caps rounds *completed*, and
is checked at the end of step 7 — after this round's fix has been applied, verified
and committed. `/audit-fix standard 1` therefore means one full audit-and-fix
cycle, not an audit on its own. Otherwise, continue to step 4.

### 4. Choose the lever

The report's **First lever** is a recommendation, not an instruction. It ranks by
severity, and severity alone starved twelve findings for fourteen consecutive
rounds — a one-line authorisation check, a `.gitignore` glob, a string sweep, none
ever selected because a fresher High always outranked them. Three rules override
the report's choice.

**Age the findings.** A finding's priority rises with the rounds it has survived.
Something that has outlived ten levers eventually outranks the next defect in an
active subsystem, and must — otherwise it is still open at round 030. Read the
prior reports for how long each candidate has been carried; if the report states a
survival count, check it against the evidence anchors rather than trusting it, as
those counters have been wrong.

**At ten rounds survived, a finding must be dispositioned before the round may
select any other lever.** Exactly one of:

- **taken** as this round's lever;
- **closed as won't-fix**, with the reason written into the audit queue;
- **closed as superseded**, naming the finding or commit that replaced it;
- **disputed**, with the evidence that contradicts it;
- **recorded as a strict xfail**, naming the round by which it must resolve.
  Strict, so the day the defect is fixed the test XPASSes and fails the suite,
  forcing whoever fixed it to retire the marker — a non-strict xfail is a
  finding that has been made invisible rather than recorded;
- **blocked on an operator decision**, naming the exact question and where it
  is recorded. **A blocked finding may not be re-blocked twice without the
  question being answered** — a third round of "waiting on a decision" means
  nobody has asked it, and the round must either get the answer or pick one of
  the other five.

**Naming is not a disposition.** This rule previously ended "a round that
selects a different lever while a ten-round finding sits undispositioned must
say so and name it" — which made disclosure an escape from the requirement it
was written to enforce, since naming is not one of the six. Round 016 was its
first application and used it exactly that way: `fac391b`'s body names eleven
undispositioned findings aged 11–16 and disposes of none, while remaining
compliant. A gate that a compliant round can walk through is not a gate.

Every ten-round finding gets one of the six, recorded in
`audits/DISPOSITIONS.md`, before the round selects any lever. If the round
cannot — because the choice is genuinely the operator's and no option is
honest without them — **stop and surface it**. That is the same standard the
rest of this file applies: a decision only the operator can make stops the
round rather than being absorbed into it.

Ageing as a comparison ranks a finding against whatever else is open, which a
fresher High always wins; at ten rounds the comparison stops and a decision
starts. "Not this round" is not one of the six — it is the answer that
produced the cohort.

**Every round takes its lever from the aged cohort when the cohort is
non-empty.** Where `audits/DISPOSITIONS.md` holds an *engineering* set with at
least one item, this round must select from it rather than from the newest
report's ranking. Only when the cohort is empty does the round fall back to
the newest report's first-ranked finding.

The rate was previously "one in three" and observably too low: audit 055
carried 33 open High findings, most surviving three or more rounds, and the
one-in-three cadence cleared at best two of those per week while new rounds
added five per audit. The engineering set was designed as a *release valve* on
severity ranking; a valve that opens 33% of the time cannot keep up with a
pressure that rises every round.

Dispositioning alone does not move anything: it decides *who* owns a finding,
not *when* it gets done, and the engineering set is precisely the group nobody
else will pick up. Severity ranking will keep preferring the newest High
forever, which is how eighteen findings reached ten to eighteen rounds. **A
fixed share of one-in-three is the only thing that has ever moved one — and
that share needs to be one-in-one until the cohort is empty**, or the same
findings will still be carried at round 100.

Within the cohort, sort by first-seen round ascending (oldest first) and pick
the top. The sweep rule below still applies inside the cohort — bundle
independent carried Highs where you can.

**The sweep rule below applies inside the cohort**, unchanged and with the same
test — the round-015 sweep closed four findings at fifteen rounds and one at
twelve that way, which is more than the preceding fourteen rounds managed
between them.

**Sweep the independent ones together.** One lever per round exists so the next
audit can attribute a regression to a single change. That reasoning does not reach
findings which are independent by construction — a config glob, a one-line guard,
a rename sweep touching no shared logic. Where **two or more** such findings are
open, a **sweep lever** taking all of them is one lever, not several. Say which
were included and why each carries no attribution risk. If any turns out to share a
call site with another, it does not belong in the sweep.

**Prefer carried Highs when composing a sweep.** The sweep exists to move
independent work faster; the carried cohort is exactly the set that most needs
moving. When two or more items in the cohort share the independence property
(no shared call site, no shared config, no shared subsystem), sweep them
together as one lever rather than picking just the oldest. If the sweep can
combine one cohort item with one fresh independent finding, still prefer two
cohort items — a fresh finding will be there next round; the cohort has been
waiting for ten.

The threshold was previously three-or-more, and observably the sweep almost
never fired: two carried Highs might qualify, three rarely did. Lowering to
two-or-more matches the shape of what actually clusters in this repo (paired
guards, `KI-XX + CQ-XX` residues, a migration + its test). The attribution
principle survives — the sweep only fires when independence is *demonstrable*,
which is exactly the bar this rule already asks for.

**Do not take a lever in a subsystem whose last three fixes failed verification.**
Where fixes keep landing new findings in the area they touched, the area is not
ready for another fix — the verification gap is. Close that first: make the guard
capable of failing, re-run the original probe against the built system rather than
accepting a green new test. Working on unverifiable ground is how 70% of this
repository's new findings came to be created by its own remediation.

Set the phase: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Phase applying-lever`.

Once chosen, implement that lever, plus nothing else. Not the second row of the
remediation table, not an unrelated tidy-up noticed on the way, not a finding
that looks more interesting. Applying eight *coupled* fixes
in one round makes the next audit unable to attribute a regression to any of them,
and turns the lifecycle tracking the loop exists to produce into noise. One
attributable change per round, verified, is the design — which a sweep of
genuinely independent items satisfies and a bundle of related ones does not.

**Before changing anything, apply `.claude/DISCIPLINE.md` rule 3** — enumerate
every consumer of the thing being changed, from a grep rather than from the
report's list, and fix all or name the deferred. That rule carries this repo's
most expensive lesson; read it rather than trusting a paraphrase. Rules 1 and 2
also bind: the guard is proven to fail first, and the result is a measurement.

If the first lever is genuinely blocked — it depends on a decision only the user
can make — stop and explain, rather than substituting a different change.

**A capacity stop is admissible only on an observed limit.** A truncated response,
a tool error, a measured context figure at the moment of stopping. Never on an
anticipated one.

"I won't have room to finish this" is a model reasoning about its own future
capacity. That is not evidence — it cannot be checked from outside, it cannot be
wrong in a way anyone can detect, and it is therefore exactly the kind of
unfalsifiable claim DISCIPLINE rule 5 exists to reject. "This call failed and
here is the error" is evidence. Only the second stops a round.

If no limit has actually been hit, **start the work.** Stop later on something
observable: a failing suite, a suite that produced no result, a guard never seen
to fail, a corrected premise, or a decision that is genuinely the operator's.

This rule was written after three consecutive rounds stopped on an asserted lack
of room, at single-digit percent of a one-million-token window. The explanation
was plausible each time and false each time, and the rule that was supposed to
govern it had been written to accept the assertion rather than test it.

A lever half-applied is worse than one not started: a partly-narrowed gate or a
half-wired rule ships a state nobody designed. And a stop that names its own
reason is worth more than one borrowing a clause that doesn't fit — round 013
stopped correctly and had to reach for the blocked-lever wording to do it.

**If the change alters what a deliverable says**, bump `RENDERER_VERSION` and add
the `CHANGELOG.md` entry in the same commit as the fix. The version constant is
what tells an operator a stored document is superseded, so a wording change that
ships without it silently makes `superseded` and `current` undecidable. This counts
as part of the one lever, not as a second one.

### 5. Verify

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Phase verifying`, then run the test suite -- through
`scripts\run-suite.ps1`, exactly as preflight did. A round's verifying run
is the one most likely to go red, so it is the one whose output most needs
to survive; quote the log's path if it does.

- **Passes**: check the observable signal the report named under First lever, and
  state whether you actually observed it. "Tests pass" is not the signal unless the
  report said it was.
- **Red**: whether the red may stand aside here is DISCIPLINE rule 6's
  carve-out, which reaches verify on the same terms it reaches the baseline
  and no looser ones. Not this step's to decide, and not a licence to re-run
  until green - re-running the whole suite is no longer what settles it. A
  red that reproduces when the node is run alone blocks the commit, whatever
  a second full run says.

**If the signal is one the operator reads from the running product** — a screen,
an endpoint, a served asset — the tree is not where it counts. Observe it at
the profile's `server_url`, per DISCIPLINE rule 12 (a profile with no
`server_url` serves nothing, and steps 1-2 do not apply):

1. **Rebuild what is served**, if the diff touched anything under the
   profile's `build_paths`: run its `build_command` in its `build_dir`.
2. **Restart the service** — the profile's `service_restart_command` — if
   the diff touched anything under its `served_paths`. The process imports
   at start-up, so a change on disk is not a change in the process that
   answers the browser.
3. **Re-check the signal against the running instance** and put the served value
   **verbatim** in the commit's `Signal:` line — the response body, the rendered
   text, the asset name. Not a paraphrase, and not "confirmed".
4. **Append a row to `OPERATOR_ACTIONS.md`** for each rebuild or restart, per
   DISCIPLINE rule 13, and stage it with the fix. A restart changes what the
   running product does, and the next audit settles claims against exactly
   that. Record it even when no version moved — that row is what later rules
   the restart out as the cause of a difference. The loop's own restarts count:
   a file holding only the operator's would make the loop's effects the
   invisible ones.

These are two conditions, not one, and they are asked separately on purpose.

**The served set is what the profile's `served_paths` names — for ClauditSEO,
all of `clauditseo/`, not `clauditseo/api/**`.** This
section used to say both, fourteen lines apart, and the narrow answer was the
wrong one: `app.py` defers **63 of its 77** `clauditseo` imports into request
handlers, so a route reaches persistence, reporting, analysts and modules at
call time. Nothing outside `api/` is off the path.

Deferred imports also make "the process is stale" the wrong description. Python
caches on first import, so a handler called before a file changed holds the old
module and one called after holds the new — two identical requests, two
answers, with no restart between them. A restart is what collapses that back to
one version, which is why the rule is a restart and not a judgement about which
directory was touched.

    <the profile's service_check_command>

answers "is the running process holding the current Python" without restarting,
and exits 2 when the running process is stale, 3 when nothing is serving. Run it when a signal is read from the product and
you did not restart in this round — that is the case nothing could previously
detect.

**Scope it by where the signal is read, not only by which directory changed.** A
round touching engine, persistence or crawler code with a signal the suite
observes owes neither a rebuild nor a restart, and must not pay for one. But the
same round owes a restart if its signal is read from a screen, because the
running process is serving the old module however green the tree is. The
question is not "what did I edit" — it is "where does the operator see this".
- **Fails**: attempt one repair. If it still fails, `git reset --hard` back to
  the audit commit for this round, stop the loop, and report exactly what broke.
  DISCIPLINE rule 6 governs: never commit red or no-result, and never weaken a
  test to reach green — a test failing because it asserted the old wrong
  behaviour is the operator's call.

### 6. Commit the fix

Run `Get-Date -Format o` and hold it as **FIX_DONE**. Take this stamp *before*
staging, not after the commit lands: the row it produces has to be inside that
commit, and a file cannot be added to a commit that already exists without
amending it. What this drops from `fix_min` is the duration of `git commit`
itself. What the alternative drops is rule 8.

Append the row through `scripts\timings-append.ps1`, never by free-hand Edit.
The helper finds `## The two lever columns, and why there are two`, walks to
that table's last body row, and inserts after it — and refuses a row whose
cell count does not match the table's header width. Free-hand appending has
landed rows past the file's end twice (`b90f568` → `8537598`, `bdb3390` →
`04359e9`) and both went red at HEAD.

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\timings-append.ps1 `
  -Section 'Rounds' `
  -Row '| <round> | <date> | <preflight_min> | <audit_min> | <fix_min> | <total_min> | <levers> | <work> | <what it was for> |'
```

`Rounds` aliases the verbose real heading. Nine columns; the shape is:

```
| round | date | preflight_min | audit_min | fix_min | total_min | levers | work | what it was for |
```

Guarded by `tests/test_loop_instructions.py`, which counts the cells rather
than trusting a reading. After staging `TIMINGS.md` and BEFORE `git commit`,
run the width guard as a preflight — cheap (single test, sub-second) and
catches any placement the helper was bypassed for:

```
.venv\Scripts\pytest.exe tests/test_loop_instructions.py::test_every_table_row_matches_its_header_width -q
```

If red, `git restore --staged TIMINGS.md`, repair the row, re-stage. Never
commit a row that lands under the wrong header.

- `preflight_min` = PREFLIGHT_DONE − ROUND_START
- `audit_min` = AUDIT_DONE − PREFLIGHT_DONE
- `fix_min` = FIX_DONE − AUDIT_DONE
- `total_min` = FIX_DONE − ROUND_START
- `levers` = the finding IDs applied, comma-separated — `CQ-01, WF-03`, not a
  count. A count cannot be read back against the report; the IDs can.
- `what it was for` = **the text after the em dash in this round's own commit
  subject**, copied, not reworded. Write the subject line first and quote it
  here, so the row and the commit cannot drift apart.

  Both columns, because neither does the other's job. The auditor renumbers
  IDs every round, so `CQ-01` in two rows is routinely two different findings
  — six of the first twenty-six rows say `WF-01` and no two mean the same
  thing. The ID is what reads back against *a named report*; the sentence is
  what reads back at a glance. With only the IDs, answering "what has this
  loop done" meant opening one report per row, which is the state the operator
  found the file in at round 026.

  For a round with no lever, both columns say so: `none (audit-only)` and the
  same reason in prose.

One decimal place throughout. `total_min` is written out rather than left to be
summed, so a row that does not add up is visible as a transcription error.

**Check the row against the marker before clearing it, and say so if they
disagree.** The marker has been accumulating `completed_seconds` per phase all
round, from the transitions themselves; the row is computed from timestamps
this session held in memory. Two independent measurements of the same thing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Read
```

Divide each `completed_seconds` value by 60 and compare against the matching
column. They will not match to the decimal — the marker banks a phase at the
transition and the row is stamped at FIX_DONE. **A minute or more apart is
worth reporting**, and report it rather than reconciling: the row is what the
file keeps, and an unexplained gap between two clocks is the kind of thing this
loop exists to notice. Do not make one read the other — that would remove the
only check either has.

**Then check the phase the marker has NOT banked, which is the one that
matters.** `completed_seconds` gains a phase only at the transition *out* of
it, so the phase a round is in when it ends is never in there — and that phase
is the one `fix_min` measures. Iterating the marker's values alone therefore
cannot see `fix_min` at all, which is precisely the column round 023 got wrong.

So compute it: `now − phase_start` from the marker, and compare that against
`fix_min` as well. Measured on a round that stopped mid-lever, the marker held
`{preflight, auditing}` and nothing for `applying-lever` — the check ran, agreed
with itself, and was blind to the only segment in question.

Also add the phases: `completed_seconds` summed, plus the unbanked tail, should
be within a minute of `total_min`. That sum is the check that would have caught
023 without knowing which column to suspect.

**On rounds after the first**, reset ROUND_START to the previous round's
FIX_DONE and write `preflight_min` as `0.0` — preflight runs once per loop, not
once per round. Carrying the original ROUND_START forward would charge round 3
with the whole loop's elapsed time and put round 1's baseline suite run in every
row, which would make the median this file exists to report climb on its own.

Then stage `TIMINGS.md` **with** the fix and its tests, in one commit:

```
fix: round <NNN> — <short description of the lever>

Resolves: <finding IDs>
Signal: <the observable signal, and whether it was confirmed>
Tests: <pass, with counts>
```

The timing row is a product of the round, not a change to the tree — committing
it separately would leave the tree dirty between rounds and block the next
round's preflight, which is the one thing this file must never do to itself.

**Rounds that never reach a fix commit** — an audit-only `deep` run, a `CLEAN`
verdict, a capacity stop, a blocked lever, or a suite that went red and was
reset — still produce a row, and it is worth more than the others: it records
where the time went when nothing shipped. Write `levers` as `none (<reason>)`,
e.g. `none (audit-only)` or `none (capacity stop)`, and

**`fix_min` is still measured, not written `0.0`.** Stamp FIX_DONE when the
round actually ends — after the decision, the write-up and the commit — and
subtract AUDIT_DONE as normal. `0.0` is the right value only when the round
genuinely ended at the audit commit, and it has to be *measured* to be that
rather than asserted.

This was an instruction to write a literal zero, and relay 022 measured what it
cost. Round 023 stopped on a corrected premise, spent **4.4 minutes** after its
audit deciding and writing it up, and recorded that as `0.0` — while `total_min`
is `FIX_DONE − ROUND_START` and captured it. Of the seventeen rounds with a
`total_min` to check against, 023 is the only row whose phases do not account
for it, and the whole gap is this. Round 020 wrote `0.0` too and does not gap,
because it really did end at the audit; the two are indistinguishable in the
file, which is the point.

Then, and
commit `TIMINGS.md` on its own at the very end of the round, after the audit
commit. Leaving it uncommitted is not an option — the next preflight stops on a
dirty tree — and folding it into the audit commit is not either, since that
commit is the untouched record of the report and holds that file alone.

### 7. Update KNOWN_ISSUES.md

Only for items whose status you can now demonstrate has changed. Move closed items
to `Resolved` with the round number. Do not add new entries for things the auditor
found in source — those live in the audit reports. The file's own opening rule is
authoritative: it holds defects by **how they were found** — running, driving, or
querying stored data — not by where they are visible afterwards. Follow that rule
as written in the file, not any paraphrase of it here. Include the update in the
fix commit.

### 8. Check the round cap

**A round may not report itself complete without a new row in `TIMINGS.md`.**
Verify it mechanically before declaring completion — do not rely on remembering
that step 6 ran:

```powershell
git show --stat HEAD | Select-String "TIMINGS.md"
```

If that returns nothing, the round is **not finished**. Say so and add the row.
If the timestamps were never captured, say *that* instead of reconstructing
them from memory or estimating from the transcript: an absent row is
recoverable and a fabricated one is not, because the median this file exists to
report cannot be audited back to anything.

*Case:* round 015 ran the full skill after `e942b1c` added the timing steps and
produced no row. Every step existed and was readable; nothing required evidence
any of them had run, so the omission was invisible to the round that made it and
was found later by an operator reading the file. This check is the evidence.
It is the same rule the product is held to — a claim must come from what the
check reports when it runs, never from the presence of the instruction that
should have produced it.

This round is now complete — audited, fixed, verified, committed, timed. If the
number of **completed** rounds has reached the maximum, stop here and report.
Otherwise begin the next round at step 1.

## When the loop ends

**Clear the liveness marker first**, before writing anything else:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Clear
```

Every ending reaches this section — `CLEAN`, the round cap, a capacity stop, a
blocked lever, a corrected premise, a suite that went red and was reset — which
is why the clear lives here rather than beside the happy path. A marker removed
only when a round succeeds becomes a permanent "a round is running" the moment
one does not, and the next preflight then has to decide whether to believe it.

A preflight that stops on a dirty tree also clears it: the marker was written at
step 0, before that check, so the round that wrote it is the round that must
remove it.

Report, briefly:

- Rounds run, and why it stopped.
- **Which lever was chosen and why**, if it was not the report's first — ageing,
  a sweep, or a subsystem held back for failed verification.
- The commit range from the starting SHA to HEAD.
- The scorecard trajectory across rounds — the four pillar scores per round, so the
  user can see whether it is actually improving or just churning.
- Anything the auditor listed under **Open questions** across all rounds,
  deduplicated. These are the things waiting on a human — and each one is a
  row in `QUESTIONS.md` (see below), not only a line here.

End with **NEXT UP**: the single next command, derived from how the loop ended.

**Write it to `NEXT_UP.md`, then commit that file alone**, as the last act of
the run:

```
next-up: after round <NNN> — <the command>
```

Update the whole `yaml` block: `command`, `reason` (one sentence, why this and
not the obvious alternative), `produced_by`, `at_commit` (the SHA this is being
written against), `newest_report`, `written`. Leave the prose sections as they
are; they explain the file, not this round.

Its own commit, at the end, for the same reason the audit-only timing row gets
one: it is a product of the run rather than part of the lever, the fix commit
has already landed by the time NEXT UP is decided, and leaving it uncommitted
would refuse the next round's preflight.

**Every ending writes it** — `CLEAN`, a capacity stop, a blocked lever, a
corrected premise, the round cap. A run that stopped has the most useful NEXT
UP of all, because the reason it stopped is the reason for the next command.

The point is that this is the only output of a round that used to exist solely
in session text. The report survives, the timing row survives, the dispositions
and the commit body survive; the best-reasoned conclusion — what to do next,
drawn from all of them together — scrolled away, and a status dashboard reading
repository state alone recommended something worse an hour later with nothing
to check itself against.

- **Audit-only run** (`deep` with no round count) → `/audit-fix standard 1`.
  The next round's Step 0 will find the unworked deep and draw its lever from
  it rather than re-auditing (SKILL.md:162, "Before step 1 — does this round
  owe an audit?"). This preserves the deep's investment: a
  `/backlog-plan --auto 1` written here typically invalidates the deep by
  committing a change before any round has taken a lever from it — measured
  from report 051 / `ef7a150` / relay 049 — spending the 25-minute deep for
  nothing. Name the first lever and say whether it is large enough to want a
  session of its own; the next round will use the naming as its selection
  hint. Fall back to `/backlog-plan --auto 1` **only** once the deep has been
  drained (all its Highs either taken, dispositioned, or blocked on an
  operator decision).
- **Stopped at the cap with findings open** → `/backlog-plan --auto 1`, since
  the plan decides whether the next lever is loop work or operator work.
- **Capacity stop** → `/backlog-plan --auto 1`, and state what the lever needs
  so the plan can size it rather than rediscover it. Stopped on a decision →
`/backlog-plan --auto 1`, with the question verbatim at the top of `reason` —
never the question in `command`, which the watcher dispatches as typed (prose
there is a NO-OP, and two halt the loop: 2026-08-23 02:04). `CLEAN` → say what
would justify the next audit rather than proposing one now.

**Every question for the operator is a row in `QUESTIONS.md`.** Whether the
round stopped on it or the auditor merely listed it under OPEN QUESTIONS: if
the register exists at the repo root, add the row (`## Q-<n> · open`, the next
unused number, `asked:` this report, `gates:` the finding/backlog/KI ids that
wait on it, `question:` one sentence, `options:` each with its cost) in the
same commit as the report, or reference the existing row by id if it is
already there. Never re-ask a question that has a row. A row whose status is
`answered` is not a question any more — it is work: take the answer as
settled, act on what it gates (or say in the report why the first lever is
elsewhere), and when the gated rows are done set the row to `acted` with the
commit. The console shows open rows to the operator and writes their answer
back; nothing else in the loop reaches them reliably.

**Why `--auto 1` and not the bare form** — DISCIPLINE rule 14. `NEXT_UP.md` is
read by whatever runs next, and what runs next is usually the watcher rather
than a person, so the form written there should be the form that can be acted
on. `--auto` is the stricter mode, not the relaxed one: six stop conditions, a
mandatory re-plan between clusters, feature clusters refused outright. `N` is a
ceiling, never a target — do not write a number above 1; a plan that wants more
asks for it in its own NEXT UP. An operator driving by hand types the command
themselves and can drop `--auto` whenever they want to see the plan first, and
that path is unchanged.

Do not declare success on the basis of a `CLEAN` verdict alone. If the auditor
scored a pillar `0 — not assessable` every round, say so: an audit that could not
see three of its four pillars is not a clean bill of health.
