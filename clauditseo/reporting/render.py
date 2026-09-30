"""Report templates: run, comparison, monthly trend — each in client-facing
or internal voice. Markdown always; Australian English prose; DD Month YYYY
dates in prose, ISO 8601 in data tables. Every metric carries source and
confidence; anything unassessed renders as [TO CONFIRM: …].
"""

from __future__ import annotations

import re
from datetime import datetime

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.engine import registry

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


class _NotAssessedChecks:
    """Membership by name, not by a hand-kept list.

    `-not-assessed` is a check's own declaration that it measured nothing;
    `playbook.py:480` already reads that suffix rather than maintaining a
    second list naming the same checks, and a duplicate list is exactly how
    this one drifted — `contrast-not-assessed` (a11y.py) and
    `sitemap-coverage-not-assessed` (tec.py) were both absent from it, so each
    printed to a client document as a defect with a fix instruction, under
    "What we found", rather than as the scope limit it states about itself.
    """

    def __contains__(self, check_id: str) -> bool:
        return check_id.endswith("-not-assessed")


NOT_ASSESSED_CHECKS = _NotAssessedChecks()

#: Bumped whenever this module changes what a document *says* — a corrected
#: figure, a regrouping, a change to what an audience is told. Not for
#: wording. It is stored on every deliverable so a file written by an older
#: renderer can be told apart from a current one, which the app previously
#: could not do: six reports sat in the list showing "Title duplicate on 2
#: pages" above thirteen URLs, long after the code stopped producing it.
#:
#: 1.0.0 is the first recorded version. Anything stored as NULL predates the
#: record and is reported as unknown rather than assumed to match — a
#: superseded document that looks current is the failure being fixed, and
#: guessing in the safe-sounding direction would recreate it.
#:
#: 1.1.0: the client-facing "not assessed" note stopped naming the providers
#: behind a gap. That changes what a client is told, so documents written by
#: 1.0.0 are superseded rather than merely older — including two I generated
#: minutes before making the change and had to go back and re-mark. The rule
#: only works if it is applied at the moment the wording changes, which is
#: the moment it is easiest to skip.
#:
#: 1.3.0: the coverage rule reached the four page-dependent dimensions it had
#: missed, so the composite and the weights in the score table both move for
#: any run whose crawl fetched nothing. A stored document written by 1.2.0
#: states a different headline figure for the same run — which is the case
#: this constant exists to make visible.
#:
#: 1.4.0: every run report now opens with what the crawl actually reached —
#: pages fetched, URLs blocked by robots.txt, and whether it stopped early —
#: and a crawl that fetched nothing states that as its own scope limit. A
#: document written by 1.3.0 makes the same claims with no way for a reader
#: to know what they rest on.
#:
#: 1.5.0: the crawl-scope line states the ratio when the site declares a
#: total — "6 of 272 discovered pages fetched" rather than "6 pages fetched".
#: A document written by 1.4.0 states the same fetch count with no way for a
#: reader to tell a small site from two percent of a large one.
#:
#: 1.6.0: the composite carries the breadth it was computed from — "94.23 out
#: of a possible 100 — measured across 6 of 272 discovered pages (2.2%)" — on
#: the run headline and both sides of a comparison. A document written by
#: 1.5.0 states the same score with the ratio two paragraphs away in the scope
#: line and nothing joining them, and the score is what gets quoted.
#:
#: 1.15.0: a finding under "New issues" that sits on a page the baseline never
#: fetched now carries the reason saying so. A document written by 1.14.0 lists
#: it among new issues with nothing to distinguish it from a real regression,
#: which on a widening re-audit is most of the section.
#:
#: (The notes above stop at 1.6.0 and the constant moved to 1.14.0 without
#: them. Not backfilled here — a note written now from a diff is a
#: reconstruction, and this block is only worth anything if each line was
#: written by the change it describes.)
#:
#: 1.16.0: the reason lines under "New issues" and "Not re-checked" state
#: client paths as backticked identifiers and give the overflow count a source
#: tag. Not cosmetic: un-backticked, any path containing a digit read to the
#: honesty gate as an untagged metric, so `assert_report_honest` refused the
#: whole document and the comparison deliverable could not be produced in
#: either direction. A document written by 1.15.0 does not exist — the
#: generator raised instead of writing one.
#:
#: 1.17.0: a dimension left unmeasured because the crawl fetched no page now
#: says so, instead of being reported as a property of the tier. The single
#: `tier_permits_external` flag was `tier is not T1 and bool(crawl.pages)`, so
#: a blocked T2 or T3 run told the client "this audit tier does not call
#: external data sources" — false, and about the thing they bought. Documents
#: written by 1.16.0 for a blocked non-T1 run state that false cause. Stored
#: findings predating the split keep the old key and re-render unchanged, so
#: an old deliverable and a fresh one can still be compared.
#:
#: 1.19.0: the trend deliverable's "Completed runs on record" counts readings
#: of the site rather than every run of it, and where it still exceeds its own
#: table it now says why on the same line. A document written by 1.18.0 states
#: a larger figure — measured at 5 above a four-row table for
#: `www.acme.com.au`, the extra being an eight-page verification — with
#: nothing on the page reconciling the two, and both tagged
#: `confidence: high`.
#:
#: 1.22.0: a brief finding quoting a figure the analyst flagged as derived
#: carries `ANALYST_FIGURE_NOTE` however many figures the brief flagged. The
#: judgement used to be made against `figures_to_verify`, which is capped at
#: `FIGURES_TO_VERIFY_CAP` so the operator's panel stays readable — so a brief
#: flagging forty-five figures caveated the first forty in the client's
#: document and printed the other five unmarked. Documents written by 1.21.0
#: and earlier understate which of their numbers are derived, and by a margin
#: that depends on how many figures the brief happened to flag.
#:
#: 1.23.0: a brief finding recorded before the derived-figure flag existed is
#: judged when it renders instead of reading back a stamp it never carried.
#: `record_expert_findings` writes the flag at record time and nothing
#: recomputed it, so 1.22.0 changed no run already in the database — measured
#: read-only, 188 of 275 stored `EXP:*` findings carry no flag at all, and 7 of
#: those quote a figure their own brief flagged as derived. Documents written
#: by 1.22.0 and earlier over those runs print those 7 as plain claims. Seven
#: is a floor: the fallback can only ask the stored `figures_to_verify`, which
#: is the capped list, because the uncapped set is not kept.
#:
#: 1.24.0: a caveat that fires where there is no figure. Two rules decided the
#: derived-figure mark and only one of them knew what a number in prose is —
#: `ungrounded_figures` masks caveat blocks, dates, standards references and
#: heading levels before flagging a digit run, while `_declares_a_figure`, which
#: asks whether a finding's summary quotes one of those flagged values, read the
#: summary with `extract_numbers` and no such rule. So `E.164` in a summary
#: matched a stored `164`, and a document written by 1.23.0 or earlier can print
#: `[TO CONFIRM: figure derived by the analyst, not measured]` beside a finding
#: whose summary quotes no derived figure at all — observed on
#: `local-signals/nap-inconsistent`, whose summary quotes two phone numbers off
#: the site. Both halves now read the same vocabulary, and the vocabulary gained
#: the two shapes it was missing: an ordered-list index or numbered heading, and
#: a two-part standards reference whose second half is digits. A caveat that
#: fires without cause is not the smaller error: it teaches the reader to
#: discount the mark, which costs the true instances 1.23.0 won.
#:
#: 1.26.0: a comparison document states the frame its counts were computed
#: under. A document written by 1.25.0 or earlier prints "New issues",
#: "Resolved issues", "Persisting issues" and "Not re-checked" with nothing
#: on the page saying how many pages the current run fetched or which
#: dimensions it audited - so a reader cannot tell twelve fixes from a
#: narrower crawl, and every one of those four counts is unframed. The scope
#: was in the diff the whole time (`compare_runs`' `scope` key, since the
#: round-023 delta) and the Compare screen was already printing it; the
#: document was the surface that did not. WF-02.
#: 1.25.0: the honesty gate reads the specialist briefs, and a brief number
#: the document cannot ground is marked rather than printed as though it had
#: been checked. Gate G7's grounding half reads `narrative`, which
#: `_analyst_section` builds with `EXP:*` excluded by construction, and the
#: brief section is appended to the document after that text is made — so the
#: most figure-dense, most model-written section of a deliverable was the one
#: text neither half of the gate ever grounded. The other half read it and
#: passed it trivially, because every brief row carries a `provenance_tag`,
#: which says where the prose came from and nothing about whether the number
#: in it was measured. A document written by 1.24.0 or earlier therefore
#: prints a fabricated brief figure beside a true source tag and no caveat —
#: audit 013's defect, in the section its fix did not reach. Measured
#: read-only over the live database: of 275 stored `EXP:*` findings, 242
#: ground cleanly and 33 quote a number the deliverable's evidence does not
#: contain. **The partition read 244 / 31 for one round, and the correction
#: is CQ-195.** 31 is the load-bearing figure and is right - it is what THIS
#: clause newly marks - but it is not the size of the ungrounded set: two of
#: the 33 were already flagged by `figure_is_unverified`, so the old sentence
#: silently moved them into "ground cleanly" and made 275 add up against a
#: population of 275 that it had partitioned twice. Re-derived by importing
#: `ungrounded_uncaveated_lines`, `_evidence_text` and `figure_is_unverified`
#: and running them over every stored `EXP:*` row, with `declared` read from
#: `runs.expert_report_figures` per run and tool as the renderer reads it -
#: the product's own predicates, not a re-implementation. The same run
#: measures a seventh number worth having: 6 rows are flagged by
#: `figure_is_unverified` and ground cleanly here, which is the two clauses
#: asking different questions and is why `or` is right at
#: `generate.py:157-160`. Two of the 33 are version
#: strings (`Apache/2.4.52`, `HTTP/1.1`) which the exemption list does not
#: cover and which now carry a caveat that reads oddly; caveating an
#: identifier is the safe direction to be wrong in, and widening the
#: exemptions is a hole in the gate the whole provenance invariant rests on.
#:
#: No corpus total is stated here, deliberately, and the reason is not the
#: one this paragraph used to give. It used to read that `CHANGELOG.md` and
#: two test docstrings SAY the marked set moved from nine to eight, against
#: a branch measured moving from seven to six - three registers, two
#: numbers, one name (CQ-182). That was true when this block landed at
#: `2a13b85` and stopped being true two commits later at `6a316d8`, which
#: corrected all three to seven-to-six. So the one block a maintainer reads
#: to learn what a stored document's version says opened by describing the
#: two registers beside it as they stood a round earlier - CQ-185, and the
#: same shape as the finding it was reporting. The standing reason to state
#: no corpus total here is the durable half: this block did not measure one.
#: 1.27.0: a comparison document states one count of what the current run
#: read. 1.26.0 put the frame in the document and took its page count from
#: the diff's `pages_crawled` — the distinct **paths** the run touched — four
#: lines above a coverage ratio computed from `scope["pages_fetched"]`, the
#: **pages** a check could read. Both were introduced by the word "fetched"
#: and both tagged `confidence: high`. They differ wherever a site serves one
#: page under two URL forms, so a document written by 1.26.0 states two counts
#: of one quantity and a reader has no way to tell which is which: on run
#: `f80bc200` of `www.acme.com.au`, "the current run fetched 224 pages"
#: against "measured across 235 of 272 discovered pages (86.4%)". This
#: version states the page count, names the path count as the separate
#: quantity it is where the two differ, and says the number once where they
#: agree. CQ-04, carried since report 024, and UX-84.
#:
#: The same version stops `_scope` standing the attempt count in for the page
#: count. `stats["eligible"]` is engine 0.9.0 and newer; before it the count
#: fell through to `stats["fetched"]`, which is URLs **tried** — so a document
#: written by 1.26.0 or earlier, for a run stored before engine 0.9.0, states
#: a coverage percentage whose numerator counts DNS failures and PDFs as
#: pages read. It is now derived from the stored evidence through the one
#: eligibility rule, and every count says which of `recorded`, `derived` or
#: `attempted` produced it. Measured over the eleven runs in the operator's
#: database: no stored figure moves, because every page those runs fetched
#: resolved — the correction is to the run that resolves nothing.
#:
#: 1.28.0: a comparison document states the baseline it counted against.
#: 1.26.0 and 1.27.0 both frame run B, and two of the document's four counts
#: are not decided by run B: `why_new` and `why_not` read the baseline's
#: crawled paths and audited dimensions, so `## New issues` and `## Resolved
#: issues` stood on a frame that appeared nowhere on the page. A document
#: written by 1.27.0 or earlier therefore prints a new-issue count a reader
#: cannot interpret — 825 new issues means one thing against a baseline that
#: crawled the whole site and another against one that crawled 99 paths, and
#: on the pair in the operator's database (`8fdeb042` against `f80bc200`) it
#: was the second. `compare_runs` had both values in hand at
#: `_run_scope(conn, run_a)` and wrote only run B's. This version carries the
#: baseline's page count, path count and dimensions in the diff and prints a
#: second sentence naming the two counts it frames, or says it could not
#: establish the baseline's frame — which is what a comparison gets whose
#: baseline run recorded neither its crawled paths nor its dimensions, since
#: the diff is computed live and can carry only what the two runs behind it
#: hold. WF-28, carried
#: since report 023, and UX-22, carried since 019: one residue seen from two
#: sides, closed in one change.
#:
#: 1.29.0: `## Score movement` states the frame its two composites were
#: computed under. Every version to 1.28.0 framed the four *counts* and left
#: the two *scores* bare — the one section of the document that asks a client
#: to read a movement was the only section with no frame, and the baseline
#: sentence 1.28.0 added scopes itself to `New issues` and `Resolved issues`
#: in its own words, so it directs the reader not to apply it here. A document
#: written by 1.28.0 or earlier therefore prints, on the pair in the
#: operator's database, `91.06` against `70.52` with nothing saying that the
#: first is T2 over seven dimensions and the second T3 over eight, or that
#: A11Y was audited only by the second. It also prints a coverage ratio on
#: exactly one of the two — the *more* complete run, since the baseline's site
#: declared no total — so the narrower run reads as the unqualified one. This
#: version names both tiers and both dimension counts, names any dimension
#: only one of the runs audited in either direction, and where only one
#: composite carries a coverage ratio says why the other has none. It states
#: those facts and makes no claim about what the movement means: UX-86,
#: carried since report 092, under `QUESTIONS.md` Q-13 answered **print both,
#: framed** by the operator on 23 August 2026.
#:
#: 1.30.0: the honesty caveat stops telling a client that a number they
#: published themselves was invented for them. One note is placed on two
#: conditions and only one of them is about provenance, so on every row the
#: grounding half marked, `[TO CONFIRM: figure derived by the analyst, not
#: measured]` asserted something nothing had established. Measured read-only
#: over the live database: of 275 stored `EXP:*` findings, 33 are ungrounded
#: and **13 of them are marked for an identifier rather than a figure** —
#: `1300 922 223` on four rows, `[505 Toorak Rd]` / `[3142]` on two, an HTTP
#: `200` on three, `foundingDate "2019"`, `Apache/2.4.52` and `HTTP/1.1`. A
#: document written by 1.29.0 or earlier therefore states, of each of those,
#: that the analyst derived it: at
#: `reports/out/www-acme-com-au-run-client-2026-08-22-91f9ad50.md:295`,
#: "Published phone 1300 922 223 … not valid E.164" carries the note, and the
#: phone number is the client's own. This version says "not measured by this
#: report", which is true on both conditions and true of an identifier. The
#: gate is untouched and marks exactly the rows it marked before — the reach
#: is unchanged and only the claim is. CQ-194, carried since report 087, under
#: `QUESTIONS.md` Q-7 answered **change the caveat's wording** by the operator
#: on 24 August 2026; the alternative, grounding a brief line against the
#: evidence the brief was given, was measured to ground 0 of the 33 because
#: that evidence is stored nowhere.
#:
#: 1.31.0: a page count says which of three ways it was arrived at, wherever
#: it is rendered. `99de440` began storing `pages_fetched_basis` beside every
#: `pages_fetched` and no renderer read it, so a count the crawler counted and
#: one reconstructed from the stored page list reached a client identical —
#: the frame clause of the provenance invariant, breached on the figure the
#: coverage ratio's numerator is. Measured read-only over the operator's
#: fifteen stored runs: 5 `recorded`, **6 `derived`, 1 `attempted`**, 3 with no
#: evidence; two of them report 235 pages and only one of those was counted at
#: crawl time. Every document a run of the current engine produces is
#: unchanged, because `recorded` renders nothing and the current engine
#: records: the text that moves is a document over an older run, which is
#: exactly the population whose count was standing on an unstated derivation.
#: A run whose evidence predates `99de440` recorded no rung, so a diff
#: computed from it has none to spread and the count is left silent rather
#: than assumed into the worst one. CQ-205, carried since report 092;
#: report 098 remediation item 9.
#:
#: 1.32.0: the coverage ratio's two ends name two populations. A document
#: written by 1.31.0 says "measured across 235 of 272 discovered pages
#: (86.4%)", where "discovered pages" governs both figures while being true
#: of only the second — the numerator is pages a check could read, the
#: denominator is URLs the sitemap declares. The same noun did the same two
#: jobs in the crawl-scope sentence ("6 of 272 discovered pages fetched").
#: **No figure moves**: 235, 272 and 86.4% are the same three numbers, which
#: is the whole content of `QUESTIONS.md` Q-14's answer — *close it, already
#: satisfied by round 092, the ratio stays 235 of 272* — and this version is
#: that answer's stated reason ("no word does two jobs") made true at the one
#: clause where round 100 found it false. The wording is the screen's own,
#: which has said "the sitemap declares" since the share caption was written.
#: CQ-70, carried since report 034 and the oldest open High in the register;
#: dispositioned a strict xfail by round 100 with a round-110 deadline, closed
#: here instead.
#: 1.33.0: a dimension code enumerated in prose for a client carries the name
#: the registry already holds for it — "audited Accessibility (A11Y),
#: AI-Surface (AIS), Content (CNT), …" where 1.32.0 wrote "audited A11Y, AIS,
#: CNT, …" and stopped. UX-85, carried by eleven reports. **No figure moves
#: and no fact is added or withheld**: the same dimension set, named. What
#: changes is that the audience the frame was written for can read it, which
#: is the whole of what the frame is for.
#:
#: The name accompanies the code rather than replacing it, because the code
#: keeps appearing below — every finding is tagged "(source: A11Y module)"
#: and every new one "A11Y was not audited by the baseline", 825 of them on
#: the comparison this was measured against. The frame is now the document's
#: key for all of them, which is why those tags are deliberately unchanged.
#:
#: Three surfaces, not the one the finding named: the comparison scope
#: sentence (current run and baseline), the run report's header line, and the
#: score-movement difference clause. A document written by 1.32.0 states the
#: same dimensions in a vocabulary its reader has no key to.
#:
#: The operator's copy is untouched — the audience distinction is what is
#: EXPLAINED, never which facts are stated.
#:
#: 1.34.0: where exactly one of a comparison's two composites carries a
#: coverage ratio, the sentence giving the reason the other carries none no
#: longer states completeness as though it were a shortfall. `_breadth_absence`
#: names four causes; three are deficiencies and the colon sentence was shaped
#: for them, but the fourth — a run that reached every page its site declared —
#: is the opposite. A document written by 1.33.0 reads "Only the current
#: composite carries a coverage ratio: the baseline run reached every page its
#: site declared", offering a run at 100% of its declared pages as the
#: qualified one beside a run at 86.4%, in the sentence written to stop that
#: exact misreading. 1.34.0 writes "Only the current composite carries a
#: coverage ratio. The baseline run reached every page its site declared, so
#: there is no shortfall to state."
#:
#: The three deficiency causes are word-for-word unchanged, and so is which
#: composite carries the ratio and which is silent. No fact is added or
#: withheld: only the frame the absence is read under, which is the frame
#: clause of the provenance invariant applied to an absence rather than a
#: figure. UX-89, carried from report 095.
#:
#: 1.35.0: a duplicate count says what it stopped counting. The ONP duplicate
#: checks changed the *population* their counts are taken over — a URL that is
#: an alternate form of another page, the same page under a tracking query, is
#: no longer a competitor for the title, so it leaves `members` and is recorded
#: under `canonical_aliases` — and the sentence reporting the count was left as
#: it was. A document written by 1.34.0 says "3 pages share the title …" of a
#: population two URLs smaller than the one the previous run's "5 pages" was
#: taken over, and gives its reader nothing to tell those apart. So a site that
#: added canonicals between two runs reads a falling count as a fix, when what
#: moved is what was counted. 1.35.0 appends the excluded count to the same
#: sentence.
#:
#: **No figure moves and no fact is withheld**: the count is the one the check
#: computed either way, and the alternate forms were already out of it before
#: this version existed. What changes is that the frame the number is read
#: under is stated where the number is, which is the provenance invariant's
#: frame clause applied to a population rather than to a source.
#:
#: Both renderers of a finding's own sentence carry it — `_finding_line`, and
#: `_group_line` where a group of one prints its finding's summary verbatim —
#: because both print the sentence the exclusion reframes. A grouped line of
#: more than one prints a check label and a page count instead, over the same
#: narrowed population, so the note is summed across the group rather than
#: dropped. CQ-230, first raised at report 100 and carried to 114.
#: 1.36.0: Security & transport reaches the client's copy, and the well-known
#: paths the sweep requested are disclosed (item 143 step BD and its addendum).
#: `SEC` named one thing when this renderer was written - the analyst layer's
#: `prompt-injection-content` note, internal by design - so every SEC finding
#: was held back from the client as a "security note". Since 0.22.0 SEC is a
#: scored dimension whose rows (HSTS, exposed files, cookie flags) are the
#: client's to fix, and `TEC/not-https` and `TEC/security-headers`, which the
#: client copy printed, were purged into it. So the internal-only filter now
#: names the note, not the dimension. The disclosure line renders in both
#: audiences and in `run-free`: the fetches happen in the free sweep.
RENDERER_VERSION = "1.36.0"

#: The analyst layer's own security note, the one SEC row that stays internal.
INTERNAL_SECURITY_CHECKS = frozenset({"prompt-injection-content"})


def _reason_markdown(reason: dict | None) -> str:
    """A comparison reason, formatted for a document that answers to the gate.

    `compare_runs` returns `{lead, paths, overflow}` and no formatting, so this
    is the only place the markdown exists. Two rules, both the gate's:

    - **Paths are backticked.** `checks.py` exempts `` `/…` `` because a URL
      path is an identifier rather than a measurement. Un-backticked, any
      client path containing a digit — `/blog/7-5m-for-smes` — reads as an
      untagged metric and `assert_report_honest` refuses the whole document.
    - **The overflow count is a measurement**, so it carries a source tag. Not
      through `m()`, which wraps the value itself and would read
      "(+8 (source: engine, confidence: high) more)" — the tag belongs at the
      end of the clause, and the previous wording is preserved exactly so this
      refactor changes no document text.

    Note what the gate actually does, because the previous version of this
    formatting claimed otherwise in its own comment: `unsourced_number_lines`
    tests `"source:" not in line.lower()` against the **whole line**. A line
    carrying any `source:` is exempt in full, so the overflow tag also exempts
    the paths beside it. The backticks are therefore load-bearing only
    on the lines with no overflow — and they stay, because a line's exemption
    should not depend on how many pages happened to be in it.
    """
    if not reason:
        return ""
    lead = reason["lead"]
    paths = reason.get("paths") or []
    if not paths:
        return lead
    named = ", ".join(f"`{p}`" for p in paths)
    overflow = reason.get("overflow") or 0
    tail = (f" (+{overflow} more, {provenance_tag()})"
            if overflow else "")
    return f"{lead}: {named}{tail}"


def au_date(iso: str | None) -> str:
    if not iso:
        return "[TO CONFIRM: date not recorded]"
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %B %Y").lstrip("0")


def provenance_tag(source: str = "engine", confidence: str = "high") -> str:
    """The one spelling of where a figure came from and how sure it is.

    Extracted because it was not one spelling. `m()` below has claimed since
    it was written to be "the only way numbers enter prose", and nineteen
    other string literals across this module, `generate.py` and
    `analysts/expert.py` wrote the same tag out by hand — table cells, prose
    tails, the analyst rows, the field-metric lines. Nothing made them move
    together, so a change to how the product names its own evidence would
    have reached the copy someone edited and no other.

    Deliberately without the surrounding punctuation. Inline in a sentence the
    tag is parenthesised and in a markdown table it is a bare cell, so the
    brackets belong to the caller and the vocabulary belongs here — a helper
    that owned the parentheses too would simply not be callable from the three
    table paths, which is how the copies started.

    `tests/test_provenance_tag.py` holds it: no string literal under
    `clauditseo/` may put `source:` and `confidence:` together except this
    one. The TypeScript surface at `dashboard/src/components.tsx:511-514` renders
    a fourth shape and is a named deferral, not an oversight — see the
    round-061 row in `audits/DISPOSITIONS.md`.
    """
    return f"source: {source}, confidence: {confidence}"


def m(value, source: str = "engine", confidence: str = "high") -> str:
    """A metric with its provenance attached — the only way numbers enter prose."""
    return f"{value} ({provenance_tag(source, confidence)})"


def section_provenance(source: str, confidence: str,
                       scope: str = "below") -> str:
    """One provenance tag for a model-written section, hoisted (Q-57).

    A model-written section — the client plan, a brief's findings table —
    used to repeat the same source tag on every line, thirty consecutive
    times and each tag longer than the line it annotated. This states it
    once under the heading; the per-line tags are dropped for the lines that
    share it, and a line whose provenance differs still carries its own.

    Two readers depend on the exact lead `Provenance note`:
    `reporting/checks.py:_SECTION_SOURCE`, which reads this line as sourcing
    the block beneath it, and the client, who reads it as the sentence that
    says where the figures came from. Changing the lead is changing the gate,
    so it is spelled in one place and both read it from here.

    The `source:`/`confidence:` vocabulary is `provenance_tag`'s and only
    `provenance_tag`'s — `tests/test_provenance_tag.py` holds that — so this
    calls it rather than writing the pair a second time.
    """
    # The short `[TO CONFIRM]` marker, not the full `ANALYST_FIGURE_NOTE`
    # literal: this line describes the convention, it is not itself a caveat on
    # a figure, so it must not read as one to a reader or count as one to a
    # test scanning for the note the findings carry.
    return (f"_Provenance note — every figure {scope} carries "
            f"{provenance_tag(source, confidence)}, except a line that states "
            f"its own. A figure this report did not measure is marked "
            f"[TO CONFIRM]._")


def not_assessed(what: str, reason: str) -> str:
    """The shape the product uses for a fact it could not establish.

    One shape, many reasons: the sentence a reader learns to recognise is
    `Not assessed: <what>. Reason: <why>.`, and every surface that cannot
    produce a figure fills in its own true why. Sharing the *string* would be
    the wrong economy — it would force one reason onto causes that differ, and
    a wrong reason reads as confidently as a right one.
    """
    return f"[TO CONFIRM: Not assessed: {what}. Reason: {reason}.]"


#: What every surface says when a run has no composite — the scoring layer
#: returns None rather than 0.0 when no dimension carried measurable weight.
#: One string, because the alternative was three: the report rendered
#: `None (source: engine, confidence: high)`, a null wearing a provenance tag
#: that asserted high confidence in it; chat raised TypeError; the CLI printed
#: the word None. A score that does not exist is the same fact everywhere, and
#: it is the `[TO CONFIRM: …]` case the product already has a vocabulary for.
#:
#: No confidence is stated: confidence qualifies a measurement, and there is
#: no measurement here to qualify.
NO_COMPOSITE = not_assessed("composite score",
                            "no dimension carried measurable weight")


def composite_phrase(score: float | None, *, precision: int = 1) -> str:
    """The composite as prose: the figure when there is one, the not-assessed
    sentence when there is not. Callers supply the surrounding sentence."""
    return NO_COMPOSITE if score is None else f"{score:.{precision}f}"


#: How many actions lead the document. Enough to be a plan, few enough that
#: it is one — a ranked list of twenty is the same enumeration in a
#: different order.
ACTIONS_SHOWN = 5


def _priority_lines(run: dict, groups: list[dict], audience: str) -> list[str]:
    """What to do first, from the scoreboard's own arithmetic.

    `biggest_gains` weights each check's deduction onto the composite and has
    existed in the engine the whole time; it shaped the app and never the
    document. The report stated its conclusion and then handed the reader 238
    findings with no order to work in.

    Points are the ceiling of what fixing every instance recovers, not a
    promise — the deduction is rate-based and capped per severity — and that
    caveat travels with the number rather than being left for the reader to
    infer.
    """
    from clauditseo.persistence.runs import biggest_gains

    gains = biggest_gains(run.get("subscores") or {})[:ACTIONS_SHOWN]
    if not gains:
        return []
    by_check = {f"{g['dimension']}/{g['check_id']}": g for g in groups}
    out = ["", "## What to do first", "",
           "Ordered by what each fix recovers on the score. The points are a "
           "ceiling — the deduction is capped and rate-based, so fixing every "
           "instance recovers at most this much, not exactly it. "
           f"({provenance_tag()})", ""]
    for i, gain in enumerate(gains, 1):
        key = f"{gain['dimension']}/{gain['check_id']}"
        group = by_check.get(key)
        pages = gain.get("pages")
        reach = (f" across {pages} page{'' if pages == 1 else 's'}"
                 if pages else "")
        out.append(
            f"{i}. **{_check_label(gain)}**{reach} — up to "
            f"{gain['composite_points']:.1f} points on the composite "
            f"({provenance_tag()})")
        if group and group.get("recommendation"):
            # Same rule as a finding line: guidance carrying a figure
            # ("120-155 characters", "exactly one H1") says where the figure
            # comes from. The gate caught these, which is the gate working —
            # a new section does not get to skip the rule the old ones keep.
            rec = group["recommendation"]
            if re.search(r"\d", rec):
                rec += (
                    f" ({provenance_tag(group['dimension'] + ' module guidance')})")
            out.append(f"   - {rec}")
    out.append("")
    return out


def _group_by_check(findings: list[dict]) -> list[dict]:
    """One entry per check, with the pages it affects.

    A hundred lines reading "N of M images on /X lack alt text" is not a
    finding list, it is the same finding a hundred times. The document said
    so itself — "usually one template rather than a separate problem in
    each" — and then enumerated all 427 separately, arguing against its own
    conclusion. One line with a page count says the same thing and can be
    acted on.

    Ordered by how many pages a check touches, because that is the order the
    work should be done in. Ties broken by severity so a critical on three
    pages outranks a low on three.

    `pages` comes from the engine's own rule rather than a second count made
    here. Counting findings and calling them pages is what produced "Title
    duplicate on 2 pages" above a list of thirteen URLs: two findings, each a
    group of pages sharing a title. Counting raw URLs instead is what made
    the plan say 99 where the finding list said 100.
    """
    from clauditseo.engine.scoring import page_paths

    groups: dict[str, dict] = {}
    for f in findings:
        key = f"{f['dimension']}/{f['check_id']}"
        g = groups.setdefault(key, {
            "dimension": f["dimension"], "check_id": f["check_id"],
            "severity": f["severity"], "source": f["source"],
            "model_id": f.get("model_id"), "confidence": f["confidence"],
            "recommendation": f.get("recommendation", ""),
            "findings": [], "urls": [],
        })
        g["findings"].append(f)
        for url in f.get("affected_urls") or []:
            if url not in g["urls"]:
                g["urls"].append(url)
        if SEVERITY_ORDER.index(f["severity"]) < SEVERITY_ORDER.index(g["severity"]):
            g["severity"] = f["severity"]
    for g in groups.values():
        # One list, counted and printed. The headline used to count one thing
        # and the list below it show another, so they could disagree without
        # either being wrong on its own terms. Deriving both from the same
        # sequence removes the possibility rather than correcting an instance
        # of it. First-seen order, because crawl order is closer to site
        # structure than sorting alphabetically would be.
        ordered: list[str] = []
        for url in g["urls"]:
            for path in page_paths([url]):
                if path not in ordered:
                    ordered.append(path)
        g["page_list"] = ordered
        # Zero when a check names no URL — a site-level finding is real but
        # is not "on N pages", and the line says so rather than reporting a
        # count of something else under the word pages.
        g["pages"] = len(ordered)
    return sorted(groups.values(),
                  key=lambda g: (-(g["pages"] or len(g["findings"])),
                                 SEVERITY_ORDER.index(g["severity"])))


#: Above this many pages, listing them all buys nothing a count does not.
URLS_SHOWN = 8


def _not_assessed_line(f: dict, audience: str) -> str:
    """What was not measured, at the detail the reader can act on.

    The gap itself belongs in both documents — a client who is not told a
    dimension went unmeasured will read its absence as a clean bill. What
    differs is the cause. "openpagerank (403)" is the operator's problem to
    fix and names a third party the client has no relationship with, no
    account for, and no way to act on; in a client document it reads as the
    supplier's plumbing showing through.

    Rebuilt from the structured evidence rather than by editing the summary
    prose, because a sentence assembled for one audience cannot be reliably
    unpicked for another — and a near-miss at removing a provider name is
    worse than not trying.

    Three causes, told apart from the evidence rather than by the wording
    that happened to be built:

    - a source was asked and refused,
    - a source answered but does not carry that signal,
    - nothing is configured for it.

    The first version of this only handled refusal, which is what the run in
    front of me happened to be doing. When the keys started working, a
    different branch produced "The configured provider (moz, openpagerank)
    does not supply it" in a client document — the same leak through the door
    I had not looked at.
    """
    evidence = f.get("evidence") or {}
    failing = evidence.get("providers_failing") or []
    answering = evidence.get("providers_answering") or []
    unmeasured = evidence.get("unmeasured") or []
    if audience == "client" and unmeasured:
        what = ", ".join(unmeasured)
        # Four causes, four true sentences. "Not attempted" is first because
        # it outranks the others: at a tier that makes no external calls, what
        # is configured and whether it would have answered are both unknown,
        # and any sentence about them is a claim the run cannot support.
        # `tier_calls_external` and `pages_fetched` are the pair that replaced
        # the single `tier_permits_external`, which was `tier is not T1 and
        # bool(crawl.pages)` — two silences collapsed into one flag, so a
        # crawl that fetched nothing was reported to the client as a property
        # of the tier they had bought. Five stored findings predate the split
        # and carry only the old key; it is read where the new pair is absent,
        # so re-rendering a stored deliverable still states what it stated.
        no_external_call = (
            evidence["tier_calls_external"] is False
            if "tier_calls_external" in evidence
            else evidence.get("tier_permits_external") is False)
        why = ("this audit tier does not call external data sources"
               if no_external_call else
               "the crawl fetched no page to measure"
               if evidence.get("pages_fetched") is False else
               "the data source for this was unavailable during this run"
               if failing else
               "the sources configured for this site do not report it"
               if answering else
               "no data source is configured for it")
        return f"- {f['dimension']}: [TO CONFIRM: Not assessed: {what}. Reason: {why}.]"
    # No default reason. "no data source available" was appended even when the
    # sentence above it had just named the source that answered, so the line
    # contradicted itself — and the contradiction read as the tool being
    # confused about its own inputs.
    reason = evidence.get("reason")
    tail = f" Reason: {reason}" if reason else ""
    return f"- {f['dimension']}: [TO CONFIRM: {f['summary']}{tail}]"


def _alias_note(findings: list[dict], src: str, audience: str) -> str:
    """What a duplicate count stopped covering, said where the count is read.

    CQ-230, first raised at report 100 and carried to 114. The ONP duplicate
    checks changed the *population* their counts are taken over: a URL that is
    an alternate form of another page — the same page under a tracking query —
    is no longer a competitor for the title, so it is dropped from `members`
    and recorded under `canonical_aliases`. The summary was left as it was:
    *"3 pages share the title …"*, with no word for which three. So a site that
    added canonicals between two runs sees the count fall and reads a fix,
    when what changed is what was counted.

    Until this, `canonical_aliases` was written at two sites in
    `clauditseo/modules/onp.py` and read at none. A key nothing reads is not
    evidence; it is a note to nobody, which is the shape DISCIPLINE rule 4
    names — coverage nobody reports is coverage nobody has.

    Both renderers of a finding's own sentence get it, because both print the
    summary the exclusion silently reframes: `_finding_line`, and `_group_line`
    where a group of one prints its finding's summary verbatim. Grouped lines
    of more than one print a check label and a page count instead, and those
    are a count of the same narrowed population, so the note is summed across
    the group rather than dropped.

    The paths themselves are internal-only and capped at `URLS_SHOWN`, for the
    reason the page list beside them is: a client is being told the count's
    frame, not handed a second list to act on.

    **No `m()` on the count, and that is the gate's own rule rather than an
    exemption from it.** G7 is line-scoped: a number must sit on a line
    carrying a `source:` tag, and this clause is appended inside the sentence
    the line's trailing `provenance_tag` already covers — the same standing
    the summary's own *"3 pages"* has had since the tag was introduced.
    Tagging it again renders *"Excludes 2 (source: ONP module, confidence:
    high) alternate URL forms"*, a parenthesis mid-clause and a second tag on
    a line that already ends in one. `src` is still taken, because the caller
    that hands it in is the one that knows which it is, and a future note that
    lands on its own line will need it.
    """
    aliases: list[str] = []
    for f in findings:
        for path in (f.get("evidence") or {}).get("canonical_aliases") or []:
            if path not in aliases:
                aliases.append(path)
    if not aliases:
        return ""
    note = (f" Excludes {len(aliases)} alternate URL form"
            f"{'' if len(aliases) == 1 else 's'} of these pages, which are "
            f"not counted above.")
    if audience == "internal":
        shown = aliases[:URLS_SHOWN]
        listed = ", ".join(f"`{a}`" for a in shown)
        more = (f" and {len(aliases) - len(shown)} more"
                if len(aliases) > len(shown) else "")
        note += f" ({listed}{more})"
    return note


def _group_line(g: dict, audience: str) -> str:
    """One check, its reach, and — when it is few enough to act on — where."""
    src = (f"{g['dimension']} module" if g["source"] == "deterministic"
           else f"model judgement ({g['model_id']})")
    n = len(g["findings"])
    # One instance keeps its own sentence, because the summary carries detail
    # a check name cannot — "24 of 31 images", "2 pages share the same meta
    # description". Several become a count, because a hundred sentences that
    # differ only in a path are one fact stated a hundred times.
    #
    # Either way the source tag stays on the line the sentence is on. Moving
    # the summary to a sub-line without it produced exactly the untagged
    # numbers the honesty check exists to stop.
    # Pages when we know pages. `n` is a count of findings, and a finding is
    # not a page: `title-duplicate` raises one per group of pages sharing a
    # title, so two findings covered thirteen pages and the headline said
    # two — above the list of thirteen that contradicted it.
    what = (g["findings"][0]["summary"] if n == 1
            else f"{_check_label(g)} on {g['pages']} pages" if g["pages"]
            else f"{_check_label(g)} — {n} findings")
    # CQ-230. Appended to `what` rather than to the assembled line, so the
    # frame sits inside the sentence the count is in and ahead of the
    # provenance tag — a clause after the tag reads as a note about the tag.
    what += _alias_note(g["findings"], src, audience)
    lines = [f"- **{g['severity']}** — {what} "
             f"({provenance_tag(src, g['confidence'])})"]
    # The pages counted above, not the URLs they were derived from. Listing
    # URLs under a page count put thirteen entries under "12 pages" — right
    # twice over and contradictory on the page.
    shown = g["page_list"][:URLS_SHOWN]
    if shown:
        listed = ", ".join(f"`{p}`" for p in shown)
        more = (f" and {m(len(g['page_list']) - len(shown))} more"
                if len(g["page_list"]) > len(shown) else "")
        lines.append(f"  - {listed}{more}")
    if audience == "internal":
        lines.append(f"  - check `{g['dimension']}/{g['check_id']}`")
    if g.get("recommendation"):
        verb = "What to do" if audience == "client" else "Fix"
        rec = f"{verb}: {g['recommendation']}"
        if re.search(r"\d", rec):
            rec += f" ({provenance_tag(src + ' guidance')})"
        lines.append(f"  - {rec}")
    return "\n".join(lines)


def _check_label(g: dict) -> str:
    """A check id as a sentence. `img-alt-missing` -> "Img alt missing"."""
    return g["check_id"].replace("-", " ").capitalize()


def _path(url: str) -> str:
    from urllib.parse import urlsplit

    split = urlsplit(url)
    return (split.path or "/") + (f"?{split.query}" if split.query else "")


def _finding_line(f: dict, audience: str) -> str:
    src = (f"{f['dimension']} module" if f["source"] == "deterministic"
           else f"model judgement ({f['model_id']})")
    # CQ-230, as in `_group_line`: the population a duplicate count was taken
    # over, said beside the count rather than left in an evidence key nothing
    # reads.
    line = (f"- **{f['severity']}** — {f['summary']}"
            f"{_alias_note([f], src, audience)} "
            f"({provenance_tag(src, f['confidence'])})")
    if audience == "internal":
        line += f"\n  - check `{f['dimension']}/{f['check_id']}` · fingerprint `{f['fingerprint']}`"
    if f.get("recommendation"):
        verb = "What to do" if audience == "client" else "Fix"
        rec = f"{verb}: {f['recommendation']}"
        # Guidance figures (e.g. "50-60 characters") need provenance too.
        if re.search(r"\d", rec):
            rec += f" ({provenance_tag(src + ' guidance')})"
        line += f"\n  - {rec}"
    return line


def _diff_line(f: dict, audience: str) -> str:
    """One line for a finding in a comparison bucket, routed by what it is.

    A `-not-assessed` check is a statement that a dimension was not measured.
    It is not a defect, it has no fix the reader can apply, and its stored
    `recommendation` is addressed to the operator — so `render_run_report`
    has sent these through `_not_assessed_line` since round 003, which
    rebuilds the sentence from structured evidence and never prints the
    stored text.

    This template did not, and rendered them through `_finding_line`
    instead. Four findings in the live database recommend setting two
    environment variables under the prefix this product was renamed away from
    on 14 August 2026, so the comparison deliverable told a fee-paying client
    to configure a product that no longer exists — measured at eight
    occurrences of that prefix in one client document, two per finding across
    all four buckets. The prefix is not spelled here, because
    `tests/test_naming.py` owns it and refuses it everywhere that ships.
    Carried as UX-10 since report 019.

    `.claude/DISCIPLINE.md` rule 3 names this exact pair in its own evidence:
    "the vendor leak in the run template but not comparison". The router is
    one function rather than a condition repeated at four call sites for the
    same reason — a fifth bucket routes correctly by construction.
    """
    if (f.get("check_id") or "") in NOT_ASSESSED_CHECKS:
        return _not_assessed_line(f, audience)
    return _finding_line(f, audience)


def _score_table(run: dict) -> list[str]:
    lines = ["| Dimension | Score | Weight | Provenance |",
             "|---|---|---|---|"]
    for dim, sub in sorted((run.get("subscores") or {}).items()):
        if not isinstance(sub, dict) or "score" not in sub:
            continue
        if sub.get("applicable", True):
            # Three different facts, not one.
            #
            #   nominal 0            deliberately excluded from the score
            #   nominal > 0, eff 0   intended to score, but nothing was
            #                        measured — a missing provider key
            #   otherwise            its share of the composite
            #
            # The first draft called both of the first two "not scored",
            # which told a client that off-page was excluded by choice when
            # it was actually dark for want of an API key. That is the
            # difference between a decision and a gap.
            nominal = (sub.get("detail") or {}).get("nominal_weight")
            if not nominal:
                weight = "not scored"
            elif not sub.get("weight"):
                weight = "not measured this run"
            else:
                weight = f"{round(sub['weight'] * 100, 1)}%"
            # A number in a score column is read as a score. A11Y at 65.4
            # with a "not scored" label beside it is the lowest figure in the
            # table and the one most likely to be quoted back — the label is
            # doing all the work of preventing a wrong conclusion, and a
            # label loses that argument against a number every time. So the
            # figure is withdrawn from the column and stated in words that
            # cannot be mistaken for a contribution.
            if weight in ("not scored", "not measured this run"):
                lines.append(f"| {dim} | — | {weight} "
                             f"| {provenance_tag()} |")
                continue
            lines.append(f"| {dim} | {sub['score']} | {weight} "
                         f"| {provenance_tag()} |")
        else:
            lines.append(f"| {dim} | not applicable | 0% "
                         f"| {provenance_tag()} |")
    return lines


#: Said beside a number this document did not measure. The analyst already
#: declares some of these — `figures_to_verify`, produced when it writes the
#: brief and stored on `expert_reports.figures` — and until 1.22.0 the
#: reporting path knew nothing about it, so the product held a correct answer
#: to "which numbers here are unverified" and printed neither it nor a warning.
#:
#: This is what makes admitting a declared figure honest rather than
#: convenient. An earlier attempt widened the gate to accept them and left
#: the document presenting them as measured; it was reverted.
#:
#: **The note says what this document did, not where the number came from,
#: and 1.30.0 is where it stopped saying the second.** `generate` places it on
#: either of two conditions (`generate.py:157-161`) and only one of them knows
#: anything about provenance: `figure_is_unverified` asks the brief whether IT
#: flagged the figure, while the grounding half asks only whether this
#: deliverable's measured evidence contains the token. A brief's prose quotes
#: the client's own site back at them, so the second fires on identifiers —
#: measured read-only over the live database, 13 of the 31 rows it newly marks
#: name a phone number, a postcode, a street number, an HTTP status or a
#: server version. Telling a client that the phone number on their own website
#: was "derived by the analyst" is not a caveat but a false statement, on the
#: one marker every true caveat in the document depends on being believed.
#: `QUESTIONS.md` **Q-7**, answered by the operator on 24 August 2026.
#:
#: The name is left alone deliberately: six test modules and three
#: version-history paragraphs import or cite it by this name, and renaming a
#: constant is not what the answer decided. What it says is the thing that had
#: to become true.
ANALYST_FIGURE_NOTE = "[TO CONFIRM: not measured by this report]"


def _analyst_section(run: dict, audience: str) -> tuple[list[str], str]:
    """Returns (lines, narrative_text) — narrative_text feeds the G7 check.

    `EXP:*` rows are specialist-brief findings, and the deliverable renders
    them in their own section with the provenance rule that section applies.
    They are stored as model judgement like every analyst finding, so they
    landed here as well: each one printed twice in one document, once with
    the confidence the brief never stated and once without it. A client
    reading both saw the tool give two answers for one finding.

    **Contract rows are excluded too, whatever their dimension** — the
    completion of that separation (item 137-answer, Q-56). A conforming
    brief's row carries `evidence.contract`, and Q-56 moves its *analysis*
    rows to `EXP:content-*`; but a brief also emits its *free* checks (a
    content brief marking a node thin at "166 words, below the 300/600-word
    floor"), which stay under `CNT` by the Free/Analysis split and are still
    model judgement. Left in, that row is judged by `ungrounded_narrative_
    numbers` — the strict grounding this section owns, which has no caveat
    escape — and its floors, absent from one run's evidence, refuse the whole
    document. Every brief row belongs to `_expert_section`'s caveat-aware
    rule, so none of them is judged here. The analyst LAYER's own insights
    carry no `contract` flag and are what remains.
    """
    analyst = [f for f in run.get("findings", [])
               if f["source"] == "model-judgement"
               and not (f.get("dimension") or "").startswith("EXP:")
               and not (f.get("evidence") or {}).get("contract")]
    if not analyst:
        return [], ""
    lines = ["", "## Analyst insights",
             "",
             "_Model judgement — commentary only. These insights never enter the "
             "score above, and every one cites the evidence it rests on._", ""]
    narrative_parts = []
    for f in analyst:
        # No `analyst_figure_unverified` branch here. It was written for this
        # section and could never fire in it: the only writer of the flag is
        # `record_expert_findings`, which stamps dimension `EXP:*`, and this
        # section excludes `EXP:*` three lines above. Half of a claimed
        # two-site change, dead on arrival, recorded in the CHANGELOG as
        # landed. The marker belongs to `_expert_section`, which renders the
        # findings that carry the flag.
        lines.append(_finding_line(f, audience))
        cites = ", ".join(f.get("evidence", {}).get("cites", []))
        if audience == "internal" and cites:
            lines.append(f"  - cites evidence items: {cites}")
        narrative_parts.append(f["summary"] + " " + (f.get("recommendation") or ""))
    return lines, "\n".join(narrative_parts)


#: The one cause `_breadth_absence` names for which the absence is
#: completeness rather than a shortfall — UX-89. Named once, and compared by
#: value at the one caller that has to word the difference, so that caller can
#: tell it from the three deficiencies without matching on the sentence: a
#: matcher over the prose is CQ-110's own defect, and this register does not
#: need another instance of it. `_breadth_phrase` is unaffected by
#: construction — it asks only whether the return is `None`.
BREADTH_COMPLETE = "{run} reached every page its site declared"


def _breadth_absence(scope: dict | None) -> str | None:
    """Why a composite carries no coverage ratio, or `None` if it carries one.

    The silence rule of `_breadth_phrase`, given a name and a reason, because
    a second reader needed the reason and not the clause. `## Score movement`
    prints two composites side by side and only one of them may carry a
    ratio — on the operator's own pair it is the *more* complete run that
    carries it, since the baseline declared no sitemap total — so the section
    has to say why the other has none (UX-86).

    Four causes, not one, and they are not the same fact. A run that reached
    every page its site declared is silent for a reason that **is**
    completeness; a run with no crawl record is silent because nothing was
    established. One sentence over both would be wrong for one of them, which
    is the rule `_diff_scope_lines` states for its own per-finding reasons.

    `{run}` rather than a subject, so the one predicate serves both runs and
    the caller supplies which. `_breadth_phrase` asks only whether this is
    `None`: the predicate has one owner, and the clause beside the figure and
    the sentence explaining its absence cannot drift apart.
    """
    if not scope:
        return "{run} stored no crawl record"
    fetched, discovered = scope.get("pages_fetched"), scope.get("discovered")
    if fetched is None:
        return "{run} recorded no count of the pages a check could read"
    if not discovered:
        return "{run}'s site declared no page total to measure against"
    if fetched >= discovered:
        return BREADTH_COMPLETE
    return None


def _breadth_phrase(scope: dict | None) -> str:
    """What share of the site a composite was computed from, as a clause.

    A composite from a fraction of a site read exactly like one from all of
    it: 94.23 from six pages of the 272 a sitemap declared, with the ratio
    two paragraphs away in the scope line and nothing joining them. The
    qualifier travels with the figure instead, because the figure is what
    gets quoted.

    The ratio itself, not `measured_share`. That figure is breadth-aware now
    and reads 0.0176 for the same run, because it scales site-level signals —
    robots.txt, HTTPS, backlinks — that were measured in full. Understating
    is the right direction for an internal number and the wrong thing to put
    in front of a client, who would read it as "we did 2% of the job".

    Silent under the scope line's rules, which `_breadth_absence` above now
    owns and names: no declared total, or a crawl that reached everything
    declared. Over-fetching means link-following found pages the sitemap
    omits, which is a finding about the sitemap rather than coverage above
    complete.

    No source tag of its own — the honesty rule is per line, and every line
    this attaches to already carries one for the score it qualifies. Tagging
    each of three more figures is what made the scope line the least readable
    sentence in the document.
    """
    if _breadth_absence(scope) is not None:
        return ""
    fetched, discovered = scope["pages_fetched"], scope["discovered"]
    # CQ-70. Each end names its own population; the three figures are
    # untouched. "discovered pages" governed both while being true of only
    # the second, and Q-14's answer — the ratio stays 235 of 272 — rests on
    # the claim that no word does two jobs, which was false here and is true
    # now. See `DISCOVERED_BASIS_PHRASE` for why the denominator's phrase can
    # be silent and the numerator's noun cannot.
    return (f" — measured across {fetched} {PAGES_FETCHED_NOUN}, "
            f"{_discovered_phrase(scope)} ({fetched / discovered:.1%})")


#: The key `compare_runs` writes the comparison's own frame under. Three
#: surfaces meet at this spelling and only two of them can read this name:
#: the writer (`compare_runs` in `clauditseo/persistence/runs.py`, which
#: imports it) and this module. The third is `dashboard/src/views.tsx`, which
#: is TypeScript and cannot import a Python constant — it spells the key by
#: hand and always will, exactly as it does for `PAGES_FETCHED_BASIS_NOTE`
#: below.
#:
#: So the constant does not by itself stop the three drifting apart, and this
#: comment used to claim it did. What stops them is
#: `tests/test_the_comparison_scope_key_is_named_once.py`, which reads all
#: three files and fails if any one of them stops going through this name —
#: CQ-204, carried for sixteen reports.
DIFF_SCOPE_KEY = "scope"


#: How a page count was arrived at, in the words the reader gets — CQ-205.
#: `_pages_fetched` in `clauditseo/persistence/runs.py` writes one of these
#: three rungs beside every `pages_fetched`, and until this constant existed
#: nothing rendered it: a count the crawler counted and a count reconstructed
#: from the stored page list reached a client identically.
#:
#: **`recorded` is deliberately absent, and that is the design rather than an
#: omission.** It is the ordinary rung — 5 of the 15 runs in the operator's
#: database, and every run the current engine writes — and a qualifier that
#: appears on every line is one nobody reads. The unusual rungs carry weight
#: only because the usual one is silent, which is the rule `_breadth_phrase`
#: above already follows for its own ratio. A caller asking for the note of a
#: recorded count gets nothing, by `.get`, not by a branch at each site.
#:
#: One owner, three surfaces: `_run_phrase` (both of `_diff_scope_lines`'
#: sentences), `_scope_lines` (the run report), and `scopeCount` in
#: `dashboard/src/views.tsx`, which cannot import this and is held to the same
#: words by `tests/test_a_page_count_says_how_it_was_arrived_at.py` reading
#: both files.
PAGES_FETCHED_BASIS_NOTE = {
    "derived": "count derived from the stored page list",
    "attempted": "count is URLs attempted, not pages read",
}


#: What the coverage ratio's DENOMINATOR counted, in the words the reader gets
#: — CQ-70, the oldest open High in the register at the time it was fixed.
#: `_scope` writes `discovered_basis` beside every `discovered`; this turns it
#: into the phrase that follows the figure, so the ratio's two ends name two
#: populations instead of sharing one.
#:
#: **The words are the screen's, not new ones.** `dashboard/src/views.tsx`
#: already renders "against 272 the sitemap declares" and "272 declared pages
#: this crawl reached". The document was the one surface saying "discovered
#: pages" over both ends, and 1.32.0 brings it to the wording the screen has
#: used since the share caption was written — so the two surfaces cannot
#: disagree about what the denominator is, which is the half of CQ-04 that
#: keeps recurring.
#:
#: An unknown basis renders no phrase at all, for `_basis_note`'s reason: a
#: scope dict this renderer did not build has told us nothing about where its
#: denominator came from, and naming one would be the invention the key exists
#: to prevent. The numerator's own noun is unconditional and carries the
#: separation on its own, so the silent case is still not one word over two
#: populations.
DISCOVERED_BASIS_PHRASE = {
    "sitemap": "the sitemap declares",
}


#: What the ratio's NUMERATOR counted, unconditionally — this is the definition
#: of `pages_fetched` (`_pages_fetched` in `clauditseo/persistence/runs.py`),
#: not a claim about a particular run, so it needs no basis to be sayable.
PAGES_FETCHED_NOUN = "pages a check could read"


def _discovered_phrase(scope: dict) -> str:
    """`"of 272 the sitemap declares"` — the ratio's denominator, said once.

    One owner for two surfaces, because they are two renderings of one fact:
    `_breadth_phrase`'s clause beside the composite and `_scope_lines`' crawl
    scope sentence both put this figure after the page count, and a fix
    reaching one of them is CQ-04's shape exactly.
    """
    phrase = DISCOVERED_BASIS_PHRASE.get(scope.get("discovered_basis") or "")
    return f"of {scope['discovered']}" + (f" {phrase}" if phrase else "")


def _basis_note(basis: str | None) -> str:
    """The parenthetical for a page count's rung, or nothing.

    Absent and `recorded` both return `""`, and they are not the same fact —
    absent means the run this count came from recorded its evidence before
    `99de440` and never recorded a rung. They
    render alike because the alternative is stating a rung on no evidence,
    which is the invention this whole key exists to prevent; the distinction
    is kept where it can be acted on, in the stored row, rather than guessed
    at here.
    """
    note = PAGES_FETCHED_BASIS_NOTE.get(basis or "")
    return f" ({note})" if note else ""


def _diff_scope_lines(scope: dict | None, audience: str) -> list[str]:
    """The frame a comparison's counts were computed under, stated with them.

    WF-02, carried since report 023. `compare_runs` has returned this since
    the round-023 delta, with a comment saying why: the diff carries the scope
    it was computed under, so no surface has to restate it and none can
    restate it differently. The screen took it. The client document did not —
    it printed "New issues", "Resolved issues", "Persisting issues" and "Not
    re-checked" as four counts, and nothing on the page said how many pages
    the current run fetched or which dimensions it audited. "Resolved issues —
    12" then reads as twelve fixes whether the current run re-crawled the
    whole site or eight pages of it.

    CQ-04, closed here and at `compare_runs`: the frame is *two* counts, not
    one. How many pages a check could read, and how many distinct paths those
    pages sit on. Round 090 stated the second under the first's name, four
    lines above a coverage ratio computed from the first — one document, one
    run, two numbers, one word.

    Not `_scope_lines`, which reads a *run's* stored `crawl_evidence`
    (`pages_fetched`, `robots_blocked`, `discovered`). This reads the *diff's*
    scope, which is a different shape describing a different thing: what the
    comparison itself could see. Sharing one function would have forced one
    sentence onto two facts.

    Silence is not an option here, which is where this departs from
    `_scope_lines`. That one returns nothing when a run recorded no scope,
    because a run stored without evidence has not told us it saw none. A
    comparison is the opposite case: the counts are printed regardless, so an
    absent frame is not a fact withheld but four figures with nothing holding
    them. The document says it could not establish the frame, in the shape the
    product already has for that.
    """
    unknown = not_assessed(
        "the frame this comparison was computed under",
        "the comparison recorded neither the pages the current run fetched "
        "nor the dimensions it audited")
    if not scope:
        return [unknown, ""]

    paths = scope.get("pages_crawled")
    dimensions = scope.get("dimensions") or []
    # CQ-04 and UX-84. Two counts of what the current run read reach this
    # function and they are different quantities: `pages_fetched` is the pages
    # a check could read, and `pages_crawled` is the distinct paths those
    # pages sit on — fewer, wherever the site serves one page under two URL
    # forms. Round 090 put this sentence four lines above the composite's
    # coverage ratio, which is computed from the other one, and both were
    # introduced by the word "fetched" and tagged `confidence: high`. On run
    # `f80bc200` of `www.acme.com.au` that read "fetched 224 pages" over
    # "measured across 235 of 272 discovered pages".
    #
    # So the sentence states the page count, which is the one the ratio uses,
    # and names the path count as the separate quantity it is — but only where
    # the two differ, since saying both when they agree is the same defect
    # from the other side.
    # Either count is None whenever the current run stored no crawl record —
    # `compare_runs` writes `None if crawled is None else len(crawled)`, and
    # omits the page count entirely for a run with no evidence. Printing a
    # null is how `None (source: engine, confidence: high)` reached a client
    # once already, through the door the run report's fix did not reach.
    pages = scope.get("pages_fetched")
    counted, audited = _run_phrase(pages, paths, dimensions, audience,
                                   scope.get("pages_fetched_basis"))
    if counted is None and audited is None:
        return [unknown, ""]

    known = " and ".join(part for part in (counted, audited) if part)
    # One tag at the end of the sentence, not one per figure — the rule round
    # 062 established for `_scope_lines` and for the same reason: what needs
    # provenance here is the claim, and the figures in it are fields of one
    # stored row read in one expression, so they could not disagree.
    lines = [f"Comparison scope: the current run {known}. ({provenance_tag()})",
             ""]
    if counted is None:
        lines += [not_assessed(
            "the pages this comparison was computed over",
            "the current run stored no crawl record, so the counts below "
            "rest on an unrecorded number of pages"), ""]
    if audited is None:
        lines += [not_assessed(
            "the dimensions this comparison covers",
            "the current run recorded no audited dimension"), ""]

    # WF-28 and UX-22, one residue seen from two sides. Everything above
    # frames run B, and two of the document's four counts are not decided by
    # run B at all: `why_new` and `why_not` read the *baseline's* crawled
    # paths and audited dimensions, so `## New issues` and `## Resolved
    # issues` stand on a frame the page did not carry. Measured in report 091
    # on the pair the operator's database holds — `## New issues — 825`
    # against a baseline that had crawled 99 paths and recorded no sitemap
    # total, so `_breadth_phrase` printed nothing beside its composite either.
    #
    # Two sentences, not one merged one. A sentence carrying both runs'
    # figures makes the reader hold four numbers and decide which pair goes
    # with which count, and the count each frames is named in its own
    # sentence instead.
    b_counted, b_audited = _run_phrase(scope.get("pages_fetched_baseline"),
                                       scope.get("pages_crawled_baseline"),
                                       scope.get("dimensions_baseline") or [],
                                       audience,
                                       scope.get("pages_fetched_basis_baseline"))
    if b_counted is None and b_audited is None:
        # Reached when the baseline run recorded neither its crawled paths
        # nor its dimensions: no comparison is kept anywhere — `compare_runs`
        # is called live by both its callers and the `reports` table holds a
        # path to a rendered file — so a diff carries baseline keys exactly
        # when run A's evidence has them, and this branch is that run rather
        # than an older artefact. The counts are printed regardless, so this
        # is the same case the docstring argues above for the current run,
        # one run over. An absent
        # frame here is not a fact withheld but a figure with nothing holding
        # it, and saying nothing would let `## New issues` read as framed by
        # the sentence above it, which frames a different run.
        lines += [not_assessed(
            "the baseline this comparison counted against",
            "the comparison recorded neither the pages the baseline run "
            "fetched nor the dimensions it audited, and the New issues and "
            "Resolved issues counts are decided against them"), ""]
    else:
        known_baseline = " and ".join(
            part for part in (b_counted, b_audited) if part)
        lines += [f"Baseline scope: the baseline run {known_baseline}. New "
                  f"issues and Resolved issues are counted against it. "
                  f"({provenance_tag()})", ""]
    return lines


def _movement_frame_lines(run_a: dict, run_b: dict,
                          audience: str) -> list[str]:
    """The frame the two composites under `## Score movement` were computed
    under, stated above them.

    UX-86, and `QUESTIONS.md` **Q-13**, which gated it. The section printed
    two composites and nothing else. Measured on the pair the operator's
    database holds: baseline `8fdeb042` is T2 over seven dimensions at 91.06,
    current `f80bc200` is T3 over eight at 70.52, and A11Y was audited only by
    the current run — so twenty points of a twenty-point fall may be the
    dimension that was added, and the document said nothing either way.
    `site_trend` would refuse that pair on tier alone and this function never
    asks it; giving the judgement one owner is WF-58 and is the next step, not
    this one. What this does is state the terms.

    **Print both, framed** (operator, 2026-08-23, answering Q-13). The
    alternative on the table was to decline to print a movement where the pair
    fails the comparability predicate; the operator took the cheaper and less
    presumptuous one, so the composites stay and the facts go beside them.
    Nothing here asserts what the movement *means* — that inference is left to
    the reader deliberately, and a later change that adds it is reversing an
    operator decision rather than improving a sentence.

    **Above the figures, not below.** The rule WF-02's fix established for the
    comparison's other counts: a frame printed under the figures it frames is
    a footnote. The two scope sentences higher up do not discharge this — the
    baseline one scopes itself to *New issues and Resolved issues* in its own
    words, which tells the reader not to apply it here.

    **Symmetric, because the framing that was already present was not.**
    `_breadth_phrase` attaches a coverage ratio to a composite only where that
    run recorded enough to compute one, and on the measured pair that is the
    current run — so the run that read 99 paths and skipped accessibility was
    the one with no qualifier on it. A frame naming one run's tier and not the
    other's would print the same defect in the sentence written to close it,
    so both tiers are always named, a dimension only the *baseline* audited is
    named as readily as one only the current run did, and an absent ratio
    states its own cause.

    Its own cause, not a shared one. Reports 092 and 094 both give that cause
    as *the baseline stored no sitemap total*; measured over the operator's
    database it is a rung further back — `8fdeb042` has no crawl evidence row
    at all — and one of the four causes `_breadth_absence` distinguishes is a
    run that reached everything its site declared, for which the absence *is*
    completeness. A single sentence would be false for at least one run it was
    printed over.

    **Silence is never the answer, including when the frame is unknown.** Both
    columns are `NOT NULL` in `audit_runs`, so a real run always has them; a
    caller assembling a run dict by hand may not, and inventing a tier would
    be the class of error the whole document exists to avoid.
    """
    tier_a, tier_b = run_a.get("tier"), run_b.get("tier")
    dims_a = sorted(run_a.get("dimensions") or [])
    dims_b = sorted(run_b.get("dimensions") or [])
    lines: list[str] = []

    if not (tier_a and tier_b and dims_a and dims_b):
        unrecorded = [name for name, tier, dims
                      in (("the baseline run", tier_a, dims_a),
                          ("the current run", tier_b, dims_b))
                      if not tier or not dims]
        lines.append(not_assessed(
            "the frame these two composites were computed under",
            f"{' and '.join(unrecorded)} recorded no tier or no dimension "
            "set, so whether the two figures were computed over the same "
            "work cannot be stated"))
    else:
        # UX-85's third consumer, found by the grep rule 3 asks for and not
        # by the report, which named only the scope sentence. This clause
        # joins codes into prose exactly as that one did — "AIS, CNT were
        # audited only in the current run" — and reaches the same client.
        # The counts a line above are `_dimension_count`, which says "8
        # dimensions" and names none, so it needs nothing here.
        only_b = _dimension_words([d for d in dims_b if d not in dims_a],
                                  audience)
        only_a = _dimension_words([d for d in dims_a if d not in dims_b],
                                  audience)
        if tier_a == tier_b and not (only_a or only_b):
            # The one case where the two clauses would restate each other:
            # same tier, same set, so the counts are one count and the
            # difference sentence has nothing to name.
            frame = (f"Score frame: both runs were audited at tier {tier_a} "
                     f"over the same {_dimension_count(len(dims_a))}.")
        elif tier_a == tier_b:
            frame = (f"Score frame: both runs were audited at tier {tier_a}, "
                     f"the baseline over {_dimension_count(len(dims_a))} and "
                     f"the current run over {len(dims_b)}.")
        else:
            frame = (f"Score frame: the baseline run was audited at tier "
                     f"{tier_a} over {_dimension_count(len(dims_a))} and the "
                     f"current run at tier {tier_b} over {len(dims_b)}.")
        if not (only_a or only_b) and tier_a == tier_b:
            difference = ""
        elif only_b and only_a:
            difference = (f"{', '.join(only_b)} {_was(only_b)} audited only "
                          f"in the current run, and {', '.join(only_a)} only "
                          "in the baseline run.")
        elif only_b:
            difference = (f"{', '.join(only_b)} {_was(only_b)} audited only "
                          "in the current run.")
        elif only_a:
            difference = (f"{', '.join(only_a)} {_was(only_a)} audited only "
                          "in the baseline run.")
        else:
            difference = "Both runs audited the same dimensions."
        stated = " ".join(part for part in (frame, difference) if part)
        lines.append(f"{stated} ({provenance_tag()})")

    # The other half of UX-86: which composite carries a coverage ratio is
    # decided by whether that run's *site* declared a total, not by how much
    # of it was read — so the absence reads as completeness unless the page
    # says otherwise. Only where exactly one of the two has one; two silent
    # composites have no asymmetry to explain, and inventing one would be this
    # finding pointing the other way.
    absent_a = _breadth_absence(run_a.get("scope"))
    absent_b = _breadth_absence(run_b.get("scope"))
    if (absent_a is None) != (absent_b is None):
        carries = "baseline" if absent_a is None else "current"
        missing, run = ((absent_b, "the current run") if absent_a is None
                        else (absent_a, "the baseline run"))
        if missing == BREADTH_COMPLETE:
            # UX-89. Three of the four causes are deficiencies and the colon
            # sentence is shaped for them; this one is not. Printed through
            # that shape it offers a run's completeness as the reason it
            # carries no ratio, so the run that read all of what it declared
            # reads as the qualified one beside a run that read 86.4% of its
            # own — the misreading this whole block exists to stop, pointing
            # the other way. Two sentences and one tag, per the one-tag-per-
            # line rule `_breadth_phrase`'s docstring states.
            stated = missing.format(run=run)
            lines.append(
                f"Only the {carries} composite carries a coverage ratio. "
                f"{stated[0].upper()}{stated[1:]}, so there is no shortfall "
                f"to state. ({provenance_tag()})")
        else:
            lines.append(
                f"Only the {carries} composite carries a coverage ratio: "
                f"{missing.format(run=run)}. ({provenance_tag()})")

    return lines + [""]


def _dimension_count(n: int) -> str:
    return f"{n} dimension{'' if n == 1 else 's'}"


def _was(codes: list[str]) -> str:
    return "was" if len(codes) == 1 else "were"


def _dimension_words(codes: list[str], audience: str) -> list[str]:
    """Dimension codes as the audience they are printed for can read them.

    UX-85, carried by eleven reports. Every surface below joined the stored
    `dimensions` list verbatim, so the copies whose audience is not the
    operator opened with "audited A11Y, AIS, CNT, LOC, OFP, ONP, PRF, TEC"
    and stopped. That is this module's own audience rule read backwards: the
    distinction between the two copies is what gets *explained*, never which
    facts are stated. The client was given the fact and not the meaning.

    **The name accompanies the code rather than replacing it**, because the
    code does not stop being used further down. A client document tags every
    finding "(source: A11Y module, confidence: high)" and every new one
    "A11Y was not audited by the baseline" — 825 findings on the comparison
    this was measured against. Keying each of those would be noise; keying
    them once, in the frame sentence that already sits above the first count,
    makes them all readable. So the frame is deliberately made the document's
    key and the per-finding tags are deliberately left alone — a bare code
    used as a repeated source tag is a different shape from a set enumerated
    in prose, and it has its own finding if it needs one.

    The registry holds the words — `AccessibilityModule.name` is
    "Accessibility" — rather than a table here, which would be a second
    vocabulary to keep in step with the modules. A code the registry does not
    hold falls back to itself: a run stored under a dimension since removed
    still renders, and inventing a name for one would be worse than printing
    the code the run actually recorded.
    """
    if audience != "client":
        return list(codes)
    known = registry.all_modules()
    return [f"{known[c].name} ({c})" if c in known else c for c in codes]


def _run_phrase(pages: int | None, paths: int | None,
                dimensions: list[str], audience: str,
                basis: str | None = None) -> tuple[str | None, str | None]:
    """`(what it read, what it audited)` for one run of a comparison.

    Shared by the current run's sentence and the baseline's rather than
    written twice. The grain rule this encodes is round 091's and it is the
    reason the function exists: `pages` is what a check could read and `paths`
    is the distinct paths those pages sit on, they differ wherever a site
    serves one page under two URL forms, and a count of one stated under the
    other's word is the half of UX-84 that was a wrong word rather than a
    wrong number. A baseline is the easier of the two places to break it —
    a run stored before the evidence column has paths and no page count at
    all — so the two sentences share this rather than agreeing by inspection.

    `basis` is CQ-205 and it attaches to the page count alone, at the end of
    the clause rather than beside the figure: a parenthetical wedged between
    "4 pages" and "across 3 distinct paths" splits one quantity's sentence in
    half with a note about the other's derivation. It is silent for a recorded
    count and for a diff that recorded no rung — `_basis_note` holds why those
    two render alike without being the same fact.

    It is deliberately *not* applied to `paths`. The path count has its own
    derivation (`len(crawled_paths)`, written by `complete_run`) with no rung
    of its own, and borrowing this one for it would state a provenance the
    stored row does not carry — CQ-04 from the other side.
    """
    if pages is not None:
        counted = f"fetched {pages} page{'' if pages == 1 else 's'}"
        if paths is not None and paths != pages:
            counted += f" across {paths} distinct path{'' if paths == 1 else 's'}"
        counted += _basis_note(basis)
    elif paths is not None:
        counted = f"read {paths} distinct path{'' if paths == 1 else 's'}"
    else:
        counted = None
    # UX-85. `audience` is required rather than defaulted, and it sits before
    # `basis` so neither call site can pass one for the other: a default here
    # would let a client call site inherit the operator's copy silently, which
    # is the failure mode this parameter exists to remove.
    words = _dimension_words(dimensions, audience)
    audited = f"audited {', '.join(words)}" if words else None
    return counted, audited


def _scope_lines(scope: dict | None) -> list[str]:
    """What the crawl reached, stated before anything is claimed about it.

    Every figure below rests on the pages this run fetched, and the document
    had no line saying how many that was — so a crawl blocked at robots.txt
    produced a scored report indistinguishable from a full audit. A reader
    cannot weigh a finding without knowing what was looked at, and the
    strongest case is the one where the answer is nothing.

    Silence when the scope was not recorded: a run stored without evidence
    has not told us it saw none, and inventing a zero here would be the same
    class of error this line exists to prevent.
    """
    if not scope:
        return []
    pages, blocked = scope["pages_fetched"], scope["robots_blocked"]
    # The ratio, when the site declared a total. "6 pages fetched" reads as a
    # small site; on a real audit it was 6 of the 272 the sitemap declares,
    # and nothing in the document distinguished those. Only when the total is
    # known and larger: "6 of 6" would assert the site is six pages, which is
    # the false confidence this exists to remove, and a crawl with no sitemap
    # has no total to state.
    #
    # CQ-70, the same one-noun-over-two-populations defect `_breadth_phrase`
    # carried: "6 of 272 discovered pages fetched" said "discovered pages" of
    # a numerator that is pages a check could read and a denominator that is
    # URLs the sitemap declares. The count leads and keeps its rung note
    # attached to it; the total follows with its own words.
    discovered = scope.get("discovered")
    fetched = f"{pages} page{'' if pages == 1 else 's'} fetched"
    # CQ-205. The same rung `_run_phrase` renders in the comparison, on the
    # run report's own sentence — one quantity, two documents, and a fix
    # reaching one of them is CQ-04's shape. It sits after the figure and
    # before the robots count so the note stays attached to the number it
    # qualifies: the blocked count is a different quantity with a different
    # derivation, and a parenthetical between them reads as covering both.
    fetched += _basis_note(scope.get("pages_fetched_basis"))
    if discovered and discovered > pages:
        fetched += f", {_discovered_phrase(scope)}"
    line = f"Crawl scope: {fetched}, {blocked} URLs blocked by robots.txt"
    if scope.get("truncated_by"):
        line += f", crawl stopped early ({scope['truncated_by']})"
    # One tag at the end of the sentence, not three inside it — the same rule
    # `_shared_cause_lines` states for the sentence beside it, applied here
    # thirteen rounds after the cohort first named this line. The honesty
    # check is per line (`checks.unsourced_number_lines` flags a line with a
    # metric-like number and no tag *anywhere* on it), so one tag discharges
    # all three figures, and the three could not have disagreed in any case:
    # they are three fields of one stored `crawl_evidence` row read in one
    # expression. `m()` is therefore not the right tool for a sentence — it
    # attaches provenance to a single value, and what needs provenance here
    # is the claim.
    lines = [f"{line}. ({provenance_tag()})", ""]
    if not pages:
        # Its own statement, not a footnote to the score: the product's rule
        # is that a scope limit is a finding in its own right.
        lines += [not_assessed(
            "every page-level signal",
            "no page was fetched, so nothing below rests on this site's own "
            "pages"), ""]
    return lines


def _shared_cause_lines(cause: dict | None) -> list[str]:
    """The scope sentence, in the artefact the client actually receives.

    It is the most commercially useful thing the product says — four
    categories, the same pages, most of the open findings, usually one
    template rather than four problems — and it stopped at the screen. An
    auditor quoting it had to retype it, and nothing kept the retyped version
    honest.

    Absent when nothing clusters. No cluster is a real answer; a weak one
    stated in a client report is a claim the data does not carry.
    """
    if not cause:
        return []
    names = cause["labels"]
    joined = (", ".join(names[:-1]) + " and " + names[-1]
              if len(names) > 1 else names[0])
    # One tag at the end of the sentence, not four inside it. The honesty
    # rule is per line, and tagging every number turned the most quotable
    # line in the report into something no one could read aloud.
    return [
        "", "## Where the work concentrates", "",
        f"{joined} affect the same {cause['pages']} pages — "
        f"{cause['findings']} of {cause['grand_total']} open findings "
        f"({round(cause['share'] * 100)}%). "
        f"({provenance_tag()})",
        "",
        # No bare count: the categories are named on the line above, so
        # repeating how many there are adds nothing and would need a source
        # tag to pass the honesty check — a tag on a number the reader can
        # see for themselves is noise.
        "That is usually one template rather than a separate problem in "
        "each. Fixing it should move all of them at once, and the next "
        "audit will say whether it did.",
        "",
    ]


def well_known_disclosure(well_known: dict | None) -> str:
    """The sentence the 143 addendum specifies, from what the sweep fetched.

    The count and up to three examples are the run's own request log, and the
    user agent and date are the ones the sweep used; nothing is a constant, so
    a sweep that fetched a different list cannot be described as this one.
    Empty where the run made no sweep."""
    if not well_known or not well_known.get("fetched"):
        return ""
    paths = [r["path"] for r in well_known["fetched"]]
    examples = [p for p in ("/.git/HEAD", "/wp-login.php", "/.env") if p in paths][:3] or paths[:3]
    when = (well_known.get("at") or "")[:10]
    return (f"This audit requested {len(paths)} well-known paths on your site "
            f"(for example {', '.join(examples)}) with ordinary GET requests, once "
            "each, to check whether they are publicly readable. It did not log in, "
            "scan ports or send anything other than a normal page request. Your "
            f"hosting logs may show these requests from {well_known.get('user_agent') or 'the audit crawler'}"
            f"{f' on {when}' if when else ''}.")


def _span(findings: list[dict]) -> tuple[str | None, str | None]:
    """The first and last `measured_at` of a section's findings."""
    dates = sorted(f["measured_at"] for f in findings if f.get("measured_at"))
    return (dates[0], dates[-1]) if dates else (None, None)


def _date_range(start: str | None, end: str | None) -> str:
    """"on 18 September 2026", or "from 18 September 2026 to 23 September
    2026" - dates in the form the honesty gate reads as a date."""
    if not start:
        return "on a date not recorded"
    a, b = au_date(start), au_date(end or start)
    return f"on {a}" if a == b else f"from {a} to {b}"


def render_run_report(site: dict, run: dict, audience: str,
                      shared_cause: dict | None = None,
                      brand: dict | None = None,
                      free_only: bool = False,
                      front: str = "",
                      as_of: dict | None = None) -> tuple[str, str]:
    """Returns (markdown, analyst_narrative).

    `as_of` is item 239 step 7: the document is the site's record - a frozen
    copy of the Latest View - rather than one audit's. `run` is then the
    audit whose composite is current, carrying the ledger's open findings,
    each dated by the run that last measured it; `as_of` holds when the copy
    was taken and the range those dates span, and the document says both,
    section by section. Absent, the document is the one run's, as before.

    `front` is the client plan (brief v18 step AY): the document the plan
    generator wrote, placed above the score and below the title, because
    that is what "the front of the client report" means - the summary a
    decision-maker reads before anything else, and the roadmap they work
    from. Empty where no plan was generated, which is the state of every
    run made before AY landed.

    `free_only` is brief v17 step AV6: the document stops after the half
    the audit answered without a model. It is stated in the document
    rather than left to be inferred from a missing section - a client
    holding two documents from one audit has to be able to tell which is
    the whole answer.

    `brand` is who the client should see on the document. Absent, it is the
    product — a report has to have a header — but an agency handing a client
    a document branded with its supplier's tool has the relationship
    backwards.
    """
    findings = [f for f in run.get("findings", []) if f["source"] == "deterministic"]
    real = [f for f in findings if f["check_id"] not in NOT_ASSESSED_CHECKS
            and f["check_id"] not in INTERNAL_SECURITY_CHECKS]
    not_assessed = [f for f in findings if f["check_id"] in NOT_ASSESSED_CHECKS]
    security = [f for f in findings if f["check_id"] in INTERNAL_SECURITY_CHECKS]

    title = ("SEO audit report" if audience == "client" else "SEO audit report (internal)")
    lines = []
    # The mark first, then the title. Only on the client's copy: an internal
    # document does not need the operator's own logo explaining who they are.
    if brand and audience == "client":
        if brand.get("logo_file"):
            lines.append(f"![{brand['name']}]({brand['logo_file']})")
            lines.append("")
        lines.append(f"**{brand['name']}**")
        lines.append("")
    dims_words = ', '.join(_dimension_words(run['dimensions'], audience))
    lines += [
        f"# {title} — {site['domain']}",
        "",
        # Item 239 step 7: the record as of a day, with the audit its score
        # is from named and dated beside it.
        (f"Prepared {au_date(as_of['taken_at'])} · the site's record as of that "
         f"day · score from audit `{run['id']}` of {au_date(run.get('finished_at'))} "
         f"({run['tier']}, dimensions {dims_words}) · engine v{run['engine_version']}"
         if as_of else
         f"Prepared {au_date(run.get('finished_at'))} · run `{run['id']}` "
         # UX-85's second consumer. The same list, the same shape, in the
         # document a client is handed most often — and outside the finding's
         # own anchor, which named the comparison only.
         f"({run['tier']}, dimensions {dims_words}) · "
         f"engine v{run['engine_version']}"),
        "",
        *([f"Each finding below is dated by the audit that last measured it: "
           f"{_date_range(as_of.get('measured_from'), as_of.get('measured_to'))}. "
           "A finding a later audit no longer found is not listed.", ""]
          if as_of else []),
        *_scope_lines(run.get("scope")),
        # The plan first, then the measurement it was written from. A
        # score table above the summary would be the document opening
        # with the thing the client asked us to interpret.
        *([front, ""] if front else []),
        "## Overall score",
        "",
        (f"Composite: {NO_COMPOSITE} Sub-scores and their weights:"
         if run["composite_score"] is None else
         f"Composite: {m(run['composite_score'])} out of a possible 100"
         f"{_breadth_phrase(run.get('scope'))}"
         f" ({provenance_tag()}). Sub-scores and their weights:"),
        "",
        *_score_table(run),
    ]

    if free_only:
        lines += ["", "_This document reports the **free checks only** — "
                  "what the audit measured mechanically. The analysis a "
                  "specialist read on top of it is not included._", ""]

    lines += _shared_cause_lines(shared_cause)

    # Accessibility is separated, not hidden.
    #
    # It is 226 of 462 open findings on the operator's own client — half the
    # list — and since 0.5.0 it carries no scoring weight at all. Interleaved
    # by severity, a client reads a document that is half accessibility,
    # presented identically to the ranking work they are paying for, with
    # nothing saying which is which. That invites the one response an audit
    # cannot recover from: you padded this.
    #
    # Separating it makes both halves defensible. The ranking findings stand
    # on their own count, and the accessibility work is presented as what it
    # is — real defects, worth fixing, not scored here.
    access = [f for f in real if f["dimension"] == "A11Y"]
    ranking = [f for f in real if f["dimension"] != "A11Y"]

    # Grouped by check, not listed one per page.
    #
    # The document used to state its own conclusion — "usually one template
    # rather than a separate problem in each" — and then enumerate all 427
    # findings separately, arguing against itself for a hundred lines. A
    # hundred entries reading "N of M images on /X lack alt text" is the same
    # finding a hundred times, and it buried the substantive work: eleven
    # pages sharing one title, eleven with no meta description, sitting
    # between them.
    groups = _group_by_check(ranking)
    lines += _priority_lines(run, groups, audience)
    intro = ("## What we found" if audience == "client" else "## Findings")
    lines += ["", intro, "",
              *([f"Measured {_date_range(*_span(ranking))}.", ""] if as_of and ranking else []),
              f"{m(len(groups))} distinct issues across "
              f"{m(len(ranking))} findings"
              + (f", plus {m(len(access))} accessibility findings listed "
                 "separately below." if access else "."),
              "",
              "Grouped by what is wrong rather than by page: one entry per "
              "issue, with the pages it affects. Most of these are a "
              "template rather than a page, which is why the counts run "
              "high and the fixes do not.", "",
              # Brief v17 step AV6. Every finding above is the sweep's -
              # `render_run_report` filters to `deterministic` on its first
              # line - and a reader was never told, so the argument the
              # product makes on screen was not being made by the artefact
              # that leaves the building.
              "Everything in this section was measured **without a model**: "
              "these are checks the audit answers mechanically, at no cost "
              "per run.", ""]
    for sev in SEVERITY_ORDER:
        at_sev = [g for g in groups if g["severity"] == sev]
        if not at_sev:
            continue
        # Named for what it holds. A variable called `pages` counting
        # findings is how "N pages" ends up over a list of a different N —
        # the label was right here only because nobody read the name.
        raised = sum(len(g["findings"]) for g in at_sev)
        lines.append(f"### {sev.capitalize()} — {m(len(at_sev))} issues "
                     f"across {m(raised)} findings")
        lines.append("")
        lines += [_group_line(g, audience) for g in at_sev]
        lines.append("")

    if access:
        lines += ["", "## Accessibility", "",
                  *([f"Measured {_date_range(*_span(access))}.", ""] if as_of else []),
                  f"{m(len(access))} findings. These are real defects and "
                  "worth fixing — several are also legal obligations — but "
                  "they are listed apart because they do not carry weight in "
                  "the score above. Search ranking impact from accessibility "
                  "is weak and indirect, and mixing the two would overstate "
                  "what fixing them does for visibility. "
                  f"({provenance_tag()})", ""]
        for sev in SEVERITY_ORDER:
            at_sev = [g for g in _group_by_check(access)
                      if g["severity"] == sev]
            if not at_sev:
                continue
            lines.append(f"### {sev.capitalize()} — {m(len(at_sev))} issues")
            lines.append("")
            lines += [_group_line(g, audience) for g in at_sev]
            lines.append("")

    if not_assessed:
        lines += ["## Not assessed", ""]
        for f in not_assessed:
            lines.append(_not_assessed_line(f, audience))
        lines.append("")

    if security and audience == "internal":
        lines += ["## Security notes", ""]
        lines += [_finding_line(f, audience) for f in security]
        lines.append("")

    # The well-known path disclosure (143 addendum, operator ruling
    # 2026-09-07): the sweep's GETs stay free and ungated, and the client is
    # told exactly what was requested, so a WAF log is never a surprise.
    # Generated from the run's own record of what it fetched, never a list.
    disclosure = well_known_disclosure(run.get("well_known"))
    if disclosure:
        lines += ["## Requests this audit made", "", disclosure, ""]

    analyst_lines, narrative = _analyst_section(run, audience)
    if free_only:
        # The narrative is still returned: it is what the honesty gate
        # grounds against, and a section that is not printed has nothing
        # to ground. Returning it and printing nothing would ask the gate
        # to check text no reader can see, so it goes too.
        analyst_lines, narrative = [], ""
    lines += analyst_lines

    lines += ["", "---",
              "_All data was collected politely (robots.txt honoured) and is stored "
              "locally. Metrics carry their source and confidence; nothing in this "
              "report is estimated silently._"]
    return "\n".join(lines), narrative


def render_comparison_report(site: dict, run_a: dict, run_b: dict,
                             diff: dict, audience: str) -> tuple[str, str]:
    lines = [
        f"# Comparison report — {site['domain']}",
        "",
        f"Baseline run `{run_a['id']}` ({au_date(run_a.get('finished_at'))}) versus "
        f"current run `{run_b['id']}` ({au_date(run_b.get('finished_at'))}). "
        "Findings are matched by stable fingerprint.",
        "",
        # WF-02: before the first count, because a frame printed under the
        # figures it frames is a footnote. The screen has stated this since
        # the round-023 delta added the key; this is the document's half.
        *_diff_scope_lines(diff.get(DIFF_SCOPE_KEY), audience),
        "## Score movement",
        "",
        # UX-86, gated on Q-13 and answered `print both, framed`. Above the
        # two figures for the same reason `_diff_scope_lines` is above the
        # four counts: a frame printed under what it frames is a footnote.
        *_movement_frame_lines(run_a, run_b, audience),
        # `m()` on a missing composite rendered `None (source: engine,
        # confidence: high)` — the same null-with-a-provenance-tag the run
        # report carried, through the door the run report's fix did not reach.
        # A figure gets its tag; the not-assessed sentence carries its own
        # reason and asserts no confidence.
        f"- Baseline composite: "
        f"{m(run_a['composite_score']) if run_a['composite_score'] is not None else NO_COMPOSITE}"
        f"{_breadth_phrase(run_a.get('scope'))}",
        f"- Current composite: "
        f"{m(run_b['composite_score']) if run_b['composite_score'] is not None else NO_COMPOSITE}"
        f"{_breadth_phrase(run_b.get('scope'))}",
        "",
        f"## New issues — {m(len(diff['new']))}", "",
        # The qualifier travels with the finding, for the reason the
        # not-re-checked section states below: a sentence asserting one cause
        # for a bucket with two kinds in it is wrong for one of them. Absent
        # on a finding the baseline was in a position to see, which is the
        # ordinary case and needs no explaining.
        *([_diff_line(f, audience)
           + (f"\n  - new to this record: {_reason_markdown(f['new_reason'])}"
              if f.get("new_reason") else "")
           for f in diff["new"]] or ["- None."]),
        "",
        f"## Resolved issues — {m(len(diff['resolved']))}", "",
        *([_diff_line(f, audience) for f in diff["resolved"]] or ["- None."]),
        "",
        f"## Persisting issues — {m(len(diff['persisting']))}", "",
        *([_diff_line(f, audience) for f in diff["persisting"]] or ["- None."]),
        "",
        # Absent from the later run because it never looked, not because it
        # was fixed. These used to be counted as resolutions: a 20-page
        # follow-up to a 100-page baseline reported 352 resolved where 5 had
        # been re-checked. Its own section, because folding it into either
        # neighbour restates the error in a different place.
        f"## Not re-checked — {m(len(diff.get('not_rechecked', [])))}", "",
        "_Open at the last audit and not re-examined by this run, so it says "
        "nothing about them either way. Each line states why._", "",
        # The reason travels with the finding rather than being asserted once
        # for the section: "outside what this run crawled" was false for a
        # page the run did fetch under a dimension it did not audit, and a
        # sentence that is wrong for part of its own list is worse than none.
        *([f"{_diff_line(f, audience)}\n"
           f"  - not re-checked: {_reason_markdown(f.get('not_rechecked_reason'))}"
           for f in diff.get("not_rechecked", [])] or ["- None."]),
    ]
    return "\n".join(lines), ""


def render_trend_report(site: dict, trend: list[dict], runs_list: list[dict],
                        audience: str) -> tuple[str, str]:
    from clauditseo.persistence.runs import AUDITED_STATUSES
    completed = [r for r in runs_list if r["status"] in AUDITED_STATUSES]

    # The count and the table under it describe one population, or the
    # sentence says why they do not. Carried since report 019 as "trend run
    # count disagrees with its own table" — a client document stating a run
    # count larger than its own rows, with nothing on the page reconciling
    # them, every number beside it tagged `confidence: high`.
    #
    # Two causes, and the caller only closes one. `runs_list` is now
    # `site_readings`, so a verification is no longer counted as an audit —
    # that was UX-41, measured at 5 against a four-row table. What is left is
    # an audit with no composite to plot: blocked before it could crawl, or
    # scored on no measurable weight. That one is not a defect to filter away
    # — dropping it would hide that an audit was attempted — so it is
    # explained here instead.
    unplotted = len(completed) - len(trend)
    if unplotted > 0:
        reconciliation = (" The table below has one row per composite score, "
                          f"and {m(unplotted)} of these runs produced none.")
    elif unplotted < 0:
        # More points than runs on record: the snapshots outlived the rows
        # that wrote them. Stated rather than silently rendered, because the
        # reader would otherwise be the one to notice the arithmetic.
        reconciliation = (f" The table below carries {m(-unplotted)} more "
                          "rows than there are runs on record, so some points "
                          "come from runs no longer stored.")
    else:
        reconciliation = ""

    lines = [
        f"# Trend report — {site['domain']}",
        "",
        f"Prepared {au_date(datetime.now().astimezone().isoformat())}. "
        f"Completed runs on record: {m(len(completed))}.{reconciliation}",
        "",
        "## Composite score over time",
        "",
        "| Captured (ISO 8601) | Composite | Provenance |",
        "|---|---|---|",
    ]
    for point in trend:
        lines.append(
            f"| {point['captured_at']} | {point['value']} "
            f"| {provenance_tag(point.get('source', 'engine'), point.get('confidence', 'high'))} |")
    if len(trend) >= 2:
        first, last = trend[0]["value"], trend[-1]["value"]
        direction = ("improved" if last > first else
                     "declined" if last < first else "held steady")
        lines += ["", f"Across the recorded runs the composite score {direction}: "
                      f"from {m(first)} to {m(last)}."]
    elif not trend and completed:
        # Two different empty trends, and they read as one. A trend point is
        # only written for a run that produced a composite, so a site whose
        # runs all went unscored has completed audits and no line to draw —
        # and was told "not enough completed runs", which sent the operator
        # looking for audits that had in fact run.
        lines += ["", not_assessed(
            "composite trend",
            "none of the completed runs produced a composite score")]
    else:
        lines += ["", "[TO CONFIRM: not enough completed runs to describe a trend]"]
    return "\n".join(lines), ""
