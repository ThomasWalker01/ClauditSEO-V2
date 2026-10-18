# Loop profile — ClauditSEO

The facts about THIS repo that the loop's skills need and must not guess. The
skills (`.claude/skills/*/SKILL.md`), the auditor (`.claude/agents/auditor.md`)
and `DISCIPLINE.md` are the loop kit — generic machinery installed by copy from
`CodeDash/loop-kit/` — and they read this file by name. Everything that used to
be written into them as ClauditSEO-specific text lives here instead, so the
same kit can run on another repo with a different profile. Keep it short and
keep it true: a wrong line here is a wrong line in every round.

```yaml
profile_schema: 1
project: ClauditSEO
# The suite the CI gate runs, with the gate's flags character for character.
# `tests/test_loop_instructions.py` checks this equals `.github/workflows/ci.yml`.
suite_command: .venv\Scripts\pytest.exe -n auto --dist loadfile -ra
suite_notes: >-
  Do not add -q: pyproject.toml sets addopts = "-q" already, and a second one
  makes -qq, which removes the "N passed" line the round records. Match the
  entry-point kind: a console-script pytest, never python -m pytest.
  Runtime: about five minutes at preflight (watcher-timed 4.6-5.8 min across
  rounds 084-088), longer under load. Run it in the FOREGROUND with a
  600000 ms timeout and wait - never run_in_background: under `claude -p`
  there is no completion notification and no later turn, and a backgrounded
  suite ended two rounds today (2026-08-23 07:00, 11:50) as NO-OPs with the
  tree left dirty. `.claude/settings.json` now denies run_in_background on
  every Bash call in this repo (DISCIPLINE rule 15, made mechanical).
python_exe: .venv\Scripts\python.exe
# The served product (DISCIPLINE rule 12). Empty means "nothing is served".
server_url: http://localhost:8020
service_restart_command: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restart-service.ps1
service_check_command: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restart-service.ps1 -CheckOnly
# Paths whose change means the running process is stale until restarted.
served_paths:
  - clauditseo/
# The front-end bundle: rebuild when these change, with this command, in this dir.
build_command: npm run build
build_dir: dashboard
build_paths:
  - dashboard/src/
  - dashboard/index.html
  - dashboard/vite.config.ts
  - dashboard/package.json
# Where the relay/watcher keeps this repo's state (inbox/, outbox/, done/ ...).
relay_dir: C:\Users\owner\Documents\AI\_relay
# The watcher itself (for rule 14's reference; not something the skills run).
watcher_script: C:\Users\owner\Documents\AI\CodeDash\watcher\watch.ps1
```

## Project context

The auditor's context for this repo. This section was `auditor.md`'s PROJECT
CONTEXT until 2026-08-22; it moved here unchanged because none of it is about
how to audit — all of it is about what is being audited.

- **Project**: ClauditSEO. Renamed from AuditDeck on 14 August 2026 — the new
  name is the contract; stale references are findings, not history.
- **What it does**: Self-hosted SEO audit application. Crawls a site at a chosen
  tier (NAV / T2 / T3), scores it deterministically across eight weighted
  dimensions (TEC, ONP, CNT, A11Y, PRF, AIS, OFP, LOC) into a 0–100 composite,
  tracks each finding's lifecycle across runs (open → fix attempted → verified →
  regressed), and layers optional model-written expert briefs over the same
  evidence. Output is a client-facing markdown deliverable led by a ranked
  action plan.
- **Design invariant — provenance**: every number carries a source and a
  confidence; unmeasured dimensions render as `[TO CONFIRM: …]` and never
  default to a score; scope limits are stated as their own findings. Treat any
  breach of this as at least High: it is the property the product is sold on.
  A stated limitation on a displayed value must appear in **rendered text** —
  not only in a `title` attribute, an `aria-label`, an `sr-only` element, or a
  string that reaches only the model. This applies to limitations, not to
  accessible names: `sr-only` text supplementing a visible label is correct and
  is not a breach. Promoted 15 August 2026 after three instances — a control
  named only for a screen reader, a pixel-width caveat reachable only by
  hovering, and a scan's stated limits written into a docstring the operator
  never sees.
  **Frame is provenance.** A number's frame — its unit, its currency, and the
  scope it was computed under — travels with the value or the value is not
  usable. A stored or displayed figure that omits its frame is a breach,
  because two figures with the same source and the same confidence are not
  comparable across different frames. Currency is annotated, never converted.
  A share is stored with the scope it was computed under, in one key beside the
  value, rather than left for the reader to re-derive. This applies to figures
  that are compared, aggregated, or carried across runs, sites or documents; a
  bare count under its own label is not a breach. Promoted 16 August 2026 after
  three instances. Note that this is not a restatement of "scope limits are
  stated as their own findings" above: that reports a limit beside the number,
  this stores the frame with it.
- **Design invariant — affordance**: anything the UI names, it must let the
  operator act on. A screen that states an object, a count or a required action
  and offers no route to it is a finding, not a cosmetic gap. Observed three
  times already: the Deliverables table says "regenerate before sending" with no
  regenerate control, the stale-analyses banner counts drifted analyses with no
  re-run, and a finding names a page with no link to open it.
- **Design invariant — real-data scale**: a collection rendered from crawl data
  must be bounded at its render site by a filter or pagination, and any element
  displaying a crawl-derived string must set `overflow-wrap`. Promoted 15 August
  2026 after four instances, three mechanisms: two screens rendering 100 pages
  into an unfiltered `<select>`, a 140-character filename widening a table until
  the column beside it left the screen, and a 57-row heading outline with
  nothing to narrow it. None of these appear against the seed fixtures; all of
  them appeared the first time a real site was crawled.
- **Design invariant — a guard's population**: a test whose assertion is that a
  set is empty must, in the same test, assert that the population it searched is
  non-empty, and derive that population from the tree rather than from a literal
  list. A fixture-built guard is the same case wearing a different shape: a
  fixture that cannot express the case the guard was written against is a
  population of zero. So is a guard that derives its population correctly and
  then decides membership with a matcher weaker than the population — the
  derivation is not the assertion. Find candidates from source by grepping for
  `assert not`, `== []`, `== 0` and `len(...) == 0` and looking for a sibling
  population assertion.
  **Floor: Medium, and High where the vacuous guard is the only evidence for a
  claim the loop acts on** — a finding recorded closed, a coverage claim carried
  between reports, or a CI gate. The High cases are demonstrated failure class 3,
  a verification gate defeated by weak matching, which is where the floor comes
  from rather than from taste: the board already ranks the class this way —
  CQ-85, CQ-190, CQ-191 and CQ-201 at Medium, CQ-207 and CQ-210 at High — so
  promotion re-ranks nothing that is already open.
  **Report the consequence, not the grep.** Measured at HEAD on 24 August 2026:
  those four patterns occur at **300 sites across 82 of the 131 files** under
  `tests/`, and **52 of those 82 derive no population from the tree at all**. A
  report carrying 300 rows is a report nobody ranks, and an unrankable batch is
  how a real rule gets ignored. A finding here names a guard whose vacuity has a
  cost that can be stated — something believed guarded that is not.
  Promoted 24 August 2026 by `QUESTIONS.md` **Q-6**, after six instances across
  five mechanisms: an empty-result assertion whose fixture excluded the 272 rows
  it was about (CQ-190), five vacuity floors lowered until a nine-tenths loss
  still read clean (CQ-191), a guard whose only assertion is "found nothing"
  (CQ-85), a fixture built with literal SQL the product cannot produce (CQ-201),
  and two guards that declared a derived population and then matched a string
  (CQ-207, CQ-210). Relay 025 named the rule in prose and it had nowhere to
  land — that is `BACKLOG.md` B-28, and this is where it lands.
- **Design invariant — an address in a comment**: a source comment that cites a
  repository path with a line number must resolve to that line, and the test
  that checks it must derive the population of such citations from the tree
  rather than from a literal list. The population is the tree, so a comment
  that names a symbol instead of a line — `fx.reference_rates`, not
  `fx.py:88` — is outside the rule rather than in breach of it, and is the
  cheaper form wherever it will do: a name does not go stale when a file grows.
  Enforced by `scripts/check_anchors.py` (`source`) over `clauditseo/`,
  `dashboard/src/` and `scripts/`, and held to zero by
  `tests/test_check_anchors.py::test_every_source_comment_anchor_resolves`.
  **Floor: Medium.** A wrong address costs a reader more than no address, and
  the class self-propagates — eight of the eleven rounds that carried CQ-151
  added a fresh instance in the commit that explained a fix.
  **Two things the guard does not decide, so a finding may still name them.**
  It resolves an address; it does not judge whether the line still says what
  the comment claims — the drift `--context` exists for on the reports side,
  with no source equivalent yet. And a citation with no directory
  (`render.py:592`) is skipped by construction rather than resolved, for the
  reason `ANCHOR` gives: guessing which `app.py` is meant is the mistake being
  guarded against. `tests/` is out of scope by the answer that promoted this,
  and measurably not a mere oversight: 23 of its 62 anchors do not resolve and
  15 of those are fixtures in `tests/test_check_anchors.py`, whose job is to
  hold wrong addresses. That corpus needs its own decision.
  Promoted 25 August 2026 by `QUESTIONS.md` **Q-16**, after CQ-151 ran eleven
  reports and its remedy was given twice without surviving a round.
- **Primary users** [INFERRED — no persona doc]: agency and consulting SEO
  practitioners auditing external client sites. Core job: run a defensible
  audit, decide what to fix first within a fee, hand the client a document, then
  prove at the next run that the fix landed. Inferred from per-client records
  and scheduling, per-client cost logging, a client-facing report voice distinct
  from internal, operator branding, and the fix-verification loop.
- **Platform / stack**: Python 3.12 (package `clauditseo`) + FastAPI; SQLite
  with WAL and busy_timeout; React + TypeScript (~23 source files, Vite) served
  as a hash-routed SPA at `localhost:8020`. Playwright/Chromium for optional
  rendering; axe-core vendored for A11Y. Registry-based engine modules; expert
  tools declared in `playbook.py`. Provider keys in a gitignored `secrets.json`
  beside the DB (0600 POSIX / broken-inheritance ACL on Windows). Windows-first
  operationally (PowerShell service scripts, `setx` guidance).
- **Already guarded by CI** — do not report as findings unless you can show the
  gate is ineffective: Python matrix (Ubuntu + Windows), packaging leak guard,
  `tsc --noEmit` + dashboard build, and a rendered-axe gate that fails if the
  tests skip. WCAG 2.2 AA is enforced on the product's own dashboard by that
  gate.
- **Demonstrated failure classes** — this codebase has shipped each of these at
  least once. Check they remain closed; a recurrence is High or above:
  1. Silent misclassification propagating into output — a lender mis-filed as
     `ecommerce` produced a report reasoning about a product catalogue that did
     not exist.
  2. Recovery paths that require a shell — a rejected provider key could not be
     corrected without editing a file and restarting the service.
  3. Verification gates defeated by weak matching — a fabricated number passed
     the analyst gate via substring comparison.
- **Hard constraints** [INFERRED]: solo developer, self-hosted, single-tenant,
  no external infrastructure. Cost-sensitive by design — model spend metered per
  brief, budgeted per tier, surfaced in the operator's currency. Continuous
  delivery, multiple builds a day, no release gating. Self-imposed but real
  compliance: WCAG 2.2 AA on the dashboard, robots.txt honoured, all data local,
  credentials excluded from database backups.
- **Out of scope** — do not raise findings here. Separate unstarted projects:
  GSC keyword/ranking data, competitor comparison, GA4/commercial tie-in,
  log-file ingestion. Unconfigured external providers: IndexNow, Places (GBP),
  Moz, DataForSEO, Bing Webmaster, Search Console. Multi-operator auth and
  whitelabel output are unexercised and out of scope until enabled.
- **Locale**: en-AU. Australian English, Australian date and currency formatting.
