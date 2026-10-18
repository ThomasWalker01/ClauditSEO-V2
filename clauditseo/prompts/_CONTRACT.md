# Prompt contract — the layout every brief follows

This is the layout file. It is not a brief and never runs. Every file in
`clauditseo/prompts/` that declares `checks:` in its header follows this
shape; a test asserts it.

## Skeleton

```
---            front-matter: id · name · part · scope (site|page) · tier · checks (list of ids)
# ROLE         one paragraph: what the specialist reads, judges, and writes
# PRINCIPLE    optional — only where the part has one (e.g. the semantic triple)
# TASK         assess → produce; the CHECK SET with ids verbatim; non-goals
# CONTEXT      every {{PLACEHOLDER}} the engine fills, one per line, with its
               fallback or "goes to not_assessable"; handling rules; the
               severity rule (registry default, raise-only). Engine-supplied
               inputs beyond this run's own evidence exist and are listed
               under "What the engine may supply beyond this run", which
               also names the payload itself: checks receive the module
               `context` dict, not a `CRAWL_EVIDENCE` global.
# FORMAT
  ## Block 1 — findings   fenced JSON, first in the output
  ## Block 2 — readable   five headings, in order, never repeating Block 1
# CONSTRAINTS  domain rules; always ends "Do not refine your own output. One pass."
```

## Block 1 — fixed fields

`part` · `run_id` · `source: "brief"` · `rows[]` · `not_assessable[]` · `assumptions[]`
Row: `check` (from the header's list) · `page` (from PAGE SET) · `status`
(FAIL | WARN | PASS-OVERRIDE) · `severity` (registry default, may be raised
with a `note`) · `evidence` (exact quote + count) · `replacement` (the full
fix, present on every FAIL/WARN) · `note`. Parts may add fields
(`page_type`, `group`, `strategy`); they may not rename or drop these.

One row per (check, page). No PASS rows. Never a question.

## Block 2 — fixed headings

1. `### <Part name> — assessment` — counts, verdict, ≤3 sentences
2. `### <Fix name> — patterns only` — the fix name is per part
   (Replacement copy · Corrected outlines · Alt text · Redirect map …)
3. `### Patterns`
4. `### Not assessable`
5. `### Out of scope`

## What varies per part, and nothing else

check ids · engine inputs · what `replacement` means · the fix heading's
name · the domain constraints · an optional PRINCIPLE.

## What the engine may supply beyond this run

`PRIOR_RUN` — the previous **site-wide** run of the same site, whatever its
tier, engine or dimension set. Narrow runs, page scans, blocked and unscored
runs are never `PRIOR_RUN`. A re-check (`kind: refresh`) IS eligible: it
records no scope of its own, and the operator ruled on 2026-09-07 that it
counts, because what it re-reads is still the whole site's record. It is the
run before this one in time, not the nearest run on the same basis — that
relation belongs to the Score trend and is named `partner_run_id` there; the
two must not be conflated.

A check or a prompt may read `PRIOR_RUN`'s stored evidence for the same
page (by the page identity the findings table uses) to say what changed:
a content hash, a canonical target, a heading list. It may not read
`PRIOR_RUN`'s findings to decide its own status — a finding's lifecycle
(new · persisting · resolved · regressed) is the record's to compute, not
the check's to re-derive.

When there is no `PRIOR_RUN` (first site-wide run, or every earlier run
narrow), a check that needs it emits `not_assessable` with the reason
`no prior site-wide run`, and a part page draws the absent-data state for
that block. It does not treat "no prior run" as "unchanged".

A dimension that was not run in `PRIOR_RUN` has no prior evidence for its
pages; a check reading it gets the same `not_assessable`, with the reason
naming the dimension.

### What the payload is actually called

Checks receive the module **`context` dict**, built in
`engine/core.py:run_audit`. There is no `CRAWL_EVIDENCE` global and there
never was — briefs have referred to one, and a check written against it
would read `None` for ever. What the dict carries:

    context["crawl"]        the CrawlResult for THIS run
    context["site"]         the site record
    context["prior_run"]    PRIOR_RUN, as described above, or None
    context["prior_pages"]  what PRIOR_RUN recorded per page (content hashes)
    context["providers"]    the provider hub
    context["run_id"]       this run

A key absent from that list is not available to a check, whatever a brief
calls it.

### Glossary — the run columns, live and dead

`scan_scope` is the live column, and its values are `site`, `full` and
`page`. `page` is the narrow one; `site` and `full` both crawled the whole
site. A `refresh` stores NULL here and is told apart by `kind`.

**`scope` and `depth` are dead columns and must not be read.** They are NULL
on every stored run (34 of them on 2026-09-07; the count moves, the fact has
not), so a check written against `scope` does not fail —
it reads `None` for every run and quietly treats them all alike. That is the
trap this glossary exists to close, and it is why they are named here rather
than simply left alone: the dead spelling is the more natural one to guess.

*Proposed, not executed:* a future migration could drop `scope` and `depth`.
Row count touched: every run row (34 on 2026-09-07), 0 of them meaningful —
every value in both columns is already NULL. Nothing in this item drops them, and nothing should until a migration
is written for it.

## What a prompt's `checks:` list may contain

Checks the brief itself emits — those a sweep cannot answer, `cost: model`
in the registry — and free checks it *reads*: it may cite one as evidence
and may return `PASS-OVERRIDE` against it where the inventory contradicts
the sweep.

It may not introduce a free check the sweep does not run. A `free` check is
one the engine promises to answer for nothing, and a prompt that lists one
no sweep emits puts a row on a part page that no run can ever produce —
the check appears in the table, is never raised, and reads as permanently
clean. Enforced by
`tests/test_a_prompt_never_claims_a_free_check_nothing_emits.py`.

## What is never in a prompt

CLARIFY / "stop and wait" · closing offers · per-page tables in Block 2 ·
`[TO CONFIRM]` for anything the engine supplies · severity vocabularies
other than HIGH / MEDIUM / LOW · "Phase 1 / Phase 2" narration.
