"""Engine orchestration.

Takes a crawl result plus a dimension selection and a tier, runs each
registered module, and returns typed results. Knows nothing about any
specific dimension (that's the registry's job), the database (persistence's
job), or HTTP (the API's job).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from clauditseo import ENGINE_VERSION
from clauditseo.crawler.types import CrawlResult

from . import registry, scoring
from .types import Finding, Site, SubScore, Tier


@dataclass
class AuditResult:
    site: Site
    tier: Tier
    dimensions: list[str]
    findings: list[Finding] = field(default_factory=list)
    subscores: dict[str, SubScore] = field(default_factory=dict)
    #: None when no dimension contributed a measurable share — a run that
    #: could not be scored, as distinct from one that scored zero. Callers
    #: that format or compare it must handle None rather than defaulting.
    composite_score: float | None = None
    engine_version: str = ENGINE_VERSION
    stats: dict[str, Any] = field(default_factory=dict)
    #: Paths this run actually fetched. The state machine needs it: a finding
    #: is only "fixed" if the page it was raised on was looked at again, and
    #: without this a 20-page nav crawl marked 456 findings on the 80 pages it
    #: never visited as fixed.
    crawled_paths: set[str] = field(default_factory=set)
    #: Paths this run took a performance trace of - the subset of
    #: `crawled_paths` the trace-derived checks could answer on (item 159).
    #: Crawling a page is not looking at it with every instrument: a refresh
    #: takes no trace unless it asks for one, the trace samples one page per
    #: template, and a machine with no renderer takes none at all. The state
    #: machine reads this so a run that did not trace a page cannot clear a
    #: finding only a trace can raise. Empty is the conservative default.
    traced_paths: set[str] = field(default_factory=set)
    #: Paths the browser image pass weighed (item 240): the instrument the
    #: image-derived checks need, as `traced_paths` is the trace's.
    imaged_paths: set[str] = field(default_factory=set)


def _merge_by_identity(findings: list[Finding]) -> list[Finding]:
    """One finding per fingerprint, with the URLs of all of them.

    The fingerprint IS the identity — `sha256(dimension:check_id:subject)`,
    and `finding_states` is keyed on it — so two findings sharing one in a
    single run is the engine contradicting its own definition. It happened
    wherever a page was reachable at two URLs: `/apply` and
    `/apply?product_type=loc` are one path, so every per-page check produced
    two identical findings. One run held 469 findings against 462
    fingerprints, and the client report listed 469 while the app's own
    headline said 462.

    Merged rather than dropped. Both URLs are real and the operator has to
    fix the page at both, so discarding one would answer "which URLs are
    affected" with less than was measured. The first finding wins for text
    and severity — they are identical by construction, since an identical
    fingerprint means the same check reached the same conclusion about the
    same subject.

    Not the same as the URL-parameter problem underneath it. That two URLs
    serve one page is a finding of its own and belongs to the URL checks;
    this only stops the same defect being counted twice while it stands.
    """
    out: dict[str, Finding] = {}
    for f in findings:
        seen = out.get(f.fingerprint)
        if seen is None:
            out[f.fingerprint] = f
            continue
        for url in f.affected_urls:
            if url not in seen.affected_urls:
                seen.affected_urls.append(url)
    return list(out.values())


#: Dimensions that must run before the rest, whatever order the caller
#: listed them in.
#:
#: A11Y is the only producer of shared context today: its rendered pass sets
#: `axe_ran`, and since item 136q it also collects the rendered anchor set
#: that `TEC/links-behind-js` compares against the initial HTML. `dims`
#: arrives from the request body, so without this the client's JSON would
#: decide whether a check can answer - and the failure would be silent, since
#: "the rendered pass did not run" and "the rendered pass ran after me" look
#: identical from the consumer's side.
#:
#: A list rather than a graph because there is one edge. The day there are
#: two, this is where the second one is written down.
RUN_FIRST = ("A11Y",)


def _in_run_order(dimensions: list[str]) -> list[str]:
    """The caller's list, with the producers moved to the front.

    Order-preserving otherwise: a module that neither produces nor consumes
    shared context runs where the caller put it, so nothing else moves.
    """
    first = [d for d in RUN_FIRST if d in dimensions]
    return first + [d for d in dimensions if d not in RUN_FIRST]


def run_audit(
    site: Site,
    crawl_result: CrawlResult,
    dimensions: list[str],
    tier: Tier,
    context: dict[str, Any] | None = None,
) -> AuditResult:
    context = dict(context or {})
    context["crawl"] = crawl_result
    context["site"] = site

    from urllib.parse import urlsplit

    from clauditseo.crawler.types import eligible

    # Eligible, not attempted. `compare_runs` reads this set as "did this run
    # re-check that page", so a URL that failed to resolve counted as checked
    # and a finding on it was reported resolved — the round-022 Critical
    # re-entering through the column added to close it.
    # Traced by the same test `prf._trace_checks` applies before it reads a
    # trace: present, and not the pass's own `{"traced": False}`.
    traces = context.get("perf_traces") or {}
    readable = eligible(crawl_result.pages)
    result = AuditResult(
        site=site, tier=tier, dimensions=list(dimensions),
        crawled_paths={urlsplit(p.url).path or "/" for p in readable},
        traced_paths={urlsplit(p.url).path or "/" for p in readable
                      if traces.get(p.url)
                      and traces[p.url].get("traced") is not False},
        imaged_paths={urlsplit(p.url).path or "/" for p in readable
                      if (context.get("image_measurements") or {}).get(p.url)})
    raw_subscores: dict[str, SubScore] = {}

    for code in _in_run_order(dimensions):
        module = registry.get(code)
        if not module.applicable(site):
            raw_subscores[code] = SubScore(dimension=code, score=0.0,
                                           weight=0.0, applicable=False)
            continue
        findings = _merge_by_identity(module.run(crawl_result.pages, tier,
                                                 context))
        result.findings.extend(findings)
        raw_subscores[code] = module.score(findings, context)

    result.composite_score, result.subscores = scoring.composite(raw_subscores)
    result.stats = {
        "pages_crawled": len(crawl_result.pages),
        # Fetched and eligible are different counts, and the second is the one
        # every page-derived check actually depends on: three 404s and a PDF
        # are pages crawled and nothing any check can read. Recorded here
        # because this is where the crawl and the modules are both in scope.
        "pages_eligible": scoring.eligible_pages(context),
        "robots_blocked": len(crawl_result.robots_blocked),
        "truncated_by": crawl_result.truncated_by,
        "findings": len(result.findings),
    }
    return result
