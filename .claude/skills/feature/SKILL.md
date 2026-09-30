---
name: feature
description: Build one FEATURES.md entry against its own acceptance signal — the
  signal quoted before the work starts and stated as met or not met in the
  commit. Marks the entry BUILT and records what it cost.
argument-hint: "<id>, e.g. F-05"
disable-model-invocation: true
---

Build one entry from `FEATURES.md`. Argument: its id, e.g. `F-05`.

Three features were built without it, and only one stated its acceptance signal
in the commit body. Nothing noticed, because nothing checked.

## 1. Preflight, then claim

`git status --porcelain` — stop on a dirty tree, unless the only dirt is receipt
registers (`TIMINGS.md`, `OPERATOR_ACTIONS.md`, `KNOWN_ISSUES.md`, `NEXT_UP.md`,
`BACKLOG.md`, `CHANGELOG.md`, `QUESTIONS.md`): commit those alone first
(`receipts: <names> — written outside a run`) and continue. Run the pinned suite — the
`suite_command` in `.claude/loop/PROFILE.md`, verbatim — and record the count.
Run it through `scripts\run-suite.ps1`, which runs that command verbatim
and keeps the whole run under `.claude/run/`: the suite is intermittently
red and a red run whose assertion text is gone tells a feature nothing
(`QUESTIONS.md` Q-36, CQ-237).

Red, or no result at all, and the feature does not start. Then:

```powershell
$start = Get-Date -Format o
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Claim -Kind feature -Subject <id> -Phase working -Start $start
```

`-Claim` exits 2 if anything else holds the marker: stop, and never clear one
you did not write.

## 2. Quote the signal before writing anything

Read the entry and **quote its acceptance signal back verbatim** before the
work starts. That is the whole point: `FEATURES.md` says "done is decided in
advance rather than argued afterwards", and a signal recalled at commit time
has already been argued afterwards.

Quote every clause. The ones that get dropped first are the negative cases —
F-01's signal required a page whose scripts were not captured to render
`[TO CONFIRM: …]` and never "none", and that clause mattered more than the
positive half.

## 3. Build it

**No guard, and no DISCIPLINE rule 1.** There is no prior failure to observe:
the behaviour does not exist. A feature gets **ordinary tests asserting the new
behaviour**, written with it and red until it is built. Say so in the tests,
out loud, so nobody later reads them as guards that were never seen to fail.

No lever machinery — no severity, cohort, ageing or ranking. `/audit-fix` must
never select a feature, and this skill must not make one selectable.

Rules that do apply, unchanged:

- **Rule 3** — enumerate every consumer of anything you change, from a grep.
- **Rule 12** — if the signal is something the operator sees on a screen,
  rebuild and restart, then read it from `http://localhost:8020`, and put the
  served value verbatim in the commit. **Rule 13** — record the rebuild or
  restart in `OPERATOR_ACTIONS.md`.
- If it changes what a deliverable says, bump `RENDERER_VERSION` and add the
  `CHANGELOG.md` entry in the same commit.

## 4. Commit, and state the signal

The suite must be green. The commit body **must state the acceptance signal and
whether it was met** — that sentence is the deliverable of this skill:

```
feat: <id> — <what it now does>

Signal: <the signal, and met or not met, clause by clause>
Tests: <count, against the preflight count>
```

**Not met is a legitimate ending.** Say which clause failed and stop; do not
redefine what done meant to make it fit. Leave the entry unmarked, write the
row, and report what is blocking it.

### Place the remainder before you may mark it

Marking changes what the entry means. `FEATURES.md` line 2 says the file holds
*"capability the product does not have. Not defects, not experience problems"* —
so the moment an entry reads `**BUILT**`, anything still missing from it is by
that same definition **not a feature**, and does not belong inside it.

The trap is mechanical rather than stylistic. `backlog-plan/SKILL.md` selects
*"every entry not marked **BUILT**"*, so marked-ness **is** the selector: work
written into a marked entry is not deprioritised, it is **unreachable**. The one
skill whose job is to see every queue at once skips the entry it lives in.

**So a run holding work it scoped and is not shipping places it first, and marks
after.** Not into the entry, and not "later". Route it by the four-row table at
the top of `FEATURES.md`, which already answers this — the destinations are the
registers' own stated purposes, not a preference:

| What you are not shipping | Where it goes | The register's own line |
| --- | --- | --- |
| Capability that still does not exist at all | a **new, unmarked** `FEATURES.md` entry, with its own acceptance signal | *"what the product cannot do at all"* — and unmarked is precisely what the planner can select |
| A defect you **watched** on the running product | `KNOWN_ISSUES.md`, with its `How to verify` | its test is *how a defect was found*; rule 12 puts you in front of the product, so this is the one defect route a feature run legitimately has |
| A defect visible **by reading** the source | nowhere you write — instead leave the entry's claim no wider than what shipped | `audits/` holds *"where the product contradicts itself"*, is the auditor's to write, and a round may not edit a report; `KNOWN_ISSUES.md` excludes what was found by reading **by name**, because the auditor reads that file and putting source-visible work there anchors it |
| Shipped, correct, and unhelpful | `BACKLOG.md` | *"where the product is correct but unhelpful"*, verbatim |

**Neither defect row is `FEATURES.md`.** Its first line excludes defects, and
once the capability exists a problem with it is not a request for it.

**A fourth case needs no placement, because the mark never goes on.** If a clause
of the acceptance signal was not met, "Not met is a legitimate ending" above
applies: the entry stays unmarked, the planner can still reach it, and there is
nothing to place. This section is for work **outside** the signal that the build
correctly declined to do.

**Then say where it went, in the entry itself.** A `**BUILT**` entry may describe
its own boundary as fully as it likes — that is most of what makes it worth
reading a year later — but a sentence naming work still to do must name **the id
it was filed as**.
`tests/test_loop_instructions.py::test_no_built_entry_holds_unplaced_work`
enforces that and nothing wider: it does not object to deferral, only to
deferral with no destination.

*The instance that bought the rule.* F-09 shipped the front card, correctly, and
named two pieces it did not ship — *"recommended as two further entries once
each is scoped in its own right"* — in prose, inside the entry it then marked
`**BUILT**`. Nobody raised them and nobody could. Filed as **B-26** on the day
the operator went looking for the work and found it in no queue at all.

### Then mark it

In the same commit: mark the entry `**BUILT**` in `FEATURES.md`, keeping the
acceptance signal in place — it is the record of what was promised and what a
later change has to keep true — and append the row through
`scripts\timings-append.ps1`, never by free-hand Edit. The helper finds
`## Other work` and refuses a row whose cell count does not match the header;
free-hand appends have landed past the file's end twice (`b90f568` →
`8537598`, `bdb3390` → `04359e9`) and both went red at HEAD:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\timings-append.ps1 `
  -Section 'Other work' `
  -Row '| feature | <id> | <YYYY-MM-DD> | <min> | feature | <what it was for> |'
```

`work` is `feature` here by definition; a commit reaching beyond the entry is
`mixed`.

After staging `TIMINGS.md` and BEFORE `git commit`, run the width guard as a
preflight — cheap, sub-second, and catches any placement the helper was
bypassed for:

```
.venv\Scripts\pytest.exe tests/test_loop_instructions.py::test_every_table_row_matches_its_header_width -q
```

If red, `git restore --staged TIMINGS.md`, repair, re-stage. Never commit a
row that lands under the wrong header.

## 5. Clear the marker, and report

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Clear` — on **every** exit path, including a
signal that could not be met. A marker cleared only on success becomes a
permanent "F-05 in progress".

Report: the signal, whether it was met, the suite count, and the commit.
