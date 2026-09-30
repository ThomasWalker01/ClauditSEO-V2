---
name: backlog
description: Capture something the product does correctly but unhelpfully into
  BACKLOG.md — usually a UI or workflow observation noticed while using it.
argument-hint: "<what you noticed, and where>"
disable-model-invocation: true
---

Capture this observation into `BACKLOG.md`:

$ARGUMENTS

## What belongs here

Things the product does **correctly but unhelpfully**. The code is not wrong; the
experience is. A missing link, a dead-end screen, a control that isn't where the
task needs it, an empty state that says nothing useful.

**What does not belong here:**

- A defect — the product contradicting itself, a wrong number, a false claim.
  That is the auditor's queue. If the observation is that something is *wrong*
  rather than *unhelpful*, say so and stop; it should go through `/audit-fix` or
  be fixed directly.
- A runtime fact not discoverable from source. That is `KNOWN_ISSUES.md`.

If it's ambiguous, ask which of the three it is rather than guessing. Putting a
defect in the backlog hides it from the loop.

## Steps

1. Read `BACKLOG.md` in full — **Open and Resolved**.

2. **Check whether this is already recorded**, before anything else. Compare on
   what the operator wanted to do and what the screen offered, not on wording;
   the same observation described twice reads as two entries and inflates the
   count that drives promotion.
   - Already recorded → name the entry and stop. Do not add it.
   - Already recorded but on a **different screen** → add it, and say so
     explicitly. A second location for one problem is exactly the evidence that
     turns a preference into a rule.
   - Covered by an already-promoted rule and already present as an instance →
     name the entry and stop.

3. Take the next free `B-NN`.
4. Work out **where** — the route, component or screen. Look it up in
   `dashboard/src/` rather than accepting a vague location; an entry without a
   location is as useless as a finding without a `file:line`.
5. Check the **Rules promoted to invariants** section. If this is an instance of
   a rule already promoted, say so in Notes and name the rule.
6. Check whether it is an instance of a *theme* that is not yet a rule. Count the
   open entries sharing that theme, including this one.

7. **Re-read the whole Open list for themes, not only this entry's.** Entries
   added at different times rhyme without anyone noticing — two screens rendering
   the same unpaginated list, three tables that truncate the same way. Compare on
   what the operator was trying to do and what the screen offered, not on wording
   or on file. Report any theme that has reached three, whether or not this entry
   belongs to it. This sweep is the point: a theme found only on entry is a theme
   found only when the third instance happens to arrive last.
8. Append the row. Keep Observation to one sentence stating what the operator
   wanted to do and what the screen offered instead.
9. Do not fix anything. This command only records.

## When a theme reaches three

Say so explicitly, and propose the rule in one sentence — the form it would take
as a design invariant, not as a description of the three instances. For example
three separate dead-ends became: *anything the UI names, it must let you act on.*

Then offer to promote it: add it to `.claude/agents/auditor.md` under PROJECT
CONTEXT as a design invariant, move it to **Rules promoted to invariants** in
`BACKLOG.md` with the date, and delete the individual entries it covers. Once
promoted, the auditor finds violations from source and the loop enforces it —
which is the point of the whole queue.

Wait for a yes before promoting. A rule stated too early, from three instances
that only look alike, gives the auditor a false invariant to enforce.

## Afterwards

Report the entry as added, and whether anything is ready for promotion.

Then **offer the one-file commit** — `BACKLOG.md` alone, a one-line message
naming the entry — and wait for a `go`. Do not commit without one. The reason to
offer rather than stay silent: an uncommitted entry leaves the tree dirty, and a
dirty tree blocks `/audit-fix` at preflight and forces `/backlog-plan` to work
around it, so every recorded observation otherwise costs the operator a manual
commit before any other tool runs. If `BACKLOG.md` already carries other
uncommitted edits, say so and do not offer — those are not this entry's to sweep
in.
