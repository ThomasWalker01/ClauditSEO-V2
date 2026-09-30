"""Findings sorted the way a page is built, rather than by the dimension
that happened to raise them.

The dimensions (TEC, ONP, CNT…) are how the engine is organised and what
scoring runs on. They are not how anyone fixes a site: you open a page in a
CMS and you fix its title, its headings, its images. This module is a lens
over the same findings, not a second opinion about them — the categories
must always sum to the same total the rest of the app reports, and a test
holds that.

Two tables, because one is not enough:

  CHECK_CATEGORY  by check id, for deterministic findings. Precise, and
                  necessary: a single sweep spans categories, so mapping by
                  tool would file every title, heading and image finding
                  from `onpage-hygiene` under one heading.
  TOOL_CATEGORY   by tool, for expert findings. Their check ids are written
                  by the model — 283 distinct in this database against 22
                  deterministic — so there is nothing static to map. What
                  they do carry is the tool that produced them, in their
                  `EXP:<tool>` dimension.

Adding a check or a tool without adding it here fails a test rather than
landing silently in an "other" bucket, which is the only way a lens like
this stays honest as the suite grows.
"""

from __future__ import annotations

from dataclasses import dataclass

ON_PAGE = "on the page"
SITE_WIDE = "across the site"
OFF_SITE = "beyond the site"
WORKFLOW = "workflow"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    group: str
    blurb: str


CATEGORIES: tuple[Category, ...] = (
    # --- what you fix by editing a page ---------------------------------
    Category("title-desc", "Title & description", ON_PAGE,
             "What each page claims to be, in the tab and in the result."),
    Category("headings", "Headings", ON_PAGE,
             "Whether each page says what it is about once, at the top, in order."),
    Category("images", "Images", ON_PAGE,
             "Alt text, dimensions and delivery."),
    Category("content", "Content", ON_PAGE,
             "Depth, duplication and readability of the words themselves."),
    Category("schema", "Structured data", ON_PAGE,
             "JSON-LD validity and the entities it declares."),
    Category("a11y", "Accessibility", ON_PAGE,
             "Whether the page can be used by keyboard, by screen reader, "
             "and by someone who cannot resolve low-contrast text."),
    Category("links", "Links on the page", ON_PAGE,
             "Internal linking, anchor text and where each page sits in the graph."),

    # --- what you fix once, for the whole site --------------------------
    Category("indexability", "Indexability & canonicals", SITE_WIDE,
             "Whether a page is allowed to be indexed, and which URL owns it."),
    Category("crawl", "Crawl & sitemaps", SITE_WIDE,
             "Reachability: robots, sitemaps, status codes, redirects."),
    Category("urls", "URLs & parameters", SITE_WIDE,
             "URL shape, duplicate forms, parameters and facets."),
    Category("speed", "Speed", SITE_WIDE,
             "Response time, page weight, caching and Core Web Vitals."),
    Category("security", "Security & transport", SITE_WIDE,
             "HTTPS enforcement and security headers."),
    Category("mobile", "Mobile", SITE_WIDE,
             "Viewport correctness and mobile rendering."),
    Category("intl", "International", SITE_WIDE,
             "Language and region targeting."),

    # --- what you cannot fix by editing the site ------------------------
    Category("backlinks", "Backlinks", OFF_SITE,
             "Referring domains and the anchor text pointing in."),
    Category("local", "Local & citations", OFF_SITE,
             "NAP consistency, the business profile and directory presence."),
    Category("ai-surface", "AI surface", OFF_SITE,
             "Whether AI crawlers can reach and quote the site."),

    # --- not a defect category; holds the dispatcher and the reporting --
    Category("workflow", "Prioritise & report", WORKFLOW,
             "Deciding what to do next, and telling the client about it."),
)

BY_KEY = {c.key: c for c in CATEGORIES}
GROUPS = (ON_PAGE, SITE_WIDE, OFF_SITE)


CHECK_CATEGORY: dict[str, str] = {
    # title & description
    "title-missing": "title-desc", "title-length": "title-desc",
    "title-duplicate": "title-desc", "meta-desc-missing": "title-desc",
    "meta-desc-duplicate": "title-desc", "meta-desc-length": "title-desc",
    "title-entity-alignment": "title-desc",
    # headings
    "h1-missing": "headings", "h1-multiple": "headings", "heading-skip": "headings",
    # the Headings brief's own checks (brief v11 step AI)
    "h1-triple-restated": "headings", "h1-title-verbatim": "headings",
    "h1-brand-repeated": "headings", "h1-hook": "headings",
    "h2-support": "headings", "h2-location-service": "headings",
    "h2-overstuffed": "headings", "h2-question-unanswered": "headings",
    "h3-sub-service": "headings", "h3-geo-map": "headings",
    # images
    "img-alt-missing": "images",
    # The Images brief's own set (brief v15 step AQ): every one of them
    # files under the part its brief writes to.
    "img-alt-decorative-nonempty": "images", "img-link-alt-not-destination": "images",
    "img-filename-generic": "images", "img-lcp-lazy": "images",
    "img-dimensions-missing": "images", "img-oversized": "images",
    "img-no-srcset": "images", "img-sizes-wrong": "images",
    "img-legacy-format": "images", "img-weight-budget": "images",
    "img-text-in-image": "images", "img-duplicate-links": "images",
    "img-sitemap-missing": "images",
    # The one header image that is not decorative (brief v16 step AU6),
    # and one image too heavy for what it shows (step AU7).
    "img-logo": "images",
    "img-logo-not-assessed": "images", "img-heavy": "images",
    # content
    "thin-content": "content", "duplicate-content": "content",
    # Content's own set (brief v17 step AX): eight the sweep answers and
    # thirteen only a brief can. All twenty-one are filed here, because a
    # part page lists every check that may write to it whether or not
    # anything has run.
    "thin": "content", "stale": "content", "no-author": "content",
    "question-unanswered": "content", "title-overlap": "content",
    "fact-density": "content", "answer-first": "content",
    "gap": "content", "format-gap": "content", "intent-gap": "content",
    "topic-drift": "content", "eeat": "content", "substance": "content",
    # Item 136q commit 6 / 136o Tab 4: what one page is about.
    "entity-page-verdict": "content",
    "answer-surface": "content", "retrieval-cost": "content",
    "cannibalisation": "content", "term-density": "content",
    "vocabulary-gap": "content", "demand-gap": "content",
    "optimisation-ratio": "content",
    "template-only-page": "content",
    "readability-long-sentences": "content", "low-text-ratio": "content",
    # structured data
    "jsonld-invalid": "schema", "schema-deprecated-rich-result": "schema",
    # The Structured data brief's own set (brief v16 step AS).
    "schema-invalid-json": "schema", "schema-deprecated-rich-result": "schema", "schema-hidden-markup": "schema",
    "schema-id-inconsistent": "schema", "schema-missing-for-type": "schema", "schema-required-missing": "schema",
    "schema-subtype-shallow": "schema", "schema-orphan-instance": "schema", "schema-orphan-not-assessed": "schema", "schema-redundant-block": "schema",
    "schema-island": "schema",
    "schema-nap-mismatch": "schema", "schema-author-missing": "schema", "schema-datemodified-missing": "schema",
    "schema-id-page": "schema", "schema-entity-model": "schema", "schema-graph-wiring": "schema",
    "schema-catalog-mismatch": "schema", "schema-sameas-misplaced": "schema", "schema-sameas-missing": "schema",
    "schema-breadcrumb-missing": "schema", "schema-entity-thin": "schema", "schema-triple-mismatch": "schema",
    "schema-review-unsupported": "schema",
    "schema-duplicate-id": "schema", "schema-missing-one-of": "schema",
    "schema-missing-recommended": "schema", "schema-missing-required": "schema",
    "schema-untyped-entity": "schema",
    # accessibility. img-alt and heading-order are deliberately NOT here:
    # they are accessibility failures too, but they already have a home, and
    # a finding counted in two categories breaks the sum.
    "html-lang-missing": "a11y", "form-control-unlabelled": "a11y",
    "link-name-missing": "a11y", "link-text-generic": "a11y",
    "button-name-missing": "a11y", "duplicate-id": "a11y",
    "aria-reference-broken": "a11y", "tabindex-positive": "a11y",
    "iframe-title-missing": "a11y", "table-headers-missing": "a11y",
    "landmark-main-missing": "a11y", "contrast-not-assessed": "a11y",
    "axe-sampled": "a11y", "axe-render-failed": "a11y", "axe-coverage": "a11y",
    # indexability
    # noindex-page split into these two at item 137 (brief v18 step BA).
    "noindex-linked": "indexability", "noindex-in-sitemap": "indexability",
    # Redirect and meta-robots checks, brief v18 step BA — the Indexability part
    # carries the redirect log (redirect-chain stays on Crawl, its older home).
    "redirect-to-404": "indexability", "meta-robots-conflict": "indexability",
    "redirect-temporary": "indexability",
    # The terminal-axis canonical checks (TEC), brief v18 step BA — filed with
    # the relation checks on the Indexability part.
    "canonical-to-404": "indexability", "canonical-loop": "indexability",
    "canonical-sitemap-conflict": "indexability",
    # The three analysis checks, brief v18 step BA (model-judged, held).
    "noindex-intent": "indexability", "redirect-map-correctness": "indexability",
    "parameter-policy": "indexability",
    "canonical-missing": "indexability",
    "canonical-mismatch": "indexability",
    # Q-54. Both sit with the canonical they are a grade of.
    "canonical-mismatch-trailing-slash": "indexability",
    "canonical-mismatch-parameter": "indexability",
    # Q-55.
    "canonical-off-host": "indexability",
    # Item 136q commit 5.
    "title-entity-incomplete": "title-desc",
    # Filed with the canonical checks, not with title-desc: the page's title
    # is only how the duplicate was noticed, and the fix is a canonical.
    "canonical-missing-variant": "indexability",
    # urls & parameters
    # The first deterministic member of this category — it was ANALYSIS_ONLY,
    # filled by the `url-hygiene` brief or not at all. Filed here and not with
    # `links`: the <a href> is only where the parameter was found, and
    # what the finding is about is the URL it builds and the duplicate that
    # URL manufactures. Same rule as `canonical-missing-variant` above.
    "internal-link-tracking-params": "urls",
    # The URLs & parameters brief's fourteen checks (brief v19 step BB): ten
    # the sweep raises from the URL strings, four the brief judges. All filed
    # on `urls`, the part they write to, whether or not anything has fired —
    # a part page lists every check that may write to it.
    "url-uppercase": "urls", "url-non-ascii": "urls", "url-separator": "urls",
    "url-encoded-chars": "urls", "url-trailing-slash-mixed": "urls",
    "url-length": "urls", "url-depth": "urls", "url-id-only": "urls",
    "url-repeated-tokens": "urls", "url-parameter-unclassified": "urls",
    "url-slug-not-descriptive": "urls", "url-slug-entity": "urls",
    "url-parameter-policy": "urls", "url-rename": "urls",
    # links (brief v17 step AW). Eight the sweep answers and four only a
    # brief can; all twelve are filed here, because a part page lists every
    # check that may write to it whether or not anything has run.
    # `redirect-chain` is the one check id two dimensions raise, and they
    # are not the same finding: TEC's is about reaching a page at all and
    # is filed with the crawl, LNK's is about a link on a page pointing
    # through a chain and is fixed by editing that link. Keyed by
    # dimension, which `category_for` tries before the bare id.
    "LNK/redirect-chain": "links",
    "inlinks-low": "links", "orphan": "links", "anchor-generic": "links",
    "anchor-duplicate-target": "links", "broken-internal": "links",
    "nofollow-internal": "links", "depth-deep": "links",
    "link-suggestion": "links", "anchor-entity": "links",
    "hub-spoke-gap": "links", "anchor-flow": "links",
    # Item 136q, so 145 can read it through. Structural, not the
    # brief-only `hub-spoke-gap` beside it: this one compares the
    # record's entity list against the initial-HTML anchor graph.
    "hub-unlinked": "links",
    # Item 136q: the link surface after rendering. (`js-rendering`, which
    # asked whether the page renders at all, retired at item 165.)
    "links-behind-js": "crawl",
    # Item 165: the head elements a crawler reads, differing between the
    # served head and the rendered one. Crawl's, not Mobile's - only the
    # viewport tag's own diff is Mobile's.
    "head-divergent": "crawl",
    # Item 151: the documents a phone and Googlebot-smartphone are served,
    # against desktop's. Crawl's: a divergence is an indexability failure
    # under mobile-first, which item 147 assigned to Crawl and Indexability.
    "mobile-parity": "crawl", "mobile-parity-size": "crawl", "bot-parity": "crawl",
    # crawl
    "robots-missing": "crawl", "sitemap-missing": "crawl",
    "sitemap-coverage": "crawl",
    # `unreachable` + its scope-guarded companion took declared-but-not-reached
    # from `sitemap-coverage` (brief v18 step AZ).
    "unreachable": "crawl", "unreachable-not-assessed": "crawl",
    # Crawl & sitemaps (brief v18 step AZ).
    "sitemap-invalid": "crawl", "sitemap-lastmod-stale": "crawl",
    "sitemap-404s": "crawl", "sitemap-noindex": "crawl",
    "sitemap-regression": "crawl",
    # Body text present only after JavaScript (brief v18 step AZ); the link half
    # of crawl.md's render-only stays with `links-behind-js` above.
    "render-only": "crawl",
    # crawl.md's brief-only checks (item 137): the two analysis checks and the
    # HELD server-refusal check. Categorised so they render on Crawl and are
    # costed (via TEC.BRIEF_ONLY_CHECKS) as model, though no sweep emits them.
    "crawl-budget-waste": "crawl", "render-policy": "crawl",
    "ua-server-refusal": "crawl",
    "http-status-error": "crawl",
    "redirect-chain": "crawl",
    # speed
    # All three Core Web Vitals, in both bands that are worth saying. The
    # module used to emit only `lcp-poor`; CrUX was returning INP and CLS on
    # every audit and they were dropped unread.
    "lcp-poor": "speed", "lcp-needs-improvement": "speed",
    "inp-poor": "speed", "inp-needs-improvement": "speed",
    "cls-poor": "speed", "cls-needs-improvement": "speed",
    # `page-weight` stays: the trace emits it as total transfer over budget.
    # `slow-response` and `caching-headers` are retired (migration 0054).
    "cwv-not-assessed": "speed", "page-weight": "speed",
    # All three states of the third-party script check are filed together:
    # "carries them", "read and carries none", and "could not be read". The
    # third is a category member in its own right precisely because it must
    # not be mistaken for the second.
    # The Speed brief's checks (item 141, brief v19 step BC): thirteen the
    # browser-trace sweep raises and five the brief judges. `page-weight` and
    # `cwv-not-assessed` above are theirs too (they move to this part). All
    # filed on `speed`, the part they write to.
    "lcp-slow": "speed", "cls-high": "speed", "inp-long-tasks": "speed",
    "ttfb-slow": "speed", "render-blocking": "speed", "unused-css-js": "speed",
    "uncompressed": "speed", "no-cache-headers": "speed", "unminified": "speed",
    "third-party-weight": "speed", "font-blocking": "speed",
    "critical-path": "speed", "lcp-cause": "speed", "cls-cause": "speed",
    "inp-cause": "speed", "third-party-policy": "speed",
    # Security & transport, brief v20 (item 143 step BD): the 56 SEC checks
    # `security.md` registers. `not-https` and `security-headers` were here and
    # were purged with their findings (migration 0056).
    "tls-legacy": "security",
    "cert-chain": "security",
    "cert-san": "security",
    "cert-key": "security",
    "http-redirect": "security",
    "mixed-content": "security",
    "http2-absent": "security",
    "hsts": "security",
    "csp-absent": "security",
    "csp-weak": "security",
    "xcto": "security",
    "referrer-policy": "security",
    "permissions-policy": "security",
    "frame-ancestors": "security",
    "cross-origin-policies": "security",
    "cors-permissive": "security",
    "cookie-flags": "security",
    "cache-authenticated": "security",
    "deprecated-header": "security",
    "version-banner": "security",
    "cms-fingerprint": "security",
    "exposed-file": "security",
    "directory-listing": "security",
    "error-leak": "security",
    "html-comment-leak": "security",
    "cms-xmlrpc": "security",
    "cms-user-enumeration": "security",
    "cms-login-exposed": "security",
    "cms-registration-open": "security",
    "cms-file-editor": "security",
    "cms-component-drift": "security",
    "spf": "security",
    "dmarc": "security",
    "dkim": "security",
    "caa": "security",
    "dnssec": "security",
    "dangling-cname": "security",
    "script-inventory": "security",
    "obfuscated-js": "security",
    "hidden-content": "security",
    "cloaking": "security",
    "cross-origin-form": "security",
    "sri-missing": "security",
    "trackers-before-consent": "security",
    "reputation": "security",
    "open-ports": "security",
    "origin-exposed": "security",
    "admin-hostnames": "security",
    "security-txt": "security",
    "privacy-policy-match": "security",
    "compromise-triage": "security",
    "csp-policy": "security",
    "header-deploy-risk": "security",
    "hsts-rollout": "security",
    "cms-abandoned-plugins": "security",
    "platform-limits": "security",
    # mobile
    # Mobile, brief v20 (item 147). `mobile-viewport` is now
    # `viewport-missing`; the other fourteen are new. All fifteen file under
    # `mobile`, which is a TEC category already (decision A option 1: the ids
    # take the TEC prefix rather than inventing a MOB dimension).
    "viewport-missing": "mobile",
    "zoom-suppressed": "mobile",
    "viewport-width": "mobile",
    "viewport-scale": "mobile",
    "viewport-duplicate": "mobile",
    "viewport-legacy": "mobile",
    "viewport-injected": "mobile",
    "viewport-divergent": "mobile",
    "horizontal-overflow": "mobile",
    "tap-target": "mobile",
    "viewport-units": "mobile",
    "viewport-source": "mobile",
    "viewport-late": "mobile",
    "viewport-keyboard": "mobile",
    "safe-area": "mobile",
    # International, brief v20 (item 148). Every one is brief-only: `intl` is
    # ANALYSIS_ONLY and no sweep raises any of them, so `check_costs()` prices
    # them `model` off `checks.LABEL_ONLY_REGISTRIES`.
    "hreflang-missing": "intl",
    "hreflang-reciprocity": "intl",
    "hreflang-self": "intl",
    "hreflang-x-default": "intl",
    "hreflang-code": "intl",
    "hreflang-target": "intl",
    "hreflang-method-mixed": "intl",
    "hreflang-sitemap-conflict": "intl",
    "locale-redirect": "intl",
    "architecture": "intl",
    "consolidation": "intl",
    # off-site
    "backlinks-not-assessed": "backlinks", "low-referring-domains": "backlinks",
    "toxic-anchor-pattern": "backlinks", "anchor-overoptimisation": "backlinks",
    "domain-authority-reported": "backlinks",
    "referring-domains-reported": "backlinks",
    "nap-missing": "local", "nap-inconsistent": "local",
    "localbusiness-schema-missing": "local", "opening-hours-missing": "local",
    "thin-location-page": "local",
    # Crawl, and now scored there too. The 2026-09-09 split filed this under
    # Crawl while keeping the finding on `AIS` (file by cause, score by
    # consequence); item 137 (brief v18 step AZ) completed the re-home — the
    # operator moved the weight, so the finding is `TEC` now and both fields
    # agree it is a crawl-access rule. The category never changed; the
    # dimension did, carried by migration 0048.
    "ai-crawler-blocked": "crawl", "llms-txt-missing": "ai-surface",
    "poor-extractability": "ai-surface",
    "extractability-not-assessed": "ai-surface",
    "edge-blocks-ai-ua": "ai-surface",
    # The rest of item 145 BG's free checks.
    "ai-crawler-allowed-unstated": "ai-surface", "noai-meta": "ai-surface",
    "ua-sensitive": "ai-surface", "content-behind-js": "ai-surface",
    "llms-txt-stale": "ai-surface", "entity-unresolvable": "ai-surface",
    "entity-unnamed": "ai-surface", "ai-experience-unmeasured": "ai-surface",
    # the engine's own notes about how it ran
    "adaptive-escalation": "workflow", "adaptive-no-escalation": "workflow",
}

#: Every rule axe reports arrives as `axe-<rule-id>`, and the rule set moves
#: with upstream releases, so this is a prefix rather than an enumeration.
CHECK_PREFIX_CATEGORY: tuple[tuple[str, str], ...] = (("axe-", "a11y"),)

#: Tool to the categories it investigates, most representative first.
#:
#: A tuple rather than a single value because a sweep genuinely serves
#: several: `onpage-hygiene` is the tool you run for a title problem, a
#: heading problem or a missing alt. Filing it under one category would have
#: left "Headings" with no way to act on it, which is how a category becomes
#: a dead end. The first entry is the primary — where this tool's expert
#: findings land, since those carry no usable check id.
TOOL_CATEGORIES: dict[str, tuple[str, ...]] = {
    "crawl": ("crawl",), "indexability": ("indexability",),
    "urls": ("urls",),
    # `js-rendering` retired at item 165; its successors are Crawl's.
    "https-security": ("security",), "mobile-basics": ("mobile",),
    "links": ("links",), "hreflang": ("intl",),
    # Content's four (brief v17 step AX). The four they replace are still
    # listed: the brief retires them after the new ones run clean on
    # Birch, and no run has been made.
    "content-coverage": ("content",), "content-substance": ("content",),
    "content-cannibalisation": ("content",), "content-benchmark": ("content",),
    "migration-redirects": ("crawl",),
    "images": ("images",),
    "page-advisor": ("title-desc", "headings", "content"),
    "a11y-sweep": ("a11y",),
    "schema-validation": ("schema",), "schema-auditor": ("schema",),
    "content-signals": ("content",), "content-brief": ("content",),
    "core-web-vitals": ("speed",),
    # `render-blocking` the TOOL is retired (item 141 step 3a). The
    # `render-blocking` CHECK is alive and is one of the thirteen the trace
    # raises -- it is in CHECK_CATEGORY above and must stay there. One id, two
    # things, and only one of them went.
    "ai-access": ("ai-surface",), "extractability": ("ai-surface", "content"),
    # `entity-graph` and `llms-txt-builder` are retired: the AI surface
    # brief carries their work (item 145).
    "citation-readiness": ("ai-surface",),
    "ai-surface": ("ai-surface",),
    "local-signals": ("local",), "gbp-audit": ("local",),
    "citations-nap": ("local",), "review-signals": ("local",),
    "backlink-profile": ("backlinks",), "link-gap": ("backlinks",),
    "disavow-review": ("backlinks",),
    # Item 238: no tool is placed under "Prioritise & report" any more. `plan`
    # writes the front of the client report and no part page (brief v18 step
    # AY); its one door is Reports' "Generate". The four planned tools that
    # stood here - prioritisation, reporting, regression-monitoring,
    # measurement-validation - have no prompt; they stay on the playbook's
    # planned list, and nothing captions them "runs in every audit".
}

# Brief v10 step AD: a brief writes to one part, and the part is the one
# its prompt's header names. The entries above stand for the sweeps and
# the planned tools, which have no prompt file; every brief's entry is
# overlaid from its header here, so the tuple's "first is primary" rule
# and the header agree by construction. The plan's header says `report`,
# which is partless: it writes the document, not a section of the site, and
# so is placed under no part (item 238).
from clauditseo import briefs as _briefs  # noqa: E402  (after CATEGORIES, which it validates against)

TOOL_CATEGORIES.update({
    tool: (part,) for tool, part in _briefs.brief_parts().items()
    if part not in _briefs.PARTLESS})

# Item 238: a check a brief declares belongs to the brief's part, where the
# register above does not already place it. With "Prioritise & report" off
# the screen the catch-all is no longer somewhere a finding can be seen, and
# the test that holds `categorise()` to the engine's own notes found ten AI
# surface analysis checks - `id-page-absent` among them - filed there.
for _brief in _briefs.catalogue():
    if _brief.part in _briefs.PARTLESS:
        continue
    for _check in _brief.checks:
        _bare = _check.split("/")[-1]
        if _bare not in CHECK_CATEGORY and _check not in CHECK_CATEGORY:
            CHECK_CATEGORY[_bare] = _brief.part


#: The tools placed under no part, by the operator's ruling in item 238:
#: `plan` writes the client report's front (its door is Reports' "Generate"),
#: and the other four are planned tools with no prompt, kept on the playbook's
#: planned list. Named, so "every playbook tool has a category" can say which
#: ones deliberately have none rather than lose the check.
UNPLACED_TOOLS = frozenset({"plan", "prioritisation", "reporting",
                            "regression-monitoring", "measurement-validation"})


#: Which specialist judges a given check (FEATURES.md F-02).
#:
#: `TOOL_CATEGORIES` maps a tool to the categories it can act on. Nothing
#: mapped a *check* to the specialist that judges it, so a findings row had no
#: way to offer "ask the specialist about this one".
#:
#: Partial on purpose, and that is the feature. A check with no specialist gets
#: no control at all — an offer that ran the wrong tool would be worse than
#: silence, because the operator would read a real judgement about something
#: other than what they clicked. Most checks are here: site-level ones
#: (`robots-missing`, `not-https`) have no page to run a page specialist
#: against, and `localbusiness-schema-missing` is filed under `local`, which
#: neither page panel covers.
#:
#: Every value must be a `PAGE_PANELS` entry whose `TOOL_CATEGORIES` include
#: that check's own category. `test_every_specialist_covers_the_category_of_
#: the_check_it_claims` holds that true, so a tool losing a category cannot
#: leave a row pointing at a specialist that no longer judges it.
CHECK_SPECIALISTS: dict[str, str] = {
    "title-missing": "page-advisor", "title-duplicate": "page-advisor",
    "title-length": "page-advisor", "meta-desc-missing": "page-advisor",
    "meta-desc-length": "page-advisor",
    "meta-desc-duplicate": "page-advisor",
    "h1-missing": "page-advisor", "h1-multiple": "page-advisor",
    "heading-skip": "page-advisor",
    "thin-content": "page-advisor", "low-text-ratio": "page-advisor",
    "readability-long-sentences": "page-advisor",
    "template-only-page": "page-advisor", "duplicate-content": "page-advisor",
    "jsonld-invalid": "schema-auditor",
}


def specialist_for(check_id: str) -> str | None:
    """The tool that judges this check, or None if nothing does.

    None is an answer, not a gap: the caller offers no control for it.
    """
    return CHECK_SPECIALISTS.get(check_id)


#: Which fields of a page advisory belong to which category (FEATURES.md F-03).
#:
#: The advisor answers its whole remit in one judgement — H1, title tag, meta
#: description, answer line and alternatives — and an operator reading the
#: Headings section wants the heading part of it. These are the views.
#:
#: Narrowing happens at the boundary, not in the prompt. One judgement serves
#: every section, so a scoped read costs nothing once any read has run; a
#: scoped prompt would fragment the cache by section and charge again for each.
#: The trade-off is that the model still produces the full remit, so scoping
#: saves reading, not tokens — said plainly here so nobody later "optimises"
#: it into a second call.
#:
#: Declared rather than computed, the same reason `DIMENSION_CATEGORIES` is:
#: `page-advisor` gaining or losing a category must be a test failure, not a
#: section that silently offers nothing.
ADVICE_SCOPES: dict[str, tuple[str, ...]] = {
    "title-desc": ("title_tag", "meta_description"),
    "headings": ("recommended_h1", "alternatives", "answer_line"),
    "content": ("answer_line", "keyword_intent", "site_role"),
}

#: Kept in every narrowed view, whatever the scope.
#:
#: These are what a recommendation rests on and the reasons it might be wrong.
#: A view that dropped them would hand back a tidier answer with its caveats
#: removed, which is the provenance invariant broken by the feature meant to
#: make the answer easier to read.
#:
#: UX-26, raised in report 033 and carried by every report since. The rule
#: above was right and this tuple did not hold to it: the two fields the
#: system prompt reserves *specifically* for stating a limitation were both
#: outside it. `compliance_notes` — "medical, financial or safety outcome
#: claims" (`page_advisor.py:60-75`) — was dropped by all three scopes, and
#: `keyword_intent`, which carries `unverified_flags` for brand-coined
#: categories, slogans and trademarked phrases, was in `content` alone, so a
#: `title-desc` or `headings` answer recommended adopting page wording with
#: the flag saying that wording is unverified removed. On a product whose
#: named primary users audit lender and finance sites.
#:
#: `keyword_intent` rides along whole because `scope_advice` filters top-level
#: keys and the caveat is a field inside it. That hands the reader three more
#: lines than the narrowing strictly needs, which is the right way for this to
#: be wrong: the stated trade is that scoping "saves reading, not tokens", so
#: a caveat costs reading and its absence costs correctness.
#:
#: `schema_notes` is deliberately NOT here, and the omission is the point of
#: naming it: it is guidance, not a limitation on a recommendation, so adding
#: it would widen the rule from "the reasons this might be wrong" to "things
#: it would be nice to keep" — at which point the tuple no longer says
#: anything and the next field is added by whoever asks loudest.
ADVICE_ALWAYS: tuple[str, ...] = ("assumptions", "conflicts", "triage",
                                  "page_read", "compliance_notes",
                                  "keyword_intent")


#: Tools that analyse ONE page rather than the site, and are not briefs.
#:
#: They have their own endpoints and their own panels, and both spend model
#: tokens. Named here because they are the only entries in `TOOL_CATEGORIES`
#: that a section can genuinely act on beyond its briefs — everything else in
#: a category's tool list either already appears as a read/run control or is
#: a sweep with nothing to start.
PAGE_PANELS: tuple[str, ...] = ("page-advisor", "schema-auditor")


#: Which categories each dimension's sweep can raise findings in.
#:
#: The launcher picks dimensions; this screen groups by category; and the two
#: are not the same granularity. ONP alone covers four categories, so "audit
#: Images" is not a thing the engine can be asked for — a picker that implied
#: otherwise would be offering a control that cannot exist.
#:
#: Declared rather than computed, so a category quietly losing its last check
#: is a test failure rather than a silent disappearance from the launcher.
#: `test_dimension_categories_matches_what_the_modules_emit` holds it true.
DIMENSION_CATEGORIES: dict[str, tuple[str, ...]] = {
    "ONP": ("title-desc", "headings", "images", "schema", "indexability"),
    "CNT": ("content",),
    "A11Y": ("a11y",),
    # `security` left TEC for its own dimension at item 143 step BD.
    "TEC": ("indexability", "crawl", "mobile", "urls"),
    "PRF": ("speed",),
    "OFP": ("backlinks",),
    "LOC": ("local",),
    # `ai-crawler-blocked` was re-homed AIS→TEC at item 137 (brief v18 step
    # AZ), so AIS no longer raises into Crawl — its checks are all AI-surface.
    # TEC already declares `crawl`, which is where the check now scores.
    "AIS": ("ai-surface",),
    "LNK": ("links",),
    "SEC": ("security",),
}

#: Categories no sweep populates. They exist because an expert analysis fills
#: them — site architecture, hreflang — and nothing else does.
#:
#: Worth stating outright on the launcher: running every dimension leaves
#: these two untouched, so a zero beside them means "no sweep covers this",
#: not "checked and clean". That is the same distinction the hollow dot draws
#: on the client screen, and the launcher is where it costs money to get
#: wrong.
#:
#: **`urls` was the third and left on 29 August 2026**, when TEC gained
#: `internal-link-tracking-params`. It is the shape this tuple is for: a
#: category is analysis-only until a sweep covers it, and the moment one does
#: the launcher's sentence about it becomes false. Held that way rather than
#: by care — `test_analysis_only_categories_really_have_no_sweep` derives the
#: covered set from `DIMENSION_CATEGORIES` and fails if the two disagree.
#: **`links` was the fourth and left on 6 September 2026**, when the LNK
#: dimension landed with eight checks the sweep answers (brief v17 step
#: AW). What was left of the category before that was a name, a block of
#: suggestions on the Analyse pane that no check and no record row ever
#: saw, and a brief.
ANALYSIS_ONLY: tuple[str, ...] = ("intl",)


def categories_for_dimension(code: str) -> list[str]:
    """Human labels for what a dimension's sweep refreshes."""
    return [BY_KEY[k].label for k in DIMENSION_CATEGORIES.get(code, ())
            if k in BY_KEY]


def refresh_for(key: str) -> dict | None:
    """The smallest run the engine can actually be asked for that refreshes
    this section, and what else comes with it.

    The section screen groups by category and the engine is asked in
    dimensions, so "refresh Headings" has no unit to be expressed in — the
    comment on `DIMENSION_CATEGORIES` above states the constraint: "audit
    Images is not a thing the engine can be asked for". `FEATURES.md` F-06
    is the entry that would make the unit fine. This is the fallback F-06
    names and sets aside: the coarse control, labelled honestly, so a section
    offers the smallest refresh that exists rather than none at all.

    `also` is built from `categories_for_dimension`, not from a second table,
    so a module gaining or losing a category changes what the control says it
    will touch in the same edit. It is the *cost* half of the offer and the
    reason this returns two things rather than a code: an operator standing in
    Headings is being told that four other sections move with it, before
    clicking rather than after.

    **Smallest, where more than one dimension covers the section.** The
    honest offer is the one that disturbs least, so the covering dimension
    with the fewest categories wins, the code breaking a tie so the answer is
    stable rather than dependent on dict order. Both would refresh the
    section; only one is the smallest thing that would.

    `indexability` is the only section two dimensions cover, and since TEC
    gained `urls` on 29 August 2026 the two are the same size — ONP five,
    TEC five — so the tie-break decides it and the offer is ONP. That is a
    real consequence of adding a check, not a detail: the Indexability
    section's refresh now names four other sections it moves where it named
    three. Nothing is claimed falsely — `also` is computed from the winning
    dimension and displayed — but the control disturbs more than it did, and
    the operator is told so before pressing rather than after.

    None is an answer, not a gap, and it is the `ANALYSIS_ONLY` case: no sweep
    populates Links on the page or International, so no run refreshes them and
    the section offers no control. Same rule as `specialist_for` — an offer
    that ran the wrong thing is worse than silence.

    **`per_page` says whether a page is a unit this offer can be narrowed to**
    (UX-39). F-06 lets the same control ask for `(url, dims)` once a page is
    named, and for one dimension that narrowing is a false claim: OFP's five
    checks all read the domain's backlink profile, so re-reading one page
    cannot change what it measures.

    Read from the engine's own `measured_per_page` declaration — the module
    stating, in its own file, whether any of its findings can be measured
    against a single page. **Not from `Category.group`**, which was the
    obvious rule and is the wrong one: AI surface and Local & citations both
    sit `beyond the site` and both emit findings against page URLs, and
    Speed, Mobile, Security and Indexability are all measurable against one
    page while sitting outside `on the page` as a heading. Grouping would
    withdraw six working controls to withdraw the one that does not work.

    **And not from `coverage_from_crawl`, which is what this read until
    Q-17.** That declaration answers a neighbouring question — can fetching
    more pages raise this dimension's coverage — and OFP is the only member
    of either set, so the proxy gave the right answer for the wrong reason
    and would have gone on giving it until a dimension was crawl-blind but
    page-capable, or the reverse. The two facts are now declared separately
    and `tests/test_page_scope_is_declared.py` checks each module's against
    its own source.
    """
    covering = [code for code, cats in DIMENSION_CATEGORIES.items()
                if key in cats]
    if not covering or key not in BY_KEY:
        return None
    code = min(covering, key=lambda c: (len(DIMENSION_CATEGORIES[c]), c))
    label = BY_KEY[key].label
    return {"dimension": code,
            "also": [l for l in categories_for_dimension(code) if l != label],
            "per_page": code not in _page_blind()}


def _page_blind() -> frozenset[str]:
    """Dimension codes no single-page re-read can move, from the engine.

    Imported inside the call rather than at module scope: importing
    `clauditseo.modules` is what registers the dimensions, and against an
    empty registry `page_blind_dims()` answers "every dimension is
    page-capable" — a wrong answer indistinguishable from a right one, which
    is the empty-result shape CQ-191 records. `clauditseo.anatomy` is
    otherwise a pure table and is imported by the analysts and the
    persistence layer, so it keeps no engine import at module scope.
    """
    import clauditseo.modules  # noqa: F401  (registers the dimensions)
    from clauditseo.engine import registry

    return frozenset(registry.page_blind_dims())


def categorise(check_id: str, dimension: str) -> str:
    """Which category a finding belongs to.

    Check id first, for every finding. It is the only thing that says what a
    finding is *about*, and it is the only way to split a sweep that spans
    categories.

    The tool is a fallback, used when an expert brief invents a check id we
    do not know. Expert findings used to be placed by tool unconditionally,
    which quietly misfiled any brief whose tool spans categories: the
    `onpage-hygiene` brief covers titles, headings and images, so its
    model-written `img-alt-missing` landed under "Title & description" —
    beside the title facts, describing images.

    Anything unknown lands in `workflow` rather than being dropped — losing a
    finding is worse than filing it oddly — and the completeness test exists
    so that never happens quietly.
    """
    # The dimension's own answer first (brief v17 step AW): one check id
    # can belong to two dimensions and mean two different things, and the
    # bare key cannot hold both. Only the collisions carry a qualified
    # entry; everything else is keyed by the id alone as before.
    qualified = CHECK_CATEGORY.get(f"{dimension}/{check_id}")
    if qualified:
        return qualified
    if check_id in CHECK_CATEGORY:
        return CHECK_CATEGORY[check_id]
    for prefix, cat in CHECK_PREFIX_CATEGORY:
        if check_id.startswith(prefix):
            return cat
    if dimension.startswith("EXP:"):
        cats = TOOL_CATEGORIES.get(dimension[4:])
        return cats[0] if cats else "workflow"
    return "workflow"


def tools_for(category: str) -> list[str]:
    """Which tools investigate this category, for the "run one of these"
    control beside it. Ordered so a tool that is mostly about this category
    comes before one that merely touches it."""
    return sorted((t for t, cats in TOOL_CATEGORIES.items() if category in cats),
                  key=lambda t: (TOOL_CATEGORIES[t].index(category), t))


def jaccard(a: set[str], b: set[str]) -> float:
    """How much two categories overlap, as a share of their union.

    Deliberately not containment. Every small category on a templated site is
    wholly inside the big one — twelve of twelve `title-length` pages sit in
    the same hundred pages that have a heading problem — so containment
    lights up almost everything and says nothing. Mutual overlap separates
    "the same underlying problem" from "a smaller problem that happens to
    live on some of the same pages".
    """
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


#: Above this, two categories are called related. Chosen from real data: the
#: pairs that share a template score 0.99–1.00, while a small category
#: sitting inside a big one scores 0.03–0.13. Anywhere in between would do;
#: there is nothing near the line.
RELATED_AT = 0.5


def shared_cause(pages_by_category: dict[str, set[str]],
                 totals: dict[str, int], grand_total: int,
                 threshold: float = RELATED_AT) -> dict | None:
    """The largest group of categories that afflict the same pages.

    This is the most useful sentence the product produces — "four categories,
    the same 20 pages, 93% of open findings, usually one template rather than
    four problems" — and it turns an unusable list into a quotable scope of
    work.

    It lived only in the dashboard, computed in TypeScript from the `related`
    map. The client report, which is the artefact an auditor actually sends,
    could not say it. Moved here so both read the same computation: a screen
    and a report that disagree about the headline number is worse than a
    report that omits it.

    Returns None when nothing clusters — no cluster is a real answer, and
    inventing a weak one would put a claim in a client report that the data
    does not carry.
    """
    clusters = []
    for seed in pages_by_category:
        others = related(pages_by_category, seed, threshold)
        if not others:
            continue
        keys = [seed, *others]
        findings = sum(totals.get(k, 0) for k in keys)
        pages = max((len(pages_by_category.get(k) or ()) for k in keys),
                    default=0)
        clusters.append({"keys": keys, "findings": findings, "pages": pages})
    if not clusters:
        return None
    # Widest first, then largest: the cluster worth naming is the one that
    # accounts for the most work, not the one that sorts first.
    clusters.sort(key=lambda c: (-len(c["keys"]), -c["findings"]))
    top = clusters[0]
    if top["findings"] < 2:
        return None
    return {
        **top,
        "labels": [BY_KEY[k].label if k in BY_KEY else k for k in top["keys"]],
        "share": round(top["findings"] / grand_total, 3) if grand_total else 0.0,
    }


def related(pages_by_category: dict[str, set[str]], selected: str,
            threshold: float = RELATED_AT) -> dict[str, dict]:
    """Categories sharing enough pages with `selected` to be worth flagging
    as one likely cause. Returns the score and the shared count, because a
    colour on its own does not tell an operator what to do."""
    target = pages_by_category.get(selected) or set()
    out: dict[str, dict] = {}
    if not target:
        return out
    for key, pages in pages_by_category.items():
        if key == selected or not pages:
            continue
        score = jaccard(target, pages)
        if score >= threshold:
            out[key] = {"jaccard": round(score, 3),
                        "shared": len(target & pages),
                        "of_selected": len(target)}
    return out
