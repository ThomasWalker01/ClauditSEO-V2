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

**Only the front card, as the entry scoped it.** The two follow-on pieces named
below — SEO surfaces excluding A11Y findings, and the accessibility section's
own severity scale in the client document — remain unbuilt and still need their
own consumer enumeration and their own acceptance signal. The `Biggest gains`
table on the same screen still ranks by points on the composite and so still
lists A11Y rows at zero; that is the first of those two pieces, and it is named
here so the boundary this entry proves is not mistaken for the whole decision.

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
and their own acceptance signal, and are **not** covered here. Recommended as
two further entries once each is scoped in its own right — F-09 delivers the
first visible piece and proves the presentational boundary the other two must
also respect.

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
are deliberately not built as part of this entry.
