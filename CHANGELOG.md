# Changelog

All notable changes to ClauditSEO are recorded here. Dates are DD Month YYYY.

## Unreleased

Engine 0.10.0. A URL and the same URL with an ad platform's tracking tag on it
are one page. `normalise_url` strips `utm_*`, `gclid`, `gbraid`, the `gad_*`
pair and the other named ad-click keys before a link is enqueued, so a crawl
stops re-fetching pages it already holds under another spelling. Every other
query parameter is preserved byte for byte: `redirect_to`, `product_type` and
`slug` are read by the server and do change what is served. Measured over the
235-page T3 crawl the change was written from, 235 fetched URLs become 225
distinct and every one of the ten collapses onto a URL that same crawl already
held — no page is lost, and about 4% of a paid crawl stops being spent twice.
Runs either side of the boundary are not comparable on their page count, which
is what the engine version move is for; no stored run's rendered figures move,
because a stored run is read back rather than recomputed.

Renderer 1.35.0. A duplicate-title or duplicate-description count states the
population it was taken over. Where the check excluded URLs that are alternate
forms of a page it already counted, the sentence beside the count says how many
were excluded — so a count that falls between two runs can be read as a fix or
as a narrowing, rather than only as the first.

### Fixed — a narrowed count stops reading as its own improvement

- **CQ-230** (audit report 100, carried unchanged by every report through 114;
  recorded as a strict xfail at round 111 with round 116 as its deadline).
  `clauditseo/modules/onp.py`'s duplicate checks stopped counting a URL that
  declares another crawled page as its canonical — the same page under a
  tracking query — and recorded the excluded members under
  `evidence["canonical_aliases"]`. That key was written at two sites and read
  at none: no renderer, no screen, no API field. The summary went on saying
  *"3 pages share the title …"* with no word for which three, so a site that
  added canonicals between two runs saw the count fall and read it as a fix.
  Both renderers of a finding's own sentence now state the exclusion —
  `_finding_line`, and `_group_line` where a group of one prints its finding's
  summary verbatim; a grouped headline over several findings sums the
  exclusions across the group, because its page count is taken over the same
  narrowed population. The excluded paths themselves are internal-only, capped
  the way the page list beside them is: a client is being told a count's frame,
  not handed a second list to act on. Stored documents rendered before this are
  superseded, which is what the version move is for.

Engine 0.9.0. "Fetched" means one thing: a page a check could actually read.
Renderer 1.30.0. A comparison report states the frame its counts were computed
under — how many pages the current run fetched, and which dimensions it
audited — so "Resolved issues — 12" can be read as twelve fixes or as a
narrower crawl, rather than only the first. Where the run read one page under
two URL forms, the sentence now names both counts and says which is which. It
states the baseline it counted against, because two of its four counts are
decided by the baseline rather than by the current run. And its two composite
scores now carry the same treatment: the tier and the dimension set each was
computed under, stated above them.

### Fixed — a partly-priced median stops reading as its own opposite

- **UX-83** (audit report 088, carried unchanged by every report through 107).
  The caveat beside a brief price read `from 1 of 3 priced runs`, which parses
  first as *three runs were priced and this came from one of them* — two priced
  medians discarded — rather than the fact, which is that one of three sampled
  runs carried a price at all. It now reads `1 of 3 runs carried a price`, with
  the qualifier on the clause instead of hanging off `runs`, so there is no
  reading in which the sampled count is a count of priced runs. Three screens
  draw it — the Brief panel, Tools and the Schedule modal — and the dispatcher
  model is given the same sentence in the prompt it is asked to fit a spend
  recommendation inside; that one was changed with them, and a guard now holds
  the two wordings together. No stored deliverable's wording changed, so the
  renderer version deliberately does not move.

### Fixed — one document has one replacement, whichever screen asks

- **CQ-199** (audit report 088, carried unchanged by every report through 107).
  The Deliverables table and the document screen each derived *"what replaced
  this?"* from `reports.supersedes`, by different orderings — the table by
  `created_at` alone, the document by `created_at` then row order. `created_at`
  is a whole-second stamp, so two replacements written in the same second made
  the two screens name **different** documents as the replacement, measured:
  table `6cd2d188`, document `652c52b8`, one original. Both now take the order
  from one constant and report the later row, which is what each already said
  in prose that it did.

### Fixed — a truncated list of pages now says what it was cut from

- **UX-93** (audit report 100, carried by every report since, blocked on
  `QUESTIONS.md` Q-26 until the operator answered it on 29 August 2026:
  *store the frame*). Two caps stood between a check and the sentence
  describing it, and the sentence could not tell them apart. Four checks store
  only the first few URLs they found; the section screen's payload then cuts
  what they stored to ten; the disclosure stated the second cut against the
  first as though the first were the total that exists. On a real site one row
  read *"51 of 272 sitemap URL(s) were not reachable"*, `PAGES 20`, and
  *"Showing 10 of 20 — the rest are stored and are not reachable from here"* —
  of which the last clause was false for thirty-one of the fifty-one, which
  had never been written down at all. A finding now carries the count it was
  cut from, the column stores it, the payload sends it, and the disclosure
  states each cut in its own words: *"Showing 10 of the 12 URLs stored"* for
  the screen's, and *"The check found 51 and stored the first 20, so the other
  31 were never recorded"* for the check's. Rows written before the column
  existed carry no frame, and the screen asserts no total for them rather than
  inferring one from the list it has.

### Fixed — the run that read everything is no longer told it read too little

Renderer 1.34.0.

- **UX-89** (audit report 095, carried unfixed by every report since, taken at
  round 105). A comparison prints one sentence when exactly one of the two
  composites carries a coverage ratio, giving the reason the other carries
  none. Four causes can put a composite in that position, and the sentence was
  shaped for three of them — a colon, then a deficiency. The fourth is not a
  deficiency: a run that reached every page its site declared carries no ratio
  *because it read all of what it declared*. Printed through the deficiency
  shape, a client read: *"Only the current composite carries a coverage ratio:
  the baseline run reached every page its site declared."* — the baseline at
  100% of its declared pages offered as the qualified one beside a current run
  at 86.4%, in the sentence written to stop exactly that misreading.
- It now reads *"Only the current composite carries a coverage ratio. The
  baseline run reached every page its site declared, so there is no shortfall
  to state."* The three deficiency causes are word-for-word unchanged, checked
  at all three against the renderer.
- **No fact is added or withheld.** The same four causes, the same ratio, the
  same silence beside the same composite. Only the frame the absence is read
  under changes, which is the frame clause of the provenance invariant applied
  to an absence rather than to a figure.

### Fixed — a client can read which dimensions their report covers

Renderer 1.33.0.

- **UX-85** (audit report 091, 23 August 2026, carried by all eleven reports
  since; dispositioned a strict xfail at round 102 with a round-103 deadline,
  closed here at that deadline). The frame added for the client was written in
  internal acronyms with no key: *"Comparison scope: the current run fetched
  224 pages and audited A11Y, AIS, CNT, LOC, OFP, ONP, PRF, TEC."* Half of the
  frame the whole change existed to state was unreadable to the audience it
  was stated for. It now reads *"audited Accessibility (A11Y), AI-Surface
  (AIS), Content (CNT), Local (LOC), Off-Page (OFP), On-Page (ONP),
  Performance (PRF), Technical (TEC)"*.
- **No fact is added or withheld.** The same dimension set, named. The words
  come from the module registry — `AccessibilityModule.name` is
  "Accessibility" — rather than a table in the renderer, which would be a
  second vocabulary to keep in step with the modules and with `/api/meta`,
  which already serves the same `name` to the dashboard.
- **The name accompanies the code rather than replacing it**, because the code
  keeps appearing below. Every finding is tagged "(source: A11Y module,
  confidence: high)" and every new one "A11Y was not audited by the baseline"
  — 825 of them on the comparison this was measured against. Keying each would
  be noise; keying them once, in the frame sentence already sitting above the
  first count, makes them all readable. The frame is now the document's key,
  and those tags are deliberately unchanged.
- **Three surfaces, not the one the finding named.** `.claude/DISCIPLINE.md`
  rule 3 asks for the consumers from a grep rather than from the report's
  list, and the grep found two more: the **run report's header line** — "(T1,
  dimensions A11Y, AIS, CNT, …)", which is the document a client is handed
  most often — and the **score-movement difference clause**, "AIS was audited
  only in the current run", one heading below the sentence the finding did
  name. `tests/test_a_client_document_can_read_its_own_dimension_names.py`
  carries a source guard over `render.py`'s joins so a fourth surface fails
  rather than ships.
- **The operator's copy is untouched.** The audience distinction is what is
  *explained*, never which facts are stated; spelling "Accessibility" at an
  operator explains a word they already own, and the rest of their document is
  written in codes.
- A code the registry does not hold renders as itself, so a run stored under a
  dimension since removed still produces a document.

### Added — a start URL can be checked without buying a crawl

- **WF-82** (audit report 065, 21 August 2026, carried at High by all 33
  reports since and never dispositioned — the oldest open finding in the
  register). The launcher's **Start URL override** field now has a **Check
  this URL** button beside it, backed by
  `GET /api/sites/{site_id}/start-url-check`. It answers whether the crawler
  would accept the URL and creates nothing: no run row, no fetch, no provider
  call, no cost entry.

  A URL the crawler *refuses* was always free — the launch route raises 422
  before it creates the run. It was the **yes** that cost something, because
  the only way to be told a URL is acceptable was to press Run audit and get
  the crawl that acceptance starts. `OPERATOR_ACTIONS.md:139` records that
  happening: a trailing-dot control URL, posted to confirm a normalisation
  fix, was accepted and left a permanent audit run, since there is no route
  to delete a site's history.

  The check consults `_validate_start_url` itself rather than restating the
  rule. Two doors disagreeing about what a host is has been this route's
  failure mode twice already, and a checker with its own opinion would be the
  third.

### Fixed — the coverage ratio's two ends now name two populations

Renderer 1.32.0.

- **CQ-70** (audit report 034, 17 August 2026, carried by all 58 reports
  since — the oldest open High in the register). The client-facing coverage
  ratio read "measured across 235 of 272 discovered pages (86.4%)". The two
  figures are counts of two different things: the numerator is pages a check
  could actually read, the denominator is URLs the site's sitemap declares.
  "discovered pages" governed both while being true of only the second. The
  same noun did the same two jobs in the crawl-scope sentence, "6 of 272
  discovered pages fetched".
- **No figure moves.** 235, 272 and 86.4% are the same three numbers before
  and after; the ratio now reads "measured across 235 pages a check could
  read, of 272 the sitemap declares (86.4%)". That is the whole content of
  `QUESTIONS.md` **Q-14**, answered by the operator on 25 August 2026 — *close
  it, already satisfied by round 092, the ratio stays 235 of 272* — and this
  is that answer's own stated reason, "no word does two jobs", made true at
  the one clause where audit round 100 found it false.
- **The wording is the screen's, not new.** `dashboard/src/views.tsx` has
  rendered "against 272 the sitemap declares" and "272 declared pages this
  crawl reached" since the share caption was written. The document was the one
  surface that said "discovered pages" over both ends.
- `_scope` now writes `discovered_basis` beside `discovered`, the way it has
  written `pages_fetched_basis` beside `pages_fetched` since CQ-04, so the
  denominator's population is a stored fact rather than something each
  renderer decides. One value today — `sitemap` — and `None` where the site
  declared no total, which is the case the ratio is silent for anyway.

### Fixed — the section refresh no longer spends model tokens it never named

- **WF-59** (audit report 051, 18 August 2026, carried to 099). "Refresh this
  section" called itself "the smallest run that covers Headings" and sent
  `{"dims":["ONP"],"tier":"auto"}`. The dimension was genuinely the smallest.
  The depth and the spend were not: `auto` is the adaptive engine choosing its
  own tier up to T3, and the server read `analyst_enabled` as
  `body.analyst or body.tier == "auto"`, so **an adaptive run enabled the
  analysts regardless of what the caller asked for**. A press labelled
  "refresh" bought model tokens and said nothing about it.
- **API change.** `analyst` on `POST /api/sites/{id}/audits` is tri-state:
  omitted or `null` means "let the tier decide" — a manual tier runs no
  analyst, an adaptive one does, which is what every existing caller has
  always meant and what all of them still get. An explicit `false` now
  declines the analysts and leaves the breadth adaptive; `true` still forces
  them on for a manual tier. It was `bool` defaulting to `false`, and `false`
  was indistinguishable from unset, so a bounded adaptive run could not be
  asked for at all. `run_adaptive` takes the same flag, defaulting to `True`,
  and says in the progress log when tasks escalated and were declined — "no
  task escalated" and "a task escalated and the caller declined it" are
  different facts and the findings show neither.
- The control sends `analyst: false` beside the tier, and its words were
  corrected in the same change: it claims the smallest **dimension** rather
  than the smallest run, and the confirmation now names the depth it commits
  to (T1 pulse, escalation to T2 or T3 on the evidence), that it records a
  score on the site's history over the one dimension it ran, and that no model
  is invoked. The `SpendMark` is gone with the spend — `SpendMark` reads "This
  spends model tokens", which the run can no longer do, and a mark that fires
  every time is what F-10 clause 2 forbids. `QUESTIONS.md` Q-18.
- Breadth is deliberately unchanged: the band still escalates, the deeper
  crawl still runs, and a dimension at CRITICAL can still buy the paid
  provider calls its band authorises. Only the model spend was declined.

### Fixed — a narrower crawl no longer reopens the statement that it is narrower

- **WF-101** (audit report 099, 24 August 2026). A run is *required* to raise
  its own scope limits as findings — "Sitemap coverage not assessed, this
  audit was scoped to the navigation tier". Once raised, each is a row in
  `findings` with a fingerprint, a state, and every transition the state
  machine offers, so `_apply_states` recorded a narrower run re-raising one as
  `fixed → regressed`: a defect that had come back. Nothing had come back. A
  smaller crawl looked at less.
- Measured on the operator's site: the 24-page verify of 24 August moved nine
  findings that way and two of the nine were statements about that run's own
  narrowness. Read-only over the live database today, six of the 31 standing
  regressions are scope statements — all six of the `info` rows and none of
  the three `low` ones — so that site's next audit reads 25.
- The test is carried by the **emitter**, not inferred by a consumer:
  `Finding.scope_statement`, set at ten emitters. Severity was the obvious
  inference and it is wrong in both directions —
  `sitemap-coverage-not-assessed` is `info` and about the run,
  `sitemap-coverage` beside it is `low` and about the site.
- The line is *does this finding appear because of how the run was made — its
  scope, tier, crawl, keys, renderer, providers — or because of what the site
  contains?* `extractability-not-assessed` and `axe-render-failed` name a
  non-assessment and are deliberately outside it: both are raised by what a
  page contains, so a page that was server-rendered and stopped being so is a
  real regression and still fires.
- A re-raised scope statement stands `open`, never `regressed`. Stated as a
  state the finding is never *in* rather than an edge it never *takes*, so the
  rows the defect had already written can leave it; `accepted-risk` is
  untouched, as everywhere. `QUESTIONS.md` Q-21.
- No migration and no new column: the only consumer runs at emission with the
  result in hand. The `-not-assessed` suffix tests in `reporting/render.py`
  and `playbook.py` ask a narrower question and are unchanged, with a guard
  enumerating the two sets against each other from source.

### Fixed — a brief run against a second page no longer deletes the first

- **KI-56**, open since 24 August 2026. A page-scoped expert brief run against
  more than one page inside one audit run kept only the last page: every
  earlier page's findings were deleted and its report overwritten, with no
  message. An operator who briefed a second page lost the first silently.
- It had already cost a measurement. Both paid runs of 24 August were billed
  for three `onpage-hygiene` pages and stored one each, and the resulting
  catch rates of 0.60 and 0.80 were read as a difference between two models
  until the cache was replayed and both turned out to have caught it.
- Two causes, one per half, and they could not be repaired separately.
  `expert_reports` was keyed `(run_id, tool_id)` with the page outside the
  key, while `store_expert_report` writes `INSERT OR REPLACE`; and
  `record_expert_findings` deleted by `(run_id, dimension)`, which is the tool
  and not the page. Repairing only the first would have made calls equal
  reports and silenced the golden harness's caveat — which detects the loss as
  *more calls billed than reports stored* — while the findings went on being
  deleted with nothing left saying so.
- **`expert_reports`**: migration `0029_expert_reports_page_key.sql` puts
  `page_url` in the primary key, `NOT NULL DEFAULT ''`. Existing rows migrate
  to `''`, which is exactly the site-scoped case, so no stored row changes
  meaning — and `''` rather than NULL because SQLite treats NULLs in a primary
  key as distinct, which would stop a site-scoped row ever being replaced
  again. `QUESTIONS.md` Q-19.
- **`findings`**: no migration and no new column. The `EXP:` fingerprint is
  deliberately site-grained — whether a code afflicts this site is the stable
  fact, not which node exhibited it today — so a second page's findings are
  merged into the first's by code, pooling the affected URLs and joining the
  summaries, which is what a single call carrying both pages already did. A
  re-read of the same page still replaces rather than accumulates: each row
  records the per-page parts it was merged from, so one page's contribution
  can be withdrawn without touching another's. `QUESTIONS.md` Q-23.
- A brief read against three pages is now three stored results rather than
  one, so the price a brief is quoted at is a median over the work that was
  actually billed. `expert_delta` compares a site's two most recent *runs*
  rather than its two most recent rows, which those extra rows would otherwise
  have made the same run twice.
- Not yet: no screen offers the earlier pages. The stored-brief endpoint
  serves the newest page, which is what it served before — then because the
  others had been deleted, now because it asks for the newest of several.

### Fixed — a page refresh is offered only where re-reading a page can help

- **UX-39**, open since report 051 and carried by every report since. With a
  page filter set, every section offered `Refresh <section> for this page —
  Re-reads / and re-measures <DIM> against it`. For Backlinks that was false
  in every clause: OFP's coverage is read from backlink provider signals
  rather than from pages, so re-reading one page could not move any of it,
  and a narrow run skips every finding that names no page — which all ten OFP
  findings on record do. The control spent a crawl and a provider call to
  change nothing, and said the opposite.
- The offer now states whether a page is a unit it can be asked for, decided
  on the server from the engine's own `measured_per_page` declarations — each
  module saying, in its own file, whether any of its findings can be measured
  against a single page. **Not** decided from the section's grouping: AI
  surface and Local & citations both sit "beyond the site" and both raise
  findings against page URLs, and Speed, Mobile, Security and Indexability are
  all measurable against one page while sitting outside "on the page" as a
  heading — grouping would have withdrawn six controls that work to withdraw
  the one that does not.
- **The predicate was `coverage_from_crawl` first, and that was the
  neighbouring fact rather than this one.** It answers "can fetching more
  pages raise this dimension's coverage"; the control needs "can re-reading
  one page move one of its findings". Both sets contain OFP and nothing else,
  so the proxy gave the right answer for the wrong reason and could not be
  caught being wrong until a dimension was crawl-blind but page-capable, or
  the reverse. `QUESTIONS.md` Q-17 split them: all eight dimension modules now
  declare `measured_per_page` outright — never defaulted, because neither
  default is safe — each arguing its own case from its own checks, and
  `registry.page_blind_dims()` reads it. **No section's offer changes today**;
  what changes is that it is derived from the fact it is about.
- `tests/test_page_scope_is_declared.py` checks each declaration by parsing
  that module's own `Finding(...)` constructions, so it is derived from the
  tree rather than from a corpus. That matters for one dimension in
  particular: the sweep `tests/test_coverage.py` builds emits **0**
  page-naming PRF findings while the operator's database holds **47**, so a
  guard written against the fixture would have certified Speed
  un-page-refreshable and passed (`KNOWN_ISSUES.md` KI-55). The source
  reading gets it right, and that case is pinned as its own assertion.
- Where a page cannot narrow a section, the site-wide control stands with the
  filter on and says why in rendered text, rather than the offer vanishing
  and leaving the operator to work out why one section behaves unlike its
  neighbours. `POST /api/sites/{id}/refresh` refuses the same case with 422
  instead of billing for it; before this it answered 200, having crawled.
- Renderer and engine versions are deliberately unmoved: no stored
  deliverable's wording changes — this is an operator control and a route.

### Fixed — a fix-attempt mark can be withdrawn

- **WF-84**, open since report 067. Ticking a finding as fix-attempted was
  write-once. `POST /api/sites/{id}/states/{fingerprint}/attempt` recorded the
  mark; nothing removed one. In the dashboard, unticking a row deleted it from
  a browser `Set` and stopped there, and the button reading `clear these marks`
  did the same for a whole list — so on the next load `seed()`, which unions
  the server's stored `attempted_at` back into the tick set, put every cleared
  mark straight back.
- The mark is not cosmetic, which is why this is a High rather than a nicety.
  `attempted_at` is what puts a finding in the "awaiting a look" count and what
  prints `_(fix attempted)_` beside it in the client's deliverable, so a
  mis-tick the operator noticed and cleared still reached a client document.
- **New**: `DELETE /api/sites/{id}/states/{fingerprint}/attempt`, clearing the
  stamp and the note together and answering 404 on a fingerprint with no row —
  the contract `mark_attempt` beside it has always had, and the asymmetry WF-95
  closed on the state verbs. The finding's **state** is deliberately untouched:
  the mark is the operator's and the state is the run's, so withdrawing a mark
  cannot undo a verdict a crawl reached.

### Fixed — the score trend recovers the dimension set of runs stored before it recorded one

- **WF-58**, again. The change below put the measured dimension set into the
  comparability key and reached rows written after it — which is no row the
  operator has. Their whole stored history predates the term, so every point
  read `dimensions: null`, unknown compared equal to unknown, and two runs
  that measured six dimensions and seven were still asserted like-for-like.
  A fix for a finding about stored history had left the stored history in the
  state the finding describes.
- The set was never missing. Every measured dimension writes its own
  `{dim}.subscore` row at the same timestamp as the composite, in the same
  transaction, under the same predicate the frame's term is built from — so
  `site_trend` now reads the set back off those rows when the frame carries
  none. Nothing is written and no migration runs: a point that records its own
  set overrides nothing, and reverting restores every prior answer.
- **Each point says where its set came from** — `recorded` by the run, or
  `derived` at read time — and the History screen states it in the same
  paragraph that explains where the line breaks: *"The dimension set for 2 of
  2 points was recovered from the per-dimension scores stored beside it, not
  recorded by the run."* A derived figure that cannot be told from a stored
  one is a provenance breach even when it is right.
- **Two runs that finish in the same second are refused, not merged.**
  `metric_snapshots` carries no run reference, so a timestamp is the only
  handle, and merging two runs' rows would report a dimension set neither of
  them measured. Such a stamp reads unknown.

### Fixed — a score trend no longer joins runs that measured different dimensions

- **WF-58**, carried at High by every report from 051 to 097. `site_trend` is
  the one function whose stated job is to say where a comparison stops being
  one. It keyed on engine version, share basis and tier — three terms that say
  which engine measured, whether crawl breadth was applied and how deep the
  crawl went, and nothing about *which dimensions ran*.

  That is the largest population change the product can make, and it is one
  click away: a section refresh on the anatomy screen runs a single dimension.
  Reproduced against a migrated database when it was first raised — a composite
  of 91.0 over eight dimensions and one of 62.0 over one, same tier, same
  version, same basis, both `comparable: True`. The operator's own history
  already shows the shape: `8fdeb042` ran seven dimensions and `e4f998d1`
  eight, with only an engine-version change separating them on the chart.

  Every trend point now stores the dimension set it was measured over, and the
  key reads it. The chart breaks its line there, and the screen names the term
  rather than falling back to "the frame changed": a break now reads
  *dimensions dropped: A11Y, PRF*. Points stored before this carry no set and
  say `unknown` — comparable with each other and with nothing else, the same
  answer a pre-0022 point with no share basis already gets. Nothing is
  backfilled: a run's dimension set is not recoverable from a row that never
  recorded it, and guessing one would invent the population the fix exists to
  state.

  Deliberately not applied to the eight per-dimension series. `onp.subscore` is
  ONP's own score from ONP's own checks, so the dimensions beside it are not
  that number's frame; adding the term there would break eight charts at every
  narrow run for a difference their values do not carry. Not stored documents
  either — the trend report has never read `comparable`, so no deliverable's
  wording moves and the renderer stays at 1.30.0.

### Fixed — the price ledger says who stored each row

- **WF-33**, carried at High since report 033 and taken once already. Round 089
  gave `entered_by` a vocabulary and made `model_prices.refresh` demand one;
  CQ-200 closed the second writer, the typed-price route. Both held. What
  neither reached is the measurement in `actor_of`'s own docstring: the column
  had *two writers and no reader at all*, and it still had none. `GET /api/rates`
  put it on the wire — the route selects `*` — and the panel's payload type
  dropped it.

  So the Money card painted a row nobody is recorded as having stored exactly
  like one with an author: the Source cell read `published` either way, which
  is an attribution the stored row does not support. On this install that is
  every row — sixteen of sixteen carry no author, against one `entered_at` of
  17 August 2026.

  The cell now states both facts, `published · api:fetch-prices` or
  `published · no author recorded`, and the table carries a caption counting
  how many of its rows cannot be attributed. Nothing is backfilled: writing a
  plausible author into the empty rows would invent a provenance nobody
  observed, and a sentinel reads as an answer where NULL is honestly absent.
  Their `source` and `source_url` do record where the *figure* came from. Both
  controls that resolve it — **read Claude prices**, which replaces a published
  row with an attributed one, and **remove** — already sit above and beside the
  note.

### Fixed — a refused press reports where the operator is looking

- **UX-82's second clause**, the half round 087 closed the announcement of and
  said outright it was not claiming. The record screen pages its table at 50
  rows and paints a refused verb's message *above* it, so a press on row 40
  put the only report of its failure above a fold the operator had scrolled
  past. The `role="alert"` added in that round told a screen reader; it told
  the operator who pressed the button nothing, which makes what remained a
  sighted-operator defect rather than the general one the finding's wording
  suggests.

  Three mechanisms were available and the obvious one reverses a written
  decision, so it went to the operator as `QUESTIONS.md` **Q-8**: move the
  note into the row, bring the operator to the note, or take focus to it.
  Answered *bring the operator to the note*. `ErrorNote` gains an opt-in
  `bringIntoView` that calls `scrollIntoView({ block: "center" })` — no
  `behavior`, so it obeys the operator's own motion setting — and the record's
  refused-verb note is the single call site that passes it. **The paragraph
  does not move.** WF-95 put it above the table deliberately, because the row
  a press failed on may not survive the table re-reading, and that reasoning
  stands: the viewport comes to the note instead.

  **Opt-in on purpose, and named rather than left to be noticed**: the other
  40 `ErrorNote` call sites keep the old behaviour. They paint into a screen
  the operator is already reading — a fetch that failed before there was
  anything else on the page, a form's own note under the form — and scrolling
  for those would move the viewport for a message already in it.

  Read off the served bundle rather than the source: a verb pressed at the
  bottom of the record, with the route forced to 404, painted its message at
  **-3011px in a 600px viewport** before this change and inside the viewport
  after.

  No `RENDERER_VERSION` bump: no stored document's wording changes.

### Fixed — the honesty caveat stops calling a client's own phone number a figure the analyst invented

- **CQ-194**, carried at High since audit report 087, and the cost of the lever
  that closed CQ-09 one round earlier. A brief row whose number the deliverable
  cannot ground renders carrying `[TO CONFIRM: …]`, and the note it carried read
  *figure derived by the analyst, not measured*. One note is placed on two
  conditions (`clauditseo/reporting/generate.py:157-161`) and only one of them
  is about provenance: `figure_is_unverified` asks the brief whether **it**
  flagged the figure; the grounding half asks only whether this document's
  measured evidence contains the token. A brief's prose quotes the client's own
  site back at them, so the second fires on identifiers.

  **Measured read-only over the live database rather than estimated.** Of 275
  stored `EXP:*` findings, 33 are ungrounded, 31 of them newly marked, and **13
  are marked for an identifier rather than a figure** — `1300 922 223` on four
  rows, `[505 Toorak Rd]` / `[3142]` on two, an HTTP `200` on three,
  `foundingDate "2019"`, `Apache/2.4.52` and `HTTP/1.1`. The instance a reader
  can open:
  `reports/out/www-acme-com-au-run-client-2026-08-22-91f9ad50.md:295` tells a
  client that the phone number published on their own website "was not
  measured" by an analyst who derived it. That is not a caveat, it is a false
  statement, and it is printed on the one marker every true caveat in the
  document depends on being believed.

  **The wording changed and the gate did not.** The note now reads
  `[TO CONFIRM: not measured by this report]`, which is true on both conditions
  and true of an identifier the client published. It marks exactly the rows it
  marked before — the reach is unchanged and only the claim is — and it is
  still the `[TO CONFIRM` marker `unsourced_number_lines` and
  `ungrounded_uncaveated_lines` read off a rendered line, which
  `tests/test_the_caveat_is_true_of_an_identifier.py` asserts alongside the
  instance so a later reword cannot green the gate by accident.

  **Why not the other remedy.** `QUESTIONS.md` **Q-7** put the choice to the
  operator, who answered *change the caveat's wording* on 24 August 2026. The
  alternative — grounding a brief line against the evidence the brief itself
  was given — was measured to ground **0 of the 33**, because that evidence is
  stored nowhere: `expert_reports` keeps the model's prose, `findings.evidence`
  keeps `{confidence_stated, from_brief}`, `analyst_cache` keeps a
  `bundle_hash` and not the bundle, and the crawl HTML is not persisted at all.
  It would have been a migration, a write path and a storage decision that
  fixed no stored row. Widening `_EXEMPT` was refused on its own terms: every
  entry in an exemption list is a hole in the gate the whole provenance
  invariant rests on.

  `RENDERER_VERSION` moves 1.29.0 → 1.30.0, because every stored deliverable
  written by 1.29.0 or earlier states the old claim on each of those rows and
  must stay distinguishable from a regenerated one.

### Fixed — the operator's own logo reaches the tab and the admin panel

- **UX-30**, carried at High since audit report 034 and never selected, because
  it cannot be seen on a development install. `/api/brand` answers `icon_href`
  with `/api/brand/logo?v=<stamp>`, and two elements handed that path straight
  to the browser: the `<link rel="icon">` the tab reads, and the `<img>` preview
  beside **replace logo** in Admin. A browser loads a subresource by itself —
  a plain GET with no `Authorization` header — and every route in this product
  is guarded, so both were a 401. The tab kept the built-in mark and the panel
  painted a broken image, with nothing on either screen saying why.

  It appears only once a credential exists. `auth` grants full access when no
  config token is set and no operator holds one, which is every machine the
  feature was built and tested on; the moment an install has a token, the
  operator's mark stops arriving on the two screens that exist to show it.

  **The bytes are now fetched with the token and the element is handed an
  object URL.** `api.blob` is the same request path as every other call —
  same header, same `ApiError` — so there is no second way of fetching that
  could drift from the first, which is the shape of the original defect.
  The tab releases the URL it stops pointing at, and the panel's hook releases
  on unmount and on every change of logo. The server's decision is untouched:
  `icon_href` is still an href or `null`, and `null` still means keep the
  default.

  Nothing a stored document says changed, so `RENDERER_VERSION` stays at
  1.29.0. The logo in a deliverable is copied beside the file by
  `copy_logo_beside` and never fetched over HTTP, which is why documents were
  never affected.

### Fixed — the score movement says what frame each of its two figures was computed under

- **UX-86**, raised at audit report 092 and carried unmoved through 094, with
  the deliverable that reproduces it still on disk. `## Score movement` was the
  one section of the comparison document that asks a client to read a change
  over time, and the only section with no frame at all. On the pair in the
  operator's database — the pair two fix steps generated client documents for
  on 23 August 2026 — it printed *Baseline composite: 91.06* against *Current
  composite: 70.52* and nothing else. Baseline `8fdeb042` is **T2 over seven
  dimensions**; current `f80bc200` is **T3 over eight**, and A11Y was audited
  only by the current run. So an unknown part of a twenty-point fall is the
  dimension that was added rather than the site getting worse, and the page
  said nothing either way.

  The two scope sentences round 090 and this round's predecessor added do not
  cover it. They frame the four issue *counts*, and the baseline one scopes
  itself in its own words to *New issues and Resolved issues* — which tells the
  reader not to apply it to the scores four lines below.

  **The section now states its frame above the two figures**, the placement
  rule WF-02 established for the counts: both tiers, both dimension counts, and
  any dimension only one of the two runs audited, named in either direction.
  Where the tiers and the sets agree it says so, because an absent sentence
  would otherwise carry the meaning "comparable" by silence. Where a run
  recorded no tier or no dimension set it says that instead of inventing one.

  **The second half was framing that was present and pointed the wrong way.**
  A composite carries a coverage ratio only where its run recorded enough to
  compute one, and on the measured pair that is the *more* complete run — so
  *measured across 235 of 272 discovered pages (86.4%)* sat on the current
  composite and the run that read 99 paths and skipped accessibility was the
  unqualified one. Where exactly one of the two carries a ratio, the section
  now says why the other has none, and says it per cause: a run that reached
  every page its site declared is silent for a reason that *is* completeness,
  and one sentence over both causes would be false for one of them.

  **Both reports give that cause as *the baseline stored no sitemap total*,
  and measured against the database it is a rung further back.** Read-only
  over `data/clauditseo.db`, `8fdeb042` has `has_evidence` False and `scope`
  None: it stored no crawl record at all. The served document says so — *Only
  the current composite carries a coverage ratio: the baseline run stored no
  crawl record.* Had the four causes been collapsed into the one sentence the
  finding's wording implies, the deliverable would have printed a false reason
  for the very run the finding was raised on.

  **What it deliberately does not do.** It makes no claim about what the
  movement means. `QUESTIONS.md` **Q-13** asked whether a section comparing two
  runs that are not comparable should print both composites framed, or decline
  to print a movement and say why; the operator answered **print both, framed**
  on 23 August 2026. The document states the facts and leaves the inference to
  the reader, which is the answer as given — and a later change that adds the
  inference is reversing an operator decision rather than improving a sentence.

  **WF-58 is released by the same answer and is not fixed here.** It has said
  since report 051 that `site_trend`'s comparability key — `(engine_version,
  basis, tier)` — cannot see the dimension set, so a composite over eight
  dimensions and one over seven at the same tier still come back `comparable:
  True`, and `render_comparison_report` still never asks it. This change states
  the terms; giving the judgement one owner both the chart and the document
  call is the next step. Report 094 ranks it as item 7 at size M.

  Renderer 1.29.0, so every comparison document written before this is marked
  superseded on the operator's register: the two on disk for `www.acme.com.au`
  print the unframed movement this closes.

### Fixed — a replayed brief says how much of its figure list it is showing

- **CQ-162**, open since audit report 085 and gated on an operator decision
  until now. A brief that is recalled rather than re-run is served from
  `analyst_cache`, and the replay used to take the spot-check list and the
  withheld count straight out of the stored payload and rebuild the total
  from those two. Thirty-eight of the forty-seven payloads in the operator's
  cache were written before the withheld count existed, so for those the
  total came out equal to the shown length — and the panel's sentence only
  draws when the total exceeds it. An over-cap brief replayed forty figures
  with no sign that any had been withheld, on the one panel whose instruction
  is to spot-check before quoting to a client.

  All three numbers now come from one re-judgement of the stored report
  against this run's evidence, which the replay already performed for a
  different purpose one statement earlier and threw two thirds of away. The
  panel reads *Showing 40 of the 55 derived figures this brief flagged*
  whether the brief has just run or has been recalled.

  **This rewrites `expert_reports.figures` where a re-judgement can be more
  than subtractive, and that is a decision rather than an implementation
  detail** — `QUESTIONS.md` **Q-2**, answered `rewrite on re-judge` by the
  operator on 23 August 2026. The cache is keyed on the hash of the evidence
  bundle, so a replay holds the crawl evidence and can ground a value again as
  well as drop one. Reading a stored brief cannot: the evidence is not kept
  beside the row, so `figures_still_derived` can only subtract, and it stays
  read-time-only with the stored row left as the operator's record of which
  briefs predate which rule.

  **Migration note.** `expert_reports.figures_withheld` is nullable, and
  migration 0027 gives NULL the meaning "never recorded" so that a zero is
  never invented for a brief nothing measured. That meaning is unchanged for
  rows already on disk. What changes is that a replay no longer produces such
  a row: it measures the count from the payload's own prose against its own
  evidence and stores the measurement, including a measured `0`. No schema
  change and no backfill — rows written before this land keep the NULL they
  have, and re-running or recalling the brief replaces it with a measurement.

  Nothing a rendered document says changed, so the renderer version is
  deliberately unmoved at 1.28.0.

### Fixed — the comparison document can be asked for from the screen that shows the comparison

- **WF-21**, carried by every audit report from 026 to 094 — sixty-eight of
  them, the longest-standing open High in the register after the three taken
  in the rounds before this one. ClauditSEO has rendered three report
  templates for its whole life, and the dashboard could ask for two. The
  comparison document was reachable only from the command line: the app's one
  control that *creates* a deliverable posts a single run id, and a
  comparison needs two, so its template menu offered `Run report` and
  `Monthly trend report` and nothing else.

  The Run comparison screen now offers **Generate comparison report**, with
  the same client/internal choice the single-run screen carries. It is the
  one screen in the product already holding both run ids, and it named the
  object — "Run comparison", four buckets of findings diffed between two runs
  — while offering no route to the artefact of it, which is the affordance
  invariant this project holds itself to.

  The control sits under the two sentences stating what the counts were
  computed against, so the scope is read before the document is asked for,
  and the document opens on the Deliverables route rather than rendering
  where it was made — producing and reading stay separate acts.

  Nothing about what a comparison document *says* changed, so the renderer
  version is deliberately unmoved at 1.28.0. Documents already on disk are
  unaffected.

### Fixed — what a score band means is on the screen, not in a tooltip

- **UX-07**, carried since audit report 024 and the oldest open High in the
  register. The composite is the product's headline number, and every screen
  drew it as a coloured mark and a figure — `● 84.2` — with the band word in
  a screen-reader-only span and the range that *defines* the band in a
  `title` on a non-focusable `<span>`. A keyboard reaches neither, so "84.2
  is good, and good means 80 or above" was mouse-only at all eight places the
  app shows a score.

  Every screen that shows a score now states the bands in text: *Score out of
  100: good is 80 or above, fair is 60 to 79, poor is below 60.* Nothing was
  moved into hidden text instead — the codebase's own invariant asks for
  rendered text, "not only in a tooltip or an `sr-only` element", and the
  guard fails if the key is hidden.

  The vocabulary now has one owner. The band word was already data and the
  range beside it was a three-way conditional inside the tooltip, so half of
  one vocabulary could be read by nothing else; both are fields of
  `SCORE_BANDS` now, and the sentence is built from it rather than written
  out, so a fourth band cannot reach a screen without its meaning beside it.

  No stored document changed, so the renderer version is deliberately
  unmoved at 1.28.0.

### Fixed — a comparison states the baseline it counted against

- **WF-28**, carried since audit report 023, and **UX-22**, carried since 019,
  which report 091 pairs as *"one residue seen from two sides"*. Renderer
  1.26.0 and 1.27.0 both frame the current run. Two of the document's four
  counts are not decided by the current run at all: a finding is **new** when
  the baseline was in a position to see it and did not, and **resolved** the
  same way from the other end, so both are decided by the baseline's crawled
  paths and audited dimensions.

  So `## New issues — 825` was printed with its frame nowhere on the page. On
  the pair in the operator's database the baseline run `8fdeb042` had crawled
  99 paths and recorded no sitemap total, which means it also printed no
  coverage ratio beside its own composite — 825 new issues against a baseline
  that had seen a fraction of the site, and nothing on the page said so.

  `compare_runs` had the values in hand the whole time: it calls
  `_run_scope(conn, run_a)` to decide those two buckets and wrote only run B's
  figures into the diff. It now carries the baseline's page count, path count
  and dimensions as well, and the document prints a second sentence naming the
  two counts it frames. A comparison stored before this version carries none of
  those keys, so its document says it could not establish the baseline's frame
  rather than leaving the reader to attach the current run's sentence to a
  count it does not describe.

  The grain rule from 1.27.0 binds the baseline sentence too, and both
  sentences are now built by one function rather than agreeing by inspection:
  a baseline stored before the evidence column has paths and no page count, and
  calling those paths "pages" would be the same wrong word one run over.

### Fixed — one count of what a run read, stated once

- **CQ-04**, first named in audit report 024 and carried by all 67 reports
  since, and **UX-84**, which is CQ-04 arriving in a client's hands. Two
  counts of "the pages this run read" are derivable from one stored run and
  every consumer was picking one:

  - `len(crawled_paths)` — the distinct **paths** the run touched. The
    Compare screen showed this, and `compare_runs` put it in the diff.
  - `scope["pages_fetched"]` — the **pages** a check could actually read.
    The coverage ratio beside each composite is computed from this.

  They differ wherever a site serves one page under two URL forms, and both
  are true. Renderer 1.26.0 put them **four lines apart in the same client
  deliverable**, both introduced by the word "fetched" and both tagged
  `confidence: high`. On run `f80bc200` of `www.acme.com.au` the document
  read *"the current run fetched 224 pages"* and, five lines down, *"measured
  across 235 of 272 discovered pages (86.4%)"* — a fee-paying reader's own
  document contradicting itself about how much of their site was read, with
  the larger of the two as the figure they would quote.

  The comparison now carries both counts and states one of them: the page
  count, which is the grain the coverage ratio's denominator is in, with the
  path count named as the separate quantity it is and only where the two
  differ. A comparison whose two counts agree says the number once. The
  screen and the document read the same two keys out of one payload.

- **The count that means "pages read" is no longer stood in for by the count
  of URLs tried.** `stats["eligible"]` is what the crawler records for "a
  page a check could read", and it has only existed since engine 0.9.0 — for
  every run stored before it, `_scope` fell through to `stats["fetched"]`,
  which counts **attempts**: a DNS failure leaves a page object, so three
  unresolvable URLs counted as three pages read. That figure is what the
  client-facing coverage percentage is computed from.

  The stored evidence keeps each page's status and content type, so the count
  is now derived through the one eligibility rule rather than assumed, and
  falls back to the attempt count only where the stored page list is short of
  the attempt count — a trimmed list, where counting it would understate.
  Every page count now carries, in one key beside it, which of the three ways
  it was arrived at: `recorded`, `derived` or `attempted`.

  Measured across the eleven runs in the operator's database before this
  landed: four record `eligible` and are untouched; the derived count agrees
  with the recorded one on all four; and on the seven without it the derived
  count equals the attempt count, because every page those runs fetched
  resolved. **No stored figure moves.** What changes is the run that resolves
  nothing, which until now reported every attempt as a page read.

### Fixed — a comparison says what it could see

- **WF-02**, first named in audit report 023 and carried by all 67 reports
  since. `compare_runs` has returned the comparison's own frame under a
  `scope` key since the round-023 delta added it, with a comment saying why:
  the diff carries the scope it was computed under, so no surface has to
  restate it and none can restate it differently.

  Two surfaces read that diff. The Compare screen took the scope and printed
  it. The **client document did not** — it printed four counts, "New issues",
  "Resolved issues", "Persisting issues" and "Not re-checked", with nothing
  anywhere on the page saying what the current run had actually looked at. A
  client reading "Resolved issues — 12" could not tell twelve fixes from a
  re-crawl of eight pages, which is the same error the "Not re-checked"
  section was itself added to remove — a 20-page follow-up to a 100-page
  baseline once reported 352 resolved where 5 had been re-checked.

  The comparison report now opens with the frame, before the first count it
  frames: `Comparison scope: the current run fetched 15 pages and audited
  OFP, PRF, TEC. (source: engine, confidence: high)`. One provenance tag at
  the end of the sentence rather than one per figure, the rule round 062
  established for the run report's scope line and for the same reason: what
  needs provenance is the claim.

  **A frame it does not have is stated, not skipped.** `pages_crawled` is
  `None` whenever the current run stored no crawl record, and printing that
  is how `None (source: engine, confidence: high)` reached a client once
  before. Where either half is missing the document says so in the shape the
  product already has — `Not assessed: … Reason: …` — and keeps the half it
  does have. Silence was the failure: a document that omits its frame reads
  exactly like one whose crawl was complete.

### Fixed — a price in the ledger says what put it there

- **WF-33.** Sixteen rows appeared in `model_prices` on 17 August 2026 with
  `entered_by = NULL`, no commit touching them and no row in
  `OPERATOR_ACTIONS.md`. They were still the whole table, and still
  unattributed, when this was measured again fifty-five audit reports later:
  `SELECT COUNT(*), SUM(entered_by IS NULL) FROM model_prices` → `16, 16`.
  Those prices sit underneath every cost figure the product quotes.

  Both write paths — `read Claude prices` and a hand-typed price — now record
  an actor in one vocabulary: `operator:<id>` when a person is identified,
  `api:<route>` otherwise. `refresh` takes it as a **required** keyword, so the
  next caller is asked the question rather than inheriting a NULL.

  **Why not simply "the authenticated operator".** That is what the audit
  originally prescribed and it would have closed nothing here. `auth` returns
  an operator dict *or None for full-access contexts*, and a stock install is
  one: one operator row, no token, no `CLAUDITSEO_TOKEN`, so every request runs
  in open local mode with no operator to name. Recording the route in that case
  is the honest answer to "what changed this row"; NULL was not.

  **The sixteen existing rows are not backfilled.** Nothing recorded who
  fetched them, and writing an actor into them now would invent the fact the
  finding is about. They keep their NULL until the next fetch overwrites them.

- **CQ-64.** `scripts/round-marker.ps1` assigned the marker's `kind` from the
  `-Kind` parameter unconditionally, against a parameter default of `round` —
  so a bare `-Phase <name>` update, which is what all four skills' own
  instructions tell them to run, preserved the subject, round, depth and start
  and silently relabelled the work. A plan in its second phase read back as a
  round, and because `exclusive` derives from the kind, a *note* kind
  (`investigation`, `backlog`, `fix`) became a lock nothing was obliged to
  clear. A kind that was not supplied is now inherited from the marker on disk,
  exactly as the subject always was; a `-Claim` still never inherits, because
  it may be displacing the marker it would be taking the kind from.

  Carried since report 033. KI-33 records why it stood: the script had no
  automated test and every documented invocation was exercised by hand. It has
  one now, running the shipped bytes in a throwaway tree.

### Fixed — a failure the operator asked for is announced, not just printed

- **UX-82.** `ErrorNote` is the dashboard's shared "that did not work" element
  and it rendered a plain `<p className="error">` — no `role`, no `aria-live`.
  It has **56 call sites across ten modules**, so every asynchronous failure
  the app reports reached a screen-reader operator as silence: a launch that
  was refused, a mark that did not save, a fetch that 503'd. WCAG 2.2 AA 4.1.3
  Status Messages, and outside what the accessibility sweep can find — axe has
  no rule for a status message nobody marked as one.

  The marking now lives on the component, `role="alert"`, so all 56 inherit it.
  Five hand-rolled error paragraphs implement the same rule and are marked
  with it: the sign-in failure (`App.tsx`), the client-report fetch failure
  (`deliverable.tsx`), the add-client form (`home.tsx`), the schedule dialog
  (`schedule.tsx`) and the brief-sweep report (`tools.tsx`).

  **Not changed, and named rather than left to be noticed**: the three screens
  that paint `budget.warning` — Admin, Home and Tools. Those render with the
  card they live in, from data fetched before paint, so an operator meets them
  as text in reading order; marking them assertive would make them interrupt
  on arrival, which is the shape the operator already answered on at
  `audits/DISPOSITIONS.md` Q3. They are registered in the guard by name.

  Read off the served bundle rather than the source: a site fetch forced to
  503 in a real browser painted `alpha is unavailable Try again` with
  `role=None` before this change and `role="alert"` after.

  **Still open, and this does not claim it**: *where* the message renders. The
  record screen pages its table at 50 rows and paints a refused verb above it,
  so a press on row 40 reports its failure off-screen. That is UX-82's second
  clause and is untouched.

  No `RENDERER_VERSION` bump: no stored document's wording changes.

### Fixed — narrowing the page advisor no longer removes the reasons its advice might be wrong

- **The rule was written down beside the tuple that broke it.** `ADVICE_ALWAYS`'s
  own docstring says these are *"what a recommendation rests on and the reasons
  it might be wrong. A view that dropped them would hand back a tidier answer
  with its caveats removed, which is the provenance invariant broken by the
  feature meant to make the answer easier to read."* It held four fields, and
  the two the system prompt reserves **specifically** for stating a limitation
  were not among them.

  `compliance_notes` — the field reserved for "medical, financial or safety
  outcome claims" — was dropped by **all three** scopes. `keyword_intent`,
  which carries `unverified_flags` for brand-coined categories, slogans and
  trademarked phrases, was in `content` alone, so a `title-desc` or `headings`
  answer recommended adopting page wording with the flag saying that wording
  is unverified removed. Both now ride along with every scope.

  Read at the running product against the operator's own stored advisory —
  `www.acme.com.au`, run `f80bc200…`, the one row in `page_advice`. Narrowed
  to `headings`, the reader now gets, verbatim:
  `"Zero credit checks" (heading) contradicts "No upfront credit checks"
  (body) — reconcile; an absolute no-credit-check claim is a misleading-conduct
  risk for a lender.` That sentence was removed by the narrowing until this
  change, on the page of the product's only real client, who is a lender.

  **The read cost nothing**: `GET /api/runs/{run}/advice` is F-04's read-back
  path, `SELECT COUNT(*) FROM cost_entries` reads 48 before and 48 after.

  `schema_notes` is deliberately **not** added, and the omission is stated in
  the code rather than left as an oversight: it is guidance, not a limitation
  on a recommendation, and adding it would widen the tuple from "the reasons
  this might be wrong" to "things it would be nice to keep".

  The guard that should have caught this was
  `test_a_narrowed_view_still_carries_its_caveats`, which asserted the two
  caveats that already survived and had been green for every one of the ~50
  reports UX-26 was carried through. It now has a sibling parametrised over
  `ADVICE_SCOPES` that asserts on the caveat **text** rather than a field name,
  so a fourth scope added without a caveat is red rather than silent, and the
  remedy is not encoded in the assertion. UX-26, report 033.

### Changed — the two screens an operator actually reads a brief on now say what the brief could not verify

- **The panel that states it was mounted in one place, and it is not one of
  them.** `ExpertPanel` has exactly one mount — `views.tsx:1506`, the run-page
  route. A stored brief is opened from the Analyses lane, at
  `analyses.tsx:558` and `:664`, and both sites rendered `ReportView` alone.
  So the count of derived figures a brief flagged, and the list to spot-check
  before quoting any of them to a client, existed on a screen an operator does
  not read briefs on and nowhere else.

  **Nothing new is fetched.** `GET /api/runs/{run}/expert/{tool}` has served
  `figures_to_verify`, `figures_withheld` and `figures_flagged` since UX-79
  (`clauditseo/persistence/runs.py:1760-1784`). Both read sites typed that
  response `{ report?: string }` and discarded all three at the type. No new
  data, no new endpoint, no prompt change — this is the field-dropped-by-the-
  panel shape (CQ-63) at two call sites.

  The block is now one component, `DerivedFigures`, with the response shape
  named once as `StoredBrief`, so the three consumers cannot come to disagree
  about what a stored brief carries. Read at the running product on
  23 August 2026, Analyses tab of `www.acme.com.au` on run `e4f998d1…`:
  `Showing 0 of the 1 derived figure this brief flagged — spot-check the brief
  itself before quoting figures from it.`, read verbatim from a real browser
  against the operator's own data on a screen that had never carried it.

  **It also puts the block under axe for the first time in its life.** The
  rendered sweep's `REVEAL["client"]` opens the Analyses lane and never opened
  the run-page panel, so `.figures-note`, `.figures-withheld` and
  `styles.css:495-502` had been read for their wording by one test and audited
  by no gate. Both classes were added to `MUST_RENDER` *before* this change
  and the coverage guard was seen to fail naming both; it passes now. What
  this does **not** close is the route-coverage half of CQ-153 — the run-page
  instance is still opened by no reveal step.

  Nothing a client reads changed and nothing on disk was rewritten, so
  `RENDERER_VERSION` is unmoved at 1.25.0. UX-03, report 086 remediation
  item 9; narrows CQ-153.

### Fixed — the one section of a client document the honesty gate never read

- **Gate G7 has two halves, and only one of them ever saw the specialist
  briefs.** `unsourced_number_lines` reads the whole document and passes the
  brief table trivially: every row carries a `provenance_tag`, which is a true
  statement about where the prose came from and no statement at all about
  whether the number in it was measured. The other half — the one that grounds
  a number against the audit's own evidence — reads `narrative`, which
  `_analyst_section` builds with `EXP:*` findings excluded by construction,
  while the brief section is appended to the document *after* that text is
  made. So the most expensive, most model-written, most figure-dense section of
  the deliverable was the one text neither half of the gate ever grounded.
  CQ-09, raised in report 024 and carried by every report since.

  This is audit 013's defect in the section its fix did not reach. Reproduced
  end to end before the change, with a brief finding reading `Organic sessions
  fell 47318 percent after the template change.`: it printed into a client
  document as `| high | brief-note | Organic sessions fell 47318 percent
  after the template change. | source: model judgement (m-1), confidence:
  medium |` — an invented figure, a true provenance tag, and no caveat.

- **The remedy is the caveat the product already has, not a refusal.** A number
  in brief prose the document cannot ground is exactly what
  `[TO CONFIRM: figure derived by the analyst, not measured]` says it is. The
  brief's own flagged-figure list cannot answer this: it was computed against
  the brief's crawl evidence on the day it ran, not against the deliverable's.
  So the row is marked when *either* the brief flagged the figure or this
  document cannot ground it, and a row satisfying both still says it once.

  **Measured read-only over the live database before the change**: of 275
  stored `EXP:*` findings across 6 runs, 244 ground cleanly against the
  deliverable's measured evidence, 31 quote something it does not contain, and
  **none of those 31 carried a caveat**. Those 31 rows are what moves. Nothing
  is rewritten on disk — the judgement is made at render, as
  `figures_still_derived` and `figure_is_unverified` already are.

  Two of the 31 are version strings — `Apache/2.4.52`, `HTTP/1.1` — which the
  gate's exemption list does not cover and which will now carry a caveat that
  reads oddly beside them. Recorded rather than fixed by widening the
  exemptions: every entry in that list is a hole in the one gate the provenance
  invariant rests on, and caveating an identifier is the safe direction to be
  wrong in.

- **The gate can still fail, which is the point.**
  `ungrounded_uncaveated_lines` reads the *rendered* prose and refuses a line
  whose number is neither grounded nor caveated — so a renderer that stops
  applying the mark is a red suite rather than a silent change to a client's
  document. That is the class UX-80 closed by deleting a `title` no guard could
  see. `_evidence_text` is deliberately not widened: audit 014 measured what
  the other direction costs.

### Added — two controls that retract and restore a finding on a client's record

- **`withdraw` and `reopen`, on the record tab of a site.** `withdraw` says the
  finding was never true: not a fix, nothing repaired, and nothing gets credit
  for one — a later run that sees it again puts it back. It is offered on
  `open`, `regressed`, `fixed` and `accepted-risk`. `reopen` puts a finding
  back among the ones counted against the site, from `fixed`, `accepted-risk`
  and `withdrawn`. Both write through `POST /api/sites/{id}/states/{fp}`, whose
  allow-list is now `runs.OPERATOR_SETTABLE_STATES` — derived from the same
  constant the model-blindness rule uses, rather than a hand-kept tuple, so a
  seventh operator-owned state is accepted without a second edit. WF-68.

  **Why this is a change worth reading and not a button.** `withdrawn` had been
  in the schema since migration `0023` and in every *reader* — the counts, the
  types, the state filter, the state's rendered meaning, the anatomy panel —
  and in no writer. Three screens named a state and nothing could reach one. Its
  own founding case was an audit that reached `www.acme.com.au` by a URL that
  could not be served and raised `not-https` and `robots-missing` against a
  site that is HTTPS and serves `robots.txt`: before `withdrawn` had a writer, a
  false finding could only be filed as one of two lies — `fixed`, which credits
  a repair nobody made, or `accepted-risk`, which records a decision nobody
  took.

  `fixed` stays refused by hand, with a 422 naming what the route will take. An
  operator setting it writes a repair claim no run gathered, which is the defect
  these controls exist to correct, reached through the product's own button.

  **What the verbs do not do.** `candidate` is offered none of them,
  deliberately: a finding seen once is not yet treated as a fact, so there is
  nothing to accept, retract or restore until a second run confirms it. A guard
  now carries that exemption as a written constant with the line that decided
  it, so a *sixth* state arriving verbless reddens rather than passing quietly
  (CQ-190 — it had been passing quietly, because the fixture wrote three states
  and 272 rows stood in the fourth).

- **The three verbs report a write that did not happen, and say what they do.**
  `set_state` was a bare UPDATE and the route answered an unconditional ok, so a
  fingerprint with no row returned 200 having written nothing; it now returns
  404, the way `mark_attempt` on the same resource always has. On screen the
  buttons disable while their POST is in flight and a failure is stated above
  the table instead of being swallowed while the table re-reads and looks
  unchanged. Each verb also carries what pressing it does — `withdraw` shipped
  beside `accept risk` with an explanation on one and nothing on the other, on
  every row it was offered on. WF-95, UX-81.

### Changed — one card spells the currency one way, and the frame says which way the total is wrong

- **The Admin card that teaches an operator how this product spells money
  spelled it two ways.** Every figure the dashboard draws reads `USD 3.00`
  through the owner, including each cell of the Model prices table — and the
  heading directly above those cells read `Model prices · $USD per million
  tokens`, with `input $/M` and `output $/M` beneath it. All three now name
  `MONEY_CURRENCY`, so the card cannot disagree with itself and the next label
  added to it inherits the answer instead of deciding one. UI-20.

  **The guard that confirmed the previous round could not see either shape.**
  `rendered_dollars` walks to a `$` and asks what follows, and yields only when
  what follows is `{` — so `$USD`, a dollar inside a word, and `$/M`, a dollar
  inside a quoted attribute it skips wholesale, both passed it by construction.
  A second detector now reads the shape that one cannot, enumerated over every
  `.tsx` and `.ts` rather than over the three sites this round knew about, with
  its own eight-case matrix beside it because two earlier versions of its
  sibling shipped green while blind. Regex end-anchors are why it needs the
  scanner's span bookkeeping rather than a regex of its own: `$/` appears
  seventeen times across `markdown.tsx`, `selection.tsx` and `home.tsx`, and
  every one is correct code.

- **The one word saying which way a money total is wrong left the screen.**
  Before UI-19, Tools rendered `— a floor: {n} of {m} entries priced`. UI-19
  collapsed three screens' sentences into `PricedFrame` — correctly; they had
  disagreed on weight — and `floor` did not survive the move, while the owner's
  own docstring went on stating its purpose as "so the number reads as a floor
  rather than as a total" for two reports. The word is back, inside the owner,
  so Tools, Home and Admin gain it in one edit. UX-80.

  Home also carried the sentence `so this figure is a floor` in a `title`
  attribute, four lines below a comment in the same file saying a `title` is
  "not a place an operator reads". It is gone rather than reworded: the frame
  now renders the direction, so the hover held nothing the operator was not
  already shown. The provenance invariant's own words — a stated limitation
  must appear in rendered text — are now guarded on this phrase across every
  `.tsx`, on the pattern the narrow-run guard beside it set.

  Read at the running product, bundle `HevQQmRX`, verbatim: Admin serves
  `Model prices · USD per million tokens` with placeholders `input USD/M` and
  `output USD/M`, and a scan of that screen's rendered text for a literal `$`
  before a letter or a slash returns nothing. Home serves
  `a floor: 14 of 48 entries priced`, and no `title` on that screen carries
  the floor sentence.

  Nothing a client reads changed, so `RENDERER_VERSION` is unmoved at 1.24.0.

### Changed — the Brief panel states a subset of a total it names

- **One sentence, two numbers, two rules.** The panel read `Showing the first
  N. M more derived figures are not listed here`, where `N` was the length of
  the list it had just painted and `M` was `figures_withheld` — a count
  computed when the brief *ran*, as everything the cap threw away. Since
  `14b4ebb` the stored list is re-judged on the way out, so `N` is a filtered
  subset rather than the first anything, and `N + M` is short of what the
  brief flagged by every value today's rule no longer derives.

  Measured read-only over `data/clauditseo.db`, 38 stored briefs: **11 lose
  values this way** — `js-rendering` 9 to 0, `content-gap` 8 to 1,
  `image-optimisation` 8 to 5.

  It now reads `Showing 6 of the 8 derived figures this brief flagged`. The
  total is `figures_flagged`, served from the same call as the list, so the
  panel asserts no arithmetic the server did not do. It is **derived and never
  stored**, on the precedent `run_expert`'s cache branch already records for
  `replay_underived`: a stored key would leave every row written before it
  replaying the defect, and this one needs nothing the row does not carry.
  `figures_withheld` keeps its meaning and its NULL — migration 0027's "never
  recorded" — and contributes nothing rather than an invented zero.

  **The block itself was gated on the list, so the worst case said nothing.**
  A brief whose figures all lapse painted no list, no total and no reason.
  Read at the running product on 23 August 2026 before the gate was widened:
  `js-rendering` on run `1d85ff71…` served nine flagged and none re-derived,
  and Playwright painted zero `.figures-withheld` elements. It now serves
  `Showing 0 of the 9 derived figures this brief flagged — spot-check the
  brief itself before quoting figures from it.`, read verbatim from a real
  browser against the operator's own data.

  Nothing a client reads changed and nothing on disk was rewritten, so
  `RENDERER_VERSION` is unmoved at 1.24.0. UX-79, report 085.

### Changed — the Brief panel judges a stored figure list by today's rule

- **A behaviour change to the screen the operator spot-checks from shipped
  with no entry here, and this register pointed at one that is silent.** The
  renderer-1.23.0 paragraph below says `14b4ebb` "extended the same read-time
  re-judgement to `expert_report` and `expert_report_figures` — the entry
  below records it"; the entry below it predates the change and does not
  mention it. This is that entry, written a round late. CQ-186, report 085.

- **What changed.** `expert_reports.figures` is what the extractor produced
  on the day the brief ran and nothing recomputes it, so the token boundary
  at round 081, the shared masking at 082 and the two vocabulary shapes at
  083 each reached the deliverable's caveat and neither route onto this
  column. `expert_report` and `expert_report_figures` now pass the stored
  list through `figures_still_derived` on the way out: subtractive only, and
  nothing on disk is rewritten — the stored row stays the operator's history
  and the only evidence of which briefs predate which rule.

  Subtractive is a property of what survives on disk rather than a caution.
  The brief's own judgement was every number the extractor saw less the ones
  grounded in the crawl evidence, and the evidence is not stored beside the
  payload, so a value today's rule would flag but the brief did not cannot be
  recovered. What can be asked is the half that needs only the brief's prose.

- **Measured read-only over `data/clauditseo.db`, 38 stored briefs and 189
  stored values.** The panel now serves **161** of them and drops 28; **11**
  briefs lose at least one — `js-rendering` 9 to 0, `content-gap` 8 to 1,
  `image-optimisation` 8 to 5, `content-brief` 8 to 6, `site-architecture`
  8 to 7, `entity-graph` 7 to 6. Of the 161 it keeps, **30** have their
  context sentence re-derived through the masked text, for the reason CQ-171
  gave: the locator may not point at an occurrence inside a span the
  extractor was blind to.

  An operator whose panel lost 28 values between two sessions can now read
  why here. Nothing a client reads changed and nothing was rewritten, so
  `RENDERER_VERSION` is unmoved at 1.24.0.

### Changed — the reference-rate confirmation counts what it lists

- **The sentence after "refresh reference rates" counted rows the operator
  cannot see.** It read `12 rates from ecb-via-frankfurter.`, where `12` is
  every currency the feed sent; the list immediately below it is the display
  currencies less the USD base, which on that same press is three clauses
  long. Nothing on the card said which number was the answer, and
  `RATE_SOURCES` holds two feeds of different breadths, so the number was not
  stable between presses either.

  It now reads `Wrote 12 rates from ecb-via-frankfurter. Listing 3 — the
  display currencies, less the USD base.` Both counts are stated and each
  carries the frame that makes it readable — the write, and the list. Neither
  is re-derived in the browser: `fx.refresh` returns `shown` beside `stored`,
  computed by calling `fx.reference_rates`, so one function owns what the
  panel can show and the count cannot disagree with the list it describes.

  The two are not bounded against each other in either direction, which is why
  the sentence does not say "3 of 12": a feed returning 170 currencies makes
  the write much the larger, and a feed answering with two currencies after an
  earlier press stored eight makes the listing larger.

  Nothing a client reads changed, so `RENDERER_VERSION` is unmoved at 1.24.0.
  UX-70, carried by reports 076 through 085.

### Changed — every money figure in the app is spelled one way

- **One month's spend was printed twice on one card in two spellings.**
  `clauditseo/money.py` rendered `USD 2.18`; `dashboard/src/components.tsx`
  rendered `$2.18 USD`. Both reach the Admin Spend card within four lines of
  each other — the server's budget warning, then the same month through the
  TypeScript owner. Compared over one value table there were three
  disagreements and not one: the currency word moved from prefix to suffix,
  the TypeScript `amount` put a `$` on the number half where Python's returns
  the digits alone, and Python grouped thousands where TypeScript did not.
  Rounding agreed.

  Every figure the dashboard draws now reads `USD 2.18` and `USD 1,234.50`.
  The prefix form won because `$` is the ambiguous half of `$2.18 USD` and
  `USD` the informative one — an en-AU operator reading a bare `$` has
  nothing telling them which dollar it is, which is the reason this
  repository already had on the record. Python's formatter is unchanged;
  TypeScript's moved to it.

  Guarded by a test that RUNS the TypeScript owner under node and compares
  its output with Python's, rather than reading both and asking each whether
  it names a currency — which is what the previous two guards did, and why
  they were green for eighteen rounds while the two disagreed. CQ-168.

- **The caveat that says a dollar figure is a floor now has one weight.**
  "n of m entries priced" was composed by three screens and each chose its
  own: Tools set it inside `<strong>` within a `p.error`, as loud as the
  budget warning it qualifies; Home set it as a muted note; Admin as a muted
  parenthetical. It is one component now, `PricedFrame`, and one class,
  `span.figure-frame`. UI-19.

### Changed — a digit run inside an identifier is not a number

- **`x509` no longer holds a `509`, and six consumers inherit it.** This
  shipped in the same window as renderer 1.21.0 and had no entry here at all
  until now — CQ-176, which is why it is dated to its own change rather than
  folded into a renderer version. `_NUMBER_TOKEN` in `clauditseo/numbers.py`
  had no boundary, so `x509` held 509, `FY25` held 25, `A11Y` held 11 and
  `hero-69a4e135.webp` held 0, 4, 42, 69 and 135.

  The boundary is an identifier SHAPE and was measured rather than chosen:
  letters BEFORE the digits, or digits again AFTER the letters, is an
  identifier; letters only at the end are a unit. Against all 38 stored
  briefs and the 35 documents under `reports/out/`, a blunt "any abutting
  letter" rule drops 579 numbers and this one drops 409 — and the 170 in the
  difference are figures with a unit or currency suffix (`0.7s`, `300ms`,
  `$5K`, `100vh`, `145k`). Dropping those would be worse than the defect and
  asymmetrically so.

  **Why it matters to an operator and not only to a test.** All six consumers
  reach the token through the same functions and so inherit the change —
  `analysts/base.py`, `analysts/expert.py`, `analysts/page_advisor.py`,
  `analysts/schema_advisor.py`, `persistence/runs.py` and
  `reporting/checks.py`. The last of those is the honesty gate, which decides
  whether a deliverable is written at all. So this changed what a generation
  refusal means, and until this entry the only record of it was a commit
  body: an operator meeting a newly refused document had nowhere to read why.

  Measured read-only over the operator's database: 13 of 189 stored flagged
  figures stop being figures — image-optimisation `135`, `20273`, `3744`;
  content-gap `01`–`07`; https-security `509`; eeat-analyst `25`;
  mobile-viewport `21`.

### Fixed — renderer 1.24.0

- **A client document warned that a number was unverified where there was no
  number.** Two rules decided that mark and only one of them knew what a
  number in prose is. `ungrounded_figures` masks caveat blocks, dates, times,
  standards references and heading levels before flagging a digit run;
  `_declares_a_figure`, which asks whether a finding's summary quotes one of
  those flagged values, read the summary with `extract_numbers` and no such
  rule. So `E.164` in a summary matched a stored `164`, and renderer 1.23.0
  printed `[TO CONFIRM: figure derived by the analyst, not measured]` beside
  `local-signals/nap-inconsistent` in a client document generated on
  22 August 2026. That summary quotes two phone numbers off the site and no
  derived figure at all.

  Both halves now read the same vocabulary, and the vocabulary itself gained
  the two shapes it was missing: the index of an ordered list or a numbered
  heading (`14.`, `## 12.`), and a two-part standards reference whose second
  half is digits (`E.164`, `H.264`, `X.509`). None of the three is a
  measurement.

  Measured read-only against the stored corpus. Over 38 briefs and 189 stored
  flagged figures, **15 stop being figures** — three occurrences of `164` in
  `E.164`, nine ordered-list
  indices in `js-rendering`, and three numbered headings in
  `site-architecture` and `content-brief`; uncapped extraction over the same
  briefs moves from 705 figures to 670. At the deliverable, the read-time
  fallback's marked set moves from **7 findings to 6**, and the one it drops
  is `local-signals/nap-inconsistent`.

  **Two numbers, one measurement, and this entry first published the wrong
  one** — CQ-182. It read "9 findings to 8". Nine and eight are the totals
  *including* the two rows that carry a stored `figure_unverified: true`,
  which the fallback branch does not decide; seven and six are what that
  branch decides, and it is the branch this change moved. Re-measured
  read-only over `data/clauditseo.db` at the corrected wording: 275 findings
  with `dimension LIKE 'EXP:%'`, of which 2 stamped true, 85 stamped false
  and 188 unstamped; the fallback marks 7 of the 188 without the masking and
  6 with it, and `local-signals/nap-inconsistent` is the one in the
  difference. Round 082's own fix commit and report 083 both say seven for
  this quantity, so the correction is towards what the other two registers
  already said rather than away from it.

  A caveat that fires without cause is not a smaller error than one that fails
  to fire: it teaches the reader to discount the mark, which costs the true
  instances renderer 1.23.0 won.

  **This entry said the panel was forward-only, and it is not any more.** It
  read: "`expert_reports.figures` is served back unrecomputed, so the Brief
  panel still lists `164` and the nine list indices until those briefs are
  re-run. Only the document's caveat is decided at read time." That was true
  when written and stopped being true at `14b4ebb`, which extended the same
  read-time re-judgement to `expert_report` and `expert_report_figures`. That
  is recorded under *the Brief panel judges a stored figure list by today's
  rule*, above — named rather than pointed at, because "the entry below" was
  the entry immediately following this one, which predates the change and is
  silent about it (CQ-186). Corrected rather than left, because a paragraph
  that disclosed a limitation honestly had become the register asserting a
  defect the product no longer has.


### Fixed — renderer 1.23.0

- **Renderer 1.22.0's fix below reached no run already in the database, and
  nothing said so.** `record_expert_findings` stamps `figure_unverified` into
  each brief finding's `evidence` when the finding is recorded, and
  `_expert_section` reads that stamp back; nothing recomputed it. So every
  improvement to the judgement — including 1.22.0's, which is the entry
  immediately below — applied only to runs made after it landed, while the
  documents an operator can generate today come from runs recorded before it.

  Measured read-only against the stored corpus: of **275** `EXP:*` findings,
  **188 carry no flag at all** (85 `false`, 2 `true`). Judged when they render
  rather than read back, **7 of those 188** quote a figure their own brief
  flagged as derived — `triage/brief-pricing`,
  `mobile-viewport/viewport-baseline-pass`, `site-architecture/blog-hub-shallow`,
  `render-blocking/lab-field-divergence`, and three under `local-signals`.
  Until now each printed into a client's document as a plain claim beside a
  `source: model judgement` tag that is true, which reads as though the number
  had been audited.

  The stored row is not rewritten. The judgement is made at read time, keyed on
  the flag being **absent** rather than falsy: a stored `false` was decided with
  the brief's uncapped figure list in hand, and re-deriving over it would
  replace a decision made at full width with one made at less.

  **Seven is a floor, not the answer.** All that survives on disk is
  `expert_reports.figures` — `figures_to_verify`, capped at
  `FIGURES_TO_VERIFY_CAP` so the operator's panel stays readable. The uncapped
  set needs the brief's `context`, which is not stored beside the payload, so a
  stored finding can only ever be re-judged at the narrower width. How many of
  the 188 are really derived is still unanswered, and answering it needs the
  brief context kept.

  One consequence worth stating, because the previous bump did not have it:
  regenerating a stored deliverable now produces a different document for the
  runs affected. At 1.22.0 the Deliverables screen marked thirteen stored
  documents "written by an older report renderer" and offered a regenerate that
  re-rendered from the same stamps and therefore changed nothing.

  Reported as CQ-161 in every audit report since 077.

### Fixed — renderer 1.22.0

- **A brief that flagged more figures than the operator's panel displays
  printed the surplus into the client's document as though they had been
  checked.** `ungrounded_figure_details` returns the first
  `FIGURES_TO_VERIFY_CAP` (40) flagged figures — a bound on how long a list a
  person is asked to spot-check — and `run_expert` handed *that capped list* to
  `record_expert_findings`, which decides `figure_unverified` per finding by
  asking whether the finding's summary quotes one of them. `generate.py` prints
  `[TO CONFIRM: figure derived by the analyst, not measured]` only when that
  flag is true.

  So the display bound decided which numbers a client is warned about. A brief
  flagging forty-five figures caveated forty of them and rendered the last five
  as plain claims, beside a `source: model judgement` tag that is true — the
  same shape as the confidence placeholder this file records at renderer
  1.14.0, where a correct-looking tag beside an unmarked number reads as though
  the figure had been audited.

  The cap stays; it is the right answer to "how long a list is readable". What
  changed is that the *judgement* is now made against every figure the
  extractor flagged, and only the *display list* is capped. The uncapped set is
  re-derived on a cached replay rather than stored in the payload, because a
  cache entry lives thirty days and is keyed on the prompts and the evidence,
  neither of which this change moves — so a stored key would have left every
  existing entry replaying the defect.

  Reported as CQ-08 in every audit report since 001; round 073 closed the other
  half of it by making the cap declare how many figures it withheld, which
  landed on the screen the operator reads and not on the artefact that leaves
  the building.

### Fixed — renderer 1.21.0

- **The first sentence of every audit document stated where its figures came
  from three times, in three identical parentheses, inside one sentence.** The
  crawl scope line read `Crawl scope: 6 (source: engine, confidence: high) of
  272 (source: engine, confidence: high) discovered pages fetched, 3 (source:
  engine, confidence: high) URLs blocked by robots.txt.` — one claim, one
  stored evidence row, one provenance, spelled out for each of the three
  figures it happens to contain.

  The honesty rule was never per number. `checks.unsourced_number_lines` walks
  the document **line by line** and flags a line that holds a metric-like
  number with no `source:` tag anywhere on it, so a single tag has always
  discharged the whole sentence. `m()` attaches provenance to one value, which
  is right for a table cell and wrong for a sentence, and applying it three
  times bought nothing the gate asked for.

  `_shared_cause_lines` had already settled this for the sentence beside it,
  with a comment saying so — *"One tag at the end of the sentence, not four
  inside it. The honesty rule is per line, and tagging every number turned the
  most quotable line in the report into something no one could read aloud."*
  The scope line now keeps the same convention its neighbour keeps.

  Measured through the running service, on the same run through the same
  route, before and after — `POST /api/reports` for blocked run `d02919eb`:

  | | before (round 058) | after |
  | --- | --- | --- |
  | scope line | `Crawl scope: 0 (source: engine, confidence: high) pages fetched, 2 (source: engine, confidence: high) URLs blocked by robots.txt.` | `Crawl scope: 0 pages fetched, 2 URLs blocked by robots.txt. (source: engine, confidence: high)` |
  | tags on that line | 2 | 1 |
  | tags in the whole document | 24 | 23 |
  | lines in the whole document | 66 | 66 |

  On a crawl that declares a total the reduction is three to one, which the
  guard covers across all five shapes the function renders — with and without
  a declared total, with and without an early stop, and the zero-page case
  whose `[TO CONFIRM: …]` line is a separate claim and keeps its own.

  Nothing the reader can check for themselves was removed: the figures, the
  ratio and the early-stop clause are unchanged, and the tag still sits on the
  line the gate reads. `tests/test_reporting_g7.py::test_the_scope_sentence_states_its_provenance_once`
  was watched failing first — `AssertionError: the scope sentence tags its
  provenance 3 times` — and asserts both halves: exactly one tag, and
  `unsourced_number_lines` still clean.

  Carried in the engineering cohort as *"scope line carries three provenance
  tags in one sentence"* since report 049, thirteen rounds. Taken by round 062
  under the cohort rule, and adjacent to what round 061 built: `provenance_tag`
  became the single place that decides what a tag says, which is what made
  "say it once" a one-line change rather than a rewrite.

### Fixed — renderer 1.20.0

- **The comparison document handed a client the operator's own setup
  instructions, naming a retired product.** `render_run_report` routes a
  `-not-assessed` check through `_not_assessed_line`, which rebuilds the
  sentence from structured evidence and never prints the stored
  `recommendation`; `render_comparison_report` rendered the same findings
  through `_finding_line`, which prints it verbatim.

  Measured rather than reasoned about. Four findings in the live database
  carry `Add AUDITDECK_PAGESPEED_KEY or AUDITDECK_CRUX_KEY for real CWV
  data.` — an environment variable naming the product this repository retired
  at round 016. Rendering one of them into each of the comparison template's
  four buckets produced **eight** occurrences of `AUDITDECK` in a single
  client document, at `  - What to do: Add AUDITDECK_PAGESPEED_KEY …`. After
  the change: **zero**, with the gap itself still stated four times, once per
  bucket — silence would let a client read an absent dimension as a clean
  bill, which is the failure `_not_assessed_line` exists to prevent.

  The route is one function, `_diff_line`, rather than a condition repeated at
  four call sites, so a fifth bucket routes correctly by construction. The
  internal copy is unchanged in substance: it still states the reason the
  dimension went unmeasured, which is the half only the operator can act on.

  Carried as UX-10 since report 019 and dispositioned to the engineering
  cohort at seventeen rounds. `.claude/DISCIPLINE.md` rule 3 names this exact
  pair in its own evidence — "the vendor leak in the run template but not
  comparison" — so the guard is written over every bucket the template
  renders, not the one a report cited.

### Fixed — renderer 1.19.0

- **A verification counted as an audit everywhere the rule had no SQL to
  live in.** The previous release gave "is this run a reading of the site"
  one owner, `kind_is_site_reading()`, and applied it to the twelve queries
  that spell their own SQL. Six readers do not: they call `list_runs()`, which
  returns the site's whole history, and the guard written to enumerate readers
  walks SQL string constants and cannot see a function call.

  What that cost, read from the running product rather than from the code.
  `GET /api/overview` returned `score: 70.52` for `www.acme.com.au` — a
  224-page audit — while `GET /api/clients/{id}` returned `latest_score: 86.2`
  and `run_count: 5` for the same site on the same page load, because it took
  the newest run of any kind: an eight-page verification. The History chat
  answered *"Latest run d4474b38 scored 86.2"*. The analyst's `query_history`
  tool handed the model that run's composite with no `kind` beside it. The
  escalation planner chose it as the baseline the next audit's tier is decided
  against, comparing six dimensions over eight pages with six over 224.

  `runs.site_readings()` is the Python twin of the SQL owner, and those five
  readers plus the trend deliverable's feed now call it. `list_runs` stays
  unfiltered and stays what the site's own runs table shows — hiding a
  verification from the history would make the crawl it performed unauditable.

- **The trend deliverable stated a run count its own table contradicted.**
  Carried in audit reports since round 019. "Completed runs on record: 5" sat
  above a four-row composite table, both tagged `confidence: high`, with
  nothing on the page reconciling them. The verification is now out of the
  count; an audit that produced no composite — blocked before it could crawl,
  or scored on no measurable weight — stays in it, because dropping it would
  hide that an audit was attempted, and the sentence explains the difference
  instead.

### Fixed — renderer 1.18.0

- **"Not assessed" had two definitions, and they disagreed.** `render.py` kept
  a hand-maintained set of three `-not-assessed` check ids; six modules each
  independently decide whether to emit one. `contrast-not-assessed` (a11y.py)
  and `sitemap-coverage-not-assessed` (tec.py) were both missing from the set,
  so each printed to a client document as a defect, under "What we found",
  with a fix instruction — for a page or section the crawl never measured.

  `extractability-not-assessed` (added by relay 025) carried the drift in the
  other direction: `Severity.LOW`, deducting up to 5 points, where every other
  `-not-assessed` check is `Severity.INFO`, deducting 0. The one check added
  after the pattern was established was also the one that broke it.

  `NOT_ASSESSED_CHECKS` is no longer a list to keep in sync. Membership is the
  check's own name — `playbook.py:480` already read the same suffix
  independently, and the guard now pins the two to agree.

### Fixed — engine 0.9.0

- **Six places counted "pages fetched" and none of them counted fetches.** A
  `Page` object survives a failed fetch — a DNS failure leaves one with
  `status=0` and an `error` — so `len(crawl_result.pages)` is the number of
  URLs *attempted*. It was written as a fetch count into `crawled_paths`
  (`engine/core.py`), `stats.fetched` (`crawler/crawl.py`, which
  `persistence/runs.py` renames `pages_fetched` and renders to a client),
  the CWV call gate and `pages_fetched` evidence (`modules/prf.py`), the
  verify endpoint's `pages` (`api/app.py`) and the CLI's page line.

  The correct measure already existed and was used by exactly one caller:
  200 with a `text/html` body, which is what `terminal_status` uses to file a
  run as blocked in the first place. It now lives beside `Page` as
  `page_is_eligible`/`eligible` in `crawler/types.py`, and every count that
  means "fetched" comes through it. `stats` gained `eligible` beside
  `fetched`, and `/api/sites/{id}/verify` returns `pages` *and*
  `pages_attempted`, because a caller asking "did this settle anything" needs
  the first and one asking "why not" needs the difference.

  Measured on two runs of the same unresolvable host, before and after:

  | | before | after |
  | --- | --- | --- |
  | `crawled_paths` | `["/"]` | `[]` |
  | `_run_scope` | `{'/'}` | `set()` |
  | evidence `pages_fetched` | `True` | `False` |
  | `providers_answering` | `["crux"]` | `[]` |

  Three consequences, all of them live. `compare_runs` reads `crawled_paths`
  as "did this run re-check that page", so a URL that failed to resolve
  counted as checked — the round-022 Critical class re-entering through the
  column added to close it. The client was told `the data source for this was
  unavailable during this run` for their own DNS failure, where the corrected
  line reads `the crawl fetched no page to measure`. And the CWV call gate
  spent a keyed provider request per provider on a host that did not resolve.

  One place deliberately still counts attempts: `modules/tec.py` asks whether
  the crawler *visited* a sitemap entry, where a 404 or a PDF was visited and
  calling it absent from the crawl would name the wrong defect. The reason is
  recorded at the line.

  No renderer bump. The renderer is untouched, and a stored document
  regenerated today produces the same text it did before, because the run's
  stored evidence is unchanged — only runs crawled by engine 0.9.0 differ.
  Bumping the renderer would have marked every stored document superseded
  when none is.

### Fixed — renderer 1.17.0

- **A blocked crawl was reported to the client as a limit of their audit
  tier.** `prf.py` computed one flag,
  `tier_permits_external = tier is not Tier.T1 and bool(crawl.pages)`, and the
  renderer mapped its false value to a single definite cause: "this audit tier
  does not call external data sources". That is true at T1. At T2 or T3 whose
  crawl fetched nothing it is false twice over — the tier does call out, and
  the real reason is that there was no page to measure.

  Live on stored data at the time of the fix: run `d02919eb` is `tier=T2,
  status=blocked` carrying `tier_permits_external=False`, sitting beside
  `1b1da5e5` at `tier=T1` carrying the same value. One document's sentence was
  true and the other's was not, and nothing in the stored evidence separated
  them. Nineteen rounds on the cohort register.

  The flag is now two — `tier_calls_external` and `pages_fetched` — and the
  renderer has a fourth true sentence for the fourth cause. The tier case still
  outranks the others, because with no call made, what is configured and
  whether it would have answered are both unknown.

  Five stored findings predate the split and carry only the old key. It is
  still read where the new pair is absent, so re-rendering a stored deliverable
  states what it stated: an old document and a fresh one remain comparable,
  which is the whole point of the version stamp.


Renderer 1.16.0. The comparison deliverable can be generated again — it could
not be, in either direction, since the reason lines were introduced.

### Fixed — renderer 1.16.0

- **The comparison document failed the product's own honesty gate and could not
  be produced at all.** Both reason lines — `not re-checked:` and, since
  1.15.0, `new to this record:` — stated the client's own paths as bare prose.
  `unsourced_number_lines` exempts a path only when it is backticked, so any
  URL containing a digit (`/blog/7-5m-for-smes`,
  `/success-stories/70k-line-of-credit`) read as an untagged metric, and the
  bare `(+N more)` suffix read as another. `assert_report_honest` therefore
  raised, `generate()` never returned a document, and `POST /api/reports`
  answered 500.

  Measured on a copy of the operator's own database, comparing a 20-page run
  against a 99-page one: **125 problems narrowing, 128 widening**, all from
  those two lines. The not-re-checked half had been broken since renderer
  1.13.0 and no test generated a comparison from runs of differing scope, so
  nothing caught it; 1.15.0 then copied the pattern onto the new side.

  Paths are now backticked — they are identifiers, which is what the gate's
  exemption is for — and the overflow count carries its own source tag rather
  than putting `source:` on the whole line, which would have exempted that
  line from the check permanently.

Renderer 1.15.0. A comparison stops reporting a finding as new to the site when
the baseline never looked at its page.

### Fixed — renderer 1.15.0

- **"New issues" asked whether the baseline reported a finding, never whether
  it looked.** `compare_runs` computed crawl scope for the later run and not
  for the baseline, so `new` was a bare set difference. On a widening
  re-audit — a 20-page first pass followed by a full 100-page audit — every
  pre-existing finding on the eighty pages the baseline never fetched was
  reported under `## New issues` in the client document, and in red on the
  compare screen. The product telling a fee-paying reader that the work made
  things worse.

  This is the mirror of the `Not re-checked` bucket added in 1.13.0, and it is
  the same question asked from the other end: a finding absent from the later
  run can mean that run did not look, and a finding present in it can mean the
  baseline did not. Each entry now carries `new_reason`, derived by the same
  ordered test the not-re-checked side uses — blocked, then dimension, then
  page — and absent on a finding the baseline was in a position to see, which
  needs no explaining and must not be qualified.

Renderer 1.14.0, engine 0.8.0. A comparison now refuses a pair from two
different sites, and asks one ordered set of questions of every finding instead
of two different sets depending on whether the finding named a page.

### Fixed — renderer 1.14.0

- **A comparison across two clients is refused rather than answered.** Nothing
  compared `site_id` — not the route, not `compare_runs`, and not `generate()`,
  which takes the *first* run's site for the document's heading. So a
  comparison deliverable spanning two clients was generable, and went out under
  one client's domain reporting the other's findings as resolved. Measured on
  the operator's stored data: of the 30 orderable run pairs, **28 were
  cross-site**, including the pair that returned eight resolutions — four of
  them accessibility findings — for a run whose dimension list held no
  accessibility. `compare_runs` now raises, so both the API and the deliverable
  path inherit one refusal; the route maps it to 422 as it already does for a
  blocked run.

- **One order of questions, asked of every finding.** The 1.13.0 entry below
  made the comparison ask what run B fetched, but applied the *dimension* test
  only to findings that named no page. A page-scoped finding took the path
  branch with no dimension test, so a finding whose dimension B never audited
  came back **resolved** as soon as B refetched its page — the ordinary case,
  not a narrow one. `_apply_states` had always refused exactly that, so the two
  rules 1.13.0 set out to unify disagreed in the opposite direction to before.
  The order is now blocked, then dimension, then page, for every finding.

- **A blocked run resolves nothing.** `complete_run` writes an empty JSON list
  for a run whose crawl was refused, and `"[]"` is a truthy string, so the
  scope read back as "fetched nothing" rather than as a reason to stop — and a
  site-level finding then only had to clear the dimension test, which a blocked
  run passes. This closes an entry open for twelve rounds that a previous
  commit message recorded as retired against code that did not close it.

- **A recorded empty crawl is no longer reported as an unknown one.** Stored
  evidence holding an empty page list returned "scope unknown", the value
  reserved for a run that never recorded its scope, against the docstring's own
  rule that unknown is not empty. The compare screen rendered the one run with
  a decisive answer as having fetched "an unrecorded number of page(s)".

### Fixed — renderer 1.13.0, engine 0.8.0

- **A run now records what it fetched, and the comparison asks it.** The
  1.12.0 entry below split resolutions from findings the later run never
  looked at, but it decided which was which by reading `finding_states` — a
  table holding one row per finding describing the state *now*. That was wrong
  in both directions: a third, later audit rewrote what an earlier pair's
  comparison said, and a five-value vocabulary meant `accepted-risk`, a
  finding the operator decided explicitly not to fix, was counted as fixed.

  `audit_runs.crawled_paths` (migration 0021) stores the paths each run
  actually fetched — a value `complete_run` always received and dropped. The
  comparison now asks that, so its answer depends only on the two runs being
  compared and cannot change afterwards. Runs stored before 0021 fall back to
  the page list in `crawl_evidence`, which is the same fact recovered rather
  than a different number substituted; where neither exists, nothing is
  reported as resolved.

  Each not-re-checked line now states its own reason — the pages this run did
  not fetch, or the dimension it did not audit. The section previously
  asserted one cause for a bucket with three, which was false for a page the
  run *had* fetched under a dimension it had not audited. The comparison also
  carries the scope it was computed under, so no surface has to restate it.

  Engine 0.8.0 because the stored run shape changed. A reader of a pre-0.8.0
  run sees the column absent, which means "scope not recorded" and never
  "fetched nothing" — those differ, and confusing them is the family of
  defects this closes.

### Fixed — renderer 1.12.0

- **A comparison no longer reports as fixed what the later run never looked
  at.** `compare_runs` was a bare fingerprint set-difference: absent from the
  later run counted as resolved. A narrower crawl makes almost everything
  absent, so on stored data a 20-page follow-up to a 100-page baseline
  reported **352 resolved** where **5** had been re-checked — the other 347
  sat on pages the run never fetched and were recorded `open` in the
  product's own lifecycle table the whole time.

  The comparison now asks that table, which already refuses to clear a
  page-scoped finding from a crawl that did not visit it. Findings absent
  because nobody looked are reported in their own **Not re-checked** section,
  in the document and on the compare screen, rather than counted as
  resolutions. A stored comparison written by 1.11.0 overstates what was
  fixed, by up to two orders of magnitude on a narrow follow-up.

### Changed — renderer 1.11.0

- **Which figures get the analyst-derived marker no longer depends on string
  sort.** The set was capped at eight and ordered by sorting the numbers as
  text, so which survived was decided by lexicographic accident. Measured on
  the operator's own briefs: 9 of 25 sat exactly at the cap, and `content-gap`
  spent all eight slots on section numbering (`0.5, 01 … 07`). Figures are now
  taken in document order — finding summaries first, because those are the
  lines the deliverable prints — and the cap is 40.

- **URL path digits are no longer reported as analyst figures.** Widening the
  scan in 1.10.0 pulled the findings index's fourth column, a list of URLs,
  into the figure extractor, which read it as prose: `/blog/2024/09/top-15-loans`
  yielded `2024`, `09` and `15`. The parser had already split that column into
  structured URLs. Introduced and fixed within one release, so no stored
  document is affected.

### Changed — renderer 1.10.0

- **The analyst-derived marker now covers figures stated only in a brief's
  findings index.** The scan that decides which figures are the analyst's own
  derivation ran on the report *after* the machine-readable index had been
  stripped out of it — and the index rows are exactly what the deliverable
  prints, so the one surface the marker exists to protect was the one surface
  the scan could not see. A brief whose prose carries no number and whose index
  row reads "Organic sessions fell 55501 percent" reached a client with that
  figure bare. It now renders `[TO CONFIRM: figure derived by the analyst, not
  measured]`.

### Changed — renderer 1.9.0

- **The analyst-derived marker now actually renders.** The 1.7.0 entry below
  claimed it landed in two places. It landed in neither: the flag it depends on
  was read out of a row every caller writes *afterwards*, so it was stamped
  `false` for good, and the Analyst-insights branch that would have rendered it
  keyed on a dimension that section excludes. A brief finding quoting a figure
  the analyst flagged now carries `[TO CONFIRM: figure derived by the analyst,
  not measured]` in the specialist-brief table, which is the surface those
  findings actually reach a client on. The figures travel as an argument now
  rather than being read back, and only the declared `value` is read — not the
  sentence it was quoted in, which used to admit every other number in that
  sentence.

- **The grounding gate no longer admits a brief's declared figures.** The
  widening was justified on the grounds that such a figure renders carrying the
  marker; it cannot, because the narrative it checks is built from a section
  that excludes brief findings. It covered no real case and let a fabricated
  figure through. Removed rather than repaired.

  Known gap, unchanged: the specialist-brief table is still outside the
  grounding check. The marker is what guards it today.

### Removed — breaking

- **Settings are read under `CLAUDITSEO_` only.** The pre-rename prefix was
  kept as a second lookup at 0.14.0 so an existing install would not go dark
  on upgrade; that window is now closed. An install still configured under
  `AUDITDECK_*` will read as unconfigured — every provider key, the API token,
  the database path and the port. **Rename the variables before upgrading**,
  or set the keys in Admin → Provider keys, which takes effect immediately and
  needs no restart.

  A name that half-works is harder to diagnose than one that does not work at
  all: with both prefixes live, an operator correcting one spelling could be
  answered by a stale value under the other, which is a failure that reads as
  the app ignoring their change.

  **The API token is the exception, and this entry originally understated it.**
  "Reads as unconfigured" is harmless for a provider key and is not harmless
  for `AUDITDECK_TOKEN`: an empty API token means *open local mode*, so an
  install that required a credential before the upgrade would have required
  none after it — an access control disappearing silently. The token is now
  **detected and refused** rather than ignored. An install still setting the
  old name gets 401 on every request, naming the rename, until
  `CLAUDITSEO_TOKEN` is set. Failing closed is deliberate: the admin panel
  cannot set this one (`CLAUDITSEO_TOKEN` is outside `secrets.MANAGED`), so a
  silent downgrade would have had no in-app signal and no in-app remedy.

  Also removed: `AUDITDECK_SECRETS_FILE`, `AUDITDECK_NO_ENV_FALLBACK` (both
  have `CLAUDITSEO_` equivalents), and the browser localStorage carry-over of
  `auditdeck:token` and `auditdeck:site`. Anyone who has opened the dashboard
  since the rename was migrated already; anyone who has not signs in once and
  re-picks a client.

### Changed — renderer 1.8.0

- The PRF not-assessed recommendation names `CLAUDITSEO_PAGESPEED_KEY` /
  `CLAUDITSEO_CRUX_KEY`. That string reaches a client comparison document
  verbatim, so this is a change to what a deliverable says and the renderer
  version moves with it.

### Changed — renderer 1.7.0

- **This entry was wrong when written — see renderer 1.9.0 above, which is
  where this actually landed.** Left in place rather than edited: it is what
  the release claimed, and the claim is the reason nobody looked again.

  An analyst finding quoting a figure the brief itself flagged for spot-checking
  renders `[TO CONFIRM: figure derived by the analyst, not measured]`, in both
  the Analyst insights list and the specialist-brief table. The analyst has
  produced `figures_to_verify` since the brief layer was built and the app has
  shown it; the deliverable did not, so the product held a correct answer to
  "which numbers here are unverified" and printed neither it nor a warning.
- The G7 grounding check is now given the deterministic evidence only. It was
  handed `run["findings"]` whole — including the model-judgement rows the
  narrative is written from — so it compared a text against itself. Audit 013
  reproduced a fabricated "Organic sessions fell 47318 percent" reaching a
  client document past a check that ran on every generation and could not fail.
  Declared analyst figures are admitted from the brief's own bundle and carry
  the marker above; nothing else was widened.

Renderer 1.6.0, engine 0.7.0. A run that measured nothing now says so, in every
document that can mention a score — and every report states what its crawl
actually reached, and how much of the site that was.

### Added

- **The composite states the breadth it was computed from.** "Composite: 94.23
  out of a possible 100" read identically whether it came from six pages or
  from all 272 the sitemap declares. It now reads "— measured across 6 of 272
  discovered pages (2.2%)", on the run headline and on both sides of a
  comparison, so the qualifier travels with the figure that gets quoted rather
  than sitting two paragraphs away in the scope line.

  The ratio itself, deliberately, and not `measured_share` — which is
  breadth-aware now and reads 0.0176 for the same run because it scales
  site-level signals that were measured in full. Understating is right for an
  internal figure and wrong in front of a client, who would read it as "we did
  2% of the job". Suppressed under the scope line's rules: no declared total,
  or a crawl that reached everything declared. The trend template states no
  breadth because its points come from `metric_snapshots`, which stores a
  value and no scope — asserted rather than assumed.

  No score changes. The composite is the same number it was.

- **The crawl-scope line states the ratio, not just the count.** A T2 audit of
  a real site with the page cap lowered fetched 6 pages of the 272 its sitemap
  declares, and the document said "6 pages fetched" — which reads as a small
  site rather than as two percent of a large one. The total was in the stored
  crawl evidence the whole time and stopped one function short of the
  sentence, the same shape as the scope line's own origin. It now reads "6 of
  272 discovered pages fetched, crawl stopped early (max_pages)". Only when a
  sitemap declared a total and it exceeds what was fetched: "6 of 6" would
  assert the site is six pages, and a crawl with no sitemap has no total to
  state.

  No score moves. Page coverage stays deliberately binary — "did we see the
  site", not "did we see all of it" — so a 6-page crawl of a 272-page site
  still reports coverage 1.0 for every page-derived dimension and composites
  as though it had seen everything. The sentence now says what the number
  does not.

- **`blocked`: a run that fetched nothing is no longer filed as complete.** A
  blanket `Disallow: /`, a 5xx on robots.txt, an unreachable host, or a crawl
  that retrieved only 404s and a PDF all end with no eligible page — no 200
  carrying an HTML body — and every one of them stored as `complete`. That is
  how a site nobody could retrieve acquired a scored client deliverable.
  Migration 0020 widens the status CHECK constraint; `runs.terminal_status`
  decides, in the one place a run now reaches a terminal state.

  It is a success, not a failure. The site answered, and "you may not look" is
  frequently the most valuable finding an audit can return, so the run keeps
  its findings, keeps `error` NULL, and stays the site's latest audit in
  `current_state` and the fix loop. Three things change around it: it writes
  no `metric_snapshots` row, gated at the writer rather than in each reader;
  `POST /api/reports` refuses it with 422 and says why; and the scheduler
  counts it as a crawl having happened, so a site that blocks every crawl is
  re-audited on its interval instead of on every tick.

  A reader of a run stored before 0.7.0 cannot assume `complete` means a page
  was read — which is what the engine version is for.

- **LOC stops describing pages it never fetched.** "No phone number found on
  any crawled page" and "No LocalBusiness structured data found on any crawled
  page" were raised, at medium severity, from zero crawled pages. Both are
  true only by vacuity and a client reads them as defects on their own site.
  The dimension now returns nothing when no page was fetched; the run's scope
  limit already states the fact once.

### Fixed

- **Every report opens with the scope of its own crawl.** `snapshot()` has
  always persisted pages fetched, URLs blocked by robots.txt and whether the
  crawl stopped early, and `_run_dict` reduced the whole blob to a boolean one
  function short of the renderer — so no document could say a crawl had fetched
  nothing, and a client could receive a scored report for a site never
  retrieved. `get_run` now assembles a `scope` dict alongside `has_evidence`,
  and the report header states it. A crawl that fetched no page raises that as
  its own scope limit rather than leaving the reader to infer it. Runs stored
  before engine 0.6.0 report `scope: None` — not recorded, which is never read
  as zero.

- **The coverage rule now reaches every dimension that depends on a page.** The
  previous entry claimed a run that fetched no pages no longer scores itself; it
  scored itself 91.67, because `page_coverage` was wired into three modules out
  of seven. LOC and A11Y are wholly page-derived and now report zero coverage on
  an empty crawl. PRF's lab half needs a page just as its field half needs a
  provider, so it no longer credits timings never taken. TEC keeps the 35% of
  itself that robots.txt and the sitemap answer in their own right, and drops
  the rest. A blocked crawl across all eight dimensions now composites to 90.0
  from TEC alone rather than 91.67 from four dimensions that measured nothing —
  and whether a site characterised by robots.txt alone should carry a composite
  at all is still open.

- **A run that fetched no pages no longer scores itself.** The page-content
  dimensions — ONP, CNT and AIS — reported `coverage: 1.0` on an empty crawl and
  `_eligible_pages` floored the denominator at one, so each landed on 100.0 at
  full weight and a site nothing was fetched from composited to 97.01. They now
  report the coverage they actually had; the weight mechanism that was already
  built for this redistributes the rest. `max(count, 1)` differs from `count`
  only at zero, so no run that fetched a page changes score.
- **A run with no measurable weight has no composite, not a zero.**
  `composite()` fell back to `or 1.0` when every share was zero, which turned a
  score that could not be computed into a confident `0.00` — the same defect as
  the 97.01, with the sign reversed. It returns `None`, `AuditResult` carries
  `float | None`, and `_snapshot_metrics` writes no trend point for a run with
  nothing to record. This path is reachable today: A11Y has a nominal weight of
  zero, so an A11Y-only run has no SEO composite and never did.
- **One vocabulary for an unassessed composite, across every template.**
  `None` was reaching the client document as `Composite: None (source: engine,
  confidence: high)` — a null wearing a high-confidence tag. `not_assessed(what,
  reason)` now owns the shape, and the run report, comparison report, monthly
  trend, chat summary and CLI all speak through it. The trend states its own
  reason rather than borrowing the run report's: it previously said "not enough
  completed runs" when there were two, neither of which had produced a score.
- **A crawl that fetched nothing clears nothing.** `_apply_states` guarded with
  `if pages and crawled and …`, so an empty `crawled` set made the condition
  falsy and every open page-scoped finding was marked `fixed`, then `regressed`
  on the next real audit. One robots-blocked run rewrote the fix history.

### Added

- `audits/` — one report per round from the `/audit-fix` loop, committed with
  the fix it produced. Rounds 001–006 found the three defects above.

## 0.14.0 — 14 August 2026

The release that renames the product, and the one where the client-facing
document finally argues its own case rather than enumerating everything the
engine noticed.

`__version__` also catches up. It read `0.1.0` through thirteen releases, so
the CLI banner, `/health` and the dashboard footer all named the first
version of the product while this file stood at the thirteenth.

### Changed

- **Admin is ordered by how often you need it**, rather than by the order the
  sections were written. Spend, then providers, then keys, then models,
  money, and finally the things set once — branding, operators, and the
  database controls, which are the most destructive on the page and no part
  of a normal day. Branding and operators share a row, since both are short
  and rarely opened; every other card carries a wide table, and squeezing
  those into half a screen would trade a tidy outline for a cramped table.
- **One provider table instead of two.** "Data sources" and "Do the
  providers answer?" listed the same ten providers and disagreed — the first
  said `configured` while the second said `refusing 403`, with an unrelated
  card between them, so an operator had to hold both in their head to work
  out that a present key was being rejected. Presence and liveness are two
  columns of one row. Whether the key panel can set a given provider, and
  where its value came from, are now decided on the server, so the two
  surfaces cannot describe the same provider differently.
- **The product is ClauditSEO.** The name was written out by hand in the API
  title, the crawler's user agent, the CLI banner, the dashboard shell and
  the page title; it is now one constant those all read, so the copies cannot
  drift apart again. `USER_AGENT` matters most of the five — it is the only
  one that reaches somebody else's server logs — and its test now asserts the
  constant rather than a literal, which is what would otherwise let a rename
  leave the crawler introducing itself under the old name.
- **The Python package is `clauditseo`.** 139 files moved, 957 occurrences
  rewritten, `data/auditdeck.db` renamed, and the console entry point and
  scheduled task re-registered. Environment variables are read under both
  `CLAUDITSEO_` and `AUDITDECK_`, so an existing install keeps its configured
  providers across the upgrade rather than going dark on every one of them.
- **The client deliverable leads with the plan.** It grouped by page, so a
  hundred lines reading "N of M images on /X lack alt text" was one finding
  restated a hundred times, and the substantive work was buried underneath.
  Findings are now grouped by what is wrong, evidence moved to an appendix,
  and provenance stamped per section instead of per line.

      127 kB -> 13 kB · 999 lines -> 143 · 503 provenance stamps -> 60
      238 findings -> 14 distinct issues

### Added

- **Provider keys are set, replaced and cleared from the admin panel.** They
  came only from the environment, so replacing a key a provider had started
  refusing meant a shell, a `setx` and a restart — which is why a rejected
  OpenPageRank key sat unfixable. Each service has a row: what is set, a box
  to replace it, a button to clear it. The store is a separate gitignored
  file beside the database rather than a table in it, so a database backup
  carries no credentials; it is plaintext and says so, with 0600 on POSIX and
  a broken-inheritance ACL on Windows, checked rather than assumed. A stored
  key beats the environment — the other order lets someone save a new key and
  still watch every request fail with the old one — and the screen says when
  it is overriding, and whether clearing hands back to the environment or
  turns the provider off. Values never come back: a key shows as its last
  four characters. Where to get each one is a link rather than an address to
  retype, opening in a new tab so a half-filled key box is not lost. Takes
  effect with no restart.
- **A client report generated with no operator name says so**, at the moment
  it is generated and above the document rather than below the file path. It
  warns and still produces the report: going out under the product name is a
  decision, not an error.
- **An operator's own name and logo on client reports.** An agency handing a
  client a document branded with its supplier's tool has the relationship
  backwards: the client is buying the agency's judgement, and which tool
  produced it is the agency's business. The two names are kept apart on
  purpose — the operator's own screens still say ClauditSEO, because an admin
  panel that lied about what it is running would be the one place they cannot
  debug from. The brand defaults to the product name, so an install that never
  opens the screen produces a headed document rather than a blank one.
  Uploaded logos are validated by content signature rather than by file name,
  and capped at 2 MB.

### Fixed

- **Two wrong numbers in the client deliverable, one root cause.** The
  headline counted findings and printed them as pages — and a finding is not
  a page, since `title-duplicate` raises one per group of pages sharing a
  title, so "on 2 pages" sat above a list of thirteen. Separately the plan
  read the engine's count, which counts distinct paths, while the finding
  list counted raw URLs; two URLs differing only by a query string made 99
  and 100 the same measurement. Neither was wrong on its own terms, which is
  what made them hard to see. `page_paths()` is now the single rule, in the
  engine beside the eligible count it has to match, and the list under a
  headline is the same sequence the headline counted rather than a second
  derivation that happened to agree. On the operator's own run, plan and
  findings now disagree on none of twelve checks, where six disagreed before.
- **"Ask every provider" asked three of ten.** The probe list was a
  hard-coded tuple. A Moz key was set, the button pressed, and no row
  appeared at all — leaving no way to tell "refused" from "never tried",
  which is the confusion the check exists to end. Moz and DataForSEO are
  probed now; the rest are listed with the reason they are not, since a
  probe that spends money or submits a URL is not a test. `not checked` is
  its own state and is coloured as one — showing it as "not configured"
  would claim a key is missing when it may be set and simply unasked.
- **Two stale admin captions.** The spend note named the old product's
  prefix, and the data-sources caption said keys live in environment
  variables only — written before the key store and false the day it
  shipped. Only half of that was wrong: "never in the database" is still
  true and is kept.
- **The client deliverable no longer names a third party and an HTTP status
  when a source is unavailable.** `openpagerank (403)` is the operator's
  problem to fix and names a service the client has no account with. The gap
  itself still appears in both documents, because a client not told a
  dimension went unmeasured reads its absence as a clean bill. Rebuilt from
  the finding's structured evidence rather than by editing the summary prose:
  a sentence assembled for one audience cannot be reliably unpicked for
  another.
- **Every PUT the dashboard made was rejected.** The request helper passed its
  own lowercase `content-type` and the shared builder spread it over the
  default `Content-Type` in a plain object; object keys are case-sensitive and
  header names are not, so both survived and fetch folded them into
  `application/json, application/json` — not a media type any parser accepts.
  Display currency, model price, tier model, brand name and site schedule all
  answered 422, which means the admin panel had never saved anything. Headers
  now merge through `Headers` with `.set()`, so an override overrides whatever
  its casing.
- **A failed save says so.** Two handlers had no error branch. Choosing a
  currency threw into nothing — no message, and no state change to re-render
  from, so the `<select>` kept showing the currency that had just failed to
  save and the next render anywhere in the card snapped it back, which reads
  as the value changing itself. Saving a model price was worse: it cleared the
  typed figure on the way past and said nothing, losing the input.
- **OpenPageRank was being asked at an address it left.** The service moved
  off domcop.com and rebuilt its API, and the old host is still up — answering
  every request, whatever the key, with `403 Invalid API key`. That is the
  worst way for an endpoint to retire: it names a cause that is not the cause,
  so the obvious response, checking the key and fetching a new one, could
  never work. Nothing about the call survived the move — different host,
  `Authorization: Bearer` instead of the `API-OPR` header, POST instead of
  GET, different field names in the reply — so the request shape is now
  pinned by tests rather than only the response mapping. Keys are issued at
  `openpagerank.keywordseverywhere.com` and start `opr_live_`; an older
  domcop key is not accepted, and the panel says so. The free tier also
  returns referring domains, which the old API could not answer at all, so
  that is read too. A domain the index has nothing on now reports nothing
  rather than an authority of zero — an absence of data is not a score.
- **A run cannot hold two findings with one fingerprint.** 469 findings
  against 462 distinct fingerprints, every duplicate a pair of URLs sharing
  one path. The fingerprint is `sha256(dimension:check_id:subject)` and the
  subject *is* the path, so two rows sharing one was the engine contradicting
  its own definition of identity — visible without opening anything, since the
  app's headline said 462 outstanding while the report listed 469. Findings
  are merged in the engine now, and merged rather than dropped: both URLs are
  real and the page has to be fixed at both. Same root cause as the earlier
  "/apply and /apply share 100% of their body text", which had been patched
  inside the duplicate-content check and only there.
- **The golden-set runner no longer writes to the live database.** Its `--db`
  defaulted to the production file, so a harness meant for fixtures had put
  six fixture clients on the operator's home screen. It now defaults to
  `data/golden-scratch.db` and refuses the live database outright.

### Development

- **CI runs the test suite across cores**: 223s serial to 52s under
  `pytest -n auto --dist loadfile`, 4.1x, with the same count passing either
  way. `loadfile` rather than the default `load` because it keeps every test
  in a file on one worker, so the speed comes from running files beside each
  other and never from reordering tests within one. Checked over three
  consecutive runs, since xdist redistributes differently each time and a
  suite with hidden order-dependence fails intermittently rather than never.
- **The Playwright browser is cached**, keyed on its version. Re-downloading
  ~150 MB on every run was the longest step in the longest job.
- The dashboard's own request builder now has tests. Everything else reaches
  the API through `TestClient`, so the code the browser actually runs had no
  coverage at all and a green suite proved nothing about it.

## 0.13.0 — 14 August 2026

Six days and seventy-seven commits behind, which for a codebase this insistent
on provenance was the one artefact that no longer described what it ships.

### Changed — engine 0.5.0, scores before and after are not comparable

- **Duplicate content means duplicate content.** `f.text` was every text node
  in `<body>`, so navigation, footers and award banners counted as content;
  the metric was containment against the *smaller* page, so any thin page
  whose text was mostly furniture scored near-total against anything sharing
  that furniture. Chrome is now defined by observation — a shingle on 60% or
  more of crawled pages is furniture, whatever tag holds it — and the metric
  is symmetric. On the operator's own site: 22 findings on 20 pages became 2
  on 100, and the survivors are real.
- Pages left with nothing of their own are reported as `template-only-page`,
  one per page rather than one per pair. Five identical pages used to produce
  ten findings for one problem.
- **Accessibility is reported, never scored.** Weight 0.10 to 0.0. The
  findings are still raised and A11Y still carries its own sub-score, but a
  weak ranking signal no longer moves an SEO composite by 10.9%.

### Added

- **Money.** Claude prices are read from Anthropic's published pricing page
  (`text/markdown`, parses without heuristics) rather than typed in; exchange
  rates come from the ECB. Every stored price records its source and date, a
  fetch never overwrites a price a human typed, and a kept price that
  disagrees with the published one is reported rather than silently kept.
- **Model choice.** Which model each tier runs on is chosen on Admin, with a
  recommended button, and a single brief can be pointed at a different model
  for one run without re-pointing the tier.
- **Prompt caching on the evidence bundle**, which was resent in full on every
  round of the tool loop. About two thirds off the bundle portion of a brief.
  Cache reads and writes are counted and priced as the separate buckets they
  are.
- **A golden evaluation set** whose labels are true by construction: a fixture
  with planted defects and deliberate traps, scored by page rather than by the
  model's choice of check id.
- **Client deliverables are openable.** Generated reports are listed and read
  back from where they were written, never regenerated — "what did we tell
  them" cannot be answered by making something new.
- **The Reports tab**: every brief produced for a site with its model, tokens,
  cost and worst severity, plus the audits that produced nothing.
- **The five-step rail** — audit, triage, analyses, fix and verify, client
  report — with per-step state and cost.
- **All three Core Web Vitals.** CrUX was returning INP and CLS on every call
  and only LCP was read. Findings now state whether they came from field data
  or a single lab run: on one page those disagreed by four times.
- Business type per site, which drives brief reasoning rather than labelling
  it, after a lender filed as "ecommerce" produced a report reasoning about a
  product catalogue that does not exist.

### Fixed

- **Fingerprint reads are scoped to the site.** `finding_states` is keyed on
  `(site_id, fingerprint)` and five queries joined on the fingerprint alone,
  so 13 rows of one client's record showed another client's URLs.
- **"No provider configured" told apart from "the provider refused."** Both
  error branches did the same thing, so a rejected key read as an absent one
  — the audit said no provider was configured while one was answering 403.
- **Analyses say how far behind they are.** All 23 were written against an
  audit three newer ones had superseded, and nothing said so.
- **"No dollar rate set" was false** when rates were set and the analyses
  simply predated them.
- Page counts count pages, not pair keys; a stored run's shape is pinned to
  its engine version by a test that fails when it moves silently.

## 0.12.0 — 8 August 2026

### Added

- **Accessibility as an audit dimension (A11Y).** Barriers a machine can
  decide from markup: missing `lang`, unlabelled form controls, links and
  buttons with no accessible name, duplicate ids, dangling aria references,
  positive `tabindex`, untitled frames, headerless data tables, no `main`
  landmark, and link text that describes the click rather than the
  destination. Scored, fingerprinted and tracked over runs like every other
  dimension.

  Nothing here duplicates an existing check. `img-alt-missing` and
  `heading-skip` stay with ONP and viewport zoom stays with TEC — all
  accessibility failures too, but raising them twice would deduct twice for
  one defect. The axe pass drops the same rules for the same reason.

- **axe-core 4.13.0, vendored** (`clauditseo/vendor/`, MPL-2.0, hash recorded
  and asserted by a test). Runs through the existing optional Playwright
  renderer to cover what HTML cannot answer — colour contrast against
  resolved styles, focus order, reading order. Absent the renderer the
  dimension raises `contrast-not-assessed` rather than letting an
  unreadable page score clean, and the note disappears the moment axe runs.

  The rendered pass samples rather than reading every page (1/5/20 by tier),
  spreads that sample across the crawl instead of taking the first N, and
  says how many it read. A page that fails to render is reported as
  unassessed, never as clean.

- **Contrast tests over the dashboard's own stylesheet** — token pairs in
  both themes, control boundaries at 3:1, plus a guard that every chip
  declares its own ink. Found eight failures on its first run.

### Changed

- Playbook phases renumbered: Accessibility takes slot 4, and structured
  data through reporting shift up one to 5–11.
- Control borders use a new `--edge` token that clears 3:1 against both the
  page and a card; `--border-strong` measured 1.74:1 and 1.57:1.
- Severity and sweep-status chips carry fixed hues with per-hue ink, rather
  than theme-dependent colours that dropped to 1.91:1 in light mode.

### Fixed

- `.tool-mark` set `color: #fff` after the severity block at equal
  specificity and silently overrode it, painting chips at 2.15:1 while every
  declared pair passed.
- `.seg-count` carried `opacity: 0.75`, blending a passing colour to 3.29:1.
  Neither of these is visible to stylesheet analysis; both were caught by
  running axe against our own dashboard, which is now clean on all three
  screens.
- Markup inside `<noscript>` is no longer checked for accessibility. A tag
  manager's untitled iframe is not a barrier anyone meets.

## 0.11.0 — 7 August 2026

### Added

- **Entity and knowledge-graph alignment (phase 4 complete).** The last
  structured-data tool: sameAs pinning, entity disambiguation, cross-page
  `@id` resolution and brand consistency, ending in corrected JSON-LD. The
  crawl supplies the site's other entity anchors, and any profile links
  observed in the markup are offered as **candidates only** — a wrong
  sameAs is worse than an absent one, so nothing is presented as a verified
  identifier. Routed to the deep tier: deciding what a node *is* is the
  whole task, and the output ships to a client's site.
- Phases 1 through 4 of the workbench are now complete: 25 of 39 tools ready.

### Fixed

- **Inline CSS was swallowing the page excerpt.** A WP Rocket used-CSS block
  consumed the entire budget before the `<body>`, so an entity audit of a
  real site saw no page content at all and said so. Inline CSS and non-JSON-LD
  script bodies are now emptied before the excerpt is capped, with the
  removal stated in the markup rather than hidden. JSON-LD is never stripped.
- Placeholder substitution matched only simple tokens, so a brief writing
  `{{EXISTING_JSONLD_OR_"none found"}}` had it left in the prompt as raw
  braces. Placeholders are now matched loosely and their inline defaults
  ignored, with a gate covering every page-scoped brief.

## 0.10.0 — 7 August 2026

### Added

- **Expert tools — phase 3 complete.** Three more briefs: **on-page hygiene**
  (nine fixed checks with copy-ready replacement title, meta and alt text,
  using the rest of the crawl as its duplicate comparison set),
  **site-wide cannibalisation map** (intent clusters with a
  consolidate/differentiate/leave verdict each), and **image optimisation**
  (formats, dimensions, srcset, lazy loading, CLS, with real byte weights
  measured by HEAD request rather than estimated).
- **Model routing by tier.** Every brief declares what the work actually is,
  and is routed accordingly: `fast` for applying a fixed checklist
  (on-page hygiene, mobile viewport), `standard` for analysis with judgement
  at the edges, `deep` where the judgement *is* the product (cannibalisation
  map, page advisor, schema auditor). Configurable via
  `AUDITDECK_LLM_MODEL_FAST` / `_DEEP`, overridable per run, and the tier and
  model used are shown on every report. The mobile viewport brief now runs on
  Haiku for roughly a tenth of the previous cost.
- Image markup capture (`loading`, `fetchpriority`, `decoding`, `srcset`,
  `sizes`, dimensions) across `<img>` and `<picture><source>`.

### Fixed

- **Briefs were asking clarifying questions into the void.** Each carries an
  interactive clarifier gate; run unattended, a question is not a pause but a
  wasted call and a report that never arrives. The framing now states plainly
  that nobody can answer, and that gaps belong in ASSUMPTIONS.
- **Editing a prompt file did not invalidate its cached reports**, so a
  prompt change appeared to do nothing. The expert cache key now includes the
  framing, the prompt file's contents and the tool's tier — this is how the
  bug above stayed hidden through a restart.
- Report figure-checking no longer flags identifiers and standards
  references (issue ids, WCAG success criteria, HTTP versions, heading
  levels) as unverified numbers.

## 0.9.0 — 7 August 2026

### Added

- **Expert tools — phase 2 complete.** Five more operator-authored briefs:
  **HTTPS and security headers**, **mobile viewport**, **site architecture
  and internal linking**, **hreflang and internationalisation**, and
  **migration and redirect mapping**. All eleven briefs now live in
  `clauditseo/prompts/`.
- **Operator inputs.** Briefs can declare context a crawl cannot derive —
  the redirect map being validated, intended locales, topic clusters,
  platform, a full TLS scan. The dashboard collects them per tool, operator
  values override derived ones, and a brief with a required input (the
  migration map) refuses to run rather than auditing the crawl as though it
  were a map.
- **More crawl evidence**: anchor text, `rel` and page region for every
  internal link (the architecture brief cannot assess anchor distribution
  without them), click depth computed across the whole graph, hreflang
  annotations, every viewport tag verbatim, retained security headers, and
  a host transport probe (negotiated TLS version, cipher, certificate
  expiry and SANs, and whether plain HTTP reaches HTTPS).
- Long briefs run in two phases along their own analysis/remediation seam,
  and `scripts/restart-service.ps1` restarts the scheduled task properly —
  `Start-ScheduledTask` on a running task is a no-op that silently keeps
  serving the old code.

### Fixed

- **Extended thinking was starving the report.** Reasoning tokens are billed
  against the same output budget as the answer: a long brief spent 24,254 of
  its 28,000 output tokens thinking and returned a truncated report, or none
  at all. Procedural briefs — fill this specified format — now run with
  thinking disabled and get the whole budget for the report. The
  deliberative tools (page advisor, schema auditor) keep it.
- The transport probe checked port 80 for sites served on an explicit
  non-standard port, blocking until timeout. It now skips the HTTP upgrade
  check there and says why, which also took the test suite from 224s to 63s.

## 0.8.0 — 7 August 2026

### Added

- **Expert tools — phase 1 complete.** Operator-authored specialist briefs
  live in `clauditseo/prompts/` and run against real crawl evidence through
  one generic runner, so adding a specialism is a prompt file plus a
  registry line rather than bespoke code. Phase 1 ships four: **crawl
  health**, **indexability directives**, **URL and parameter hygiene** and
  **JavaScript rendering**. Reports are markdown, rendered as the brief
  specifies rather than forced through a JSON schema.
- **Crawl evidence capture.** The crawler now records what findings cannot:
  the internal link graph (inlink counts and sample sources, so orphans are
  detectable), per-sitemap fetch outcomes including sitemap-index following,
  `X-Robots-Tag` headers, `Link` header canonicals, the parameter space, and
  the URL forms that collapsed onto an already-fetched page. Each run stores
  a compact snapshot (derived facts, no page bodies) so expert tools run
  against a completed audit without re-crawling.

### Fixed

- **The crawler fetched the homepage twice.** A link to the bare origin
  (`https://site.com.au`) and the start URL (`https://site.com.au/`) were
  treated as different pages, producing a phantom "100% duplicate of itself"
  finding, double-counting every homepage check, and skewing the
  `eligible_pages` denominator that rate-based scoring divides by. URLs are
  now normalised for the crawler's own bookkeeping — scheme and host case,
  default ports, empty path, fragment — and pages are deduplicated by their
  final URL after redirects. Path case and query strings are preserved
  because they can genuinely address different content.
- Written briefs were delivered JSON-encoded, so every newline reached the
  model as a literal `\n`. Text payloads are now sent as text.

## 0.7.0 — 7 August 2026

### Added

- **Real structured-data validation (engine 0.3.0)**. ONP previously only
  checked that JSON-LD *parsed*. It now parses the graph (expanding `@graph`
  and arrays) and validates it: Google-required properties per type,
  "at least one of" sets, recommended properties, untyped entities,
  duplicate `@id` references, and rich-result types Google has deprecated
  or narrowed. LocalBusiness subtypes inherit LocalBusiness requirements.
- **Schema auditor (SCHEMA-J)** — on-demand per page, findings before fixes.
  Part 1 diagnoses (verdict per rich result, current state, content
  readiness, property validation table, severity-ranked issue register);
  Part 2 supplies corrected paste-ready JSON-LD, a fix map, required on-page
  changes, implementation steps and re-validation instructions. Split across
  two calls because a full validation table plus a complete JSON-LD document
  cannot fit one output budget — and a truncated audit is worth nothing.
  Values the page does not show come back as `[TO CONFIRM: property]`.

### Fixed

- **Advisors could recommend dead markup.** A page advisory suggested
  FAQPage "to capture rich-result eligibility" — markup Google restricted to
  authoritative government and health sites in August 2023. Deprecation
  facts now live in `schema_rules.py` as tested data, are supplied to the
  model as authoritative evidence, and an eligibility claim for a deprecated
  type is caught at ingest however it is phrased.
- The analyst loop collapsed every non-tool stop reason to `end_turn`, so a
  model that exhausted its output budget looked identical to one with
  nothing to say. The API's real stop reason is now reported, which is what
  made the two failures above diagnosable.
- Provider HTTP calls used a flat 120-second read timeout, which killed long
  structured answers mid-reply and surfaced as a 500. Timeouts now suit the
  work, and provider failures return a readable envelope instead of crashing
  the endpoint.
- The test suite read the developer's own API keys through the Windows
  registry fallback, so "this provider is unconfigured" assertions passed or
  failed depending on whose machine ran them. The suite is now hermetic.

## 0.6.0 — 6 August 2026

### Added

- **Page advisor (PAGE-J)** — the first prescriptive analysis in the suite.
  Where the deterministic ONP checks report that a page *has no* H1, the
  advisor recommends what the H1 *should say*: triage on four axes
  (commercial, multi-page, YMYL, search-facing) decides depth, then it
  returns the H1, title tag, meta description and the answer line beneath
  the heading, with ranked alternatives, site-role and cannibalisation
  calls, keyword/intent verdicts, schema and compliance notes. On demand,
  one page at a time, budget-capped and cached. It fetches the page live
  and may pull a sibling with `fetch_page` to verify a cannibalisation
  claim before asserting it.
- **Run view rebuilt around causes**: a headline score with the dimension
  table, the analyst priority plan promoted to the top, findings grouped by
  check with affected pages collapsed underneath ("136 pages · likely one
  shared cause") instead of one flat row per occurrence, and a per-page
  drill-down that hosts the advisor. The flat table is still one click away.

### Fixed

- Number-grounding compared JSON-escaped text, so an em dash (`—`)
  was read as the figure 2014 — any Australian-English prose could be
  rejected as fabricating numbers. All number comparisons now serialise
  with `ensure_ascii=False`, with a regression test.
- The no-new-numbers rule now applies to copy destined for the page
  (headings, title, meta, answer line) rather than to editorial rationale,
  where craft guidance such as character counts is legitimate and was
  causing whole advisories to be rejected.

## 0.5.0 — 6 August 2026

### Changed — external review response

- **Rate-based scoring (engine 0.2.0, HISTORY-BREAKING)**: per-check
  deductions now scale with the share of eligible pages affected, capped at
  a per-severity ceiling; site-level findings still deduct flat. Real
  100-page crawls no longer floor dimensions at 0, T1 and T2 runs of the
  same site score within tolerance (new gate), trends and adaptive banding
  operate on meaningful numbers. Scores predating this version are not
  comparable; snapshots now record their tier (migration 0003).
- **Injection defence moved with the agentic loop**: pages fetched by the
  `fetch_page` tool are scanned like bundle extracts — instruction-like
  text is stripped from the tool result, an explicit warning is attached,
  and a SEC finding joins the run (new gate).
- **No-new-numbers is token-grounded**: numbers validate as whole
  normalised tokens against an allowed set, not substrings — a fabricated
  "43" is no longer grounded by a "1043" inside a hash or count (new gates
  in G5 and G7 paths).
- **Analyst cache is versioned and expiring**: the key includes a hash of
  every prompt, rule and tool definition (any change auto-invalidates), and
  entries expire after 30 days.
- **Run execution hardened**: SQLite busy_timeout, at most 2 concurrent
  audits, interrupted runs marked failed on server start, failure reasons
  in their own column and shown in the UI.
- **start_url containment**: audits may only target the site's own domain
  (or subdomains); private/loopback hosts are rejected unless
  `AUDITDECK_ALLOW_ARBITRARY_START_URL=1` (the staging escape hatch).
- Bundle extract caps scale by tier (T3: 25 pages × 2000 chars) and
  extracts are selected by relevance to the task's dimension, not crawl
  order. Report filenames now carry site, template, audience and date.
  Optional `AUDITDECK_MODEL_PRICES` converts token spend to dollars in the
  cost log — operator-supplied, never invented.

## 0.4.0 — 6 August 2026

### Added

- **Adaptive tiered audits (tier "auto", now the default)**: deterministic
  results decide what runs next. A free T1 pulse scores every dimension;
  bands (healthy ≥95, watch 80–94, concern 60–79, critical <60 — operator
  configurable via AUDITDECK_BAND_*) decide escalation. Healthy dimensions
  stop at pulse; anything below triggers one escalated crawl (T3 when
  critical, else T2); final scores decide which analyst tasks run
  automatically (CONCERN and worse, PRI-J whenever judgement ran), within
  the existing token ceilings. Paid providers are enabled only for
  dimensions whose CRITICAL band authorises the spend. Overrides:
  regressions escalate regardless of score, a critical finding lifts one
  band, and hysteresis stops re-spending on dimensions unchanged since the
  last deep run. Every escalation is recorded as an info finding carrying
  its reasons. Pure-function policy engine (engine/staging.py), gated by
  unit tests on every band/override plus an end-to-end fixture proving a
  75-scoring Content dimension gets its analyst while a clean On-Page
  dimension stays at pulse.

## 0.3.0 — 6 August 2026

### Added

- **Agentic analyst loop**: analysts are no longer single-turn. Three tools
  are exposed to the model via the Messages API `tools` parameter —
  `fetch_page` (audited host only, robots honoured, per-run fetch budget),
  `run_check` (re-run one dimension against one URL), `query_history`
  (read-only runs/trend/states) — and a loop executes tool_use blocks,
  feeds `tool_result`s back, and continues until the model stops on its
  own, the token budget is spent (enforced inside the loop), or the round
  cap trips. Bad tool calls become `is_error` results the model can react
  to, never exceptions. Successful tool results carry citable evidence ids
  (t0, t1, …) and their text joins the no-new-numbers evidence pool. The
  cache now stores post-validation findings so tool-grounded results
  replay token-free. Scripted-response tests drive the loop with zero
  network: tool round-trip, budget cut mid-loop, bad tool survival, and
  the runaway-round cap.

## 0.2.0 — 6 August 2026

### Added

- **Multi-operator support** (P9): per-operator login tokens (stored as
  SHA-256 hashes, shown once at creation), `owner`/`member` roles with
  repository-level scoping — members see only clients they own and other
  clients' resources answer 404 without leaking existence. Open local mode
  is preserved until the first token exists; the legacy `AUDITDECK_TOKEN`
  keeps full access. New CLI: `clauditseo operator add | list`. The hosted-
  platform port path (SQLite → Postgres) is documented in ARCHITECTURE.md.

## 0.1.0 — 6 August 2026

First complete build (phases P0–P8, all gates passing).

### Added

- **Crawler**: polite BFS crawler — robots.txt honoured (5xx robots = fetch
  nothing), identifiable user agent, per-tier hard budgets (pages, request
  timeout, wall clock, inter-request delay), redirect-chain tracking,
  sitemap and llms.txt metadata reads.
- **Audit engine**: seven dimensions (TEC, ONP, PRF, CNT, OFP, LOC, AIS)
  behind a common three-method module interface with registry-based
  composition; deterministic scoring with visible, renormalised weights;
  LOC weight redistribution when not applicable; new dimensions compose
  with zero engine changes.
- **Providers**: optional connector hub — Moz, DataForSEO and OpenPageRank
  backlinks; PageSpeed, CrUX and Search Console for Google data —
  confidence-weighted multi-source merge, graceful keyless degradation,
  T1 provably makes no provider calls.
- **History**: stable finding fingerprints with an open → fixed → regressed
  state machine (accepted-risk never auto-changed), fingerprint-diff run
  comparison, metric snapshots powering trend charts, per-run cost log.
- **LLM analyst layer**: four analysts (PRI-J, CNT-J, ONP-J, AIS-J) over
  evidence bundles; Anthropic provider plus a first-class deterministic
  mock; (task, model, bundle-hash) cache — repeat runs spend zero tokens;
  budget caps with tail-first task cuts; prompt-injection text in crawled
  pages surfaced as security-note findings; ingest rejects uncited findings
  and invented figures. Analyst output never affects scores or states.
- **Dashboard**: client/site management, site detail with regression banner
  and score trend, run detail with a visually separate analyst band, run
  comparison, staged audit launcher (dimensions × tier × analyst toggle
  with budget readout), deterministic read-only history chat citing the
  runs behind each answer, single-operator token login.
- **Reporting**: run, comparison and monthly-trend templates in
  client-facing and internal voices; every metric carries source +
  confidence; keyless gaps render as `[TO CONFIRM: …]`; automated honesty
  checks (no unsourced numbers; no narrative figures absent from evidence)
  run on every generation and block dishonest output. Markdown always,
  WeasyPrint PDF when available.
- **CLI**: `clauditseo migrate | seed | serve | demo | audit run | report`
  with the staged `--dims ... --tier ...` interface.
- Schema is multi-operator-ready from migration 0001 (operators table,
  ownership columns) ahead of the P9 multi-user phase.
