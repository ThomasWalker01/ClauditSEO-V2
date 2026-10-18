"""Deterministic scoring: identical findings in, identical score out — and
comparable across crawl sizes.

Per-page findings deduct on a RATE basis: each (check_id) group costs
`ceiling × affected_pages / eligible_pages`, capped at its severity's
ceiling, so 40 thin pages out of 400 costs the same share as 4 out of 40 and
no single check can zero a dimension. Site-level findings (no page rate to
speak of) deduct a flat amount. This replaced flat per-finding deductions in
engine 0.2.0 after real 100-page crawls floored dimensions at 0 — scores
before and after that version are not comparable.

The composite is a weighted mean of applicable sub-scores with weights
renormalised across whatever ran. Weights are always reported alongside
scores — never just the composite.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .types import Finding, Severity, SubScore

# Relative importance, not shares of a fixed pie: composite() renormalises
# across whatever dimensions a run actually selected. That is what lets A11Y
# be added without moving any score already in the database — a historical
# run that did not include it is scored over exactly the weights it had.
DEFAULT_WEIGHTS: dict[str, float] = {
    # 0.22 until SEC left it (item 143 step BD, 2026-09-13): 0.04 moved to
    # SEC below, so the total is unchanged and transport keeps about the
    # influence `not-https` had as one of TEC's checks.
    "TEC": 0.18,
    "ONP": 0.22,
    "CNT": 0.16,
    "PRF": 0.14,
    "OFP": 0.12,
    # Reported, never scored. Accessibility defects are real and the sweep
    # still raises them, but their direct ranking impact is weak — and at
    # 10.9% of the composite they moved an SEO score by more than the
    # evidence supports, which invites the reader to conclude the list was
    # padded. Weight 0 IS the statement: `composite` excludes a zero-weight
    # dimension from the total it renormalises over, so nothing here is
    # double-declared and no second flag can disagree with it.
    "A11Y": 0.0,
    # Half of ONP, by the operator's decision on 2026-09-06 (Q-50).
    # Zero was the safe default and was the wrong answer: a dimension at
    # weight zero is the product saying internal linking does not affect
    # ranking, which is not what anybody here believes. Half of ONP
    # because linking is a smaller lever than what is on the page and a
    # real one.
    #
    # **This moves every existing composite**, and that is accepted rather
    # than avoided: the trend's break annotation exists for exactly this
    # and will read "dimensions added: LNK", after which the line stops
    # being a comparison and says so.
    "LNK": 0.11,
    "AIS": 0.08,
    "LOC": 0.06,
    # Security & transport, its own dimension since item 143 step BD. 0.04,
    # taken from TEC: not zero - HTTPS is a confirmed signal and a zero would
    # say transport does not affect ranking, the reasoning the operator
    # rejected for Links (Q-50) - and not more, because the rest of the 56
    # checks is hygiene and the compromise verdict is a first-line statement,
    # not a score. The design session's ruling (question channel 2026-09-13),
    # flagged for the operator: build on it unless he says otherwise.
    "SEC": 0.04,
}

# Maximum a single check may deduct when it affects every eligible page.
CHECK_CEILING: dict[Severity, float] = {
    Severity.CRITICAL: 30.0,
    Severity.HIGH: 20.0,
    Severity.MEDIUM: 12.0,
    Severity.LOW: 5.0,
    Severity.INFO: 0.0,
}

# Flat deduction for site-level findings (robots missing, no HTTPS, …).
SITE_DEDUCTION: dict[Severity, float] = {
    Severity.CRITICAL: 25.0,
    Severity.HIGH: 10.0,
    Severity.MEDIUM: 5.0,
    Severity.LOW: 2.0,
    Severity.INFO: 0.0,
}


def page_paths(urls: Iterable[str]) -> set[str]:
    """The distinct pages a set of URLs names. One rule, used everywhere.

    Public and shared because every place that counts pages has to count them
    the same way. It did not: scoring counted paths and the report counted
    raw URLs, so one document said a check affected 99 pages in its plan and
    100 in its finding list, for the same check — two URLs differing only by
    a query string. Both numbers were right under their own definition, which
    is what made the disagreement so hard to see.

    Paths rather than whole URLs, because `eligible` counts crawled pages and
    a crawl normalises trailing slashes; comparing raw URLs against it would
    reintroduce the /x against /x/ double-count the crawler already fixed. A
    query string does not make a second page for this purpose — `/apply` and
    `/apply?product_type=loc` are one page to fix, and counting them as two
    inflates every rate whose denominator is pages crawled.
    """
    from urllib.parse import urlsplit

    return {urlsplit(u).path or "/" for u in urls if u.startswith("http")}


def _pages_touched(group: list[Finding]) -> int:
    """How many distinct pages a check's findings actually name.

    The numerator of "N of M pages", so it has to be pages. `subject` is only
    whatever makes a finding unique — for `duplicate-content` that is the
    pair key `/a|/b` — so counting subjects counts pairs.

    Falls back to the subject count only when a group names no URL at all, so
    a check that reports without citing pages still reports something rather
    than a bare zero.
    """
    paths = page_paths(u for f in group for u in f.affected_urls)
    return len(paths) or len({f.subject for f in group})


def eligible_pages(context: dict[str, Any] | None) -> int:
    """How many fetched pages a page-scoped check could have applied to.

    No `max(count, 1)` floor. The floor was a division guard, and it bought
    safety by asserting a page that was not there: on a crawl that fetched
    nothing every page rate divided by one phantom page, collapsed to zero,
    and the dimension reported full marks. A denominator is not the place to
    invent evidence — the division is guarded at its own call site instead.
    """
    from clauditseo.crawler.types import eligible

    crawl = (context or {}).get("crawl")
    if crawl is None:
        # No crawl in context at all: a caller scoring findings directly
        # rather than a run. One is the arithmetic identity for "rate by
        # finding count", not a claim that a page was fetched.
        return 1
    # The predicate lives beside `Page` rather than here, because five other
    # places need the same answer and this one is not reachable from a crawler
    # or an API handler.
    return len(eligible(crawl.pages))


def page_coverage(context: dict[str, Any] | None) -> float:
    """The share of a page-scoped dimension's intended signal actually obtained.

    Zero fetched pages means zero coverage: a dimension that measures page
    content and was handed no page measured none of it, and must carry no
    weight into the composite rather than a perfect score. Anything above zero
    is 1.0 — this answers "did we see the site" and not "did we see all of
    it". Crawl breadth (a 20-page nav crawl of a 271-page site) is a separate
    question with its own scope reporting, and folding it in here would move
    every score on record.
    """
    return 1.0 if eligible_pages(context) else 0.0


def subscore(dimension: str, findings: list[Finding], default_weight: float,
             context: dict[str, Any] | None = None, *,
             coverage: float = 1.0,
             unmeasured: tuple[str, ...] = ()) -> SubScore:
    """Standard sub-score. Analyst (model-judgement) findings never affect it.
    A page-scoped finding is one whose subject is a path; everything else is
    site-scoped and deducts flat.

    `coverage` is the share of the dimension's intended signal that was
    actually obtained. It does not move the sub-score — a dimension is still
    marked out of what it looked at — but it scales the weight that sub-score
    carries into the composite, so unmeasured ground is redistributed to
    dimensions that did measure rather than counted as clean."""
    deterministic = [f for f in findings if f.source == "deterministic"]
    eligible = eligible_pages(context)

    page_groups: dict[str, list[Finding]] = {}
    site_findings: list[Finding] = []
    by_severity: dict[str, int] = {}
    for f in deterministic:
        by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1
        if f.subject.startswith("/") or "|/" in f.subject:
            page_groups.setdefault(f.check_id, []).append(f)
        else:
            site_findings.append(f)

    deduction = 0.0
    check_detail: dict[str, dict] = {}
    for check_id, group in sorted(page_groups.items()):
        severity = max((f.severity for f in group),
                       key=lambda s: CHECK_CEILING[s])
        # Guarded here rather than by flooring the denominator: with no page
        # fetched there is no rate to compute, and a check that raised
        # anything without one is site-scoped in all but name.
        rate = min(1.0, len(group) / eligible) if eligible else 1.0
        cost = round(CHECK_CEILING[severity] * rate, 2)
        deduction += cost
        # Findings and pages are not the same count, and one check can raise
        # several on one page: `duplicate-content` names both sides of a pair,
        # so 20 pages produced 21 findings and the table read "21 of 20
        # pages". Both are recorded; the display uses the one its label
        # claims. The deduction still rates on findings, which is what every
        # stored score was computed from — changing that is an engine-version
        # decision, not a display fix, and is noted rather than smuggled in.
        #
        # Counted from the URLs, not from `subject`. A subject is whatever
        # makes the finding unique, which for a duplicate pair is the pair
        # key — so counting subjects counted pairs and called them pages. It
        # stopped reading "21 of 20" only because the next crawl was larger,
        # which is the worst way for a wrong number to go quiet.
        check_detail[check_id] = {"affected": len(group), "eligible": eligible,
                                  "pages": _pages_touched(group),
                                  "rate": round(rate, 3), "deduction": cost}
    for f in site_findings:
        deduction += SITE_DEDUCTION[f.severity]

    return SubScore(
        dimension=dimension,
        score=max(0.0, round(100.0 - deduction, 2)),
        weight=default_weight,
        coverage=max(0.0, min(1.0, coverage)),
        unmeasured=tuple(unmeasured),
        detail={"finding_counts": by_severity, "deduction": round(deduction, 2),
                "per_check": check_detail, "eligible_pages": eligible,
                # Kept because composite() overwrites `weight` with the
                # post-coverage, post-renormalisation share. Without the
                # nominal figure there is no way to say afterwards how much
                # of the intended audit a stored run actually covered.
                "nominal_weight": default_weight},
    )


def composite(subscores: dict[str, SubScore]) -> tuple[float | None, dict[str, SubScore]]:
    """Weighted composite over applicable sub-scores; weights renormalised so
    they sum to 1 across whatever actually ran. Each sub-score carries its
    module's default weight in, so a new dimension composes with zero changes
    here. Returns (score, subscores with effective weights filled in).

    The score is **None** when no dimension contributed a measurable share.
    That is not the same as zero, and the distinction is the product's own
    invariant: 0.0 is a measurement meaning "perfectly bad", while None means
    there was nothing to measure. A number cannot say the second, and every
    surface that averages, plots or compares scores would silently take the
    zero at face value.

    A dimension contributes `weight × coverage`. Unmeasured ground is
    redistributed to the dimensions that did measure — the same mechanism
    that lets an unselected dimension drop out — rather than being scored as
    clean. Before this, a site with no provider keys was handed 100/100 for
    both Performance field data and Off-page, a quarter of the composite
    awarded for not having looked, and the number went *up* the less the
    suite could see.
    """
    def share(s: SubScore) -> float:
        # A zero weight means "reported, not scored" — the dimension runs, its
        # findings are raised and its own sub-score is kept, but it neither
        # contributes to the composite nor is redistributed away from.
        return s.weight * s.coverage if s.applicable else 0.0

    total_weight = sum(share(s) for s in subscores.values())
    out: dict[str, SubScore] = {}
    if not total_weight:
        # `or 1.0` used to stand here, which made an absent denominator behave
        # like a whole one and returned 0.00 — a measurement, in the position
        # the product leads with. The sub-scores are still returned: what each
        # dimension saw is reported even when none of it can be composed.
        for dim, sub in subscores.items():
            out[dim] = SubScore(dimension=dim, score=sub.score, weight=0.0,
                                applicable=sub.applicable, coverage=sub.coverage,
                                unmeasured=sub.unmeasured, detail=sub.detail)
        return None, out

    score = 0.0
    for dim, sub in subscores.items():
        eff = share(sub) / total_weight
        score += sub.score * eff
        out[dim] = SubScore(dimension=dim, score=sub.score, weight=eff,
                            applicable=sub.applicable, coverage=sub.coverage,
                            unmeasured=sub.unmeasured, detail=sub.detail)
    return round(score, 2), out


def share_basis(scope: dict | None) -> str:
    """Which of the two quantities `measured_share` returns for this scope.

    One owner for the predicate, because the label is stored beside the value
    and a label that drifted from the arithmetic would be worse than none —
    it would assert breadth was applied on a figure that never had it. Both
    the multiplication below and the stored `scope` column read this, so they
    cannot disagree.

    `coverage` is dimension coverage alone: the site declared no total, or the
    crawl recorded no fetched count, so there is no breadth to apply. The
    same rule as the scope line — no ratio at all when the site declared none.
    """
    discovered = (scope or {}).get("discovered")
    fetched = (scope or {}).get("pages_fetched")
    return "coverage+breadth" if discovered and fetched is not None else "coverage"


def measured_share(subscores: dict[str, SubScore],
                   scope: dict | None = None) -> float:
    """How much of the intended audit this run actually covered, 0-1.

    Two things limit coverage and this counts both.

    Per-dimension `coverage` says how much of each signal was obtained — a
    dark provider, a dimension with no page to read. Read from the nominal
    weights kept in `detail`, so it works on a run loaded back from the
    database as well as one still in memory. Every stored run carries
    `nominal_weight`; the 1.0 for an empty numerator is the arithmetic
    identity for a run with no applicable dimensions, not a fallback for a
    run that predates the field.

    `scope` adds crawl breadth, which coverage cannot express because
    `page_coverage` is deliberately binary — it answers "did we see the
    site", not "did we see all of it". A real T2 audit that fetched 6 of the
    272 URLs a sitemap declared reported 0.796: a figure describing the
    provider signals it lacked, silent about the 98% of the site it never
    opened. Same source and same rule as the scope line: the site's declared
    total, and no ratio at all when it declared none.

    Deliberately blunt: breadth scales the whole figure, including signals
    that are site-level and were fully measured — robots.txt, HTTPS,
    backlinks. That understates them. It is the safe direction for a number
    whose only job is to stop a partial audit reading as a complete one, and
    the alternative needs each dimension to declare what share of it is
    page-derived, which is a bigger change than this figure is worth.

    Nothing is repriced here. `coverage`, `weight` and the composite are
    untouched; this is the description of them, not an input to them.
    """
    nominal = total = 0.0
    for sub in subscores.values():
        if not sub.applicable:
            continue
        w = float((sub.detail or {}).get("nominal_weight") or 0.0)
        nominal += w
        total += w * sub.coverage
    share = total / nominal if nominal else 1.0

    if share_basis(scope) == "coverage+breadth":
        # Capped at 1.0: link-following can reach pages a sitemap omits, and
        # fetching more than was declared is a finding about the sitemap, not
        # coverage above complete.
        share *= min(1.0, scope["pages_fetched"] / scope["discovered"])
    return round(share, 4)
