"""The workbench: every tool the suite can offer, in the order you would
actually work a site.

Ordering principle — fix what invalidates other work first. Copy written for
a page that cannot be indexed is wasted; a heading rewritten before the
template is fixed gets rewritten again. So the sequence runs foundation →
page → meaning → surfaces → authority → proof, and within a phase the
cheap deterministic sweep always precedes the expensive judgement call.

Status is honest about what exists:
    ready     the tool is built and testable now
    partial   built and running, but some checks need a key it does not have
    needs_key built, but inert until a provider key is configured
    planned   not built; awaiting its expert specification

`partial` is never authored below — `resolved()` derives it. A tool used to
flip to "ready" as soon as *any* key in `satisfied_by` was present, which was
too coarse to be true: the free OpenPageRank key satisfied `backlink-profile`
while supplying none of the three signals its checks actually read. Keys are
therefore declared per check, in `gated`, and a tool is only "ready" when
every check it advertises can fire.

`spec` records whether a tool has a written expert prompt behind it. The
two that do (the page advisor and the schema auditor) are the pattern the
rest should follow.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

READY, NEEDS_KEY, PLANNED = "ready", "needs_key", "planned"
PARTIAL = "partial"   # derived by resolved(), never written in the table

# THE RULE, stated once (item 157, channel 20260912-0940):
#
#     A check may be reported as passing only if the run measured it.
#     Absence of a finding is not a pass.
#
# It is written here, at the top of the file that decides what can fire, because
# three local fixes for three instances of it were not enough to stop a fourth.
# Each instance was fixed on its own and each comment was written after it bit:
# `img-sitemap-missing` read as passing on Birch's home page while the brief was
# saying site-wide that it could not judge it (`part_page.tsx`); "link-gap runs
# in every audit" on screen for a tool that is not built (`anatomy.tsx`); and
# the one that produced this rule -- the Speed part reporting "18 checks pass"
# for a run whose recorded dimensions did not include PRF, `cwv-not-assessed`
# among them.
#
# Its two readers: `resolved()` below, for what can fire on this install before
# any run; and `runs.not_assessed_payload`, for what a stored run actually
# measured. Anything else that renders "passing", "clean" or "N checks pass"
# owes this rule an answer.

# What an operator would go and sign up for, rather than the setting name.
#
# The phrase half of `CAPABILITIES` below; a name here is a name there. Kept as
# its own map because these five are the ones with a sign-up page, which is what
# an operator needs to read, and `renderer` has none.
KEY_NAMES: dict[str, str] = {
    "moz_token": "Moz", "dataforseo_login": "DataForSEO",
    "openpagerank_key": "OpenPageRank", "crux_api_key": "CrUX",
    "pagespeed_api_key": "PageSpeed Insights",
}


class Capability(NamedTuple):
    """One thing that must be true for a gated check to fire (item 157).

    `check(cfg)` answers whether it holds; `remedy` is the phrase `_dark_note`
    puts in front of an operator. A capability is not necessarily a key:
    whether it is satisfied by pasting a token or by installing a package is a
    detail of the remedy, not of the gate, and the sentence on screen cares
    about neither (channel 20260912-0940).
    """
    check: Callable[[object], bool]
    remedy: str


def _configured(key: str) -> Callable[[object], bool]:
    """A capability satisfied by a settings field being non-empty -- which is
    every capability this file had before item 157, and the shape `resolved()`
    used to read inline."""
    return lambda cfg: bool(getattr(cfg, key, ""))


def _renderer_present(_cfg: object) -> bool:
    """Whether this machine can take a performance trace at all.

    **Never called at import**, and that is a constraint rather than a
    preference: `perf.available()` touches the filesystem and can spawn a
    process, so a module-level probe would put a subprocess in the import path
    of everything that imports the playbook. It is called inside `resolved()`,
    which memoises it for the life of one call.

    **A probe that raises is not a satisfied capability.** An exception means
    dark, and the note says which. Treating a throwing probe as truthy would
    reproduce item 157's own defect with extra steps.
    """
    try:
        from clauditseo import perf
        return bool(perf.available())
    except Exception:
        return False


#: Every capability a check may be gated on, by the name a `gated` map uses.
#:
#: A config key is just a predicate over `cfg` (`_configured`), so the five that
#: existed before item 157 are in here with their behaviour unchanged --
#: `resolved()` went from reading `getattr(cfg, k, "")` inline to asking this
#: registry, at one line. `renderer` is the first that is not a key, which is
#: what the registry exists for.
CAPABILITIES: dict[str, Capability] = {
    # `an OpenPageRank key`, `a Moz key`. A first-letter test, not a phonetic
    # one -- it is wrong for names like "hour" and right for all five here,
    # which are the only names it is ever applied to.
    **{key: Capability(_configured(key),
                       f"{'an' if name[0].upper() in 'AEIOU' else 'a'} "
                       f"{name} key")
       for key, name in KEY_NAMES.items()},
    "renderer": Capability(
        _renderer_present,
        "the renderer extra installed (pip install clauditseo[render]) and a "
        "Chromium for it"),
}


def satisfied(name: str, cfg, _memo: dict | None = None) -> bool:
    """Whether one capability holds, by name.

    An unknown name is **not satisfied**, rather than an error or a pass: a
    `gated` map naming a capability this registry does not have is a mistake,
    and the safe reading of a mistake here is that the check cannot fire. A
    `gated` map that silently granted itself a capability is the failure this
    item is about.
    """
    cap = CAPABILITIES.get(name)
    if cap is None:
        return False
    if _memo is not None and name in _memo:
        return _memo[name]
    # **A probe that raises is not a satisfied capability**, and the wrap is
    # HERE rather than inside one capability's own predicate. It was inside
    # `_renderer_present` first, which made the guarantee true of that one
    # capability and false of the rule -- exactly the patch-on-a-path shape
    # that let item 157's defect class recur three times. Caught by
    # `test_a_probe_that_raises_is_dark_rather_than_satisfied`, which asks the
    # registry rather than the renderer.
    #
    # One exploding probe must also not take the workbench down for every
    # other tool, which is the second reason this is not left to propagate.
    try:
        got = bool(cap.check(cfg))
    except Exception:
        got = False
    if _memo is not None:
        _memo[name] = got
    return got

# kind: how an operator invokes it
SWEEP = "sweep"        # runs as part of any audit covering its dimension
PAGE = "page"          # on-demand, one page at a time
SITE = "site"          # on-demand, whole site
REPORT = "report"      # produced after a run

PLAYBOOK: list[dict] = [
    {
        "phase": "1. Crawl and indexability",
        "why": "If search engines cannot reach or index a page, every other "
               "improvement to it is wasted effort. Settle access first.",
        "tools": [
            {"id": "crawl", "name": "Crawl & sitemaps",
             "status": READY, "kind": SWEEP, "dims": ["TEC"],
             "spec": "Crawl & sitemaps analysis (item 137, brief v18 step AZ) — "
                     "reads the checks' crawl and sitemap rows and writes each "
                     "fix as its artefact; supersedes the old crawl-health "
                     "narrative.",
             "expert": "crawl",
             "does": "robots.txt reachability and AI-crawler rules, sitemap "
                     "validity/coverage/regression against the crawl, "
                     "reachability and render parity. The checks raise the "
                     "findings; the analysis writes the robots diff, the sitemap "
                     "URL list and the render policy, and judges crawl-budget "
                     "waste. The UA matrix and server-refusal are held until "
                     "task 4.",
             "checks": ["robots-missing", "ai-crawler-blocked",
                        "sitemap-missing", "sitemap-invalid",
                        "sitemap-coverage", "sitemap-regression",
                        "unreachable", "render-only", "head-divergent",
                        "mobile-parity", "mobile-parity-size",
                        "bot-parity"]},
            {"id": "indexability", "name": "Indexability directives",
             "status": READY, "kind": SWEEP, "dims": ["TEC"],
             "spec": "Indexability Directives Expert analysis — noindex, "
                     "canonical-missing and canonical-mismatch with conflict "
                     "resolution.",
             "expert": "indexability",
             "does": "noindex directives on internally linked pages and "
                     "canonical correctness. The expert analysis adds inlink "
                     "counts, canonical target status, chains and loops, and "
                     "resolves contradictory signals.",
             "checks": ["noindex-linked", "noindex-in-sitemap", "canonical-missing",
                        "canonical-mismatch", "canonical-to-404", "canonical-loop",
                        "canonical-sitemap-conflict", "redirect-to-404",
                        "redirect-temporary", "meta-robots-conflict"]},
            # brief v19 step BB: the contract URLs & parameters brief. It
            # replaced the legacy `url-hygiene` brief on the `urls` part — ten
            # free checks the sweep raises from the URL strings, four the brief
            # judges — retired once the live Birch and Acme runs were clean
            # (item 141), the way `crawl` superseded the old crawl-health.
            {"id": "urls", "name": "URLs & parameters",
             "status": READY, "kind": SITE, "dims": ["TEC"],
             "spec": "URLs & parameters analysis (item 141, brief v19 step BB) — "
                     "the character, case, separator, length, depth and slug "
                     "of each URL, the pattern table, and the parameter "
                     "inventory classified against the site's rules and "
                     "Indexability's canonicals; renames only under the inlink "
                     "cap and always with a 301.",
             "expert": "urls",
             "does": "whether each URL is readable and states its entity, "
                     "whether the site keeps one form per page, and which "
                     "parameters make duplicates. The checks raise the ten "
                     "free string checks; the analysis derives the pattern table, "
                     "classifies each parameter (handed to Indexability), "
                     "judges whether a slug is descriptive, and proposes a "
                     "rename only where it is worth the risk.",
             "checks": ["url-uppercase", "url-non-ascii", "url-separator",
                        "url-encoded-chars", "url-trailing-slash-mixed",
                        "url-length", "url-depth", "url-id-only",
                        "url-repeated-tokens", "url-parameter-unclassified",
                        "url-slug-not-descriptive", "url-slug-entity",
                        "url-parameter-policy", "url-rename"]},
        ],
    },
    {
        "phase": "2. Technical foundation",
        "why": "Site-wide settings that shape how every page is treated. "
               "Cheap to fix once, expensive to fix per page later.",
        "tools": [
            {"id": "https-security", "name": "HTTPS and security headers",
             "status": READY, "kind": SWEEP, "dims": ["SEC"],
             "spec": "Web application security engineer analysis — transport, "
                     "headers, cookies and leakage, analysis before "
                     "remediation, staged CSP and HSTS rollout.",
             "expert": "security",
             "does": "HTTPS enforcement and security headers. The automatic checks flag the obvious gaps; the expert analysis "
                     "adds the TLS probe "
                     "(negotiated version, cipher, certificate, HTTP-to-HTTPS "
                     "path) and returns deployable config with rollback.",
             # The SEC checks the sweep emits today (item 143 step BD, first
             # stage). The rest of the 56 are registered and reported not
             # assessed with their reason until their collectors land.
             "checks": ["http-redirect", "tls-legacy", "cert-chain", "cert-san",
                        "mixed-content", "hsts", "csp-absent", "csp-weak", "xcto",
                        "referrer-policy", "permissions-policy", "frame-ancestors",
                        "cookie-flags", "cache-authenticated", "deprecated-header",
                        "version-banner", "cms-fingerprint", "html-comment-leak",
                        "cross-origin-form", "sri-missing",
                        # Stage two: the well-known path sweep.
                        "exposed-file", "directory-listing", "error-leak",
                        "cms-xmlrpc", "cms-user-enumeration", "cms-login-exposed",
                        "cms-registration-open", "security-txt",
                        # Stage three: public DNS lookups (the `dns` extra).
                        "spf", "dmarc", "dkim", "caa", "dnssec", "dangling-cname",
                        "cors-permissive", "cross-origin-policies", "script-inventory",
                        "obfuscated-js", "hidden-content", "cloaking",
                        "http2-absent", "cert-key", "trackers-before-consent"]},
            {"id": "mobile-basics", "name": "Mobile viewport",
             "status": READY, "kind": SWEEP, "dims": ["TEC"],
             "spec": "Mobile Rendering Specialist analysis — viewport correctness "
                     "per page against WCAG 2.1 SC 1.4.4, zoom suppression "
                     "treated as an accessibility failure.",
             "expert": "mobile-viewport",
             "does": "the viewport tag per page, read verbatim: present at all, "
                     "device-width, initial-scale, zoom not suppressed, "
                     "duplicates, pre-responsive directives. The expert analysis "
                     "adds the render-dependent half.",
             # Item 147, brief v20: `mobile-viewport` became `viewport-missing`
             # and five more joined it. Only the six the sweep RAISES are here
             # — `test_ready_sweeps_reference_checks_the_engine_actually_emits`
             # is the guard, and it is right to: a sweep advertising a check
             # nothing emits reads as covered and is not.
             "checks": ["viewport-missing", "viewport-width", "viewport-scale",
                        "zoom-suppressed", "viewport-duplicate",
                        "viewport-legacy"]},
            {"id": "links", "name": "Links on the page",
             "status": READY, "kind": SITE, "dims": ["LNK"],
             "spec": "Internal linking analysis — under-linked and orphan pages "
                     "with the source, anchor and placement for each fix; "
                     "hub-and-spoke integrity; anchor variety and whether an "
                     "anchor names the entity it points at.",
             "expert": "links",
             "checks": ["inlinks-low", "orphan", "anchor-generic",
                        "anchor-duplicate-target", "broken-internal",
                        "redirect-chain", "nofollow-internal", "depth-deep"],
             "does": "which pages nothing links to, which are under-linked "
                     "and from where they should be linked, whether an anchor "
                     "names the page it points at, and whether hubs and their "
                     "spokes link to each other."},
            {"id": "hreflang", "name": "Hreflang and internationalisation",
             "status": READY, "kind": SITE, "dims": ["TEC"],
             "spec": "Hreflang expert analysis — reciprocity matrix, x-default "
                     "assessment, canonical alignment, one implementation "
                     "method only.",
             "expert": "hreflang",
             "does": "language and region targeting, return-tag reciprocity, "
                     "x-default handling. The crawler reads head annotations; "
                     "sitemap and HTTP-header alternates are not yet inspected "
                     "and the analysis is told so."},
            {"id": "migration-redirects", "name": "Migration and redirect mapping",
             "status": READY, "kind": SITE, "dims": ["TEC"],
             "spec": "Migration and redirect analysis — chains, loops, status "
                     "codes, bad destinations, equity preservation, corrected "
                     "map as CSV.",
             "expert": "migration-redirects",
             "does": "validates a redirect map you supply against the live "
                     "destination structure. The map cannot be derived from a "
                     "crawl, so this analysis requires it as an input and says so "
                     "rather than auditing the crawl as if it were one."},
        ],
    },
    {
        "phase": "3. On-page",
        "why": "Page-level signals: what each page claims to be about, and "
               "whether it says so clearly and distinctly.",
        "tools": [
            # Brief v15 step AQ: the Images brief, which is what the
            # on-page hygiene sweep and the page-scoped image brief both
            # became. The sweep's own image checks are its, and the brief
            # writes the corrected markup for each.
            {"id": "images", "name": "Images",
             "status": READY, "kind": SITE, "dims": ["ONP"],
             "spec": "Images specialist analysis — the delivery layer and the "
                     "on-page layer, inventory before advice, no estimated "
                     "file sizes and no review markup without provenance.",
             "expert": "images",
             "does": "alt text and decorative alt; filenames; the main image's "
                     "loading and priority; width and height; responsive "
                     "srcset and sizes; formats and weight; text baked into "
                     "pixels; image-anchored links; image sitemaps. The analysis "
                     "writes corrected markup for every failure, one change "
                     "per image even where it closes several checks.",
             "checks": ["img-alt-missing", "img-alt-decorative-nonempty",
                        "img-filename-generic", "img-lcp-lazy",
                        "img-dimensions-missing", "img-no-srcset",
                        "img-legacy-format", "img-duplicate-links"]},
            # Brief v10 step AG: the first brief named for the part it writes
            # to, covering only that part's checks and emitting only its
            # codes - the pattern the other parts follow.
            # Brief v11 step AJ: the second brief on the contract, reading
            # the outline the crawl records and the triples the Title &
            # description brief derives.
            {"id": "headings", "name": "Headings",
             "status": READY, "kind": SITE, "dims": ["ONP"],
             "spec": "Headings analysis - thirteen checks over each page's outline "
                     "against the semantic triple, a corrected outline for every "
                     "failing page.",
             "expert": "headings",
             "does": "whether each page's h1 restates the business, service and "
                     "place its title claims, whether the h2s support it and the "
                     "h3s break it into sub-services and locations, and whether "
                     "the outline is in order - with a corrected outline per page.",
             "checks": ["h1-missing", "h1-multiple", "heading-skip", "h1-triple-restated",
                        "h1-title-verbatim", "h1-brand-repeated", "h1-hook", "h2-support",
                        "h2-location-service", "h2-overstuffed", "h2-question-unanswered",
                        "h3-sub-service", "h3-geo-map"]},
            {"id": "title-desc", "name": "Title & description",
             "status": READY, "kind": SITE, "dims": ["ONP"],
             "spec": "Title & description analysis - six fixed checks over the "
                     "whole page set, replacement copy for every failure, "
                     "the checks' results and the comparison set supplied.",
             "expert": "title-desc",
             "does": "what each page claims to be in the tab and in the "
                     "result: title and description presence, length and "
                     "duplication across the set, with a copy-ready "
                     "replacement for every failure.",
             "checks": ["title-missing", "title-length", "title-duplicate",
                        "meta-desc-missing", "meta-desc-length", "meta-desc-duplicate"]},
            {"id": "page-advisor", "name": "Page advisor (H1, title, meta, answer line)",
             "status": READY, "kind": PAGE, "dims": ["ONP"],
             "spec": "H1 analysis prompt — triage on commercial / multi-page / "
                     "YMYL / search-facing, then recommend with ranked "
                     "alternatives.",
             "does": "recommends the single best H1 plus title tag, meta "
                     "description and the answer line beneath the heading, "
                     "with ranked alternatives, site-role and cannibalisation "
                     "calls, and compliance flags.",
             "endpoint": "/api/runs/{run_id}/advise"},

        ],
    },
    {
        "phase": "4. Accessibility",
        "why": "Whether the page can be used at all — by a screen reader, by "
               "keyboard alone, by someone who cannot resolve low-contrast "
               "text. Much of it overlaps with what search engines need, and "
               "in Australia the DDA applies to websites regardless.",
        "tools": [
            # No "spec": that key marks a tool built from an operator-written
            # expert prompt, and this one is deterministic throughout.
            {"id": "a11y-sweep", "name": "Accessibility checks",
             "status": READY, "kind": SWEEP, "dims": ["A11Y"],
             "does": "language declaration, form control labelling, link and "
                     "button accessible names, duplicate ids, dangling aria "
                     "references, positive tabindex, frame titles, table "
                     "headers, main landmark. With the renderer installed it "
                     "adds colour contrast, focus order and reading order — "
                     "none of which can be decided from HTML, and all of which "
                     "the run says plainly it did not check when the renderer "
                     "is absent.",
             "checks": ["html-lang-missing", "form-control-unlabelled",
                        "link-name-missing", "link-text-generic",
                        "button-name-missing", "duplicate-id",
                        "aria-reference-broken", "tabindex-positive",
                        "iframe-title-missing", "table-headers-missing",
                        "landmark-main-missing"]},
        ],
    },
    {
        "phase": "5. Structured data",
        "why": "How the page describes itself to machines. Sits after on-page "
               "because the markup must reflect the headings and copy above.",
        "tools": [
            {"id": "schema-validation", "name": "Structured data validation",
             "status": READY, "kind": SWEEP, "dims": ["ONP"], "spec": None,
             "does": "parses the JSON-LD graph and validates it: required and "
                     "one-of properties per type, recommended properties, "
                     "untyped entities, duplicate @id, and rich-result types "
                     "Google has deprecated or narrowed.",
             "checks": ["jsonld-invalid", "schema-missing-required",
                        "schema-missing-one-of", "schema-missing-recommended",
                        "schema-deprecated-rich-result", "schema-untyped-entity",
                        "schema-duplicate-id"]},
            # Brief v16 step AS: one Structured data brief on the contract,
            # where a page-scoped auditor and an entity brief stood. It reads
            # the crawl's own inventory - every block as parsed - rather than
            # re-fetching, and it is site-scoped because half its checks are
            # questions about the run: an @id is inconsistent only against
            # the other pages' @ids.
            {"id": "structured-data", "name": "Structured data",
             "status": READY, "kind": SITE, "dims": ["ONP"],
             "spec": "Structured data auditor and entity specialist analysis - "
                     "one entity, one canonical @id, markup that states only "
                     "what the page visibly says.",
             "expert": "structured-data",
             "does": "inventories every block as parsed, then judges the page "
                     "against Google's requirements and the site's entity "
                     "record: what parses, what each page type needs, "
                     "required properties, @id consistency and orphan "
                     "instances, duplicate blocks, NAP against the record, "
                     "sameAs against subjectOf, markup with no visible "
                     "counterpart, breadcrumbs and article dates. It writes "
                     "corrected JSON-LD for every failure.",
             "checks": ["schema-invalid-json", "schema-missing-for-type",
                        "schema-required-missing", "schema-deprecated-rich-result",
                        "schema-id-inconsistent", "schema-orphan-instance",
                        "schema-redundant-block", "schema-nap-mismatch",
                        "schema-sameas-misplaced", "schema-graph-wiring",
                        "schema-breadcrumb-missing", "schema-datemodified-missing"]},
            {"id": "schema-auditor", "name": "Schema auditor and remediation",
             "status": READY, "kind": PAGE, "dims": ["ONP"],
             "spec": "Structured data auditor prompt — findings before fixes, "
                     "Google governs where it restricts Schema.org.",
             "does": "diagnoses eligibility per rich result, validates every "
                     "documented property, ranks issues by severity, then "
                     "supplies corrected paste-ready JSON-LD with a fix map "
                     "and re-validation steps.",
             "endpoint": "/api/runs/{run_id}/schema-audit"},
        ],
    },
    {
        "phase": "6. Content",
        "why": "Whether the page deserves to rank once it can be found and "
               "understood. The most expensive work, so it comes after the "
               "cheap structural wins.",
        "tools": [
            {"id": "content-coverage", "name": "Content · Coverage",
             "status": READY, "kind": SITE, "dims": ["CNT"],
             "spec": "What the site should cover and does not — services x "
                     "node types, Covered / Partial / Missing, with the "
                     "demand, value, difficulty and effort of each gap.",
             "expert": "content-coverage",
             "does": "the topical map: which services and locations have a "
                     "page, which have a thin one, and which node types are "
                     "missing from each."},
            {"id": "content-substance", "name": "Content · Substance",
             "status": READY, "kind": SITE, "dims": ["CNT"],
             "spec": "Whether a page earns its place — experience, evidence, "
                     "the answer surface a model can quote, and what it costs "
                     "a reader to get to the answer.",
             "expert": "content-substance",
             "does": "reads the free rows and judges what is missing from the "
                     "page itself, proposing copy drawn only from facts the "
                     "page, the site or the record supply."},
            {"id": "content-cannibalisation", "name": "Content · Cannibalisation",
             "status": READY, "kind": SITE, "dims": ["CNT"],
             "spec": "Pages competing for one subject: which survives, which "
                     "is differentiated, which is folded in, and which is "
                     "retired and redirected.",
             "expert": "content-cannibalisation",
             "does": "clusters the overlapping pages, names a survivor by "
                     "inlinks then age then depth, and gives each other page "
                     "one disposition."},
            {"id": "content-benchmark", "name": "Content · Benchmark",
             "status": READY, "kind": SITE, "dims": ["CNT"],
             "spec": "This page against the pages that outrank it. Held "
                     "until the site record carries a competitor set, "
                     "keyword data, a top-10 corpus and a publish history.",
             "expert": "content-benchmark",
             "does": "term density, vocabulary gaps and demand against a "
                     "competitor corpus — every row held until that corpus "
                     "is on the record."},
            {"id": "content-signals", "name": "Content quality checks",
             "status": READY, "kind": SWEEP, "dims": ["CNT"], "spec": None,
             "does": "thin pages, near-duplicate bodies by shingle overlap, "
                     "readability, content-to-template ratio.",
             "checks": ["thin-content", "duplicate-content",
                        "readability-long-sentences", "low-text-ratio"]},
            {"id": "content-brief", "name": "Content brief generator",
             "status": READY, "kind": PAGE, "dims": ["CNT"], "spec": "content-brief.md",
             "does": "a content brief for a new or rewritten page: "
                     "structure, entities to cover, questions to answer, "
                     "internal links to earn."},
        ],
    },
    {
        "phase": "7. Performance",
        "why": "A tie-breaker rather than a foundation, but a genuine one — "
               "and cheap to measure once the page is otherwise right.",
        "tools": [
            {"id": "core-web-vitals", "name": "Core Web Vitals (field and lab)",
             "status": NEEDS_KEY, "kind": SWEEP, "dims": ["PRF"], "spec": None,
             "satisfied_by": ["crux_api_key", "pagespeed_api_key"],
             "needs": "CLAUDITSEO_CRUX_KEY (field) or CLAUDITSEO_PAGESPEED_KEY (lab)",
             "does": "real LCP, INP and CLS rather than local proxies.",
             "checks": ["lcp-poor", "cwv-not-assessed"],
             # cwv-not-assessed is ungated on purpose: it is the finding that
             # fires *because* the key is absent.
             "gated": {"lcp-poor": ["crux_api_key", "pagespeed_api_key"]}},
            # brief v19 step BC: the contract Speed brief over the per-page
            # performance trace. Thirteen free checks the browser-trace sweep
            # raises and five the brief judges per template.
            #
            # `render-blocking` is RETIRED (step 3a): its two clean runs are
            # Birch `ff313d06` (live, 12 pages traced) and twenty22 `95ac5495`
            # (live, 48 crawled / 12 traced, standing in for Acme under the
            # operator's 2026-09-12 ruling), which is the standard
            # migration-redirects.md and url-hygiene.md were held to. The
            # `render-blocking` CHECK is untouched and is one of the thirteen --
            # only the legacy page-scoped brief is gone.
            #
            # `perf-signals` is retired too (migration 0054), and the migration
            # carries the reasoning: a purge rather than a re-home, because
            # `slow-response` had a successor on only 12 of 45 pages and the
            # other two had none at all.
            {"id": "speed", "name": "Speed",
             "status": READY, "kind": SITE, "dims": ["PRF"],
             # Item 157: the checks that exist only because a trace was taken
             # are gated on the renderer being installed. Before this, a machine
             # with no Chromium advertised all thirteen as ready and the part
             # page reported them as passing.
             #
             # `page-weight` is here since item 168: its HTML-bytes proxy was
             # retired at migration 0054, so the trace is the only thing that
             # measures it and an untraced install cannot answer it. `cwv-not-assessed`
             # is not here either - it is the finding raised BECAUSE nothing
             # ran, which `resolved()` already declines to count as a working
             # check.
             #
             # This list is `prf.TRACE_DERIVED_CHECKS`, written out because this
             # table is literal data and importing a module into it at import
             # time is how an import cycle starts. Guarded against that set by
             # `test_the_renderer_gate_is_the_trace_derived_set`, so the two
             # cannot drift.
             "gated": {c: ["renderer"] for c in (
                 "lcp-slow", "cls-high", "inp-long-tasks", "ttfb-slow",
                 "render-blocking", "unused-css-js", "uncompressed",
                 "no-cache-headers", "unminified", "third-party-weight",
                 "font-blocking", "page-weight")},
             "spec": "Speed analysis (item 141, brief v19 step BC) — the render "
                     "path in discovery order, the Core Web Vitals as Google "
                     "measures them, and the cause behind each number, from a "
                     "throttled per-page performance trace; one plan per "
                     "template, never per page.",
             "expert": "speed",
             "does": "reads the trace and judges each template: the free checks "
                     "raise slow vitals, render-blocking, unused/uncompressed/"
                     "uncached/unminified resources, third-party weight and "
                     "font-blocking; the analysis writes the critical-path plan, "
                     "the LCP/CLS/INP causes and the third-party policy. Image "
                     "weight is the Images part's, referenced not recounted.",
             "checks": ["lcp-slow", "cls-high", "inp-long-tasks", "ttfb-slow",
                        "render-blocking", "unused-css-js", "uncompressed",
                        "no-cache-headers", "unminified", "third-party-weight",
                        "font-blocking", "page-weight", "cwv-not-assessed",
                        "critical-path", "lcp-cause", "cls-cause", "inp-cause",
                        "third-party-policy"]},
        ],
    },
    {
        "phase": "8. AI surface",
        "why": "Increasingly where discovery happens. Depends on structure "
               "and content already being right, so it sits late.",
        "tools": [
            {"id": "ai-access", "name": "llms.txt and answer extractability",
             "status": READY, "kind": SWEEP, "dims": ["AIS"],
             "spec": "AI surface analysis: reachability per agent class, the entity "
                     "anchor, enrichment from the site record, liftable passages and "
                     "the /llms.txt assessment.",
             "expert": "ai-surface",
             "does": "llms.txt presence and heading structure that supports "
                     "answer extraction. The robots rules for the AI agents "
                     "(every non-search agent in the agent list, one row each) "
                     "are `ai-crawler-blocked`, re-homed to the Crawl "
                     "& sitemaps checks at item 137 as a crawl-access rule.",
             "checks": ["llms-txt-missing", "edge-blocks-ai-ua",
                        "ai-crawler-allowed-unstated", "noai-meta", "ua-sensitive",
                        "content-behind-js", "llms-txt-stale", "entity-unresolvable",
                        "entity-unnamed", "ai-experience-unmeasured",
                        "poor-extractability", "extractability-not-assessed"]},
            {"id": "extractability", "name": "Answer extractability judgement",
             "status": READY, "kind": SITE, "dims": ["AIS"], "spec": None,
             "does": "whether an assistant could lift a correct, "
                     "self-contained answer, and what blocks citation. Runs "
                     "automatically when adaptive staging bands AI-Surface at "
                     "concern or worse."},
            {"id": "citation-readiness", "name": "Citation and brand-mention readiness",
             "status": PLANNED, "kind": SITE, "dims": ["AIS"], "spec": None,
             "does": "whether the brand is cited by assistants today, which "
                     "sources they draw on, and what would earn a citation."},
        ],
    },
    {
        "phase": "9. Local",
        "why": "Only applicable to businesses with a physical or service-area "
               "footprint; its weight redistributes when it is not.",
        "tools": [
            {"id": "local-signals", "name": "Local signals checks",
             "status": READY, "kind": SWEEP, "dims": ["LOC"], "spec": "local-signals.md",
             "does": "NAP presence and consistency across pages, "
                     "LocalBusiness structured data, opening hours, location "
                     "page substance.",
             "checks": ["nap-missing", "nap-inconsistent",
                        "localbusiness-schema-missing", "opening-hours-missing",
                        "thin-location-page"]},
            {"id": "gbp-audit", "name": "Google Business Profile audit",
             "status": READY, "kind": SITE, "dims": ["LOC"], "spec": "gbp-audit.md",
             "does": "categories, attributes, posts, photos, Q&A, and how the "
                     "profile aligns with the site."},
            {"id": "citations-nap", "name": "Off-site citations and NAP",
             "status": READY, "kind": SITE, "dims": ["LOC"], "spec": "citations-nap.md",
             "does": "directory consistency beyond the site itself, duplicate "
                     "listings, missing citations."},
            {"id": "review-signals", "name": "Review signals",
             "status": READY, "kind": SITE, "dims": ["LOC"], "spec": "review-signals.md",
             "does": "review velocity, distribution, response rate, and the "
                     "policy line on marking reviews up."},
        ],
    },
    {
        "phase": "10. Off-page authority",
        "why": "Last of the work phases because links follow from something "
               "worth linking to. Fix the asset before promoting it.",
        "tools": [
            {"id": "backlink-profile", "name": "Backlink profile",
             "status": NEEDS_KEY, "kind": SWEEP, "dims": ["OFP"], "spec": None,
             "satisfied_by": ["moz_token", "dataforseo_login", "openpagerank_key"],
             "needs": "CLAUDITSEO_MOZ_TOKEN, CLAUDITSEO_DATAFORSEO_LOGIN or "
                      "CLAUDITSEO_OPENPAGERANK_KEY",
             "does": "referring domains, anchor distribution, toxic patterns.",
             "checks": ["backlinks-not-assessed", "low-referring-domains",
                        "toxic-anchor-pattern", "anchor-overoptimisation",
                        "domain-authority-reported", "referring-domains-reported"],
             # OpenPageRank returns a domain-authority number and nothing
             # else, so it unlocks only the reference finding. The three
             # checks that score need referring-domain counts and anchor
             # text, which only the paid indexes supply.
             "gated": {"low-referring-domains": ["moz_token", "dataforseo_login"],
                       "toxic-anchor-pattern": ["moz_token", "dataforseo_login"],
                       "anchor-overoptimisation": ["moz_token", "dataforseo_login"],
                       "domain-authority-reported": ["moz_token", "dataforseo_login",
                                                     "openpagerank_key"],
                       "referring-domains-reported": ["moz_token", "dataforseo_login"]}},
            {"id": "link-gap", "name": "Competitor link gap",
             "status": PLANNED, "kind": SITE, "dims": ["OFP"], "spec": None,
             "does": "domains linking to competitors but not to this site, "
                     "ranked by attainability."},
            {"id": "disavow-review", "name": "Toxic link review and disavow",
             "status": PLANNED, "kind": SITE, "dims": ["OFP"], "spec": None,
             "does": "manual-review workflow before any disavow, since "
                     "disavowing good links is the common own goal."},
        ],
    },
    {
        "phase": "11. Prioritise, report, monitor",
        "why": "Turning findings into sequenced work, and proving the work "
               "moved something.",
        "tools": [
            {"id": "plan", "name": "Client plan",
             "status": READY, "kind": REPORT, "dims": [],
             "spec": "plan.md",
             "does": "the front of the client report: executive summary, "
                     "what is blocking, the upgrade-before-publish ratio, a "
                     "roadmap by horizon and workstream, what the client "
                     "must supply, how we will know, and the risks the rows "
                     "imply. It finds nothing - every sentence cites a check "
                     "id or a part, and one that cites neither is dropped."},
            {"id": "prioritisation", "name": "Dependency-aware priority plan",
             "status": READY, "kind": SITE, "dims": [], "spec": None,
             "does": "sequences the run's findings into a plan with business "
                     "rationale, grouping by shared root cause so a template "
                     "fix is not repeated per page."},
            {"id": "reporting", "name": "Client and internal reports",
             "status": READY, "kind": REPORT, "dims": [], "spec": None,
             "does": "run, comparison and trend reports in client-facing or "
                     "internal voice; every metric carries source and "
                     "confidence, gaps render as [TO CONFIRM].",
             "endpoint": "/api/reports"},
            {"id": "regression-monitoring", "name": "Regression monitoring",
             "status": READY, "kind": SITE, "dims": [], "spec": None,
             "does": "fingerprints each finding so the same issue is tracked "
                     "across runs: open, fixed, regressed. Regressions are "
                     "surfaced loudly rather than averaged away."},
            {"id": "measurement-validation", "name": "Measurement validation",
             "status": PLANNED, "kind": SITE, "dims": [], "spec": None,
             "does": "whether analytics and Search Console are actually "
                     "recording what the audit assumes: tagging, filters, "
                     "property coverage, conversion definitions."},
        ],
    },
]


def resolved(cfg) -> list[dict]:
    """The playbook with key-gated tools resolved against the running config.

    The status in the table above is what a tool needs, not what it has. A
    tool whose key is present must not keep reporting "needs key": the
    workbench is the operator's map of what will actually run, and a badge
    that contradicts the configuration makes every other badge suspect.
    """
    # Memoised for the life of this call, which is what lets a capability be a
    # runtime probe rather than an attribute read (item 157): `renderer` asks
    # `perf.available()`, and a tool loop would otherwise ask it once per gated
    # check. Per call rather than per process, so an install that gains a
    # renderer is seen by the next request and not only by the next restart.
    seen: dict[str, bool] = {}
    phases = []
    for phase in PLAYBOOK:
        tools = []
        for tool in phase["tools"]:
            gated = tool.get("gated")
            if tool["status"] in (READY, NEEDS_KEY) and gated:
                live, dark = [], {}
                for check in tool.get("checks", []):
                    keys = gated.get(check)
                    # The one line item 157 changed: a capability is asked, not
                    # read. `satisfied` treats an unknown name as unsatisfied,
                    # so a `gated` map cannot grant itself a capability the
                    # registry does not have.
                    if not keys or any(satisfied(k, cfg, seen) for k in keys):
                        live.append(check)
                    else:
                        dark[check] = keys
                tool = {**tool, "checks_live": live, "checks_dark": sorted(dark)}
                # A "-not-assessed" check is the finding raised *because*
                # nothing ran. Counting it as a working check would let a
                # tool that measures nothing describe itself as partly
                # working, which is the failure this whole change is about.
                live = [c for c in live if not c.endswith("-not-assessed")]
                if not dark:
                    tool["status"] = READY
                    tool["needs"] = f"{tool.get('needs', '')} — configured".lstrip(" —")
                elif live:
                    # Some checks fire and some cannot. Saying "ready" here is
                    # what let a tool silently under-deliver.
                    tool["status"] = PARTIAL
                    tool["dark_note"] = _dark_note(dark)
                else:
                    tool["status"] = NEEDS_KEY
                    tool["dark_note"] = _dark_note(dark)
            elif tool["status"] == NEEDS_KEY and tool.get("satisfied_by"):
                if any(getattr(cfg, k, "") for k in tool["satisfied_by"]):
                    tool = {**tool, "status": READY,
                            "needs": f"{tool['needs']} — configured"}
            tools.append(tool)
        phases.append({**phase, "tools": tools})
    return phases


def gating_for(check_ids, cfg) -> dict[str, dict]:
    """What the playbook knows about each of these checks' gating (item 157).

    The **join**, not a switch of source. `briefs.catalogue()` stays the list of
    which checks a part has, because the playbook is not a superset of it -- and
    neither contains the other: measured on this tree, 148 brief-declared check
    ids against the playbook's 137, with **53 brief ids in no tool** and **42
    playbook ids in no brief**. Either single-source answer would silently
    delete checks from a screen (channel 20260912-0940).

    So membership and gating are read from the list that is already right about
    each, and joined here. One entry per id asked for, and each says which of
    three things it is:

        {"state": "live"}                     gated, and its capabilities hold
        {"state": "dark", "needs": [...],
         "note": "..."}                       gated, and they do not
        {"state": "unclaimed"}                no playbook tool names this check

    **`unclaimed` is declared, not inferred from absence**, which is the same
    defect class this item exists to fix: a check missing from the gating map
    must not read as "gated and live". The 53 land here, and they are mostly the
    analysis checks briefs judge and no sweep emits.
    """
    claimed: dict[str, list[str] | None] = {}
    for phase in PLAYBOOK:
        for tool in phase["tools"]:
            gated = tool.get("gated") or {}
            for check in tool.get("checks", []):
                # First tool wins, and a gate beats no gate: two tools naming
                # one check where only one gates it must not turn on which was
                # authored first.
                if check not in claimed or (claimed[check] is None
                                            and gated.get(check)):
                    claimed[check] = gated.get(check)

    seen: dict[str, bool] = {}
    out: dict[str, dict] = {}
    for full in check_ids:
        bare = full.split("/")[-1]
        if bare not in claimed:
            out[full] = {"state": "unclaimed"}
            continue
        needs = claimed[bare]
        if not needs or any(satisfied(k, cfg, seen) for k in needs):
            out[full] = {"state": "live"}
        else:
            out[full] = {"state": "dark", "needs": list(needs),
                         "note": _dark_note({bare: list(needs)})}
    return out


def _dark_note(dark: dict[str, list[str]]) -> str:
    """One sentence naming the checks that cannot fire and what would free
    them — the thing an operator needs before quoting the work, not after."""
    # The remedy comes from `CAPABILITIES` rather than from `KEY_NAMES` alone
    # (item 157). The sentence used to end "supplies the data they read", which
    # is true of a provider key and false of the first capability that is not
    # one: a renderer supplies no data an operator signs up for, it is a package
    # they install. So the note says what a check NEEDS and lets each capability
    # word its own half.
    n = len(dark)
    names = sorted({k for ks in dark.values() for k in ks})
    wants = " or ".join(CAPABILITIES[k].remedy if k in CAPABILITIES
                        else KEY_NAMES.get(k, k) for k in names)
    return (f"{n} check{'s' if n > 1 else ''} cannot run here "
            f"({', '.join(sorted(dark))}) — "
            f"{'they need' if n > 1 else 'it needs'} {wants}.")


def summary(phases: list[dict] | None = None) -> dict:
    """Counts by status, for the workbench header."""
    tools = [t for phase in (phases or PLAYBOOK) for t in phase["tools"]]
    return {
        "total": len(tools),
        "ready": sum(1 for t in tools if t["status"] == READY),
        "partial": sum(1 for t in tools if t["status"] == PARTIAL),
        "needs_key": sum(1 for t in tools if t["status"] == NEEDS_KEY),
        "planned": sum(1 for t in tools if t["status"] == PLANNED),
        "with_spec": sum(1 for t in tools if t.get("spec")),
    }
