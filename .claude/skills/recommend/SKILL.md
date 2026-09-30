---
name: recommend
description: Re-derive one open QUESTIONS.md row's options against HEAD and write
  a stamped recommendation beside them, with the argument against the pick stated
  as plainly as the pick. It never writes the answer.
argument-hint: "<row id>, e.g. Q-14"
disable-model-invocation: true
---

Re-derive one row of `QUESTIONS.md` and write a `recommendation:` beside its
`options:`. Argument: the row id, e.g. `Q-14`.

## Why the register needs this

An `options:` block is written once and read for days, and it decays faster than
the `question:` above it. The question is about a decision; the options are about
a tree, and the tree moves every commit.

Four cases, all measured on 2026-08-24, in one register, in one afternoon:

- `Q-12`'s options priced a choice between two answers to one question when the
  tree held two different quantities and both were true, and the fix had already
  landed the other way;
- `Q-5` said *"exactly one of the manifest's files diverges"* when five did;
- a backlog entry's central premise was false against the module it named;
- `Q-20` falsified a ruling a relay item had made three hours earlier.

An operator choosing between those options is choosing between costs that are no
longer real. This skill re-takes the measurements and says what it found.

## What it may write, and what it may not

| Field | This skill |
| --- | --- |
| `recommendation:` | writes it, replacing any earlier one whole |
| `derived_at:` | writes it, always, in the same edit |
| `question:` | never. A question is re-asked by pointing at its row, and a reworded question makes the register unciteable |
| `options:` | never. The operator is choosing between the options as stated, and a skill that edits them changes the choice out from under them |
| `answer:` | **never.** That is the operator's field |
| the `## Q-n` heading and its status | never. `open` stays `open` until the operator answers |

A recommendation that could set its own answer is not a recommendation. That is
the whole reason the register keeps the two fields apart.

## 1. Preflight, then claim

`git status --porcelain` — stop on a dirty tree, unless the only dirt is receipt
registers (`TIMINGS.md`, `OPERATOR_ACTIONS.md`, `KNOWN_ISSUES.md`, `NEXT_UP.md`,
`BACKLOG.md`, `CHANGELOG.md`, `QUESTIONS.md`): commit those alone first
(`receipts: <names> — written outside a run`) and carry on from the clean base
that leaves.

```powershell
$start = Get-Date -Format o
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Claim -Kind recommend -Subject <Q-id> -Phase working -Start $start
```

`-Claim` exits 2 if anything else holds the marker — a round, a plan, a relay
item. Stop, say what holds it, and never clear one you did not write.

**Then check the row's status, before reading anything else.** This skill runs on
`open` rows only. On `answered` or `acted`, stop and say so: the decision is
already made, and a recommendation printed beside a decided question is noise the
next reader has to spend attention refuting. On `closed`, stop for the same
reason.

## 2. Read the row whole, then take its options apart

Read the entire block — `asked:`, `gates:`, `question:`, `options:` — and the
`asked:` source it names, where it names one. The options are usually
semi-structured: bold leads, or separated by `;`. Enumerate them in the order
`options:` states them, and keep that order everywhere below, because the
operator reads the two lists side by side.

Then, for each option, write down **the claim it prices** — the sentence that
has to be true for its cost to be real. A count, a path, the state of a job, a
commit that did or did not land. An option with no such claim prices a
preference rather than a fact, and it is re-derived as *not derivable* rather
than as *holds*.

## 3. Re-derive each claim against HEAD

DISCIPLINE rule 2: measure, don't infer. Every number in an option is a
measurement somebody took at a commit that is no longer HEAD. **Take it again,
now, with the command that takes it.** Do not reason about whether it is likely
to have changed, and do not accept the register's own number as evidence for
itself — that is the specific mistake all four cases above are.

- A **count** is re-counted. Say the command and the number.
- A **path** is checked to exist at that path. A file that moved falsifies every
  option that named it, and moving is the commonest way one of these rows dies.
- A **commit, finding, question or report** named by id is resolved and read —
  `git log`, the register, the report, whichever holds it.
- A **red job, a failing test, a wrong screen** is re-observed, not remembered.
  Where the observation costs a restart, that is DISCIPLINE rule 12 and the
  restart is the price of the claim.

Each option then gets exactly one of three verdicts:

- **holds** — re-measured, still true. Give the measurement, not the adjective.
- **no longer true** — re-measured, and it is not. Give both numbers, or the old
  path and the new one. This verdict is the reason the skill exists.
- **not re-derivable** — the claim cannot be measured from this tree, or the
  option prices a preference. Never round this up to *holds*: an unchecked
  option presented as current is the failure this skill was built to end.

## 4. Write the recommendation, in three leads

One field, three leads, in this order and in these words. The wording is fixed so
that a reader — and a guard — can find each part without parsing prose:

```
recommendation: >-
  Re-derived: <one clause per option, in options: order, each with its verdict
  and the measurement behind it>.
  Pick: <the option, named as options: names it, and why, in the operator's
  terms>.
  Against: <the strongest argument against the pick, and what being wrong about
  it would cost>.
derived_at: <sha>, <YYYY-MM-DD>
```

**`Re-derived:` comes first, before the pick, and that ordering is load-bearing.**
A recommendation that leads with its conclusion invites the reader to stop there.
One that leads with what it re-measured makes a falsified option impossible to
walk past. Where re-derivation killed an option, say so here in that option's own
words — *"B — no longer true: the manifest ships four `.ps1` targets and zero
`.sh`, not the two the row prices"* — rather than quietly recommending A and
leaving the reader to work out what became of B.

**`Against:` is never empty and never "none".** If nothing can be said against
the pick, the row is not a question and should be answered rather than
recommended: say that, and still fill the clause with why. A recommendation with
no counter-argument is a decision wearing a recommendation's clothes, and at a
glance the operator cannot tell the two apart.

**`Pick:` may be `none of the stated options`**, where re-derivation falsified
all of them. That is a real and useful outcome — it says the row needs re-asking
against the tree it is now about, which is the operator's call and not this
skill's.

## 5. The stamp is the safety, not a nicety

`derived_at:` carries **the SHA the recommendation was derived against, and the
date**, and it is written in the same edit as `recommendation:` — never after,
and never next time.

The reason is not bookkeeping. A stored recommendation is *more* dangerous than
a stale `options:` block, because a confident recommendation is more likely to be
acted on without being re-read. With the stamp, staleness is mechanical: anything
can ask `git rev-list --count <sha>..HEAD` and say *derived 41 commits ago*, or
ask `git diff --name-only <sha>..HEAD` and say the better thing — *derived before
a commit that touched the files this row is about*. Without it, this field makes
the decay problem worse than leaving the row alone.

So the SHA is `git rev-parse --short HEAD` **taken at the moment the derivation
was taken**, not at commit time where the two differ, and the date is
`YYYY-MM-DD`. `tests/test_loop_instructions.py` refuses a `recommendation:` with
no resolvable stamp beside it, so a stamp left for later is a red suite rather
than a quiet omission.

## 6. Re-running on a row that already carries one

Replace the whole block — both fields — and never stack a second recommendation
under the first. Two recommendations with two stamps is a row the operator has to
date-sort before reading, which is the state this field exists to end.

Say in the commit what changed between the two. An option falsified since the
last derivation, or a pick that moved, is the most useful line in the diff.

## 7. Commit, record what it cost, clear the marker

`QUESTIONS.md` and `TIMINGS.md`, in one commit:

```
recommend: <Q-id> — <the pick, in a few words>

Re-derived: <the verdict per option, one line each>
Derived at: <sha>, <YYYY-MM-DD>
```

Append the row through `scripts\timings-append.ps1`, never by free-hand Edit; the
helper finds `## Other work` and refuses a row whose cell count does not match
the header:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\timings-append.ps1 `
  -Section 'Other work' `
  -Row '| recommend | <Q-id> | <YYYY-MM-DD> | <min> | QUESTIONS.md | <the pick> |'
```

After staging and BEFORE `git commit`, run the width guard as a preflight:

```
.venv\Scripts\pytest.exe tests/test_loop_instructions.py::test_every_table_row_matches_its_header_width -q
```

If red, `git restore --staged TIMINGS.md`, repair, re-stage. Then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\round-marker.ps1 -Clear
```

**Every exit path clears it** — including a row this skill refused to touch
because it was already answered.

## 8. Report

Say which row, the verdict per option, the pick, the argument against it, and the
stamp. Where an option was falsified, lead with that: it is the finding, and the
recommendation is only what follows from it.
