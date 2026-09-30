"""PRF — Performance dimension.

With a PageSpeed/CrUX key: real Core Web Vitals through the provider hub
(high/medium confidence). Without one: lab-style signals from the crawl
itself — response time, page weight, caching headers — tagged low
confidence, plus an explicit not-assessed finding for CWV so nothing is
silently invented.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from clauditseo.crawler.types import CrawlResult
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Confidence, Finding, Severity, Site, SubScore, Tier
from clauditseo.perf import UNAVAILABLE as UNAVAIL

SLOW_MS = 1000
HEAVY_BYTES = 200_000

#: The Speed brief's budgets (brief v19 step BC), the thresholds the
#: trace-based free checks read. Google's own vital thresholds for LCP/CLS/INP
#: (also the gauge bands), plus TTFB and a page-weight budget in KB. A site
#: record may override any of them; these are the defaults.
LCP_GOOD_MS = 2500
CLS_GOOD = 0.10
INP_GOOD_MS = 200
TTFB_GOOD_MS = 800
PAGE_WEIGHT_BUDGET_KB = 1000
#: A file more than this share whitespace reads as unminified; a minified
#: bundle collapses well under it. Deliberately generous — a false positive
#: here nags over a LOW finding, so the bar is set where only genuinely
#: pretty-printed source trips it.
UNMINIFIED_RATIO = 0.20
#: More than this share of a stylesheet or script shipped-but-unused is worth a
#: LOW row; coverage is noisy below it.
UNUSED_SHARE = 0.5

#: PRF's registry entry (brief v19 step BC). The dimension has always carried
#: its free-check severities inline in the emitters rather than in a table, so
#: DEFAULT_SEVERITY stays empty — the thirteen free checks are priced FREE via
#: `anatomy.CHECK_CATEGORY` like every sweep check. What the register is needed
#: for is BRIEF_ONLY_CHECKS: the five Speed analysis checks the `speed.md` brief
#: judges over the trace, which no sweep emits, so they must be priced `model`.
DEFAULT_SEVERITY: dict = {}
BRIEF_ONLY_CHECKS: tuple[str, ...] = (
    "critical-path", "lcp-cause", "cls-cause", "inp-cause", "third-party-policy")

#: Google's published Core Web Vitals bands: good at or under the first,
#: poor above the second, "needs improvement" between them.
#:
#: All three vitals, not just LCP. CrUX was already returning `inp_ms` and
#: `cls` on every audit and this module read only `lcp_ms`, so two thirds of
#: the data the API call paid for was fetched and dropped. INP replaced FID
#: as a Core Web Vital in March 2024; a site with a 600 ms INP was invisible
#: here while the call that measured it had already been made and billed.
CWV_BANDS: dict[str, tuple[float, float, str]] = {
    "lcp_ms": (2500, 4000, "Largest Contentful Paint"),
    "inp_ms": (200, 500, "Interaction to Next Paint"),
    "cls": (0.1, 0.25, "Cumulative Layout Shift"),
}
LCP_POOR_MS = CWV_BANDS["lcp_ms"][1]

#: The middle band is reported, not scored. A site at 3663 ms LCP is not
#: passing and was being told nothing at all, because only "poor" spoke — so
#: the audit's silence read as approval for a genuinely mediocre number.
CWV_SEVERITY = {"poor": Severity.HIGH, "needs improvement": Severity.LOW}


def _budgets(site) -> dict:
    """The Speed thresholds for this site — the record's where it names them
    (brief v19 step BC), the defaults otherwise. Stored as text like the other
    budget fields, parsed here."""
    def _num(key, default):
        raw = getattr(site, key, None) if site else None
        try:
            return type(default)(str(raw).strip()) if raw not in (None, "") else default
        except (TypeError, ValueError):
            return default
    return {
        "lcp_good": _num("lcp_good", LCP_GOOD_MS),
        "cls_good": _num("cls_good", CLS_GOOD),
        "inp_good": _num("inp_good", INP_GOOD_MS),
        "ttfb_good": _num("ttfb_good", TTFB_GOOD_MS),
        # The page weight budget is the existing `budget_page_kb` (brief v19
        # step BC names it page_weight_budget and says it exists); read that
        # field rather than adding a second budget for the same thing.
        "page_weight_budget": _num("budget_page_kb", PAGE_WEIGHT_BUDGET_KB),
    }


def _band(metric: str, value: float) -> str:
    good, poor, _label = CWV_BANDS[metric]
    if value > poor:
        return "poor"
    if value > good:
        return "needs improvement"
    return "good"


def _fmt(metric: str, value: float) -> str:
    return f"{value:.2f}" if metric == "cls" else f"{value:.0f} ms"


#: The four gauges the Speed part draws, in the brief's order, each on its own
#: published bands (brief v19 step BC: "thresholds are Google's … stored in the
#: registry, never ours").
#:
#: The three Core Web Vitals are DERIVED from `CWV_BANDS` above rather than
#: retyped, so a threshold cannot be Google's in the check and ours on the
#: gauge — that divergence is the defect the BC checkpoint already found once,
#: when the gauge drew fixed 40/66% stops against a value coloured by the real
#: thresholds. TTFB is listed separately because it is NOT a Core Web Vital and
#: CrUX does not return it under that name; adding it to `CWV_BANDS` would make
#: the field-data loop ask a provider for a metric it does not serve.
#:
#: `trace` is where the figure comes from on a `perf` trace; `proxy` is the
#: label the strip must carry where the figure is a stand-in. INP is not
#: lab-measurable at all (no interaction trace in this step), so it is shown as
#: its TBT proxy and labelled — never synthesised (item 141's read-and-report
#: step says so in as many words).
GAUGE_BANDS: dict[str, dict] = {
    "lcp": {"label": "LCP", "good": CWV_BANDS["lcp_ms"][0],
            "poor": CWV_BANDS["lcp_ms"][1], "unit": "ms", "trace": "lcp",
            "name": CWV_BANDS["lcp_ms"][2], "proxy": None},
    "cls": {"label": "CLS", "good": CWV_BANDS["cls"][0],
            "poor": CWV_BANDS["cls"][1], "unit": "", "trace": "cls",
            "name": CWV_BANDS["cls"][2], "proxy": None},
    "inp": {"label": "INP", "good": CWV_BANDS["inp_ms"][0],
            "poor": CWV_BANDS["inp_ms"][1], "unit": "ms", "trace": "tbt_ms",
            "name": CWV_BANDS["inp_ms"][2], "proxy": "TBT"},
    "ttfb": {"label": "TTFB", "good": TTFB_GOOD_MS, "poor": 1800, "unit": "ms",
             "trace": "ttfb_ms", "name": "Time to First Byte", "proxy": None},
}


def gauge_band(key: str, value: float) -> str:
    """Which of Google's three bands a gauge value sits in. One function, so
    the marker's colour and the band it is drawn on cannot disagree."""
    spec = GAUGE_BANDS[key]
    if value > spec["poor"]:
        return "poor"
    if value > spec["good"]:
        return "needs improvement"
    return "good"


def _bare(host: str) -> str:
    """A host without `www.`, for deciding whose it is.

    `www.example.com` and `example.com` are one party, and comparing them as
    written charged a site as a third party to itself: the first live Birch
    trace started at the apex, every resource came back on `www.`, and the
    ledger listed `www.beacon.com.au` above two real third parties with
    1,658 ms of main-thread work against it. A subdomain that is NOT `www.` is
    left alone on purpose — `static.parastorage.com` is a third party to
    `parastorage.com` in every sense that matters here.
    """
    return (host or "").lower().removeprefix("www.")


#: The checks that exist only because a trace was taken (item 157).
#:
#: A run holding no trace has not *passed* these -- it has not measured them,
#: and `runs.not_assessed_payload` uses this set to say so. The distinction is
#: the whole of item 157: absence of a finding is not a pass.
#:
#: **`page-weight` is in the set since item 168.** It was shared with the
#: HTML-bytes proxy until migration 0054 retired that reading, so an untraced
#: run from before 0054 really did measure it with the weaker instrument; since
#: 0054 the only emitter is `_resource_checks`, which reads a trace, so an
#: untraced run measures nothing of it. `runs.not_assessed_payload` keeps the
#: first case honest with its own rung (`PAGE_WEIGHT_PROXY_UNTIL`). Every id
#: below is emitted from a trace and from nowhere else -- `ttfb-slow` included,
#: because the untraced instrument for that subject was `slow-response`, a
#: different id, retired with the proxy.
#:
#: Guarded by derivation rather than by review: the test runs the module twice,
#: once over a trace and once without, and asserts this set is exactly the ids
#: the first emits and the second cannot.
TRACE_DERIVED_CHECKS: frozenset[str] = frozenset({
    "lcp-slow", "cls-high", "inp-long-tasks", "ttfb-slow",
    "render-blocking", "unused-css-js", "uncompressed", "no-cache-headers",
    "unminified", "third-party-weight", "font-blocking", "page-weight",
})

#: The migration that retired the HTML-bytes `page-weight` (item 168). A run
#: created before it was applied measured `page-weight` without a trace, so it
#: is not reported unmeasured on an untraced run from then. The boundary is
#: read from `schema_migrations.applied_at` in the database the run lives in:
#: 0054 shipped without an engine version bump, so no version marks it.
PAGE_WEIGHT_PROXY_UNTIL = "0054_retire_the_lab_proxy_checks.sql"


def third_party_ledger(trace: dict, first_party_host: str) -> list[dict]:
    """Bytes and main-thread milliseconds per third-party host, from one trace.

    The two axes the brief's ledger draws, and the same two the
    `third-party-weight` check reads — one implementation, called by both,
    because this rule written out twice is how six places came to count
    `len(pages)` instead (`crawler.types` records that case).

    Main-thread ms comes from Long Animation Frames' per-script attribution
    (`{url, ms}`), which is the only source that can charge main-thread time to
    a third-party host: the Long Tasks API attributes at frame level and
    returns "unknown", which is why the earlier version of this charged nobody.
    A script with no third-party host — the document, "self", first party — is
    not charged here.
    """
    mine = _bare(first_party_host)
    bytes_by: dict[str, int] = {}
    ms_by: dict[str, float] = {}
    for r in (trace.get("resources") or []):
        host = urlsplit(r.get("url") or "").netloc.lower()
        if host and _bare(host) != mine:
            bytes_by[host] = bytes_by.get(host, 0) + (r.get("transfer") or 0)
    for task in (trace.get("long_tasks") or []):
        for src in (task.get("scripts") or []):
            h = urlsplit(src.get("url") or "").netloc.lower()
            if h and _bare(h) != mine:
                ms_by[h] = ms_by.get(h, 0) + (src.get("ms") or 0)
    return sorted(
        ({"host": h, "bytes": bytes_by.get(h, 0),
          "main_thread_ms": round(ms_by.get(h, 0), 1)}
         for h in (set(bytes_by) | set(ms_by))),
        # Main thread first, weighted: a 40 KB script holding the thread for
        # 300 ms costs the client more than a 400 KB image that costs nothing.
        key=lambda r: -(r["bytes"] + r["main_thread_ms"] * 1000))


CWV_ADVICE = {
    "lcp_ms": ("Optimise the largest above-fold element: compress images, "
               "preload the hero asset, cut render-blocking resources."),
    "inp_ms": ("Reduce main-thread work on interaction: break up long tasks, "
               "defer non-essential scripts, and avoid heavy event handlers."),
    "cls": ("Reserve space for anything that loads late: set width and height "
            "on images and embeds, and avoid inserting content above "
            "existing content."),
}


class PerformanceModule:
    code = "PRF"
    name = "Performance"
    default_weight = scoring.DEFAULT_WEIGHTS["PRF"]
    #: The page-naming checks are the trace's: every one of
    #: `TRACE_DERIVED_CHECKS` (`page-weight` among them since item 168), each measured against one
    #: load of one URL, so re-fetching it re-measures them. `cwv-not-assessed`
    #: is site-scoped and does not change the answer.
    #:
    #: The four lab proxies that used to be named here — `slow-response`, the
    #: HTML-bytes `page-weight`, `caching-headers`, `third-party-scripts` — are
    #: retired (migration 0054). A page refresh takes the trace since item
    #: 159 (`api/app.py::_narrow_trace`), and a run that did not trace a page
    #: cannot clear these on it (`runs._untraced`).
    #:
    #: **Do not derive this from `tests/test_coverage.py`'s fixture**, which
    #: emits 0 page-naming PRF findings against 2 site-scoped and would
    #: certify this dimension un-page-refreshable. The operator's own
    #: database holds 47 page-naming PRF findings against 10. That
    #: disagreement is `KNOWN_ISSUES.md` KI-55 and it is the reason this fact
    #: is declared here and guarded against this file's source rather than
    #: against a corpus. See `registry.page_blind_dims`.
    measured_per_page = True

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        hub = context.get("providers")
        findings: list[Finding] = []

        # Attempts are not fetches. A DNS failure leaves a Page object, so
        # gating on `crawl.pages` spent a keyed CWV call per provider on a
        # host that did not resolve — and it is the response to that wasted
        # call that then told the client why their site was not measured.
        from clauditseo.crawler.types import eligible
        readable = eligible(crawl.pages)

        cwv = None
        # T1 makes no external API calls by contract.
        if hub is not None and tier is not Tier.T1 and readable:
            cwv = hub.cwv_metrics(readable[0].url)

        if cwv:
            # Field and lab are different measurements and must never be
            # presented as the same one. CrUX is what real users experienced;
            # PageSpeed is one synthetic run on Google's hardware. On this
            # site they disagree by four times — 3663 ms against 14746 — and
            # the hub returns whichever provider answers first, so a page
            # with no CrUX data (common on low-traffic URLs) silently falls
            # back to a lab number that reads far worse with nothing saying
            # the basis changed. The source travels into every finding.
            for metric, (good, poor, label) in CWV_BANDS.items():
                got = cwv.get(metric)
                if not got or got.value is None:
                    continue
                band = _band(metric, got.value)
                if band == "good":
                    continue
                basis = ("field data from real users" if got.source == "crux"
                         else "a single lab run, not real-user data")
                findings.append(Finding(
                    dimension=self.code,
                    check_id=f"{metric.split('_')[0]}-{band.replace(' ', '-')}",
                    severity=CWV_SEVERITY[band],
                    summary=(f"{label} p75 is {_fmt(metric, got.value)} — "
                             f"{band} (good is {_fmt(metric, good)} or "
                             f"under, poor is above {_fmt(metric, poor)}). "
                             f"Measured from {basis}."),
                    subject="site", affected_urls=[readable[0].url],
                    evidence={metric: got.value, "source": got.source,
                              "band": band, "good_at_or_under": good,
                              "poor_above": poor},
                    confidence=Confidence(got.confidence),
                    recommendation=CWV_ADVICE[metric],
                ))
            # A lab-only answer is not field data (answer 20260916-0140): the
            # hub falls through to PageSpeed when CrUX holds no record, and
            # without this row the sweep credited field coverage for a single
            # synthetic run the brief and the field bar both call lab.
            if not any(getattr(v, "source", None) == "crux"
                       for v in cwv.values() if v is not None):
                findings.append(self._field_not_assessed(hub, tier, readable, lab=cwv))
        else:
            findings.append(self._field_not_assessed(hub, tier, readable, lab=None))

        findings.extend(self._trace_checks(crawl, context))
        return findings

    def _field_not_assessed(self, hub, tier: Tier, readable: list, *,
                            lab: dict | None) -> Finding:
        """The one `cwv-not-assessed` row, from either branch of `run`: no CWV
        answer at all (`lab=None`), or an answer carrying lab values only.
        One builder, so the two rows cannot drift in evidence shape."""
        # The same evidence shape OFP uses, so the client branch of
        # _not_assessed_line can rebuild a sentence about the site rather
        # than about our suppliers. Which vendors the operator holds keys
        # for is not a finding about the client's site and is not
        # something the client can act on — the leak closed for backlinks
        # at 85c86d6 stayed open through this door.
        #
        # Failures are scoped to the CWV providers: hub.failures is
        # hub-wide, so an unrelated backlink provider answering 403 would
        # otherwise make this line claim the CWV source was unavailable
        # when in fact none is configured. Three states, three true
        # sentences: none configured, configured and refusing, configured
        # and reporting nothing for this site.
        # Only a provider that was asked can be said to have answered.
        # The condition guarding the call above IS the definition of
        # "asked" — T1 makes no external calls by contract, and it is the
        # tier `auto` and adaptive mode start on — so deriving this from
        # what is configured told a client their own site had been
        # measured and found silent, from a call never made.
        # Two different silences, and they must not collapse into one
        # sentence: a tier that never calls out, and a tier that would
        # have called out with nothing configured to call.
        # Two conditions, two names. They used to share one —
        # `tier_permits_external = tier is not Tier.T1 and bool(crawl.pages)`
        # — and the renderer mapped its false value to a single definite
        # cause, "this audit tier does not call external data sources".
        # True at T1. False at T2 or T3 whose crawl fetched nothing, where
        # the tier does call out and the reason is that there was nothing
        # to measure. Live on stored data: run d02919eb is T2 and blocked
        # carrying False, beside 1b1da5e5 at T1 carrying the same value,
        # and nothing in the evidence told them apart.
        # And `pages_fetched` is the same word as the gate above, so it
        # is the same measure. Built from `bool(crawl.pages)` it read
        # True on a crawl that resolved nothing, which is the one case
        # the sentence it feeds exists to describe.
        tier_calls_external = tier is not Tier.T1
        pages_fetched = bool(readable)
        asked = hub is not None and tier_calls_external and pages_fetched
        cwv_names = ([getattr(p, "name", type(p).__name__)
                      for p in hub.cwv_providers] if asked else [])
        failing = [detail for name, detail in
                   (hub.failures.items() if asked else [])
                   if name in cwv_names]
        failed_names = {d.get("provider") for d in failing}
        evidence = {"unmeasured": ["Core Web Vitals field data"],
                    "needs": ["a PageSpeed or CrUX API key"],
                    "tier_calls_external": tier_calls_external,
                    "pages_fetched": pages_fetched,
                    "providers_answering": [n for n in cwv_names
                                            if n not in failed_names],
                    "providers_failing": failing}
        summary = ("Core Web Vitals not assessed — no PageSpeed or CrUX API key "
                   "configured (or no field data). Local timing signals below carry "
                   "low confidence.")
        recommendation = ("Add CLAUDITSEO_PAGESPEED_KEY or CLAUDITSEO_CRUX_KEY for "
                          "real CWV data.")
        if lab is not None:
            # Three true sentences for the lab-only path; the no-answer
            # sentences above are false here, since a lab key answered.
            lab_run = "The vitals below are one PageSpeed lab run, not real-user data."
            if "crux" not in cwv_names:
                reason = "no CrUX key is configured"
                recommendation = "Add CLAUDITSEO_CRUX_KEY for real-user data."
            elif "crux" in failed_names:
                reason = "CrUX was unavailable during this run"
                recommendation = "Retry once CrUX answers; see providers_failing."
            else:
                reason = "CrUX holds no record for this URL"
                recommendation = ("A missing CrUX record is a traffic-threshold fact, "
                                  "not a configuration gap. Treat the lab vitals as "
                                  "directional until a field source is connected on "
                                  "Admin > Sites (no provider here reads one yet).")
            summary = f"Core Web Vitals field data not assessed: {reason}. {lab_run}"
            evidence["needs"] = ["real-user field data (a CrUX record for this URL)"]
            evidence["lab_source"] = next(
                (getattr(v, "source", None) for v in lab.values()
                 if getattr(v, "source", None)), "pagespeed")
            evidence["lab_metrics"] = sorted(k for k, v in lab.items() if v is not None)
        return Finding(
            dimension=self.code, check_id="cwv-not-assessed", severity=Severity.INFO,
            scope_statement=True, summary=summary,
            subject="cwv", affected_urls=[], evidence=evidence,
            confidence=Confidence.LOW, recommendation=recommendation,
        )

    # --- the Speed browser-trace free checks (brief v19 step BC) -----------

    def _trace_checks(self, crawl: CrawlResult, context: dict) -> list[Finding]:
        """The thirteen free Speed checks, per page, from the performance trace
        (`clauditseo.perf`, stored under each page's `perf`). Silent where no
        trace was taken — a run with no renderer reads `{"traced": False}` and
        emits nothing here rather than a value nobody measured. Every threshold
        a trace value is judged against is a budget the site record may
        override; the defaults are Google's own where the metric has one.

        These read the trace, they do not take it: the capture is `perf.py`'s,
        the judgement is here, and the brief's five analysis checks (lcp-cause,
        critical-path, …) are the model's over the same trace.
        """
        traces = context.get("perf_traces") or {}
        if not traces:
            return []
        site = context.get("site")
        budgets = _budgets(site)
        start_host = urlsplit(crawl.start_url).netloc.lower()
        findings: list[Finding] = []
        for page in crawl.pages:
            if page.status != 200:
                continue
            tr = traces.get(page.url)
            if not tr or tr.get("traced") is False:
                continue
            path = urlsplit(page.url).path or "/"
            findings += self._vital_checks(path, page.url, tr, budgets)
            findings += self._resource_checks(path, page.url, tr, budgets, start_host)
        return findings

    def _vital_checks(self, path, url, tr, budgets) -> list[Finding]:
        out: list[Finding] = []
        lcp = tr.get("lcp") or {}
        lcp_ms = lcp.get("ms")
        if isinstance(lcp_ms, (int, float)) and lcp_ms > budgets["lcp_good"]:
            sev = Severity.HIGH if lcp_ms > CWV_BANDS["lcp_ms"][1] else Severity.MEDIUM
            el = lcp.get("element") or "the largest element"
            out.append(Finding(
                dimension=self.code, check_id="lcp-slow", severity=sev,
                summary=f"{path}: LCP {lcp_ms:.0f} ms lab (over {budgets['lcp_good']} ms), "
                        f"element {el}.",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"lcp_ms": lcp_ms, "element": el, "is_image": lcp.get("is_image"),
                          "url": lcp.get("url"), "sub_parts": lcp.get("sub_parts"),
                          "measured": "lab"},
                recommendation="See the lcp-cause plan for this template; if the LCP is "
                               "an image, its fix is on the Images part."))
        cls = tr.get("cls") or {}
        cls_val = cls.get("value")
        if isinstance(cls_val, (int, float)) and cls_val > budgets["cls_good"]:
            sev = Severity.HIGH if cls_val > CWV_BANDS["cls"][1] else Severity.MEDIUM
            shifts = [s for shift in (cls.get("shifts") or [])
                      for s in (shift.get("sources") or [])][:5]
            out.append(Finding(
                dimension=self.code, check_id="cls-high", severity=sev,
                summary=f"{path}: CLS {cls_val:.2f} lab (over {budgets['cls_good']}), "
                        f"shifting {', '.join(shifts) or 'unattributed elements'}.",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"cls": cls_val, "shifts": cls.get("shifts"), "measured": "lab"},
                recommendation="Reserve space for anything that loads late; see cls-cause "
                               "for this template."))
        tbt = tr.get("tbt_ms")
        if isinstance(tbt, (int, float)) and tbt > budgets["inp_good"]:
            out.append(Finding(
                dimension=self.code, check_id="inp-long-tasks", severity=Severity.MEDIUM,
                summary=f"{path}: {tbt:.0f} ms total blocking time during load "
                        f"(INP lab proxy; INP is not lab-measurable).",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"tbt_ms": tbt, "long_tasks": tr.get("long_tasks"),
                          "proxy": "TBT for INP", "measured": "lab"},
                recommendation="Break up the long tasks the trace lists; see inp-cause."))
        ttfb = tr.get("ttfb_ms")
        if isinstance(ttfb, (int, float)) and ttfb > budgets["ttfb_good"]:
            out.append(Finding(
                dimension=self.code, check_id="ttfb-slow", severity=Severity.MEDIUM,
                summary=f"{path}: TTFB {ttfb:.0f} ms (over {budgets['ttfb_good']} ms).",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"ttfb_ms": ttfb, "measured": "lab"},
                recommendation="Profile the server response: caching, origin latency, "
                               "or a CDN in front of it."))
        return out

    def _resource_checks(self, path, url, tr, budgets, start_host) -> list[Finding]:
        out: list[Finding] = []
        resources = tr.get("resources") or []

        blocking = [r for r in resources if r.get("blocking") is True]
        if blocking:
            kb = sum((r.get("transfer") or 0) for r in blocking) // 1024
            out.append(Finding(
                dimension=self.code, check_id="render-blocking", severity=Severity.MEDIUM,
                summary=f"{path}: {len(blocking)} render-blocking resource(s) in the head "
                        f"({kb} KB) without async/defer/media.",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"resources": [r["url"] for r in blocking][:10],
                          "count": len(blocking), "bytes": kb * 1024, "measured": "lab"},
                recommendation="Defer or async non-critical CSS/JS; inline the above-fold "
                               "CSS subset; see critical-path for the ordered plan."))

        unused = [r for r in resources
                  if isinstance(r.get("coverage"), dict) and (r["coverage"].get("total") or 0)
                  and 1 - (r["coverage"].get("used", 0) / r["coverage"]["total"]) > UNUSED_SHARE]
        if unused:
            out.append(Finding(
                dimension=self.code, check_id="unused-css-js", severity=Severity.LOW,
                summary=f"{path}: {len(unused)} file(s) ship more than "
                        f"{UNUSED_SHARE * 100:.0f}% unused CSS/JS.",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"files": [{"url": r["url"],
                                     "used": r["coverage"]["used"],
                                     "total": r["coverage"]["total"]} for r in unused][:10],
                          "measured": "lab"},
                recommendation="Code-split and load per route; strip unused rules."))

        uncompressed = [r for r in resources
                        if r.get("type") in ("css", "script")
                        and r.get("compression") == "none"]
        if uncompressed:
            out.append(Finding(
                dimension=self.code, check_id="uncompressed", severity=Severity.LOW,
                summary=f"{path}: {len(uncompressed)} text resource(s) served without "
                        "br/gzip compression.",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"resources": [r["url"] for r in uncompressed][:10],
                          "measured": "lab"},
                recommendation="Enable Brotli or gzip for text responses at the origin "
                               "or CDN."))

        uncached = [r for r in resources
                    if r.get("type") in ("css", "script", "font", "image")
                    and not r.get("cache_control")
                    and r.get("cache_control") != UNAVAIL]
        if uncached:
            out.append(Finding(
                dimension=self.code, check_id="no-cache-headers", severity=Severity.LOW,
                summary=f"{path}: {len(uncached)} static asset(s) without a Cache-Control "
                        "header.",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"resources": [r["url"] for r in uncached][:10], "measured": "lab"},
                recommendation="Set long-lived, immutable Cache-Control on fingerprinted "
                               "static assets."))

        unmin = [r for r in resources
                 if r.get("type") in ("css", "script")
                 and isinstance(r.get("whitespace_ratio"), (int, float))
                 and r["whitespace_ratio"] > UNMINIFIED_RATIO]
        if unmin:
            out.append(Finding(
                dimension=self.code, check_id="unminified", severity=Severity.LOW,
                summary=f"{path}: {len(unmin)} CSS/JS file(s) look unminified "
                        f"(whitespace over {UNMINIFIED_RATIO * 100:.0f}%).",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"files": [{"url": r["url"], "whitespace_ratio": r["whitespace_ratio"]}
                                    for r in unmin][:10], "measured": "lab"},
                recommendation="Minify CSS/JS in the build step."))

        # Bytes per third-party host from the resource list, and main-thread ms
        # per host from the long tasks' script attribution — the two axes the
        # brief's ledger draws. A task attributed to a third-party script's host
        # adds its whole duration to that host; a task with no third-party
        # attribution ("self", the document, or first-party) is not charged to
        # anyone here.
        # One implementation, shared with the part page's ledger — see
        # `third_party_ledger`.
        ledger = third_party_ledger(tr, start_host)
        # Heavy on either axis: 50 KB shipped, or 50 ms of main thread.
        rows = [r for r in ledger
                if r["bytes"] > 50 * 1024 or r["main_thread_ms"] > 50]
        if rows:
            heavy = [r["host"] for r in rows]
            total_ms = round(sum(r["main_thread_ms"] for r in rows), 1)
            out.append(Finding(
                dimension=self.code, check_id="third-party-weight", severity=Severity.MEDIUM,
                summary=f"{path}: {len(heavy)} third-party host(s) ship "
                        f"{sum(r['bytes'] for r in rows) // 1024} KB and "
                        f"{total_ms:g} ms of main-thread work; heaviest "
                        f"{rows[0]['host']} ({rows[0]['bytes'] // 1024} KB, "
                        f"{rows[0]['main_thread_ms']:g} ms).",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"hosts": rows[:10], "measured": "lab"},
                recommendation="Delay, gate or drop third parties by paint impact; see "
                               "third-party-policy."))

        fonts = tr.get("fonts") or []
        bad_fonts = [f for f in fonts
                     if f.get("display") in (None, UNAVAIL, "auto", "block")
                     or f.get("preloaded") is False]
        if fonts and bad_fonts:
            out.append(Finding(
                dimension=self.code, check_id="font-blocking", severity=Severity.MEDIUM,
                summary=f"{path}: {len(bad_fonts)} web font(s) without font-display: swap "
                        "or a preload (FOIT risk).",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"fonts": [f.get("family") for f in bad_fonts][:10], "measured": "lab"},
                recommendation="Set font-display: swap and preload the one or two fonts the "
                               "first paint needs."))

        transfer = sum((r.get("transfer") or 0) for r in resources)
        if transfer > budgets["page_weight_budget"] * 1024:
            out.append(Finding(
                dimension=self.code, check_id="page-weight", severity=Severity.MEDIUM,
                summary=f"{path}: {transfer // 1024} KB transferred "
                        f"(over {budgets['page_weight_budget']} KB); image share is on the "
                        "Images part, not recounted here.",
                subject=path, affected_urls=[url], confidence=Confidence.LOW,
                evidence={"transfer_bytes": transfer,
                          "budget_kb": budgets["page_weight_budget"], "measured": "lab"},
                recommendation="Cut the heaviest resources by paint impact; images are the "
                               "Images part's."))
        return out

    # --- third-party scripts, by host and counted (FEATURES.md F-01) -------

    # What this dimension is meant to cover, and how much of it each half is.
    # Field data is the larger share: how the page actually behaves for real
    # visitors is the thing being measured, and response time and document
    # weight are proxies for it.
    FIELD_SHARE = 0.6

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # The not-assessed finding the run already emits is also the record
        # of what was missed — no extra state to keep in step with it.
        dark = any(f.check_id == "cwv-not-assessed" for f in findings)
        # Two halves with two different requirements: the field half needs a
        # provider, the lab half needs a page to time. The old expression
        # credited the lab half unconditionally, so a crawl that fetched
        # nothing still reported 0.4 coverage for timings never taken. Same
        # values as before wherever a page was fetched.
        field = 0.0 if dark else self.FIELD_SHARE
        lab = (1.0 - self.FIELD_SHARE) * scoring.page_coverage(context)
        return scoring.subscore(
            self.code, findings, self.default_weight, context,
            coverage=field + lab,
            unmeasured=("Core Web Vitals field data",) if dark else (),
        )


registry.register(PerformanceModule())
