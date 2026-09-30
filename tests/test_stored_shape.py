"""A run's stored shape is versioned, and this fails when it moves silently.

`audit_runs.engine_version` has existed since the first migration. It sat at
0.3.0 for six days while coverage, per-check page counts, crawl scope, run
kind and per-run expert reports were all added, so sixteen runs of materially
different shapes all claimed the same version.

That is not a filing complaint. A reader cannot ask "does this run have that
field?" of a version that never moves, so it guesses instead — and a guessed
value is indistinguishable from a measured one. `biggest_gains` read
`stats.get("pages", stats.get("affected"))`, so a run that never recorded a
page count silently reported its finding count and a client-facing table read
"21 of 20 pages". Every fallback deleted alongside this test was the same
shape of mistake.

So the shape is pinned here, per version. Adding a key is not a failure to be
suppressed — it is the moment to decide whether readers of older runs still
work, and to bump ENGINE_VERSION so they can tell. Update EXPECTED and the
version together, in the commit that changes the shape.

Deliberately cheap. It audits a two-page fixture served from 127.0.0.1 — no
external site, no crawl budget, no model tokens — because a shape guard has to
run on every commit and nothing about the shape needs a real site to observe.
"""

from __future__ import annotations

from pathlib import Path

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo import ENGINE_VERSION
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite

#: Two pages, one link, deliberate defects — enough to produce a per-check
#: detail block and a site-level finding without fetching anything real.
HOME = ("<html lang=en><head><title>t</title></head><body><main><h1>h</h1>"
        "<h4>skipped</h4><img src=/i.png><p>Short.</p>"
        "<a href='/two'>two</a></main></body></html>")
TWO = ("<html lang=en><head><title>t</title></head><body><main><h1>h</h1>"
       "<img src=/j.png><p>Short.</p></main></body></html>")
ROUTES = {"/robots.txt": (200, {"Content-Type": "text/plain"},
                          "User-agent: *\nAllow: /\n"),
          "/": (200, {}, HOME), "/two": (200, {}, TWO)}

FAST = TierBudget(max_pages=5, request_timeout_s=5, wall_clock_s=30, delay_s=0)

#: The stored shape at ENGINE_VERSION. Keys only — values move with the site,
#: shapes move with the code, and only the second is a compatibility event.
EXPECTED: dict[str, dict[str, set[str]]] = {
    # 0.5.0 changed how two dimensions score, not what a run stores, so the
    # shape is 0.4.0's. Recorded rather than aliased: the next change should
    # diff against what this version actually writes, and a chain of "same as
    # the one before" is how a shape guard stops guarding.
    # 0.6.0 adds `scope` to what `get_run` assembles: pages fetched, URLs
    # blocked by robots.txt, and whether the crawl stopped early. The counts
    # were already stored in `crawl_evidence`; the assembler dropped them, so
    # no document could say a crawl had fetched nothing. A reader of a 0.5.0
    # run sees `None` — not recorded — which must never be read as zero.
    "0.6.0": {
        # `get_run`'s shape, which is what every reader actually sees — the
        # stored columns plus what it assembles (findings, costs,
        # has_evidence, scope). Pinning the table alone would miss a
        # reader-visible change made in the assembler.
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "progress", "scope", "site_id", "started_at", "status",
            "subscores", "tier",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        # Read back by briefs months after the crawl, so a key quietly
        # appearing or going is what puts a table of empty columns in front
        # of a client with no explanation.
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "meta_description", "meta_robots", "nap_mentions", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.7.0 does not add a column. It changes what a stored value MEANS: a
    # crawl that obtained no eligible page now stores as 'blocked', so
    # 'complete' at 0.7.0 guarantees at least one page was read and
    # 'complete' at 0.6.0 does not. A reader comparing the two without
    # knowing that compares a measured site against one that was never
    # fetched — which is the class of mistake this constant exists to make
    # answerable. Recorded in full rather than aliased to 0.6.0, for the
    # reason stated above 0.5.0: a chain of "same as the one before" is how
    # a shape guard stops guarding.
    # 0.10.0 changes which URLs are fetched, not what a run stores, so the
    # shape is 0.9.0's — spelled out in full rather than aliased, for the
    # reason given against 0.5.0 above.
    #
    # `normalise_url` now strips tracking parameters, so an ad-tagged link and
    # the clean link beside it are one entry in the frontier and one row in the
    # page inventory. Measured over stored run
    # `fe97cc61ab52468ebb0c4bff36ac69f7`: 235 fetched URLs, 225 distinct once
    # stripped, every one of the ten collapsing onto a base the same crawl
    # already held.
    #
    # A link record inside `evidence_page["links"]` gained an `href` — the
    # link as the markup wrote it, kept because `url` can no longer carry a
    # tracking parameter and TEC's `internal-link-tracking-params` reports
    # exactly that spelling. It does not appear below because this guard pins
    # the keys of a page record and not of the link dicts inside it; that is
    # a real gap in the guard rather than a decision, and it is why the
    # version moved on the strip rather than on the field.
    #
    # The shape being identical is again the point, and again why the version
    # had to move. Nothing about a stored row says which normalisation
    # produced it, so `engine_version` is the only thing distinguishing a
    # `pages_fetched` of 225 that means "ten spellings folded" from one that
    # means "the site lost ten pages" — and that column is the first term of
    # the comparability key `site_trend` builds in
    # `clauditseo/persistence/runs.py`, so a trend across the boundary is
    # scored as two frames rather than one.
    # 0.11.0 adds `scan_scope`, `scan_depth` and `scan_url`: what the run WAS,
    # in the words it was chosen with. A run row could previously only describe
    # itself as "T1 — TEC, ONP, A11Y…", which is the engine's vocabulary and
    # answers neither of the questions anyone asks first — how much of the site
    # was this, and how hard did it look.
    #
    # A reader of any earlier run sees `None` on all three, and `None` must be
    # rendered as *not recorded*, never as a scope. Those runs were not chosen
    # on these axes; the screen falls back to the tier line, which is what they
    # were actually described by at the time.
    #
    # The `scan_` prefix is not decoration. `scope` is already in this set,
    # assembled since 0.6.0 and meaning the CRAWL's scope — pages fetched, URLs
    # blocked. An unprefixed column would have shadowed it in the assembled row
    # and this guard is what caught that before it shipped.
    "0.11.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            # Derived at read time from kind, scan_scope and crawled_paths
            # (brief v6 step V2): the server's classification, present on every
            # row whatever its age.
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "meta_description", "meta_robots", "nap_mentions", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.13.0 stores an image inventory per page (brief v15 step AQ):
    # `image_inventory` is one record per image-bearing surface, carrying
    # what that image's own markup says - format, declared dimensions,
    # loading, fetchpriority, decoding, srcset, sizes, alt, the link around
    # it, the region it sits in, its caption and the words beside it.
    #
    # What is deliberately absent is as much of the shape as what is
    # present. The width an image renders at, its file weight, whether it
    # is the LCP candidate and any CSS aspect-ratio need a browser or a
    # fetch, and this crawl does neither. A reader of any run, old or new,
    # must not substitute a number for them: the Images brief is handed
    # `[not measured]` and its own rule turns that into a held row naming
    # the field. A reader of a pre-0.13.0 page sees no `image_inventory`
    # at all and has `images` - the (src, alt) pairs - and nothing else.
    # 0.12.0 records each page's heading outline with its region and the
    # words after every heading (brief v11 step AJ): `outline` is a list of
    # [level, text, in_main, next_text] and `main_region` says how the main
    # region was found - <main>, role=main, <article>, or "whole body". A
    # reader of an earlier page sees neither key, and the Headings brief's
    # context says so under its assumptions rather than guessing a region.
    # 0.14.0 records every structured-data block on a page as parsed (brief
    # v16 step AS): `schema_inventory` is one row per node - format, @type,
    # @id, whether it parsed, which script carried it, and its properties
    # flattened two levels - and `profile_links` is the page's links to
    # profile hosts. A block that does not parse is kept with
    # `parse_ok: false` and its error, because that *is*
    # `schema-invalid-json` and dropping it would delete the finding.
    #
    # **Two things are absent and the absence is the point.** Microdata and
    # RDFa are not parsed - this reader takes
    # `<script type="application/ld+json">` and nothing else - so a page
    # whose markup is Microdata stores no blocks, which must never be read
    # as "this page has no structured data". And `profile_links` is
    # candidates: whether the entity *controls* a profile is a fact about
    # ownership no crawl can see, and it is the site record's
    # `sameas_sources` that answers it.
    #
    # A reader of a pre-0.14.0 page sees neither key and has `schema_types`
    # and `jsonld_blocks` - a list of type names and a count - which is
    # what the Structured data checks had to work from before this.
    "0.14.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    "0.16.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash", "opening",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            # The blocks as served, which the Structured data picture is
            # built from (brief v16a step AT-b). `jsonld_blocks` beside it
            # is still the count and still means what it meant.
            "jsonld_raw",
            "outline", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.17.0 adds `has_post_form` to every page record (brief v16h): whether
    # the page carries a `<form method=post>`. The headers grid names the odd
    # route and, where that route takes a customer's details, says it is the
    # one to fix first - and nothing recorded which routes those were. A
    # reader of an older run sees the key absent, which it must read as "not
    # known" rather than as "not a form": every page on every run before this
    # would otherwise look like a route that takes no details.
    #
    # 0.16.0 is not pinned separately. It moved what a finding's `evidence`
    # carries (136j's `instances[]` and `count`), which is inside a JSON
    # column rather than the page record this guard walks, so the shape it
    # measures did not change. Recorded rather than aliased, for the reason
    # stated above 0.5.0.
    # 0.18.0 adds `redirect_statuses` to every page record (item 137, FEATURES
    # F-13): the status code of each redirect hop, parallel to `redirect_chain`,
    # which is what lets `redirect-temporary` tell a 302 from a 301. A reader of
    # an older run sees the key absent, which it must read as "not captured" —
    # never substitute a status for it, and `redirect-temporary` simply does not
    # fire on such a run. The list of URLs `redirect_chain` carries is unchanged,
    # so every reader of that stays as it was.
    # 0.19.0 adds `perf` to every page record (item 141, brief v19 step BC): the
    # performance trace `clauditseo.perf` takes under a fixed device profile.
    # Every record carries the key — the trace, or `{"traced": False}` where none
    # was taken. A reader of an older run sees the key absent (read as "not
    # captured", never a substituted zero); a field the browser could not supply
    # inside a trace is `"unavailable"`. This guard walks the page record's own
    # keys, so it pins that `perf` is present; the trace's nested shape is pinned
    # by `test_the_perf_trace_keeps_its_keys` beside it, the way 136j's
    # `instances[]` is pinned inside its own JSON column rather than here.
    # 0.20.0 changes only what is INSIDE `perf` -- `head_html` became
    # `head_rendered`, and `head_fetched` and `mobile_render` joined it
    # (brief 160 steps 1-3). No run column and no page key moved, so this
    # shape is 0.19.0's. The trace's own key set is guarded separately, by
    # `test_the_trace_keys_are_the_named_set` below, which is where that
    # change is pinned.
    # 0.27.0 adds the top-level `mobile_parity` evidence key (item 151); the
    # page record and run columns are 0.26.0's - spelled out in full, not
    # aliased.
    "0.27.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.26.0 reads head-divergent from the existing head pair; nothing stored
    # moves, so the shape is 0.25.0's - spelled out in full, not aliased.
    "0.26.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.25.0 reads trackers-before-consent from the existing trace and adds a
    # top-level `consent` evidence key; the page record and run columns are
    # 0.24.0's - spelled out in full, not aliased.
    "0.25.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.24.0 adds the TLS probe's ALPN and certificate-key fields, inside the
    # `transport` evidence key rather than the page record, so the shape is
    # 0.23.0's - spelled out in full, not aliased.
    "0.24.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.23.0 adds SEC collectors (item 143 step BD). The UA matrix's new
    # `bodies` sits inside the `ua_matrix` evidence key, not the page record,
    # and `access-control-allow-credentials` is a header value inside
    # `headers`, so the shape is 0.22.0's - spelled out in full, not aliased.
    "0.23.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.22.0 adds the SEC dimension (item 143 step BD): a run gains a SEC
    # subscore, but the subscore's own keys and the page record are unchanged,
    # so the shape is 0.21.0's - spelled out in full, not aliased.
    "0.22.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.21.0 moves the width `title-length` fires at (item 152), not what a run
    # stores, so the shape is 0.20.0's - spelled out in full rather than
    # aliased, for the reason given against 0.5.0 above.
    "0.21.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    "0.20.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    "0.19.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks", "perf",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    "0.18.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks",
            "redirect_chain", "redirect_statuses", "requested_url",
            "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    "0.17.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash",
            "opening", "content_type", "discovered_via", "elapsed_ms", "h1",
            "has_post_form",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks",
            # The raw blocks beside the flattened inventory, since 0.16.0
            # (brief v16a step AT-b): a graph cannot be rebuilt from two
            # levels with lists collapsed to their first member.
            "jsonld_raw", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    "0.15.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates", "content_hash", "opening",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory", "profile_links", "schema_inventory",
            "outline", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    "0.13.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "effective_scope", "site_reading",
            "started_at", "status",
            "subscores", "tier",
            "scan_scope", "scan_depth", "scan_url",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "main_region", "meta_description", "meta_robots", "nap_mentions",
            "image_inventory",
            "outline", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.9.0 changes what goes *into* `crawled_paths`, not what a run stores,
    # so the shape is 0.8.0's — spelled out rather than aliased, for the reason
    # given against 0.5.0 above.
    #
    # 0.8.0 recorded "the set of paths a run actually fetched" and built it
    # from every page object the crawler produced. A Page survives a failed
    # fetch, so a host that did not resolve was written into that set and
    # `compare_runs` counted the finding on it as re-checked. From 0.9.0 the
    # set holds eligible pages only — 200 with an HTML body — and the same
    # rule governs the `pages_fetched` in a finding's evidence and the CWV
    # call gate that spent a keyed request on the unresolvable host.
    #
    # The shape being identical is the point, and it is why the version had to
    # move: nothing about a stored row tells a reader which rule produced it,
    # so `engine_version` is the only thing that distinguishes a `crawled_paths`
    # of `[]` meaning "fetched nothing" from a pre-0.9.0 `["/"]` meaning
    # "attempted one thing, fetched nothing". Comparing runs across the
    # boundary has to read this column, not the paths.
    "0.9.0": {
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "started_at", "status",
            "subscores", "tier",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "meta_description", "meta_robots", "nap_mentions", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    # 0.8.0 adds `crawled_paths`: the set of paths a run actually fetched,
    # recorded at completion. `complete_run` always received it and dropped
    # it, so `compare_runs` had no way to ask "did this run look at that
    # page" and twice substituted worse evidence — a bare set-difference that
    # reported 352 resolutions where 5 had been re-checked, then a read of
    # `finding_states` that let a later run rewrite an earlier comparison.
    #
    # A reader of a pre-0.8.0 run sees the column absent. It must be read as
    # "scope not recorded", never as "fetched nothing": those differ, and the
    # second is the whole family of defects this column closes. Where such a
    # run stored `crawl_evidence`, the page list there is the same fact and
    # is used — that is recovering the value, not substituting another.
    "0.8.0": {
        # `get_run`'s shape, which is what every reader actually sees — the
        # stored columns plus what it assembles (findings, costs,
        # has_evidence, scope). Pinning the table alone would miss a
        # reader-visible change made in the assembler.
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "crawled_paths", "progress", "scope", "site_id",
            "started_at", "status",
            "subscores", "tier",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        # Read back by briefs months after the crawl, so a key quietly
        # appearing or going is what puts a table of empty columns in front
        # of a client with no explanation.
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "meta_description", "meta_robots", "nap_mentions", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
    "0.7.0": {
        # `get_run`'s shape, which is what every reader actually sees — the
        # stored columns plus what it assembles (findings, costs,
        # has_evidence, scope). Pinning the table alone would miss a
        # reader-visible change made in the assembler.
        "run_columns": {
            "analyst_enabled", "composite_score", "costs", "created_at",
            "created_by", "dimensions", "engine_version", "error",
            "findings", "finished_at", "has_evidence", "id", "kind",
            "progress", "scope", "site_id", "started_at", "status",
            "subscores", "tier",
        },
        "subscore": {
            "applicable", "coverage", "detail", "score", "unmeasured",
            "weight",
        },
        "subscore_detail": {
            "deduction", "eligible_pages", "finding_counts",
            "nominal_weight", "per_check",
        },
        "per_check": {"affected", "deduction", "eligible", "pages", "rate"},
        # Read back by briefs months after the crawl, so a key quietly
        # appearing or going is what puts a table of empty columns in front
        # of a client with no explanation.
        "evidence_page": {
            "a11y", "canonical", "click_depth", "content_dates",
            "content_type", "discovered_via", "elapsed_ms", "h1",
            "headers", "heading_levels", "heading_total", "headings",
            "hreflang", "image_total", "images", "jsonld_blocks", "lang",
            "link_header_canonical", "links", "local_schema",
            "meta_description", "meta_robots", "nap_mentions", "outlinks",
            "redirect_chain", "requested_url", "schema_types", "status",
            "title", "url", "viewport_tags", "word_count", "x_robots_tag",
        },
    },
}


def _audited(tmp_path):
    """One completed audit over the fixture, read back from the database."""
    fixture = FixtureSite(ROUTES).start()
    try:
        conn = connect(tmp_path / "shape.db")
        migrate(conn)
        op = repo.ensure_default_operator(conn)
        site = repo.create_site(conn, repo.create_client(conn, op, "C"),
                                fixture.base_url + "/")
        dims = ["TEC", "ONP", "A11Y", "CNT"]
        crawled = crawl(fixture.base_url + "/", Tier.T2, budget=FAST)
        result = run_audit(Site(domain=fixture.base_url + "/"), crawled, dims,
                           Tier.T2)
        run_id = runs.create_run(conn, site, dims, "T2")
        from clauditseo.crawler.evidence import snapshot
        runs.store_evidence(conn, run_id, snapshot(crawled))
        runs.complete_run(conn, run_id, result)
        return conn, runs.get_run(conn, run_id), runs.get_evidence(conn, run_id)
    finally:
        fixture.stop()


def _report(kind: str, actual: set[str], expected: set[str]) -> str:
    added = sorted(actual - expected)
    removed = sorted(expected - actual)
    return (
        f"The stored shape of {kind} changed at ENGINE_VERSION {ENGINE_VERSION}.\n"
        f"  added:   {added or '-'}\n"
        f"  removed: {removed or '-'}\n\n"
        "This is a compatibility event, not a test to silence. Decide what a\n"
        "reader of an older run should do — say the field is absent, never\n"
        "substitute another number for it — then bump ENGINE_VERSION and add\n"
        "the new shape to EXPECTED in this file, in the same commit.")


def test_engine_version_has_a_recorded_shape():
    """The guard cannot guard a version nobody described."""
    assert ENGINE_VERSION in EXPECTED, (
        f"ENGINE_VERSION is {ENGINE_VERSION} and this file does not describe "
        "it. A bump without a recorded shape leaves the next change "
        "unguarded — add the shape in the commit that bumps.")


def test_the_run_row_keeps_its_shape(tmp_path):
    _, run, _ = _audited(tmp_path)
    assert run["engine_version"] == ENGINE_VERSION, (
        "a fresh run must stamp the current version")
    expected = EXPECTED[ENGINE_VERSION]["run_columns"]
    assert set(run) == expected, _report("a run row", set(run), expected)


def test_the_subscore_keeps_its_shape(tmp_path):
    _, run, _ = _audited(tmp_path)
    shape = EXPECTED[ENGINE_VERSION]
    subs = run["subscores"]
    assert subs, "the fixture produced no subscores to check"

    for dim, sub in subs.items():
        assert set(sub) == shape["subscore"], \
            _report(f"subscore {dim}", set(sub), shape["subscore"])
        assert set(sub["detail"]) == shape["subscore_detail"], \
            _report(f"detail of {dim}", set(sub["detail"]),
                    shape["subscore_detail"])

    per_check = [(dim, check, stats)
                 for dim, sub in subs.items()
                 for check, stats in sub["detail"]["per_check"].items()]
    assert per_check, (
        "the fixture raised no per-page findings, so the per-check shape went "
        "unchecked — the guard would pass while blind")
    for dim, check, stats in per_check:
        assert set(stats) == shape["per_check"], \
            _report(f"per_check {dim}/{check}", set(stats), shape["per_check"])


def test_the_crawl_evidence_keeps_its_shape(tmp_path):
    """Briefs read this back months later; a key that quietly appears or goes
    is what puts a brief's table of empty columns in front of a client."""
    _, _, evidence = _audited(tmp_path)
    pages = evidence.get("pages") or []
    assert pages, "the fixture stored no pages"
    expected = EXPECTED[ENGINE_VERSION]["evidence_page"]
    for page in pages:
        assert set(page) == expected, \
            _report(f"evidence for {page.get('url')}", set(page), expected)


def test_the_perf_trace_keeps_its_keys():
    """The per-page `perf` trace (0.19.0, item 141 brief v19 step BC) is a dict
    inside the page record, so `test_the_crawl_evidence_keeps_its_shape` above
    pins that the `perf` KEY is present but not the trace's own shape — the
    guard walks the record's keys, not this dict's (the same blind spot 136j's
    `instances[]` has). Declared in `perf.TRACE_KEYS`/`RESOURCE_KEYS` and pinned
    here, so a field added to a trace or a resource row is a deliberate change
    to a named set rather than a silent shape drift the Speed part meets as an
    empty column."""
    from clauditseo import perf
    assert perf.TRACE_KEYS == {
        "device_profile", "ttfb_ms", "fcp_ms", "lcp", "cls", "tbt_ms",
        "long_tasks", "resources", "fonts", "head_rendered",
        "head_fetched", "mobile_render", "frames"}
    assert perf.RESOURCE_KEYS == {
        "url", "type", "bytes", "transfer", "start_ms", "duration_ms",
        "blocking", "async", "defer", "media", "discovered_by", "cache_control",
        "compression", "coverage", "whitespace_ratio"}


def test_a_page_with_no_trace_still_carries_the_perf_key(tmp_path):
    """Every page record has `perf` whether or not a trace was taken — set to
    `{"traced": False}` where none was — so a reader never meets a missing key
    and `test_stored_shape` reads one shape (item 154's degrade-on-value rule)."""
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Tier
    page = Page(url="https://x.test/", requested_url="https://x.test/", status=200,
                content_type="text/html", content="<html><body>x</body></html>")
    ev = snapshot(CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[page]))
    assert ev["pages"][0]["perf"] == {"traced": False}
    # And a supplied trace round-trips onto the right page.
    ev2 = snapshot(CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[page]),
                   perf_traces={"https://x.test/": {"device_profile": "d", "ttfb_ms": 120}})
    assert ev2["pages"][0]["perf"]["ttfb_ms"] == 120


def test_nothing_reads_a_missing_field_as_a_different_number(tmp_path):
    """The rule the whole file exists to hold.

    `pages` absent must render as absent. It used to fall back to `affected`,
    and the two differ precisely where it matters — `duplicate-content` names
    both sides of a pair — so a run missing the field reported the wrong
    number under the right label.
    """
    _, run, _ = _audited(tmp_path)
    stripped = {
        dim: {**sub, "detail": {**sub["detail"], "per_check": {
            check: {k: v for k, v in stats.items() if k != "pages"}
            for check, stats in sub["detail"]["per_check"].items()}}}
        for dim, sub in run["subscores"].items()}

    gains = runs.biggest_gains(stripped)
    assert gains, "the fixture produced no gains to check"
    assert all(g["pages"] is None for g in gains), (
        "a run with no page count must report it as absent; substituting the "
        "finding count is how '21 of 20 pages' reached a client report")
    assert any(g["affected"] is not None for g in gains), (
        "the field that IS present must still be reported")


def test_a_trend_point_records_which_engine_produced_it(tmp_path):
    """Scores from different engine versions are not comparable — 0.5.0 alone
    changed duplicate detection and stopped A11Y scoring — and a quarterly
    client trend chart is exactly where that gets forgotten. The version was
    stamped on the run from day one and never on the snapshot, so the chart
    could not tell."""
    conn, run, _ = _audited(tmp_path)
    site = conn.execute("SELECT id FROM sites").fetchone()["id"]
    trend = runs.site_trend(conn, site)
    assert trend, "the audit recorded no trend point"
    assert all(p["engine_version"] == ENGINE_VERSION for p in trend)
    assert all(p["comparable"] for p in trend), "one version, all comparable"


def test_a_trend_marks_where_a_comparison_stops_being_one(tmp_path):
    """`comparable` is the fact a reader needs; the version alone leaves them
    diffing a column."""
    conn, _, _ = _audited(tmp_path)
    site = conn.execute("SELECT id FROM sites").fetchone()["id"]
    # A second point from a different engine, as an upgrade would write.
    conn.execute("INSERT INTO metric_snapshots (id, site_id, metric_key, value,"
                 " source, confidence, captured_at, tier, engine_version)"
                 " VALUES ('x', ?, 'composite_score', 91.0, 'engine', 'high',"
                 " '2099-01-01T00:00:00+00:00', 'T2', '9.9.9')", (site,))
    conn.commit()
    trend = runs.site_trend(conn, site)
    assert trend[0]["comparable"] is True, "the first point has nothing before it"
    assert trend[-1]["comparable"] is False, (
        "the point after an engine change is not comparable with the one before")


def test_a_trend_marks_where_the_tier_changed_under_it(tmp_path):
    """Tier is the third thing that frames a point, and it was the one left out.

    The key was built from `(engine_version, basis)`. Tier sits in the same
    row and decides more than either: a T2 crawl and a T3 crawl of one site
    are two different measurements of two different populations of pages, and
    one engine version does not make them one. Reproduced against the
    operator's own database before this was written -- site `2537f69f` holds
    `91.06 T2 0.8.0` followed by `70.52 T3 0.8.0`, and `site_trend` returned
    the second at `comparable: True`. A 20-point collapse across a tier
    boundary, positively asserted to be like-for-like, by the one function
    whose stated job is to say where a comparison stops being one.

    Same engine version and same basis on both points, so tier is the only
    term that differs and the assertion cannot pass for the wrong reason.
    """
    conn, _, _ = _audited(tmp_path)
    site = conn.execute("SELECT id FROM sites").fetchone()["id"]
    # A deeper crawl of the same site on the same engine, as an escalation
    # would write. `scope` is left NULL because the composite_score writer
    # does not set it -- so both points carry basis None and differ in tier
    # alone.
    conn.execute("INSERT INTO metric_snapshots (id, site_id, metric_key, value,"
                 " source, confidence, captured_at, tier, engine_version)"
                 " VALUES ('t3', ?, 'composite_score', 70.52, 'engine', 'high',"
                 " '2099-01-01T00:00:00+00:00', 'T3', ?)", (site, ENGINE_VERSION))
    conn.commit()
    trend = runs.site_trend(conn, site)
    assert trend[0]["comparable"] is True, "the first point has nothing before it"
    assert trend[-1]["tier"] == "T3" and trend[0]["tier"] == "T2", (
        "the fixture must differ in tier or this asserts nothing")
    assert trend[-1]["engine_version"] == trend[0]["engine_version"], (
        "one engine version, so the version cannot be what fails it")
    assert trend[-1]["comparable"] is False, (
        "a T3 crawl and a T2 crawl are not one series")


def test_every_category_says_which_dimensions_it_scores_under(tmp_path):
    """The Current screen groups by how you fix something; the score groups by
    dimension. Nothing joined the two, so a reader who improved Headings could
    not tell which sub-score should move.

    Derived from the findings rather than a static table, so it describes the
    data in front of the reader — and a category with no findings correctly
    names no dimensions rather than claiming one.
    """
    conn, _run, _ev = _audited(tmp_path)
    site = conn.execute("SELECT id FROM sites").fetchone()["id"]
    view = runs.anatomy_view(conn, site)

    mapping = view["category_dimensions"]
    assert set(mapping) == {c["key"] for c in view["categories"]}, (
        "every category needs an entry, including the empty ones")
    populated = {k: v for k, v in mapping.items() if v}
    assert populated, "the fixture raised findings but none carried a dimension"
    for key, dims in populated.items():
        by_key = {c["key"]: c for c in view["categories"]}
        # A coverage note names a dimension without being counted (brief v5
        # step S), so the notes stand beside the total here.
        # `["value"]`: the count carries its population since item 156.
        assert by_key[key]["total"]["value"] + by_key[key].get("notes", 0) > 0, (
            f"{key} names dimensions but holds no findings")
        assert all(":" not in d for d in dims), (
            "an expert dimension must be reduced to its base code")
