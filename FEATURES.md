# Features

Capability the product does not have. Not defects, not experience problems —
things it has never been able to do.

| File | Holds | Found by | Consumed by |
| --- | --- | --- | --- |
| `audits/NNN-*.md` | where the product contradicts itself | the auditor | `/audit-fix` |
| `KNOWN_ISSUES.md` | runtime facts not derivable from source | the operator | the auditor's gather step |
| `BACKLOG.md` | where the product is correct but unhelpful | the operator, by eye | the operator, directly |
| `FEATURES.md` | what the product cannot do at all | the operator | the operator, directly |

## These are not levers

**`/audit-fix` never selects from this file, and must not.** The loop's job is
to close the distance between what the product claims and what it does. A
capability that does not exist makes no claim, so there is nothing for an audit
to find and nothing for a lever to close. An entry here becomes work when the
operator says so, weighed against the open findings by hand — that balance is a
judgement about what the product is for, not a rule a loop can apply.

## DISCIPLINE rule 1 does not apply here

Rule 1 says a guard must be seen to fail before the fix is written. There is no
failing behaviour to observe first: the behaviour does not exist, so a "guard"
for it would assert something the code has never attempted, and it would pass
the moment the feature half-works.

**A feature gets an ordinary test asserting the new behaviour**, written with
the feature and red until it is built — not a guard, and not a probe against
the old code. Say so out loud, because the alternative is a test that cannot
fail, which is the exact defect rounds 027 through 030 spent four levers
cleaning out of the guards this repository already had.

The **acceptance signal** below is what that test asserts. It is written before
the work starts, so "done" is decided in advance rather than argued afterwards.

## Feature work records itself, like everything else that takes time

Before starting an entry here, claim the marker; clear it at the commit:

```powershell
$start = Get-Date -Format o
scripts\round-marker.ps1 -Claim -Kind feature -Subject F-0N -Phase working -Start $start
```

At the commit, append a row to `## Other work` in `TIMINGS.md` —
`| feature | F-0N | <date> | <min> | <work> | <what it was for> |` — stage it
with the feature's own commit, then `scripts\round-marker.ps1 -Clear`. `work`
is `feature` by definition for an entry here; the derivation rule still applies
to anything the commit touched beyond it, and a commit spanning both is
`mixed`.

**`/feature <id>` does all of the above**, and is the way to build an entry
here. It quotes the acceptance signal before the work starts, requires it in
the commit body stated as met or not met, marks the entry and writes the row.

It exists because the discipline was measured rather than assumed. F-01, F-02
and F-03 were built without it: all three commits recorded the signal in this
file, but only `b617e48` stated it in the commit body. Nothing noticed, because
nothing checked. The instruction above is what the skill enforces — kept here
because a file that says what it expects is worth more than one that delegates
it entirely.

## Why this file exists

`BACKLOG.md` holds things the product does correctly but unhelpfully. Entries
that were really absent capability sat in it because there was nowhere else,
and they never moved: `/backlog-plan` clusters by where work lands and
correlates against open findings, and an absent capability has no finding to
correlate with and cannot outrank twenty-two open Highs. Every plan ranked them
last, correctly, forever.

---

## F-01 — say whether a site carries analytics or tracking — **BUILT**

*Routed from `BACKLOG.md` B-21.*

**Built 17 August 2026.** Acceptance signal met in full, including the
negative case. Tests: `tests/test_third_party_scripts.py`. The entry is kept
rather than deleted, because the acceptance signal is the record of what was
promised and is what a later change has to keep true.

Two cases were added beyond the signal as written, both being ways this gets
quietly wrong: `//host/a.js` against `/a.js` — off-origin and own-origin, both
without a scheme — and a `200 text/html` response with an **empty body**, which
passes every eligibility test in this codebase and would otherwise have been
reported as a clean site. All three findings are `INFO`, which deducts 0.0 in
both scoring tables, so reporting this moves no score.

**Intent.** The operator wants an audit to report whether a site loads
third-party scripts — analytics, pixels, tag managers — because a site carrying
six trackers and one carrying none are different products to advise on, and
today the audit says nothing either way.

**Scope, decided by the operator:** third-party scripts reported **by host,
counted**. Not a maintained list of named vendors. Naming "Google Analytics"
asserts an identification the product cannot verify from a `src` attribute,
while counting hosts reports a measurement. A vendor list also ages badly.
Vendor naming, if it is ever wanted, is an additive change on top of this.

**Acceptance signal.**

1. A run over a page loading scripts from two external hosts reports two
   third-party script hosts, named by host, with a count — and reports the
   same page's own-origin scripts as not third-party.
2. **The negative case, which is the half that will bite.** A page whose
   scripts were not captured must not render identically to a genuinely clean
   site. "No third-party scripts found" is a claim; a run that could not
   measure renders `[TO CONFIRM: …]` and never "none". This is the provenance
   invariant, and it is the empty-crawl 97/100 defect waiting to happen inside
   a new module.

**Technical note carried over.** The evidence is already fetched and then
discarded: `pagefacts.py:15` treats `script` as a void-capture tag, so only
JSON-LD text survives and `src` attributes are dropped at extraction. This is
keeping what is already in hand, not crawling anything new.

---

## F-02 — run a specialist against one finding — **BUILT**

*Routed from `BACKLOG.md` B-07.*

**Built 17 August 2026.** Acceptance signal met both ways. Tests:
`tests/test_check_specialists.py` and the F-02 tests in
`tests/test_page_advisor.py`.

`CHECK_SPECIALISTS` maps a `check_id` to the tool that judges it, declared in
`anatomy.py` beside `TOOL_CATEGORIES` and held true by three invariants: every
key is a check the modules actually raise, every value is a `PAGE_PANELS`
entry, and every specialist covers the category of the check it claims. The
third caught a mistake while the map was being written —
`localbusiness-schema-missing` reads like schema work and is filed under
`local`, which neither page panel covers, so it correctly gets nothing.

**The refusal is the half that matters.** A check with no specialist offers no
control at all, and a check another tool owns is refused by name before any
model call rather than answered. `jsonld-invalid` asked of the page advisor
returns "judged by schema-auditor", not a heading recommendation — a control
that ran the wrong tool would return a real, fluent judgement about something
other than what the operator clicked, which is worse than silence because it
looks like an answer.

The decision is made once, on the server: `specialist` rides on the finding
row, so the screen cannot offer a control the server would refuse. A finding
names its own scope — the category of its check — so F-03's narrowing is what
makes the answer about the finding rather than about the page.

**Intent.** The operator is looking at a single finding and wants the
specialist that judges *that check* to run against it. Today the only run verbs
on the screen target the whole page.

What is absent is one level finer than the map that exists. `TOOL_CATEGORIES`
(`clauditseo/anatomy.py:170`) maps each tool to the categories it can act on,
which is why the banner offers the tools it does; nothing maps a `check_id` to
the specialist that judges that check, and no run can be scoped to a single
finding.

**Acceptance signal.** From a findings row, invoking the specialist runs it
against that finding's check and page and returns a judgement naming the same
`check_id` — and a check with no specialist mapped to it offers no control at
all rather than a control that runs the wrong tool.

---

## F-03 — scope the advisor to the section being read — **BUILT**

*Routed from `BACKLOG.md` B-13.*

**Built 17 August 2026.** Acceptance signal met both ways: scoped to Headings
the advisor returns the heading recommendation and no meta-description
rewrite, and with no scope it returns the full remit exactly as before. Tests:
`tests/test_page_advisor.py`, the scoped section.

**Narrowing is a view, not a second call**, and that was the design decision.
One judgement serves every section, so a scoped read costs nothing once any
read has run; scoping the *prompt* instead would fragment the cache by section
and charge again for each. The trade-off is that scoping saves reading rather
than tokens, which is stated at `ADVICE_SCOPES` so nobody later "optimises" it
into a second call.

Two things beyond the signal, both provenance. `ADVICE_ALWAYS` keeps
`assumptions`, `conflicts`, `triage` and `page_read` in every narrowed view —
a view that dropped the caveats would hand back a tidier answer with the
reasons it might be wrong removed. And the panel says it was narrowed, in
rendered text, because a narrowed answer and a thin answer look identical
otherwise.

A scope the advisor does not cover is **refused, not ignored**. Falling back to
the full remit would have returned everything and read as though the narrowing
had worked, so an operator would believe they were reading `a11y` advice from a
tool that never judges it.

**Intent.** The operator is reading one section — Headings, say — and wants
advice about that section. The Page advisor returns its whole fixed remit: H1,
title tag, meta description and answer line.

Nothing here is wrong or misleading: the panel states its remit before it runs,
and `TOOL_CATEGORIES` offers it under the three categories its output genuinely
touches. The capability that is missing is narrowing —
`advise_url()` (`analysts/page_advisor.py:216`) takes no scope parameter, so
the screen has nothing to pass the open category to.

**Acceptance signal.** Invoked from the Headings section, the advisor returns
recommendations about headings and does not return a meta-description
rewrite; invoked with no scope, it returns the full remit exactly as it does
today.

---

## F-04 — read back advice already produced — **BUILT**

*Routed from `BACKLOG.md` B-14.*

**Built 19 August 2026.** Cost: 23.4 minutes to build, after 2.1 minutes spent
stopping at the decision this entry reserved for the operator - 25.5 across the
two relay 051 invocations. Acceptance signal met
clause by clause — the evidence for each is in the commit body of the build,
and the tests are the F-04 section of `tests/test_page_advisor.py`.

**Option B, and the operator chose it.** Advice is stored against
`(run_id, url)` in a new `page_advice` table (`0024_page_advice.sql`), following
the `expert_reports` precedent from `0005`: one row per page per run, and
re-advising replaces that row rather than accumulating history. The rejected
alternative was a GET that assembles the bundle and returns cache-or-empty. It
fails the signal the moment the operator edits the page in response to the
advice — the bundle hash is taken over the page's own content, so the read-back
would go blank exactly when it was acted on, which is the whole workflow.

That is not theoretical. Four cached advisories from 15 August were probed
against their live pages on 19 August and **all four missed**: the pages had
moved on. Option A would have shown the operator nothing for any of them.

**The cache-hit path stores too.** Advice reaching the operator as an
`analyst_cache` hit never touches the code that writes the run-scoped row, so
without that the panel would offer to generate what it had just displayed. The
two tables answer different questions and both are written.

**One resolver for both paths.** `scope` and `check_id` narrow — and refuse —
identically on the read as on the produce, because a GET answering in the full
remit where the POST refuses would show fluent advice about a check this tool
never judged, with nothing on screen to say so. The stored row always holds
the full remit; narrowing stays a view taken on the way out (F-03), or
re-entering a different section would read a judgement with its own fields
missing.

**"Advise again" was kept deliberately.** Once stored advice shows on mount
there is no un-advised state to click through, and the operator who edits the
page in response to the advice has to be able to ask about what they changed.
Without it this feature would have removed a control while adding one.

**One clause is not yet observed at the running product**, and that is a spend
decision rather than a defect. `status: none` on a real run was read live from
`http://localhost:8020` — the third clause. Showing stored advice live needs
advice to exist there, and no cached advisory still matches its page, so
producing one costs a real Opus call on the operator's key. Four probes
confirmed the miss with the cost ledger unmoved at 46 entries; nothing was
spent to find out. The other two clauses are measured through the API against
the real cost table in `tests/test_page_advisor.py`. **That outstanding reading is
registered as B-29**, which is what makes it reachable — nothing inside a
**BUILT** entry is.

**Intent.** The operator generated advice, moved to another section and back,
and was offered "Advise on this page" again as though nothing had been made.

This is not a cost defect — the cache is real and a repeat click returns
`cached: True, tokens: 0`. What is absent is any way to *read* stored advice:
the only endpoint is `POST /api/runs/{run_id}/advise`, `PageAdvice` holds its
result in local state with no mount-time read, and unmounting discards it. A
GET cannot be added trivially, because the cache key is
`task#cache_version` + `model_id` + `bundle_hash` — whether a hit exists is
unknowable without assembling the bundle, which is what the POST already does.

**Decision needed before building**, and it is the operator's: a GET that
assembles the bundle and returns cache-or-empty without calling the provider,
or advice stored against run + url so the panel can read it directly.

**Acceptance signal.** Re-entering a section for which advice exists shows that
advice without calling the provider — measured as zero tokens and no new cost
entry — and a section with none offers to generate it.

---

## F-05 — run the probe a brief names — **BUILT**

*Routed from `BACKLOG.md` B-17.*

**Built 19 August 2026**, through the `/feature` contract carried out by relay
item 053. Acceptance signal met, clause by clause — the evidence for each is
in the commit body of the build. Tests: `tests/test_probes.py`, 45 of them,
two of which need a browser and gate in the `rendered-a11y` job.

**Three defects were found by the running product and none by the suite**,
which is rule 12 earning its place rather than a formality it cleared. All
three were invisible to a green suite for the same underlying reason: a test
writes its own fixture text, and fixture text is short, single-line and
contains no hostnames.

1. **A false positive on the real brief.** `apex-redirect` matched
   "HTTP/2/HTTP/3 availability not observable … requires `curl --http2 -I
   https://www.13acme.com.au/`" — on the `www` inside the host and the `curl`
   inside the example command. It would have offered a redirect measurement
   as the answer to a protocol question, which is exactly what the
   subject-and-qualifier rule exists to stop.
2. **Wrapped markers never matched at all.** These items are long and wrap in
   the stored markdown; the renderer joins a paragraph's lines with a space
   before tokenising. Keyed on raw text, screen and server disagreed for
   every wrapped marker, so a runnable item rendered as a plain
   `[TO CONFIRM: …]` offering nothing — indistinguishable, on screen, from an
   item this product cannot measure. Of thirteen items in the live brief the
   one runnable item was a wrapped one, so on real data the feature offered
   nothing at all while every test passed. `probes.normalise` now owns the
   key and `markdown.tsx` names it where it does the same thing.
3. **A table left behind by an abandoned attempt** — see the migration note
   below.

**The migration is 0026 and drops before it creates.** An earlier abandoned
attempt at this entry survives as a git stash (`ffca91d`, 19 Aug 17:27,
untracked files only) carrying its own `0025_probe_results.sql` on a
different key — `(run_id, tool_id, item_key)` against this one's
`(run_id, probe_id, target)`. It had been applied to the operator's live
database before the work was set aside, so there `probe_results` already
existed, incompatibly, with `0025_probe_results.sql` already recorded in
`schema_migrations`. A same-named migration is skipped by filename and
`CREATE TABLE IF NOT EXISTS` is skipped by name, so nothing anywhere said so
until the first real probe returned `no column named target`. The drop is a
rename rather than a deletion: the table had never held a row, because the
feature that writes to it is this one.

**Worth recording about that stash**, since it is a second independent
attempt at the same entry: it reached the same three load-bearing
conclusions — the target comes from the audited site and never from the
brief, no probe shells out, and an outcome that is not evidence is not a
result. It also named a repository rule this build had not found,
`tests/test_program_names.py`, which forbids handing a bare program name to
`subprocess` and independently settles the OCSP question. The two differ on
where an answer is keyed and on whether a failure is stored; this build
stores failures, so the operator can see an attempt was made.

**Two of the six are runnable, and four are refused on the record.** The
entry named cipher ordering, chain completeness, OCSP stapling, apex
redirect, HTTP/2 and the origin inference. Chain completeness and the apex
redirect are answerable with a socket and a request, and are. The other four
are not, each for a reason written into `probes.py` beside the registry:

- **OCSP stapling** — the item this entry quotes — has no API in Python's
  `ssl`. Only the OpenSSL binary answers it, and `crawler/transport.py`
  settled for this whole area that a scanner is not shelled out to
  ("without shelling out to an external scanner", its opening lines). That
  decision was followed rather than reopened, which means the entry's own
  example is a *negative* case on screen. That is the right outcome and
  worth stating plainly: the illustration was of the shape these items take,
  not a requirement that this one become measurable.
- **Cipher ordering** needs the handshake repeated with the client's
  preference reversed, and TLS 1.3's suites cannot be ordered through
  `set_ciphers` at all — so the answer would be about TLS 1.2 while reading
  as though it were about the server.
- **HTTP/2** needs `h2`, which is not a dependency. httpx without it
  negotiates 1.1 every time, so "no HTTP/2" would be a fact about the
  machine running the audit. That is exactly the confusion `transport.py`
  built `NOT_OFFERED` to refuse, and adding a dependency to make one item
  clickable is not what this entry asked for.
- **The origin behind a CDN** is not measurable from outside.

**The brief's text is never executed, and this is the substance of the
feature rather than a caveat on it.** The item names a command because a
human would type one; the product matches the item against a registry and
runs its own Python. A product that shelled out to a string composed by a
language model would have built a remote-execution path out of a report, and
the target is not on the wire either — it is read from the run's own site, so
neither half of what runs can be redirected by the prose or by the request.

**Rendered inline, not in a panel.** The marker is a sentence inside the
report, and a panel would have produced the one state the signal rules out:
the item settled in a sidebar while the paragraph it belongs to, three
screens down, still reads `[TO CONFIRM: …]`. So `markdown.tsx` tokenises the
marker and `ReportView` owns the wrap — which is also what stopped this
shipping to one screen of four. A brief is opened from the briefs panel, from
two report modals on the run page and from the client screen's section
reading; `tests/test_probes.py` enumerates those call sites out of the
dashboard source rather than from a list, because a hard-coded list of three
is how a partial fix passes.

**A failed probe is stored and does not settle anything.** `status` is
`measured` or `failed`, and only `measured` replaces the marker. The worst
thing this feature could have shipped is a `[TO CONFIRM: …]` overwritten by a
confident sentence that a timeout produced, so a refused connection is
recorded — the operator should see it was tried — and the item is left
exactly as it was, with the offer standing. The one test here that opens a
real socket opens it at a closed loopback port for precisely that
distinction.

**Intent.** A brief lists unresolved questions, each naming the exact shell
command that would settle it — `[TO CONFIRM: requires openssl s_client
-status]` — and the operator has no way to run any of them from the product.

Six of the seven in the `https-security` brief are the provenance invariant
working: cipher ordering, chain completeness, OCSP stapling, apex redirect,
HTTP/2 and the origin inference are genuinely unmeasured, and saying so is the
product being honest. What is absent is everything after that sentence — no way
to run the probe, no way to record the answer, no way to mark one settled.

**Acceptance signal.** A `[TO CONFIRM: …]` item that names a runnable probe
offers to run it; running it records the result against that run and the item
renders as settled with its measured value and a source tag. An item naming no
runnable probe still renders as `[TO CONFIRM: …]` and offers nothing — the
honesty is the feature, not the thing being removed.

---

## F-06 — refresh one section — **BUILT**

*Routed from `BACKLOG.md` B-18.*

**Built 18 August 2026**, through the `/feature` contract carried out by relay
item 048. Acceptance signal met, clause by clause. Tests:
`tests/test_page_refresh.py`, 17 of them, and two more in
`tests/test_section_refresh.py`, which need a browser.

**Intent.** The operator is working in one section and wants to re-run the
audit for it. The only route is a dimension-wide run started from another
screen.

The granularity is the substance. The launcher picks **dimensions**; this
screen groups by **category**; one dimension spans several categories — TEC
refreshes Indexability & canonicals, Crawl & sitemaps, Security & transport
*and* Mobile, and ONP spans five. So standing in Security & transport, the
smallest thing that can be asked for pulls in three other sections.

`anatomy.py` states the constraint plainly: "audit Images is not a thing the
engine can be asked for — a picker that implied otherwise would be offering a
control that cannot exist". That is still true of *audit Images*, and it was
read here as "so this is a new engine unit, not a button" — which was the one
sentence in this entry that turned out to be wrong.

**What was actually missing was an entry point and a set of rules, not a
unit.** `crawl_site` has taken `only_urls` and `run_audit` a dimension list
since the verify path was built, and `AuditModule.run` takes an arbitrary page
set — so "re-measure this page for the dimension covering this section" was
always a call the engine could serve. The constraint `anatomy.py` records is
about **category** granularity, which is still not askable: a refresh of
Headings runs ONP, and ONP still emits for four other categories. The unit is
`(url, dims)`; "section" is this screen's framing of it.

**A present-capability fallback exists and is not this feature**: the section
could state which dimension covers it, start that, and say what else comes
with it. That is a `BACKLOG.md` change and could be done first. Recorded here
so the two are not confused — the fallback tells the truth about a coarse
control; the feature makes the control fine.

**The fallback was built on 18 August 2026**, through relay item 047, hours
before the entry itself. `anatomy.refresh_for` answers each section with the smallest
dimension that covers it and the other sections that move with it, both
derived from `DIMENSION_CATEGORIES` rather than a second table; the section
pane offers it as *Refresh this section*, states the cost before the click,
and confirms before spending. Tests: `tests/test_section_refresh.py`, 17 of
them — 12 static and 5 in a browser. Two things it deliberately did not do
were the reasons F-06 remained the feature: the run it started was
dimension-wide, so the acceptance signal below was not met and was never
attempted; and the control was honest about that rather than approximating it.

**What the fine unit cost, and what it may claim.** `POST /api/sites/{id}/refresh`
takes a page and a section, derives the covering dimension from
`anatomy.refresh_for` — so there is no second way to configure a run — and
carries three rules that are the substance of the feature rather than
paperwork around it:

  - **A third run kind.** `kind='refresh'`, beside `audit` and `verify`.
    Everything that scores, trends or compares filters to `kind='audit'`, so
    those guards covered it on arrival. Checked rather than assumed, which is
    how three readers that had *no* filter were found: Home's score and last
    run, the scheduler's clock for unattended audits, and `crawl_diff`, which
    read a one-page crawl against a full one and reported the home page as
    removed. All three took a `verify` run the same way and had since `verify`
    shipped; all three now count audits.
  - **It scores nothing.** One page over one dimension measures a different
    population, and the comparability key is `(engine_version, scope.basis,
    tier)` — 0012's argument for the version, 0022's for the basis and WF-56's
    for the tier, a fourth time. The absence of a composite is the feature.
  - **It closes only what it read.** The page rule in `_apply_states` is
    inherited untouched — the one whose `and crawled` once let an empty crawl
    clear every open finding on a site — and one rule is added for a narrow
    run: it may not clear a *site-scoped* finding either, because one page is
    not a reading of the site.

**Its tier is inherited from the audit it refreshes**, not chosen. A T2
refresh laid over a T3 audit would reintroduce through this endpoint the
defect WF-56 closed at the launcher.

**Everything the dimension emits for that page is recorded**, not a slice
matching the section. A finding filtered out is indistinguishable from a
finding that no longer fires, and the resolution rule reads exactly that
difference. So the control says what else refreshes rather than pretending
less happened — the same honesty the coarse control had, at a smaller scale.

047's control was narrowed rather than replaced: with a page selected the
section offers the fine unit and claims only that page; with none selected the
coarse offer stands and now names the route to the finer one instead of
denying that one exists.

*The same change closed a dead end F-07 shipped.* Its unplaced-outline note
read "The next audit of this page will point at it", promising page
granularity — the one granularity `DIMENSION_CATEGORIES` says the engine
cannot be asked for. It now names the smallest run that would record the
position and points at the control that starts it, guarded by
`test_no_screen_promises_an_audit_of_one_page`, which reads every screen
rather than the one that had it.

**Acceptance signal.** A refresh started from one section re-audits that
section's checks and leaves the other sections' findings and timestamps
untouched — verified by comparing stored findings either side, not by the
screen redrawing.

**The signal as built, and why the wording above could not be met as
written.** *Other sections* was the wrong axis and the entry says so itself
three paragraphs up: a refresh of Headings runs ONP, ONP emits for four other
categories, and suppressing those findings to leave the other sections
untouched would make a held-back finding indistinguishable from one that
stopped firing. The axis that carries the intent is the **page**, and that is
what was built and measured:

> A refresh started from a section re-measures that section's page for the
> dimension covering it, and leaves every other page's findings and timestamps
> untouched — verified by comparing stored findings either side, not by the
> screen redrawing. It closes only findings whose page it actually revisited.
> It writes no comparable composite, and the site trend is unchanged by it.

Both are kept. The first is what was promised and is the record of it; the
second is what was delivered, and the difference between them is the design
decision this entry argues for rather than a signal quietly relaxed to fit.

---

## F-07 — open the heading outline at the fault — **BUILT** (display moot since Q-51)

**Built 18 August 2026**, through the `/feature` contract carried out by relay
item 045. Acceptance signal met, clause by clause; the wording below is
unchanged and is the record of what was promised. Tests:
`tests/test_heading_fault.py`, now 16 static — the 4 browser tests that read
the display retired with it (see below).

**The display half is moot since Q-51 (7 September 2026, operator; landed as
relay item 144).** F-07 opened and marked the Headings card's *tagged outline
list* at the recorded position. Brief v16d then drew the outline as a ladder
beside that list, and Q-51 retired the list as a second outline of the same
page (136e's own instruction). The ladder reads `onp.heading_outline_state` —
the function the check itself calls — so it marks the skip from the outline
directly and never needed the stored index; F-07's whole apparatus for taking
the position from the finding and refusing a position the list cannot bear out
is therefore moot rather than merely dropped. The check still records
`outline_index` (it is cheap and a later display may want it), which is why the
check-side tests survive; the four browser tests that exercised the list
display (`.out-fault`, `.out-unplaced`) went with the list.

**The position is an index, not a second sentence of prose.** `heading-skip`
evidence gains `outline_index`, the 0-based position of the offending heading
in the same list `evidence.snapshot` stores and the screen renders, so the two
cannot disagree about which heading is meant. `anatomy_view` carries it onto
the wire and **omits the key entirely** where none was recorded — a `null`
would be a value, and a screen reading it would have to remember that this
particular one means "nobody measured this".

**The screen never marks a position the outline in front of it cannot bear
out.** The client re-does the check's own arithmetic against the list it is
about to render: the marked row must be more than one level deeper than the
row above it. That is not defensive decoration — the facts panel assembles
each field from the most recent run that recorded it while a finding comes
from the run that last raised it, so the two readings of a page are not
guaranteed to be the same one. A stale position now renders unopened with the
reason stated, which is the same answer as clause 3's.

**Verification boundary, stated rather than glossed.** Clause 3 was read from
the running product at `http://localhost:8020`: the `www.13acme.com.au`
heading-skip finding stored on 17 August carries no position, and the served
screen marks nothing, says why, and still lists the finding. Clauses 1 and 2
were driven in a browser against the built bundle served over HTTP by the real
app — `test_heading_fault.py`'s live tests — and **not** at `:8020`, because
every finding stored there predates the change and producing a placed one
means spending a fresh audit against a client's site.

*Routed from the third element of `BACKLOG.md` B-09, which stays open for the
rest.*

**Intent.** The operator reads `heading-skip` and wants the outline to open at
the heading that skipped a level.

The other two things B-09 asks for — rendering level as size rather than a
repeated `H4` label, and collapsing the tree — are presentation of data the
screen already holds, and remain in `BACKLOG.md`. This one is not: the check
emits `H2→H4 on /` as prose and no index ties it to a position in the list, so
there is nothing to open *at*.

**Acceptance signal.** `heading-skip` carries the position of the offending
heading in the page's outline, and the outline scrolls to and marks that
position. A finding produced before the check emitted a position renders the
outline unopened rather than guessing at one.

---

## F-08 — the browser tab carries the product's own identity — **BUILT**

**Built 17 August 2026**, the first entry built through `/feature`. Acceptance
signal met, clause by clause; the wording below is unchanged and is the record
of what was promised. Tests: `tests/test_brand_icon.py`.

**The decision is the server's**, which is what made the negative cases
testable rather than only observable in a browser. `/api/brand` answers
`icon_href`: a URL when a stored logo is on disk *and* carries a mime a browser
renders as an icon, and `null` for every way that can fail. The screen obeys it
and holds no policy, so a case cannot be forgotten there — there is only an
href or nothing.

**Clause 3's second half turned out to be unreachable through the product**, and
is asserted anyway. `sniff()` admits PNG, JPEG, GIF and WebP by magic bytes and
a browser takes all four, so an unusable stored mime cannot arrive by upload
today. `ICON_MIMES` is stated as its own set regardless, because "may this be a
logo" and "may this be an icon" are different questions, and a format added to
the first must be a deliberate decision about the second.

**Verification boundary, stated rather than glossed.** Clause 1 was read from
the running product: the served page no longer carries the `A` letterform, does
carry the `C`, and is still a data URI. Clause 2's decision and both negative
cases are covered by test, and the swap is present in the served bundle — but
it was not driven end to end, because that needs a logo written into the
operator's live brand data, which reaches client-facing documents. **That
outstanding reading is registered as B-29**, with F-04's, for the same reason:
a clause verified only at the test boundary is in no queue otherwise.

*Routed from an operator observation, 17 August 2026. Never held a `B-` number:
it was raised as a backlog item and is recorded here instead, because the tab
icon cannot be sourced from stored data at all today.*

**Intent.** The operator keeps this tool in a pinned tab all day and finds it
among twenty others by its icon. The icon is a blue tile lettered **A**, from a
name the product no longer has, while `APP_NAME` and the page title are both
`ClauditSEO` — so the tab reads `A | Clau…`. Meanwhile the admin panel already
holds a brand logo that never reaches the tab.

**Two absences, and they are different things.** The favicon is a hardcoded
inline SVG data URI at `dashboard/index.html:13`, in a static file served
before any API call — there is no mechanism by which stored data can reach it.
And the stored logo (`branding.set_logo`, `POST /api/brand/logo`) is scoped by
its own docstring to "client-facing documents", not to the application's own
chrome. Neither is a defect in what exists; both are capability that does not.

**Scope, decided by the operator:** the icon registered in the admin panel
becomes the favicon going forward, with a default used until one is registered.
So the default is a fallback, not the destination — which means the default
must also stop being wrong, since it is what every install shows on first run.

**Acceptance signal.**

1. With no logo registered, the tab shows a default icon consistent with
   `APP_NAME`, and not the `A` letterform of the previous name.
2. With a logo registered through the admin panel, the tab shows that logo, and
   replacing it changes the tab without a rebuild. `Brand()` already
   cache-busts the rendered logo by a save counter (`admin.tsx:737-739`); the
   tab has to honour the same replacement or it will show the old mark
   indefinitely, which is this entry's own defect returning by a new route.
3. **The negative cases, which are the half that will bite.** `BrandData`
   already carries `logo_missing` (`admin.tsx:646-649`), so a registered logo
   whose file is gone must fall back to the default rather than render a broken
   image — a tab with no icon is harder to find than a tab with the wrong one.
   And a stored logo whose mime type a browser will not accept as an icon must
   be refused at upload or fall back visibly; it must not silently produce an
   empty tab icon, which looks identical to the app failing to load.

**Technical note carried over.** `index.html:11-12` states the reasoning the
current icon was chosen for: "Data URI keeps it a one-file change with no build
step and no request." That is a real constraint this feature has to answer
rather than ignore — sourcing the icon from stored data costs a request, or a
runtime `<link rel="icon">` swap after the brand call the app already makes.

**Why this is worth doing beyond appearance.** `USER_AGENT` is built from
`BOT_NAME` specifically "so it cannot drift from the name on the report the same
crawl produces" (`crawler/types.py`). The favicon is that same drift, in the one
asset no constant reaches — and it is the first thing the operator sees.

---

## F-09 — accessibility carries its own total, separately from the SEO composite — **BUILT**

*The operator's own decision, recorded 17 August 2026 — not routed from a
`BACKLOG.md` entry or an audit finding.*

**Built 19 August 2026, in relay 052.** Cost: see the `relay | 052` row in
`TIMINGS.md`, which is the one row this invocation is allowed to write. All
three clauses MET, each read off the running product on the operator's own
database rather than off the source — the evidence per clause is in the commit
body, and the tests are `tests/test_accessibility_headline.py`.

Run `f80bc200` served `70.5 / composite / 100` beside `66.8 / accessibility /
100 / scored separately — not part of the composite`, with no `A11Y` row left
in the table decomposing the composite. Clause 1 is exact rather than
approximate on that run: the stored sub-scores by their stored weights sum to
70.52, which is the stored composite, and accessibility's term in that sum is
0.0. Clause 3 was found live rather than contrived — audit `8fdeb042` selected
seven dimensions and not A11Y, and renders `not assessed`, with no headline
figure element on the page at all.

**Only the front card, as the entry scoped it — and the first of the two
remainders has since closed by another route.** The two follow-on pieces named
below were SEO surfaces excluding A11Y findings, and the accessibility section's
own severity scale in the client document. Both were left needing their own
consumer enumeration and their own acceptance signal, and both were registered
as **B-26** — which is still where the unbuilt one lives.

**The first is closed, and this paragraph used to say otherwise.** It read: the
`Biggest gains` table "still ranks by points on the composite and so still lists
A11Y rows at zero". That stopped being true at `954247f` on 20 August 2026,
which took the auditor's **UX-46** (`audits/058-2026-08-19.md:202` — the same
defect, found from the document side) and excluded a dimension carrying no
weight inside `biggest_gains` itself (`clauditseo/persistence/runs.py:1342`)
rather than in either consumer. One predicate at the single source reaches every
reader: the run payload the dashboard's table draws (`api/app.py:1929` →
`dashboard/src/views.tsx:1132`), the client document's actions
(`reporting/render.py:248`), and triage's brief (`api/app.py:131` →
`analysts/expert.py:1104`). So the piece this entry deferred was delivered
whole, by a fix round rather than by the feature entry it was waiting for —
which is why the sentence above outlived the defect it described. Guarded by
`test_an_unweighted_dimension_offers_no_ranked_action`
(`tests/test_reporting_g7.py:1000`), which also asserts the A11Y finding is
still in the document's Accessibility section, so the plan losing the row is a
correction and not a deletion.

**Read at the running product on 22 August 2026, relay 070**, on this entry's
own evidence run `f80bc200`: `GET /api/runs/f80bc200…` at `:8020` serves eight
`biggest_gains` rows — ONP, CNT, TEC, PRF — and **no** A11Y row, while the same
payload still carries `A11Y` at `66.83` for the headline card this entry
shipped. The rendered client document for that run leads with five actions and
**none** is A11Y, its count sentence already reads "17 distinct issues across
547 findings, plus 510 accessibility findings listed separately below", and its
`Accessibility` section still carries all 510. Triage's gains table is fed by
the same excluded list. Nothing in the accessibility deliverable was removed.

**The second piece — the accessibility section's own severity scale — remains
unbuilt**, and **stays registered as B-26**, which is where it lives until it is
scoped as an entry of its own — naming the register is what makes it reachable,
since nothing inside a **BUILT** entry is.

**Intent.** One client document, two sections. Accessibility is scored
separately, in its own right, on its own scale, and never summed with the SEO
composite. The separation is what lets it be stated properly, not a way of
setting it aside.

**The number already exists; this is a surfacing job.** `DEFAULT_WEIGHTS["A11Y"]
= 0.0` in `scoring.py:34-41`, and the comment there argues the zero correctly:
at 10.9% of the composite, accessibility moved an SEO score by more than the
evidence supports. **This entry does not touch that reasoning, and does not
touch any weight.** Weight 0 only removes A11Y from the renormalisation
`composite()` performs — the dimension still runs, scores, and stores a full
`SubScore`, with its own `score`, `coverage`, `unmeasured` and `detail.per_check`
breakdown, on every run already in the database. The front card has never read
that value; this entry is the first thing that does.

**What the zero weight did not account for is volume.** A11Y is 803 of 2,122
findings ever produced — 38% — with 381 marked `high`, and confirmed in code:
`gains`/`DEDUCTION_TABLE` (`analysts/expert.py:1107-1116`) includes A11Y rows
at `composite_points: 0`, since that figure is computed against the same zero
weight. So an A11Y finding is present in every SEO surface that ranks by
recovered points and can never be chosen by one — `high` means "work this" in
seven dimensions and "this will never surface" in the eighth, on one screen.
Giving accessibility its own score resolves that: its findings become rankable
against each other, on a scale where they are the whole population, not a
zero-point remainder of someone else's.

**The positive case for separate rather than folded-in.** Accessibility
enforcement is legislative — ADA litigation, the European Accessibility Act —
not algorithmic; Google's own stated position is that accessibility is not a
direct ranking factor. So it is a second deliverable with its own standard and
its own reason to act, not a zeroed component of an SEO score. It also keeps
the operator's hedge cheap: if ranking behaviour ever changes, a separated
dimension is re-weighted by changing one number, not restructured.

**This entry is the front card only — the smaller of three pieces wearing one
coat.** The full decision names five changes: a front-card headline, its
decomposition, an accessibility section with its own severity scale, SEO
surfaces (counts, rankings, triage) excluding A11Y findings, and a client
document carrying both sections. The last three share no mechanism with the
first two — excluding A11Y from triage's tables and the deduction-derived
counts is a data-filtering change reaching `analysts/expert.py`'s `_triage_
context` and every other consumer of `gains`, and a document section with its
own severity scale is a `reporting/render.py` restructuring with its own
semantics to decide (does "Critical" mean the same thing as a barrier severity
that it means as an SEO severity?). Both need their own consumer enumeration
and their own acceptance signal, and are **not** covered here. Registered as
B-26 and recommended as two further entries once each is scoped in its own
right — F-09 delivers the first visible piece and proves the presentational
boundary the other two must also respect.

**Acceptance signal**, decided rather than left open:

1. The composite score for an existing stored run is identical before and
   after — assertable directly against runs already in the database, and it
   proves the change is presentational rather than something that quietly
   moved a client-facing number.
2. The front card renders the **stored** A11Y subscore, verbatim, never one
   recomputed by the card itself. Two numbers for the same thing is how they
   start to disagree.
3. **Not optional — inherited from `composite()`'s own invariant, not
   restated loosely:** *0.0 is a measurement meaning perfectly bad; `None`
   means there was nothing to measure.* A run whose accessibility sweep did
   not execute — `applicable: false`, or `coverage` 0 — renders on the card as
   **not assessed**, never as a score and never as zero. The stored `SubScore`
   already carries `coverage` and `unmeasured` to say so; this needs no new
   mechanism, only that the card honours what is already there.

**Not in scope.** No weight in `scoring.py` changes, and no A11Y check is
added, removed or altered — what is detected does not change. The six-tile
overview is separate and still being designed; nothing here anticipates its
layout. The two follow-on pieces named above — SEO surfaces excluding A11Y,
and the accessibility section's own severity scale in the client document —
are deliberately not built as part of this entry, and are registered as B-26.

---

## F-10 — every control that spends says so, from one shared component — **BUILT**

**Built 18 August 2026, at the second attempt.** Acceptance signal met, all
four clauses. Tests: `tests/test_spend_mark.py`.

The first build (`711557e`) was reverted (`e979b1c`) for marking a control
that does not spend: `tools.tsx`'s working-set button opens the confirmation
dialog, and the two buttons inside it are what commit the call. Clause 2
forbade exactly that, and the first build's tests could not see it because
they only ever asserted marks were *present*. The rebuild's enumeration is
therefore drawn from the server — the handlers that reach
`provider_from_settings` — rather than from the controls that look like they
spend, and `test_the_dialog_opener_carries_no_mark` is the assertion the
revert should have had.


*Routed from `BACKLOG.md` B-22, decided in relay 032, clarified in relay 034.*

**Intent.** The operator looked at a button about to call a model and could
not tell from the screen that pressing it spends anything, let alone how
much — the money model is complete and honest (per-tool prices, month-to-date
spend, caps and warnings all exist), but it is rendered on Admin, one screen
away from every control that incurs it. B-22 diagnosed the gap; the decision
that closes it was made in relay 032 and clarified in relay 034: **the button
carries the intent to spend, not the amount.**

    $ Run the 23 not yet run          <- intended
    $ Run the 23 not yet run  ~$1.45  <- not

The presence of the `$` is the whole message. A figure may still be shown
elsewhere on the screen — somewhere the eye reaches second — but not welded
into the control that commits it. This removes on-button figures rather than
adding to them: `expert.tsx:290,345,355` currently renders `pill-cost` (a
priced or token figure) as a child of the button element itself, and that
placement is what changes.

**Scope, decided by the operator:** a marker, not a price. It asserts *that*
an action spends, never *what* it costs — the two are different claims with
different confidence, and B-22's own history is a prediction that was wrong.

**Acceptance signal.**

1. **Every control that initiates a paid model call carries the marker, and
   the set is enumerated from a grep rather than from memory** — at minimum
   `advice.tsx` ("Advise on this page"), `tools.tsx` (`Run all N` /
   `Run the remaining N`), `expert.tsx` (`run all N` / `run the remaining N`
   / `re-run`), and `analyses.tsx`'s run verbs, but the grep is the source of
   truth, not this list. A marker on the controls someone remembered is the
   defect this entry exists to fix.
2. **No control that does not spend carries it.** A marker on every button
   says nothing — the same "check that fires every time" failure this
   codebase has already shipped twice, in `poor-extractability` and in
   CQ-76's own subject matter.
3. **One shared component.** B-22's whole diagnosis was five screens each
   deriving their own answer and disagreeing; a marker built per screen
   recreates exactly that.
4. **The negative case, which is the one that matters.** With no price
   entered, the marker still appears. `admin.tsx:70` states that until a
   price is entered every cost in the app renders in tokens rather than a
   blank — the honest answer, not an absence — and the marker asserts that
   the action spends *at all*, not what it costs. A marker that disappears
   when the price is unknown has quietly become a price by another name.

**Not in scope.** Whether a figure is shown elsewhere on the screen, and
where, is not decided here — only that it does not sit inside the control.
The Tools summary line's own illegibility (relay 033, `BACKLOG.md` B-25 —
the token figure and the dollar figure sum different populations of the same
brief set) is not this entry's to fix, though moving the figure off the
button may narrow it as a side effect, worth a line in the commit if it does.

## F-11 — a finding that states a count must show what it counted — **BUILT**

**Built 25 August 2026, from relay item 090.** Acceptance signal met, every
clause, and each one read at the running product rather than from the tests.
Tests: `tests/test_a_count_reaches_what_it_counted.py`.

**The design call the signal left open was decided as "expands in place".**
The three the entry offered were the drawer, the page filter and an in-place
expansion. The drawer is the `page` panel, which is scoped to one page and
would have made a three-page finding into three separate presses. The page
filter re-scopes the entire screen — every section, every count — so reaching
one finding's evidence would have thrown away the section the operator was
reading. Expanding in place is the only one of the three that leaves the
finding on screen beside its own evidence, which is the whole complaint.

**Read at `http://localhost:8020`, bundle `CwFq9coy`, on the finding the
signal names.** `title-duplicate`, *"3 pages share the title 'Acme Finance:
straightforward funding for SMEs' — they compete for the same query"*: the
cell reads `3▾`, pressing it holds `window` (no navigation) and paints
`https://www.acme.com.au/` and the two `utm_`-tagged forms of it, each an
absolute `href` opening in a new tab, each label distinct. `PAGES 0` on
`domain-authority-reported` and `backlinks-not-assessed` renders `0` and no
control at all. The `PAGES 38` `title-duplicate` on the same screen paints
ten links and the sentence *"Showing 10 of 38"*.

**What was not shipped, and where it went.** The screen reaches ten of
thirty-eight because the payload sends `affected_urls[:10]`; the other
twenty-eight are stored and reachable from no screen. That is inside the
signal — *"Truncation is stated where it happens"* — and outside it as work,
because the entry's own **Out of scope** forbids a new endpoint or query for
URLs the API does not already serve. Filed as **`BACKLOG.md` B-30**, with
the measurement that makes it small: exactly two of `www.acme.com.au`'s 236
open findings cross the cap.

**Intent.** The section screens render a finding, a severity, a **Pages** number
and a state. The number is the whole of the evidence: *"3 pages share the title
'Acme Finance: straightforward funding for SMEs' — they compete for the same
query"*, `PAGES 3`, and no way to reach those three. The operator is told a
problem exists, told how big it is, and left to find it. Differentiating three
titles is a five-minute job once you know which three; without them the first
step is a manual crawl the product already did.

This is not a missing capability, which is why it is worth doing. The finding
row already carries `affected_urls` to the client (`dashboard/src/expert.tsx:27`
types it; `views.tsx:903` counts a set of it), and a `UrlLinks` component already
renders exactly this list on other screens
(`dashboard/src/components.tsx:267` and `:479`). The section findings table —
the one that owns the `Fixed?` column in `dashboard/src/fixloop.tsx` — shows the
count and not the list. The pieces are built and not connected.

**The rule this entry asks for, stated generally so it outlives the one screen.**
Wherever the product states a quantity of affected things, the operator can reach
those things in one action from where the quantity is stated. A count is a
summary of a list; a summary that cannot be expanded is a claim the reader has to
take on trust, and this product's whole argument is that it does not ask for
trust. `SWEEP` findings are the sharpest case because a sweep is the thing that
counted — the note above this table already says *"The sweep counted the
problems; no specialist has read them"*, which is honest about the analysis and
silent about the evidence.

**Acceptance signal.** From a section screen, a finding whose `PAGES` is greater
than zero reaches its affected URLs without a new page load and without the
operator constructing a query — the count itself is the natural control, and
whether it expands in place, opens the existing drawer, or filters the page list
is a design call this entry does not make. Each URL is followable to the page it
names. A finding whose `affected_urls` is empty renders no control at all rather
than an empty one, because a site-scoped finding legitimately names no page and
an affordance that opens onto nothing is worse than none — `QUESTIONS.md` Q-20
is currently open on precisely which briefs those are, and this entry must not
assume the answer. Truncation is stated where it happens: `api/app.py:2115`
already slices to three URLs in one path, so a screen showing three of eleven
says so rather than implying eleven were three. Verified on the `title-duplicate`
finding on `www.acme.com.au`, which reads `PAGES 3` today.

**Out of scope, deliberately.** No new endpoint and no new query: if a screen
needs URLs the API does not already serve to it, that is a finding to report
rather than work to absorb here. It does not change what a sweep counts, what a
specialist reads, or the `$` controls that run one — the complaint is that the
evidence behind a number is unreachable, not that the number is wrong.

## F-12 — a part-page block sizes to its column, and there is one breakpoint — **BUILT**

Item 136m. Every v16 mockup was drawn at 1100–1240 px. The column is not that
wide, and nobody had measured it.

Measured on the running product, Client › a part page, browser default zoom,
2026-09-07:

| viewport | column | card | with the Re-audit drawer |
|---|---|---|---|
| 1920 | 1084 | 1042 | 768 |
| 1440 | 1076 | 1034 | 760 |
| 1280 | 916 | 874 | 600 |

Two assumptions in the brief were wrong. The right panel is **fixed at
300 px**, not a proportion; and it is **absent on a three-block part page**, so
those get the whole column. `.shell` caps at 1400 px, so the column never
exceeds 1084 however wide the display — a breakpoint at the mockups' assumed
column would have put every part page permanently in its narrow layout.

**The rule.**

1. A block sizes to the **content column**, never to the viewport. This is a
   `@container` query, and that is the substance rather than the technique: a
   drawer part is 768 px wide on a 1920 display, and no media query can see
   that. A block behaves the same whether its column is narrow because the
   window is small or because something is beside it.
2. **One breakpoint, `--part-narrow`, at 1000 px** — below the 1084 and 1076
   columns, above the 916 one, so 1280 stacks and 1440 does not. At 916 a
   two-up gives about 450 px a side, which is where it stops being readable.
   The literal is written once, in the single `@container part` rule in
   `styles.css`; the custom property is what documents it, because CSS cannot
   read a custom property inside a container query.
3. Two-up layouts stack below it. Multi-column grids **drop columns** rather
   than overflow. **Horizontal scroll inside a block is never the answer** — a
   block that scrolls sideways has hidden something and does not admit it.
4. SVG text does not render below 11 px; a block whose `viewBox` would take it
   under switches to its narrow layout instead of shrinking further.

**Held by** `tests/test_the_part_page_column.py`: no block overflows its
column at any of the three widths, the part page is a query container, and no
block stylesheet carries its own pixel breakpoint. `score_trend.css` keeps a
media query and is named in the guard — the trend is drawn on the Audit step,
not on a part page, so it has no part column to size to.

**Found by building it.** Four block stylesheets carried private viewport
breakpoints — `crawl_depth.css` and `schema_graph.css` at 1024, and
`canonical_chains.css` and `images_budget.css` at 1100 — none measured, all
keyed to the window rather than the column. And `.img-markup` ran **1796 px**
past a 1042 px column, so an `<img>` tag's attributes sat off-screen with
nothing saying so; it wraps now.

## F-13 — tell a temporary redirect from a permanent one (`redirect-temporary`) — **BUILT (item 137)**

**Built.** The crawler now captures each redirect hop's status in
`redirect_statuses`, parallel to `redirect_chain` (`fetch.py`: `[r.status_code
for r in resp.history]`), stored on the `Page` and in the evidence snapshot. TEC
raises `redirect-temporary` (LOW) when any hop answered 302/303/307. The parallel
field is what let it land without disturbing `redirect_chain`: `evidence.py`'s
readers and TEC's `len(page.redirect_chain)` count are untouched, and a run
crawled before the capture has no statuses and raises nothing — the deferral
resolving, not a false clean. `test_the_redirect_and_meta_checks` holds the
temporary/permanent/no-capture cases. The prompt registry and the indexability
playbook tool now list it; the registry cost/severity guard names it LOW.

**Was — the deferral this replaced.**
Brief v18 step BA registers `TEC/redirect-temporary` — a 302/303/307 on what
should be a permanent move (LOW). The product **could not** raise it, because the
crawler discards the status code of each redirect hop at capture:
`fetch.py:43` stores `redirect_chain=[str(r.url) for r in resp.history]`, URLs
only, and `types.py:42` says so — "intermediate URLs, in order". So a 302 is
indistinguishable from a 301 in stored evidence, and no downstream check can
recover it (channel 20260910-0850 confirmed the hold).

**Scope, named so it is its own item and not a rider on BA.** `resp.history`
entries carry `.status_code`, so the *capture* is a one-line change. What makes
it a separate item is the stored shape: `redirect_chain` is a list of strings
read by `evidence.py` (`:99`, `:272`) and counted for length by TEC's
`redirect-chain` check, so changing it to carry per-hop status (pairs, or a
parallel `redirect_statuses` field) touches all three, and old stored runs keep
the old shape — the reader has to tolerate both. Until then `redirect-temporary`
is registered by the brief but never fires; it is deferred here, not dropped.

The other twelve BA checks landed at item 137 (`redirect-to-404`,
`meta-robots-conflict`, `noindex-linked`/`-in-sitemap`, the canonical relation
and terminal families); this is the one that could not.
