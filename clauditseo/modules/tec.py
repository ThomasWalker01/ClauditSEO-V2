"""TEC — Technical dimension.

Site- and page-level technical health: robots, sitemaps and coverage,
status codes and redirect chains, HTTPS and security headers, indexability
directives, mobile viewport. All checks run offline against the crawl
result; nothing here calls an external API.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from clauditseo import urlshape
from clauditseo.crawler.crawl import normalise_url, strip_tracking_params, tracking_params_in
from clauditseo.crawler.robots import RobotsPolicy, robots_url_for
from clauditseo.crawler.types import CrawlResult
from clauditseo.crawler.ua_matrix import (AI_AGENT_CLASSES, BLOCK_CONSEQUENCE, UA_MATRIX_AGENTS,
                                          agents_of)
from clauditseo import security_headers
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import (Confidence, Finding, Severity, Site,
                                     SubScore, Tier)
from clauditseo.linksuggest import MIN_INLINKS

from .onp import (TERMINAL_CANONICAL_CHECKS, canonical_chain_state,
                  canonical_nodes_from_crawl)
from .pagefacts import extract_facts, html_pages, rendered_words

#: The trace's own "we could not read this" marker. Imported rather than
#: retyped: a check comparing against a different spelling of it would read
#: an unavailable field as a value.
from clauditseo.perf import UNAVAILABLE as UNAVAIL


#: The AI agents `ai-crawler-blocked` tests robots.txt against: every agent in
#: `crawler.ua_matrix.UA_MATRIX_AGENTS` whose class is not `search`, tokens
#: included (item 145 step BG; was five names here and eight there). Homed in
#: TEC since item 137 (brief v18 step AZ): the check is a robots.txt rule, a
#: crawl artefact, scored beside `robots-missing`; migration 0048 carries the
#: stored rows.
AI_CRAWLERS = agents_of(*AI_AGENT_CLASSES)


#: Tagged links kept per finding. The untruncated count rides beside them as
#: `links_total`, so a display showing a subset can say that it is one.
LINK_EVIDENCE_CAP = 20


def _norm_path(u: str) -> str:
    """A URL's path, trailing slash normalised — so a sitemap listing /a/ and a
    page fetched as /a are the same page. The one rule the noindex-in-sitemap
    check and migration 0049 both read (item 137, brief v18 step BA)."""
    p = urlsplit(u).path or "/"
    return p if p == "/" else p.rstrip("/")


def _int_field(site, key: str, default: int) -> int:
    """A numeric site-record threshold (brief v19 step BB), or its default.
    The thresholds are stored as text like the budget fields beside them, so a
    blank or unparseable value falls back rather than raising."""
    raw = getattr(site, key, None) if site else None
    try:
        return int(str(raw).strip()) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


#: The registered default severity for each TEC check (brief v11 step AI's
#: registry, extended to TEC by brief v18 step AZ). One table, read by
#: `checks._registries()` — the same shape ONP, LNK and CNT already keep — so
#: the registry can answer "what is TEC's default severity" and "what does a
#: TEC check cost" without scraping the source.
#:
#: These are the severities the sweep already emits; the table names them, it
#: does not change them, and `test_tec_joins_the_registry` holds the two in
#: agreement. The emitters below still carry the values inline (unlike ONP,
#: which reads its table): wiring them to read from here is a mechanical
#: follow-up that must not move a single severity, kept out of the commit that
#: introduces the table. Two checks escalate on a condition the registry
#: cannot hold — `links-behind-js` to HIGH when the page is orphaned,
#: `http-status-error` to CRITICAL on a 5xx — and the base is recorded here.
DEFAULT_SEVERITY: dict[str, Severity] = {
    "links-behind-js": Severity.MEDIUM,          # HIGH when orphaned (emitter)
    # HIGH (item 137-answer): robots-missing is already in
    # `checks.BLOCKER_CHECKS`, so MEDIUM was the product disagreeing with
    # itself — a blocker it did not rank like one. Raised after the audit-data
    # reset, so no historical trend line bends under two rule sets.
    "robots-missing": Severity.HIGH,
    # HIGH, and a registered blocker (`checks.BLOCKER_CHECKS`). Re-homed from
    # AIS to TEC (item 137, brief v18 step AZ): a robots.txt rule blocking the
    # AI retrieval agents is a crawl-access failure by cause, so it is scored
    # here beside robots-missing rather than on the AI-surface subscore.
    "ai-crawler-blocked": Severity.HIGH,
    "sitemap-missing": Severity.MEDIUM,
    # brief v18 step AZ redefines `sitemap-coverage` to reached-pages-absent-
    # from-the-sitemap and gives declared-but-not-reached its own id,
    # `unreachable` (with the scope-guarded companion). MEDIUM per crawl.md;
    # the raise from LOW is a fresh severity for a replaced decision, not a
    # bent history.
    "sitemap-coverage": Severity.MEDIUM,
    "unreachable": Severity.MEDIUM,
    "unreachable-not-assessed": Severity.INFO,
    # Crawl & sitemaps, brief v18 step AZ. Site-level sitemap health, judged
    # from the sitemap files the crawl read (crawl.sitemaps / .sitemap_lastmod)
    # — no page correlation, so no partial-crawl caveat.
    "sitemap-invalid": Severity.HIGH,
    "sitemap-lastmod-stale": Severity.LOW,
    "sitemap-404s": Severity.MEDIUM,
    "sitemap-noindex": Severity.MEDIUM,
    "sitemap-regression": Severity.HIGH,
    # brief v18 step AZ. Non-link render parity: body text present only after
    # JavaScript, per page, from the rendered sample. The link half of what
    # crawl.md's `render-only` names stays with `links-behind-js` (the operator's
    # split, 2026-09-09), which already carries the router-only-anchor signal
    # with its whole-site guard; crawl.md:65 cross-references it.
    "render-only": Severity.MEDIUM,
    "internal-link-tracking-params": Severity.MEDIUM,
    "http-status-error": Severity.HIGH,          # CRITICAL on 5xx (emitter)
    # MEDIUM (item 137, brief v18 step BA): indexability.md registers it MEDIUM,
    # and it is no longer a blocker (dropped from checks.BLOCKER_CHECKS in the
    # same step) — a redirect chain resolves to a live page, so the page is
    # reached, unlike a robots block. Severity is not in the fingerprint, so
    # this moves no stored identity; it does move the score, by the operator's
    # call (channel 20260910-1430).
    "redirect-chain": Severity.MEDIUM,
    # Mobile, brief v20 (item 147). `mobile-viewport` became
    # `viewport-missing` and rose to HIGH: a page with no viewport tag does not
    # render responsively at all, which is not a MEDIUM. No migration was owed
    # — the live database held zero `mobile-viewport` rows.
    #
    # ONLY THE SIX THE SWEEP RAISES ARE HERE, which is a deliberate departure
    # from the item's literal instruction. It lists severities for all fifteen
    # and puts only three in the brief-only register; that is the END state,
    # after the 360 px render harness (its step 8) exists. Today the sweep
    # raises six, and this table's own rule is that it is "pinned to exactly
    # what the sweep raises". Registering twelve here would price six of them
    # FREE on the part page while nothing emits them — which is the exact
    # defect the item's section A warns about, arriving from the other side.
    # When step 8 lands, the render-dependent ids move from BRIEF_ONLY_CHECKS
    # to here.
    "viewport-missing": Severity.HIGH,
    "zoom-suppressed": Severity.HIGH,
    "viewport-width": Severity.MEDIUM,
    "viewport-scale": Severity.MEDIUM,
    "viewport-duplicate": Severity.MEDIUM,
    "viewport-legacy": Severity.MEDIUM,
    # And the six the trace made measurable (brief 160 steps 1-3). Three from
    # `mobile_render` -- taken in perf's own 412 x 823 Pixel 5 pass, which was
    # already the harness item 147's step 8 asked for -- and three from the
    # `head_fetched` / `head_rendered` pair, which is a diff rather than a
    # second render.
    #
    # **This is now exactly the 12/3 split item 147 asked for**, and arriving
    # at it by this route is the point: the item's list was the end state, the
    # interim registration was six, and each id moved into this table on the
    # run where a sweep could actually raise it. `DEFAULT_SEVERITY`'s rule --
    # pinned to exactly what the sweep raises -- held at every step.
    "viewport-injected": Severity.HIGH,
    "viewport-divergent": Severity.MEDIUM,
    # Item 165: what the retired `js-rendering` parity table asked of the
    # head, from the same head pair. One row per page naming every element.
    "head-divergent": Severity.MEDIUM,
    # Item 151: mobile and bot parity, retrieved rather than inferred. The
    # parity probe (`crawler/parity.py`) fetches a sample as desktop Chrome,
    # iPhone Safari and Googlebot-smartphone and compares the documents.
    # `bot-parity` is its own id, not a subject on `mobile-parity`: the
    # evidence that prompted it was a bot difference with no device one.
    "mobile-parity": Severity.HIGH,
    "mobile-parity-size": Severity.MEDIUM,
    "bot-parity": Severity.HIGH,
    "horizontal-overflow": Severity.MEDIUM,
    "tap-target": Severity.MEDIUM,
    "viewport-units": Severity.MEDIUM,
    "viewport-late": Severity.LOW,
    # noindex-page (one HIGH blocker on any noindex page) was split at item 137
    # (brief v18 step BA) into a linked page (the real problem, HIGH, blocker)
    # and one merely in the sitemap (LOW). Migration 0049 re-homes the stored
    # rows.
    "noindex-linked": Severity.HIGH,
    "noindex-in-sitemap": Severity.LOW,
    # Indexability & canonicals, brief v18 step BA. redirect-to-404 is a broken
    # redirect (HIGH); meta-robots-conflict is meta robots vs X-Robots-Tag
    # disagreeing on indexation (MEDIUM).
    "redirect-to-404": Severity.HIGH,
    "meta-robots-conflict": Severity.MEDIUM,
    # A temporary redirect (302/303/307) on a permanent move, LOW (brief v18
    # step BA). Unblocked by the F-13 per-hop status capture.
    "redirect-temporary": Severity.LOW,
    # The terminal-axis canonical checks, brief v18 step BA — crawl-state facts
    # about where a chain ends, born TEC while the relation checks stay ONP
    # (channel 20260910-0830). One verdict per page (onp.canonical_verdict), so
    # a terminal check suppresses the ONP relation one for the same page.
    "canonical-to-404": Severity.HIGH,
    "canonical-loop": Severity.HIGH,
    "canonical-sitemap-conflict": Severity.MEDIUM,
    # URLs & parameters, brief v19 step BB — the ten free checks the sweep
    # raises from the URL strings alone (`urlshape.analyse_url` and the two
    # site-level tables). The two HIGH ones make duplicate pages:
    # `url-trailing-slash-mixed` when both slash forms are reached, and
    # `url-parameter-unclassified` a query key with no class and no canonical
    # on its variants. The four analysis checks the brief judges are in
    # BRIEF_ONLY_CHECKS below, not here.
    "url-uppercase": Severity.MEDIUM,
    "url-non-ascii": Severity.MEDIUM,
    "url-separator": Severity.MEDIUM,
    "url-encoded-chars": Severity.LOW,
    "url-trailing-slash-mixed": Severity.HIGH,
    "url-length": Severity.LOW,
    "url-depth": Severity.LOW,
    "url-id-only": Severity.MEDIUM,
    "url-repeated-tokens": Severity.LOW,
    "url-parameter-unclassified": Severity.HIGH,
}

#: Checks the crawl brief (crawl.md, item 137 brief v18 step AZ) judges but no
#: TEC sweep emits, so they cost a model call and are NOT in DEFAULT_SEVERITY
#: (which is pinned to exactly what the sweep raises). `crawl-budget-waste` and
#: `render-policy` are the brief's two analysis checks; `ua-server-refusal` is
#: HELD — registered so the brief may name it, not emitted until the UA matrix
#: and the CDN/WAF site field land (task 4). Membership here is what makes
#: `check_costs()` price all three as `model`; their part is set in
#: `anatomy.CHECK_CATEGORY`.
BRIEF_ONLY_CHECKS: tuple[str, ...] = (
    "crawl-budget-waste", "render-policy", "ua-server-refusal",
    # Indexability & canonicals, brief v18 step BA — the three analysis checks,
    # model-judged and held: noindex-intent until the site record's
    # `intended_noindex` is set, redirect-map-correctness `not_assessable`
    # without a `migration_map`, parameter-policy proposing when
    # `parameter_rules` is empty. Registered so the brief may name them; no
    # sweep emits them, so they cost a model call and are not in DEFAULT_SEVERITY.
    "noindex-intent", "redirect-map-correctness", "parameter-policy",
    # URLs & parameters, brief v19 step BB — the four analysis checks the
    # `urls.md` brief judges and no sweep emits, so they cost a model call and
    # are priced `model`. `url-slug-entity` is HELD until the page triple (the
    # GBP category from v11) exists; the other three propose a slug, a
    # parameter class handed to Indexability, or a rename under the inlink cap.
    "url-slug-not-descriptive", "url-slug-entity", "url-parameter-policy",
    "url-rename",
    # Mobile, brief v20 (item 147). Three of the fifteen, and the three that
    # are JUDGEMENT rather than measurement, so no capture will ever move them
    # into DEFAULT_SEVERITY:
    #
    #   viewport-source    which authoring location owns the tag -- a theme
    #                      file, a plugin, a tag manager. The head says what
    #                      the tag is, never who put it there.
    #   viewport-keyboard  whether the layout survives the soft keyboard, which
    #                      is a judgement about a state no trace enters.
    #   safe-area          whether the notch inset is handled as the design
    #                      intends, which needs the intent.
    #
    # Nine sat here until brief 160: the six the trace made measurable moved to
    # DEFAULT_SEVERITY on the run where a sweep could raise them.
    "viewport-source", "viewport-keyboard", "safe-area")


#: Viewport content tokens that mark a pre-responsive tag (item 147, brief
#: v20). The prompt's wording is exact: "MobileOptimized, HandheldFriendly, or
#: target-densitydpi INSIDE the viewport content" — so these are looked for in
#: the tag's own content string, not as sibling meta tags, which is also all
#: `pagefacts` captures.
_LEGACY_VIEWPORT_TOKENS = ("mobileoptimized", "handheldfriendly",
                           "target-densitydpi")

#: The 200% zoom WCAG 2.1 SC 1.4.4 requires. A `maximum-scale` below this
#: prevents it.
_MIN_MAX_SCALE = 2.0


#: A viewport tag's content, from a head's raw HTML. The head is capped at
#: 4 KB by the trace, so this is a scan of a small string rather than a parse.
_VIEWPORT_IN_HEAD = re.compile(
    r"""<meta[^>]*\bname\s*=\s*['"]?viewport['"]?[^>]*>""", re.I)
_CONTENT_ATTR = re.compile(r"""\bcontent\s*=\s*(['"])(.*?)\1""", re.I | re.S)
#: What counts as render-blocking ahead of the viewport tag, for
#: `viewport-late`: a stylesheet or a script with no `async`/`defer`.
_BLOCKING_IN_HEAD = re.compile(
    r"""<link[^>]*\brel\s*=\s*['"]?stylesheet['"]?[^>]*>"""
    r"""|<script(?![^>]*\b(?:async|defer)\b)[^>]*\bsrc\s*=[^>]*>""", re.I)


#: The Mobile checks that exist only because a trace was taken (brief 160
#: steps 1-3), TEC's counterpart to `prf.TRACE_DERIVED_CHECKS` and read by the
#: same rung of `runs.not_assessed_payload`.
#:
#: Needed because rung 2 knew only PRF's set, and these six are TEC: on a run
#: with no trace they hit no rung at all -- TEC ran, so rung 1 was silent;
#: they were not in PRF's set, so rung 2 was silent; they are swept, not
#: brief-only, so rung 3 was silent -- and they read as CLEAN. A tap-target
#: check reported as passing by a run that never rendered a page.
#:
#: The six parse checks are NOT here: they read the crawl's own
#: `viewport_tags` and are measured on every page whether or not a trace ran.
TRACE_DERIVED_CHECKS: frozenset[str] = frozenset({
    "horizontal-overflow", "tap-target", "viewport-units",
    "viewport-injected", "viewport-divergent", "viewport-late",
    "head-divergent",
})

#: The engine version each TEC check was first measured in, read by the same
#: not-assessed rung as `sec.COLLECTED_SINCE`: a traced run from before it
#: never looked, and must not read as passing.
COLLECTED_SINCE: dict[str, str] = {"head-divergent": "0.26.0",
                                   "mobile-parity": "0.27.0",
                                   "mobile-parity-size": "0.27.0",
                                   "bot-parity": "0.27.0"}

#: The checks the parity probe answers (item 151). Read by the not-assessed
#: rung: a run whose crawl carries no `mobile_parity` block never fetched as a
#: phone or as Googlebot-smartphone, and must not read as parity holding.
PARITY_CHECKS: frozenset[str] = frozenset({"mobile-parity", "mobile-parity-size",
                                           "bot-parity"})

#: Size fields that mean Googlebot was shown different copy or a different
#: link graph, not only lighter markup (item 153's settling question): on the
#: bot pair these raise `bot-parity`; bytes and the main-region hash alone
#: stay `mobile-parity-size`.
_BOT_CONTENT_FIELDS = ("words", "internal_links")

_HEAD_LINK = re.compile(r"<link\b[^>]*>", re.I)
_HEAD_META = re.compile(r"<meta\b[^>]*>", re.I)
_HEAD_ATTR = lambda name: re.compile(  # noqa: E731
    rf"""\b{name}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_A_REL, _A_HREF, _A_HREFLANG = _HEAD_ATTR("rel"), _HEAD_ATTR("href"), _HEAD_ATTR("hreflang")
_A_NAME, _A_PROPERTY, _A_CONTENT = _HEAD_ATTR("name"), _HEAD_ATTR("property"), _HEAD_ATTR("content")


def _attr(pattern, tag: str) -> str | None:
    m = pattern.search(tag)
    return next((g for g in m.groups() if g is not None), "").strip() if m else None


def head_elements(head: str) -> dict[str, str]:
    """The head elements a crawler reads besides the viewport, keyed so two
    heads compare element by element: `canonical`, `meta description`, `meta
    robots`, `hreflang <lang>`, `og:<property>`. The last of a repeated key
    wins, as a parser's would."""
    out: dict[str, str] = {}
    for tag in _HEAD_LINK.findall(head or ""):
        rel = (_attr(_A_REL, tag) or "").lower().split()
        if "canonical" in rel:
            out["canonical"] = _attr(_A_HREF, tag) or ""
        elif "alternate" in rel and _attr(_A_HREFLANG, tag):
            out[f"hreflang {_attr(_A_HREFLANG, tag).lower()}"] = _attr(_A_HREF, tag) or ""
    for tag in _HEAD_META.findall(head or ""):
        name = (_attr(_A_NAME, tag) or "").lower()
        prop = (_attr(_A_PROPERTY, tag) or "").lower()
        if name in ("description", "robots"):
            out[f"meta {name}"] = _attr(_A_CONTENT, tag) or ""
        elif prop.startswith("og:"):
            out[prop] = _attr(_A_CONTENT, tag) or ""
    return out


def _head_divergent(code: str, facts, url: str, trace: dict | None) -> list[Finding]:
    """TEC/head-divergent (item 165): a head element among canonical, meta
    description, meta robots, hreflang and og:* that appears only after
    JavaScript, or that JavaScript changes. One row per page naming every
    divergent element - one fault, not one per element. An element the script
    removes is not this check's, as the item defines it. Silent without both
    heads: an untraced page is not assessed, not clean."""
    if not trace or trace.get("traced") is False:
        return []
    fetched, rendered = trace.get("head_fetched"), trace.get("head_rendered")
    if not fetched or fetched == UNAVAIL or not rendered or rendered == UNAVAIL:
        return []
    before, after = head_elements(fetched), head_elements(rendered)
    diverged = []
    for key in sorted(set(before) | set(after)):
        if key not in before:
            diverged.append({"element": key, "case": "injected", "fetched": None, "rendered": after[key]})
        elif key in after and before[key] != after[key]:
            diverged.append({"element": key, "case": "changed", "fetched": before[key], "rendered": after[key]})
    if not diverged:
        return []
    names = ", ".join(f"{d['element']} ({d['case']})" for d in diverged[:6])
    return [Finding(
        dimension=code, check_id="head-divergent", severity=DEFAULT_SEVERITY["head-divergent"],
        summary=f"{facts.path}: JavaScript changes what the head tells a crawler - {names}.",
        subject=facts.path, affected_urls=[url],
        evidence={"elements": diverged, "measured": "lab"},
        confidence=Confidence.LOW,
        recommendation="Serve these elements in the HTML the server sends. A crawler that does "
                       "not run scripts reads the served head, so a canonical, robots or "
                       "hreflang set by JavaScript is one it may never see.",
    )]


def _viewport_tags_in(head: str | None) -> list[str]:
    """Every viewport tag's `content` in a head, in document order.

    Returns [] for an absent or UNAVAILABLE head, which is NOT the same as a
    head with no viewport tag -- the callers all check the head is real first,
    because "we could not look" and "we looked and found none" are the two
    answers item 157 exists to keep apart.
    """
    if not head or head == UNAVAIL:
        return []
    out = []
    for tag in _VIEWPORT_IN_HEAD.findall(head):
        m = _CONTENT_ATTR.search(tag)
        out.append(m.group(2).strip() if m else "")
    return out


def _mobile_render_checks(code: str, facts, url: str,
                          trace: dict | None) -> list[Finding]:
    """The six Mobile checks a rendered page answers (brief 160 steps 1-3,
    item 147's step 8 and its two head-diff checks).

    **No second render pass and no second harness.** `perf.py` is already a
    412 x 823 Pixel 5 emulation with JavaScript executing under a CDP session,
    and these are measurements taken in that pass: `mobile_render` for the
    three layout ones, and the `head_fetched` / `head_rendered` pair for the
    two diffs. Item 147 asked for that instrument at 360 px three days before
    it was built at 412.

    **412, stated, not silently substituted for 147's 360.** The width travels
    in the evidence of every finding, the way `device_profile` travels on the
    Speed part, so a reader knows which phone the overflow was measured on. A
    360 px pass would be a second emulation in the same session and is not on
    by default.

    Silent where the page carries no trace. That is 3b's shape: the instrument
    that looked answers, and the screen says `not_assessed` for the rest
    (item 157) rather than a proxy guessing from markup it cannot see.
    """
    if not trace or trace.get("traced") is False:
        return []
    out: list[Finding] = []
    path = facts.path
    render = trace.get("mobile_render")
    fetched, rendered = trace.get("head_fetched"), trace.get("head_rendered")

    if isinstance(render, dict):
        width = render.get("viewport_width")
        profile = f"{width} x {render.get('viewport_height')} CSS px"

        overflow = render.get("overflow_px") or 0
        if overflow > 0:
            named = render.get("overflowing") or []
            first = (f"{named[0].get('tag')}"
                     f"{'.' + named[0]['cls'].split()[0] if named[0].get('cls') else ''}"
                     if named else "an element the pass could not name")
            out.append(Finding(
                dimension=code, check_id="horizontal-overflow",
                severity=Severity.MEDIUM,
                summary=f"{path} is {render.get('document_width')} px wide in a "
                        f"{width} px viewport — {overflow} px of sideways "
                        f"scroll, starting with {first}.",
                subject=path, affected_urls=[url],
                evidence={"overflow_px": overflow, "viewport": profile,
                          "document_width": render.get("document_width"),
                          "elements": named[:10], "measured": "lab"},
                confidence=Confidence.LOW,
                recommendation="Find the element wider than the viewport and cap "
                               "it: max-width:100%, or box-sizing on a padded "
                               "fixed width. Sideways scroll on a phone is a "
                               "layout fault, not a preference.",
            ))

        small = render.get("small_tap_targets") or []
        if small:
            floor = render.get("tap_target_min_px") or 24
            out.append(Finding(
                dimension=code, check_id="tap-target", severity=Severity.MEDIUM,
                summary=f"{path}: {len(small)} interactive element(s) smaller "
                        f"than {floor} x {floor} CSS px, which WCAG 2.2 SC "
                        f"2.5.8 sets as the minimum.",
                subject=path, affected_urls=[url],
                evidence={"elements": small[:10], "minimum_px": floor,
                          "viewport": profile, "measured": "lab"},
                confidence=Confidence.LOW,
                recommendation=f"Give each control at least {floor} x {floor} px "
                               "of hit area — padding counts, so the visible "
                               "icon need not grow.",
            ))

        units = render.get("viewport_unit_elements") or []
        if units:
            out.append(Finding(
                dimension=code, check_id="viewport-units", severity=Severity.MEDIUM,
                summary=f"{path}: {len(units)} element(s) sized in viewport "
                        "units or fixed-positioned — on a phone the visible "
                        "area shrinks as the URL bar appears, so 100vh is "
                        "taller than the screen.",
                subject=path, affected_urls=[url],
                evidence={"elements": units[:10], "viewport": profile,
                          "measured": "lab"},
                confidence=Confidence.LOW,
                recommendation="Prefer dvh/svh over vh for full-height blocks, "
                               "and check any fixed element against the "
                               "keyboard and the URL bar.",
            ))

    # The two head-diff checks. Both need BOTH heads; with either missing the
    # answer is unknown, and the screen says so rather than this inventing one.
    if (fetched and fetched != UNAVAIL) and (rendered and rendered != UNAVAIL):
        in_fetched = _viewport_tags_in(fetched)
        in_rendered = _viewport_tags_in(rendered)
        if in_rendered and not in_fetched:
            out.append(Finding(
                dimension=code, check_id="viewport-injected", severity=Severity.HIGH,
                summary=f"{path} has no viewport tag in the HTML the server "
                        f"sent; one appears only after JavaScript runs "
                        f"({in_rendered[-1]!r}).",
                subject=path, affected_urls=[url],
                evidence={"rendered": in_rendered, "fetched": [],
                          "measured": "lab"},
                confidence=Confidence.LOW,
                recommendation="Put the viewport tag in the served HTML. A "
                               "client-side tag arrives after the first layout, "
                               "so the page reflows and any crawler that does "
                               "not execute scripts never sees it at all.",
            ))
        elif in_fetched and in_rendered and in_fetched[-1] != in_rendered[-1]:
            out.append(Finding(
                dimension=code, check_id="viewport-divergent",
                severity=Severity.MEDIUM,
                summary=f"{path} serves viewport {in_fetched[-1]!r} and ends up "
                        f"with {in_rendered[-1]!r} after JavaScript — two "
                        "different answers about the same page.",
                subject=path, affected_urls=[url],
                evidence={"fetched": in_fetched, "rendered": in_rendered,
                          "measured": "lab"},
                confidence=Confidence.LOW,
                recommendation="Serve the tag you want and stop rewriting it. "
                               "Whichever is correct, the first layout uses the "
                               "served one.",
            ))

        # `viewport-late` needs the FETCHED head, because it is about the order
        # the server sent things in. The rendered head's order can be anything
        # a script left behind.
        if in_fetched:
            first = _VIEWPORT_IN_HEAD.search(fetched)
            blocking_before = [m.group(0) for m in _BLOCKING_IN_HEAD.finditer(fetched)
                               if first and m.start() < first.start()]
            if blocking_before:
                out.append(Finding(
                    dimension=code, check_id="viewport-late", severity=Severity.LOW,
                    summary=f"{path} declares its viewport after "
                            f"{len(blocking_before)} render-blocking resource(s) "
                            "in the head, so the browser starts laying out at "
                            "the wrong width.",
                    subject=path, affected_urls=[url],
                    evidence={"blocking_before": blocking_before[:5],
                              "measured": "lab"},
                    confidence=Confidence.LOW,
                    recommendation="Move the viewport meta above every "
                                   "stylesheet and synchronous script. It is "
                                   "two lines after <head>.",
                ))
    return out


def _as_float(raw) -> float | None:
    """A viewport number, or None where it is absent or not a number.

    A malformed value is not zero: `initial-scale=one` must not read as a scale
    a comparison can be made against.
    """
    if raw in (None, ""):
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _viewport_pairs(content: str) -> dict[str, str]:
    """A viewport content string as key/value pairs: keys lowercased, values
    verbatim.

    A segment with no `=` is kept as a key with an empty value rather than
    dropped. `width` on its own is a misspelling of `width=device-width`, and
    the check that reads it has to be able to see the difference between that
    and no width at all.
    """
    out: dict[str, str] = {}
    for part in content.split(","):
        key, sep, value = part.partition("=")
        key = key.strip().lower()
        if key:
            out[key] = value.strip() if sep else ""
    return out


def _viewport_checks(code: str, facts, url: str) -> list[Finding]:
    """The six viewport checks a parse can answer (item 147, brief v20, the
    first of its three capture groups).

    Everything here reads `pagefacts.viewport_tags`, which already holds every
    viewport tag verbatim in document order, so this adds no capture. The one
    check that existed before, `mobile-viewport`, is `viewport-missing` now and
    is HIGH rather than MEDIUM: a page with no viewport tag does not render
    responsively at all.

    **The prompt's precedence rules are applied here rather than left to the
    brief.** `viewport-missing` sets aside `viewport-width`, `viewport-scale`,
    `zoom-suppressed` and `viewport-legacy`: there is no tag, so a claim about
    what the tag says would be a claim about nothing. That is BA's
    one-verdict-per-page pattern, and doing it in the sweep hands the brief a
    set that is already consistent instead of one it has to suppress.

    `viewport-duplicate` deliberately sets aside nothing, per the prompt: the
    effective tag is judged on its own merits and the duplication is its own
    defect. The last tag wins in a browser, so that is the one read.

    The other nine ids of this brief need a rendered head, the tag's position
    in the head, or a 360 px render harness. They are in `BRIEF_ONLY_CHECKS`
    and this function is silent about them by design.
    """
    tags = list(getattr(facts, "viewport_tags", None) or [])
    path = facts.path
    if not tags:
        return [Finding(
            dimension=code, check_id="viewport-missing", severity=Severity.HIGH,
            summary=f"No viewport meta tag on {path} — the page will not "
                    "render responsively on mobile.",
            subject=path, affected_urls=[url], evidence={},
            recommendation='Add <meta name="viewport" content="width=device-width, '
                           'initial-scale=1"> to the page head.',
        )]

    out: list[Finding] = []
    effective = tags[-1]
    pairs = _viewport_pairs(effective)

    if len(tags) > 1:
        out.append(Finding(
            dimension=code, check_id="viewport-duplicate", severity=Severity.MEDIUM,
            summary=f"{len(tags)} viewport meta tags on {path}; the last one wins "
                    f"in the browser, so {effective!r} is the effective tag.",
            subject=path, affected_urls=[url],
            evidence={"tags": tags, "effective": effective},
            recommendation="Keep one viewport tag, and delete the others rather "
                           "than editing them, so which one applies stops being "
                           "a question.",
        ))

    if pairs.get("width", "").lower() != "device-width":
        got = (f"width={pairs['width']!r}" if pairs.get("width")
               else f"the tag reads {effective!r}")
        out.append(Finding(
            dimension=code, check_id="viewport-width", severity=Severity.MEDIUM,
            summary=f"Viewport on {path} does not set width=device-width — {got}.",
            subject=path, affected_urls=[url],
            evidence={"viewport": effective, "width": pairs.get("width")},
            recommendation="Set width=device-width so the layout viewport matches "
                           "the device instead of a fixed pixel width.",
        ))

    scale = pairs.get("initial-scale")
    if scale is None or _as_float(scale) != 1.0:
        said = (f"sets initial-scale={scale!r}" if scale is not None
                else "sets no initial-scale")
        out.append(Finding(
            dimension=code, check_id="viewport-scale", severity=Severity.MEDIUM,
            summary=f"Viewport on {path} {said} — it should be 1.",
            subject=path, affected_urls=[url],
            evidence={"viewport": effective, "initial_scale": scale},
            recommendation="Set initial-scale=1 so the page opens unzoomed.",
        ))

    # `minimum-scale` is NOT part of this check and never triggers it on its
    # own. The prompt says so in terms, and it is the mistake worth naming: a
    # low minimum-scale lets a user zoom OUT, which suppresses nothing.
    user_scalable = pairs.get("user-scalable", "").lower()
    max_scale = _as_float(pairs.get("maximum-scale"))
    blocked = user_scalable in ("no", "0", "0.0")
    capped = max_scale is not None and max_scale < _MIN_MAX_SCALE
    if blocked or capped:
        why = ("user-scalable=no" if blocked
               else f"maximum-scale={pairs.get('maximum-scale')}")
        out.append(Finding(
            dimension=code, check_id="zoom-suppressed", severity=Severity.HIGH,
            summary=f"Viewport on {path} prevents zoom ({why}) — WCAG 2.1 SC "
                    "1.4.4 requires 200% without loss of content.",
            subject=path, affected_urls=[url],
            evidence={"viewport": effective,
                      "user_scalable": pairs.get("user-scalable"),
                      "maximum_scale": pairs.get("maximum-scale"),
                      "minimum_required_max_scale": _MIN_MAX_SCALE},
            recommendation="Remove user-scalable=no and any maximum-scale below "
                           "2. Pinch-zoom is an accessibility requirement, not a "
                           "layout preference.",
        ))

    legacy = [t for t in _LEGACY_VIEWPORT_TOKENS if t in effective.lower()]
    if legacy:
        out.append(Finding(
            dimension=code, check_id="viewport-legacy", severity=Severity.MEDIUM,
            summary=f"Viewport on {path} carries pre-responsive settings "
                    f"({', '.join(legacy)}) that no current browser reads.",
            subject=path, affected_urls=[url],
            evidence={"viewport": effective, "legacy_tokens": legacy},
            recommendation="Drop the legacy settings; width=device-width with "
                           "initial-scale=1 is what replaced them.",
        ))
    return out


def _norm(url: str) -> str:
    """One spelling for comparing a rendered href with a parsed one. The
    browser resolves `href` against the base, so both sides are absolute;
    the fragment is dropped because `#top` is the same destination."""
    try:
        split = urlsplit(url)
    except ValueError:
        return url
    return f"{split.netloc.lower()}{(split.path or '/').rstrip('/') or '/'}?{split.query}"


#: The sitemap protocol's per-file URL cap. A file over it is invalid and must
#: be split (brief v18 step AZ). The 50 MB size cap is the protocol's other
#: bound; the crawl does not keep each file's byte size, so that half is not
#: judged and `sitemap-invalid` says so rather than implying it passed.
SITEMAP_MAX_URLS = 50_000

#: `render-only` thresholds (brief v18 step AZ). The signal is the empty-shell
#: shape: the initial HTML carries almost no body text while the rendered DOM
#: carries real content, so a reader that does not run scripts sees a blank
#: page. Conservative on purpose — a MEDIUM per-page finding must not fire on a
#: page that merely hydrates a little extra. A page whose initial body is under
#: the floor AND whose rendered body clears the minimum is render-dependent;
#: a genuinely thin page is low on both sides and says nothing here.
RENDER_ONLY_RAW_MAX = 50        # initial-HTML body words at or below this reads as a shell
RENDER_ONLY_RENDERED_MIN = 100  # and the rendered DOM has to carry real content


def _lastmod_in_future(stamp: str) -> bool:
    """Whether a sitemap `<lastmod>` is dated after now. Lenient: a value that
    does not parse as a date is *not judged* future — a malformed lastmod is a
    different fault, and guessing one into the other would misreport it."""
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat((stamp or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt > datetime.now(timezone.utc)


class TechnicalModule:
    code = "TEC"
    name = "Technical"
    default_weight = scoring.DEFAULT_WEIGHTS["TEC"]
    #: Most checks name the page. `robots-missing` and `sitemap-missing`
    #: read one well-known URL each; `not-https`, `http-status-error`,
    #: `redirect-chain`, `noindex-linked`, `noindex-in-sitemap`,
    #: `mobile-viewport` and `security-headers` are properties of the single
    #: response the crawler got for that page, and re-fetching it re-measures
    #: all of them. Only
    #: `sitemap-coverage-not-assessed` is site-scoped.
    #:
    #: Q-17 rejected keying this on the presentation group precisely to keep
    #: this dimension's control: Crawl & sitemaps, Security & transport,
    #: Mobile and Indexability all sit outside "on the page" as a *heading*
    #: and are every one of them measurable against a single page. See
    #: `registry.page_blind_dims`.
    measured_per_page = True

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        findings: list[Finding] = []
        findings += self._site_checks(crawl, context.get("site"))
        # Needs the previous run, which only the caller holds, so it reads the
        # injected context rather than the crawl (brief v18 step AZ; the shape
        # `prior_pages`/`CNT/stale` already use).
        findings += self._sitemap_regression(crawl, context.get("prior_sitemap"))
        findings += self._page_checks(
            crawl, context.get("perf_traces"))
        findings += self._link_checks(crawl)
        findings += self._links_behind_js(crawl, context)
        findings += self._render_only(crawl, context)
        findings += self._canonical_terminal_checks(crawl, context)
        findings += self._url_checks(crawl, context)
        findings += self._parity(crawl)
        return findings

    def _parity(self, crawl: CrawlResult) -> list[Finding]:
        """The parity probe's three checks (item 151), read from the block the
        crawl stored - the comparison itself is `crawler.parity.compare`, so
        there is one rule for what differs.

        `mobile-parity` (HIGH): the iPhone was served a different status, final
        URL, title, description, canonical or robots than desktop.
        `bot-parity` (HIGH): Googlebot-smartphone was served one of those, or
        different copy or internal links, than the browser on the same device
        class. `mobile-parity-size` (MEDIUM): the documents differ in size,
        main-region hash, word or link count while the named fields agree -
        Birch's case - for either pair, where the pair did not already raise
        HIGH on the page.

        Silent without a block, which the part page reads as not assessed. A
        clean block raises nothing; its `statement` is the stored negative."""
        block = getattr(crawl, "mobile_parity", None)
        if not block or not block.get("pages"):
            return []
        from clauditseo.crawler.parity import JS_STATEMENT

        def differs(pair: dict) -> dict:
            return {x["field"]: {"base": x["base"], "other": x["other"]}
                    for x in pair["named"] + pair["size"]}

        device_named, bot_high, size_rows = [], [], []
        for row in block["pages"]:
            device, bot = row["device"], row["bot"]
            if device["verdict"] == "named":
                device_named.append({"url": row["url"], "differs": differs(device)})
            elif device["verdict"] == "size":
                size_rows.append({"url": row["url"], "pair": "iphone vs desktop",
                                  "differs": differs(device)})
            bot_content = [x for x in bot["size"] if x["field"] in _BOT_CONTENT_FIELDS]
            pair = f"googlebot-smartphone vs {row.get('bot_compared_with', 'iphone')}"
            if bot["verdict"] == "named" or (bot["verdict"] == "size" and bot_content):
                bot_high.append({"url": row["url"], "pair": pair, "differs": differs(bot)})
            elif bot["verdict"] == "size":
                size_rows.append({"url": row["url"], "pair": pair, "differs": differs(bot)})

        base_evidence = {"sample_rule": block.get("sample_rule"), "mode": block.get("mode"),
                         "probed": block.get("probed"), "agents": block.get("agents"),
                         "javascript_executed": False, "basis": block.get("covers"),
                         "measured": "crawler names from this crawler's address"}
        probed = block.get("probed") or len(block["pages"])
        out: list[Finding] = []

        def emit(rows: list[dict], summary: str, recommendation: str, *, check_id: str):
            urls = sorted({r["url"] for r in rows})
            out.append(Finding(
                dimension=self.code, check_id=check_id,
                severity=DEFAULT_SEVERITY[check_id],
                summary=f"{summary} {JS_STATEMENT}",
                subject="site", affected_urls=urls[:20], affected_total=len(urls),
                evidence={**base_evidence, "pages": rows[:10]},
                recommendation=recommendation))

        if device_named:
            fields = sorted({f for r in device_named for f in r["differs"]})
            emit(device_named,
                 f"{len(device_named)} of {probed} probed page(s) serve an iPhone a different "
                 f"document from desktop: {', '.join(fields)}.",
                 "Mobile-first indexing reads the phone's document. Serve the same title, "
                 "description, canonical and robots to every device, or find the dynamic "
                 "serving rule that changes them.", check_id="mobile-parity")
        if bot_high:
            fields = sorted({f for r in bot_high for f in r["differs"]})
            emit(bot_high,
                 f"{len(bot_high)} of {probed} probed page(s) serve Googlebot-smartphone a "
                 f"different document from a browser: {', '.join(fields)}.",
                 "Fetch the page in Search Console's URL inspection and compare it with the "
                 "browser's copy. If Google sees less copy or fewer links, find the CDN, "
                 "cache or plugin rule keyed on the user agent.", check_id="bot-parity")
        if size_rows:
            urls = {r["url"] for r in size_rows}
            emit(size_rows,
                 f"{len(urls)} of {probed} probed page(s) differ in size, main-region text "
                 "or link count between crawler names while the title, description, "
                 "canonical and robots agree.",
                 "Diff the two documents named here. Markup or assets alone is a note; "
                 "different visible copy or links is the finding to raise with the site.",
                 check_id="mobile-parity-size")
        return out

    def _url_checks(self, crawl: CrawlResult, context: dict) -> list[Finding]:
        """The ten free URLs & parameters checks (brief v19 step BB): facts
        about each reached URL's string, and the one site-level parameter
        check. The four analysis checks (`url-slug-*`, `url-parameter-policy`,
        `url-rename`) are the brief's and are not emitted here.

        Thresholds come from the site record where set (`url_max_chars` and
        the three beside it) and fall back to `urlshape`'s defaults. The
        parameter inventory reads the unstripped `href` on every link, not the
        reached URL set, because the crawler strips tracking keys from its
        identities — see the `urlshape` module docstring.
        """
        site: Site | None = context.get("site")
        max_chars = _int_field(site, "url_max_chars", urlshape.DEFAULT_URL_MAX_CHARS)
        max_words = _int_field(site, "slug_max_words", urlshape.DEFAULT_SLUG_MAX_WORDS)
        max_depth = _int_field(site, "max_depth", urlshape.DEFAULT_MAX_DEPTH)

        pages = html_pages(crawl.pages)
        oks = [p for p in pages if p.status == 200]
        findings: list[Finding] = []

        # Per-page string facts.
        for page in oks:
            a = urlshape.analyse_url(page.url)
            path = a["path"]
            base = dict(subject=path, affected_urls=[page.url])
            if a["uppercase"]:
                findings.append(Finding(
                    dimension=self.code, check_id="url-uppercase", severity=Severity.MEDIUM,
                    summary=f"{path} has uppercase letters — one case per URL, or the "
                            "same page answers at two spellings.",
                    evidence={"path": path}, **base))
            if a["non_ascii"]:
                findings.append(Finding(
                    dimension=self.code, check_id="url-non-ascii", severity=Severity.MEDIUM,
                    summary=f"{path} has non-ASCII characters in the path.",
                    evidence={"path": path}, **base))
            if a["separator"]:
                findings.append(Finding(
                    dimension=self.code, check_id="url-separator", severity=Severity.MEDIUM,
                    summary=f"{path} joins words with something other than a hyphen "
                            "(an underscore, a space or camelCase).",
                    evidence={"slug": a["slug"]}, **base))
            if a["encoded_chars"]:
                findings.append(Finding(
                    dimension=self.code, check_id="url-encoded-chars", severity=Severity.LOW,
                    summary=f"{path} percent-encodes punctuation "
                            f"({', '.join(a['encoded_chars'])}).",
                    evidence={"encoded": a["encoded_chars"]}, **base))
            if a["path_length"] > max_chars or a["slug_word_count"] > max_words:
                findings.append(Finding(
                    dimension=self.code, check_id="url-length", severity=Severity.LOW,
                    summary=f"{path} is long — {a['path_length']} characters / "
                            f"{a['slug_word_count']} slug words "
                            f"(over {max_chars} / {max_words}).",
                    evidence={"path_length": a["path_length"],
                              "slug_words": a["slug_word_count"],
                              "url_max_chars": max_chars, "slug_max_words": max_words},
                    **base))
            if a["depth"] > max_depth:
                findings.append(Finding(
                    dimension=self.code, check_id="url-depth", severity=Severity.LOW,
                    summary=f"{path} is {a['depth']} segments deep (over {max_depth}).",
                    evidence={"depth": a["depth"], "max_depth": max_depth,
                              "pattern": urlshape.derive_pattern(path)},
                    **base))
            if a["id_only"]:
                findings.append(Finding(
                    dimension=self.code, check_id="url-id-only", severity=Severity.MEDIUM,
                    summary=f"{path}'s slug is a number or id with no words.",
                    evidence={"slug": a["slug"]}, **base))
            if a["repeated_tokens"]:
                findings.append(Finding(
                    dimension=self.code, check_id="url-repeated-tokens", severity=Severity.LOW,
                    summary=f"{path} repeats a word in the path "
                            f"({', '.join(a['repeated_tokens'])}).",
                    evidence={"repeated": a["repeated_tokens"]}, **base))

        findings += self._trailing_slash_mixed(oks)
        findings += self._parameter_unclassified(crawl, oks, site)
        return findings

    def _trailing_slash_mixed(self, oks: list) -> list[Finding]:
        """A genuine both-forms duplicate: `/x` and `/x/` both reached as
        200s, neither redirecting to the other (a redirect collapses them and
        the crawler would only have kept one). One finding per pair, on the
        pair's shared path."""
        by_stripped: dict[str, list[str]] = {}
        for p in oks:
            path = urlsplit(p.url).path or "/"
            if path == "/":
                continue
            stem = path.rstrip("/")
            by_stripped.setdefault(stem, []).append(path)
        findings: list[Finding] = []
        for stem, forms in sorted(by_stripped.items()):
            if len({f.endswith("/") for f in forms}) > 1:
                findings.append(Finding(
                    dimension=self.code, check_id="url-trailing-slash-mixed",
                    severity=Severity.HIGH,
                    summary=f"{stem} answers both with and without a trailing slash "
                            "— two URLs, one page.",
                    subject=stem, affected_urls=sorted(set(forms)),
                    evidence={"forms": sorted(set(forms))},
                    recommendation="Pick one form and 301 the other to it; keep the "
                                   "site's convention consistent."))
        return findings

    def _parameter_unclassified(self, crawl: CrawlResult, oks: list,
                                site: Site | None) -> list[Finding]:
        """A query key seen in the crawl with no class in the site record's
        `parameter_rules` and no canonical on any variant carrying it. HIGH:
        an unowned parameter manufactures a duplicate. Site-level — one finding
        per key, keyed to the site root like the other site-wide TEC rows."""
        # `canonical present on a variant` = the variant was reached and
        # declares a canonical. Tracking variants are never reached (stripped),
        # so they read as zero, which is the whole point.
        has_canon: dict[str, bool] = {}
        for p in html_pages(crawl.pages):
            has_canon[normalise_url(p.url)] = bool(extract_facts(p).canonical)

        def canonical_present(variant: str) -> bool:
            return has_canon.get(normalise_url(variant), False)

        hrefs: list[str] = [p.url for p in oks]
        for p in html_pages(crawl.pages):
            for link in (p.link_details or []):
                href = link.get("href") or link.get("url")
                if href:
                    hrefs.append(href)

        rules = getattr(site, "parameter_rules", None) if site else None
        inventory = urlshape.parameter_inventory(hrefs, canonical_present)
        root = crawl.start_url
        findings: list[Finding] = []
        for row in inventory:
            key = row["key"]
            if urlshape.classify(key, rules) is not None:
                continue
            if row["canonical_present"] > 0:
                continue
            findings.append(Finding(
                dimension=self.code, check_id="url-parameter-unclassified",
                severity=Severity.HIGH,
                summary=f"?{key}= is on {row['seen']} URLs with no class in the site "
                        f"record and no canonical on any variant — an unowned "
                        "parameter making duplicates.",
                subject=f"?{key}=*", affected_urls=[root],
                evidence={"key": key, "seen": row["seen"],
                          "canonical_present": row["canonical_present"]},
                recommendation="Classify the parameter (tracking, sort, filter, "
                               "pagination, content) and let Indexability set the "
                               "canonical policy for it."))
        return findings

    def _canonical_terminal_checks(self, crawl: CrawlResult, context: dict) -> list[Finding]:
        """The terminal-axis canonical checks (item 137, brief v18 step BA):
        facts about where a page's canonical chain ends, not what its markup
        says. They are born TEC — a dead or looping target is a crawl-state
        fact — while the relation checks stay ONP (channel 20260910-0830).

        One walk, one verdict per page, shared with ONP: `chain["check"]` is the
        single answer (`onp.canonical_verdict`), and TEC emits it only when it is
        a terminal check, so a page raises exactly one canonical finding on this
        axis and ONP suppresses its relation check for the same page. The nodes
        are built once and shared through `context`, whichever module runs first.
        """
        nodes = context.get("canonical_nodes")
        if nodes is None:
            nodes = canonical_nodes_from_crawl(crawl)
            context["canonical_nodes"] = nodes

        findings: list[Finding] = []
        for page in html_pages(crawl.pages):
            chain = canonical_chain_state(page.url, nodes)
            verdict = chain["check"]
            if verdict not in TERMINAL_CANONICAL_CHECKS:
                continue
            path = urlsplit(page.url).path or "/"
            canon = extract_facts(page).canonical
            target = chain["nodes"][-1]["path"] if len(chain["nodes"]) > 1 else path
            if verdict == "canonical-to-404":
                findings.append(Finding(
                    dimension=self.code, check_id="canonical-to-404", severity=Severity.HIGH,
                    summary=f"{path} canonicalises to {target}, which the crawl reached "
                            f"as a {chain['terminal']} — the canonical target is not there.",
                    subject=path, affected_urls=[page.url],
                    evidence={"canonical": canon, "terminal": chain["terminal"]},
                    recommendation="Point the canonical at a live page, or make it "
                                   "self-referencing if this page is the original.",
                ))
            elif verdict == "canonical-loop":
                findings.append(Finding(
                    dimension=self.code, check_id="canonical-loop", severity=Severity.HIGH,
                    summary=f"{path}'s canonical chain never reaches a page that owns "
                            "itself — it loops.",
                    subject=path, affected_urls=[page.url],
                    evidence={"chain": [n["path"] for n in chain["nodes"]]},
                    recommendation="Make one URL in the loop self-canonical and point the "
                                   "others at it.",
                ))
            elif verdict == "canonical-sitemap-conflict":
                findings.append(Finding(
                    dimension=self.code, check_id="canonical-sitemap-conflict",
                    severity=Severity.MEDIUM,
                    summary=f"{path} is in the sitemap, but its canonical points at "
                            f"{target}, which is not — the sitemap and the canonical "
                            "name different forms of the page.",
                    subject=path, affected_urls=[page.url],
                    evidence={"canonical": canon},
                    recommendation="Make the sitemap and the canonical agree — list the "
                                   "canonical form in the sitemap, or drop this one.",
                ))
        return findings

    def _sitemap_regression(self, crawl: CrawlResult, prior: dict | None) -> list[Finding]:
        """Declared sitemap URLs fell >=20% since the previous run (brief v18
        step AZ). Silent, never green, when there is no comparable prior: a
        first run has no baseline, so reporting a fall would be inventing one —
        the rule `prior_run`'s docstring states. The drop and its guard are
        `runs.sitemap_drop_fraction`, shared with `watch_changes` so an alert
        and this finding cannot disagree about what a regression is."""
        if not prior:
            return []
        from clauditseo.persistence.runs import sitemap_drop_fraction
        after_total = len(crawl.sitemap_entries)
        after_unread = any(not (s.status == 200 and not s.error)
                           for s in crawl.sitemaps)
        frac = sitemap_drop_fraction(prior.get("total", 0), prior.get("unread", False),
                                     after_total, after_unread)
        if frac is None:
            return []
        return [Finding(
            dimension=self.code, check_id="sitemap-regression", severity=Severity.HIGH,
            summary=f"Declared sitemap URLs fell {frac * 100:.0f}% since the last "
                    f"run — {prior['total']} to {after_total}.",
            subject="site", affected_urls=[crawl.start_url],
            evidence={"before": prior["total"], "after": after_total,
                      "drop_fraction": round(frac, 3)},
            recommendation="Confirm the drop is intentional. A sudden fall usually "
                           "means broken sitemap generation, not a removed section.")]

    # --- item 136q commit 2 ---------------------------------------------

    def _links_behind_js(self, crawl, context: dict) -> list[Finding]:
        """Internal links that exist only after the page renders.

        The link surface AFTER rendering succeeds. (The retired `js-rendering`
        brief asked whether the page renders at all; item 165.)

        **What a sample can and cannot say (operator, 2026-09-08).**
        `render_only` is a fact about ONE page - this anchor is in the
        rendered DOM and not in the initial HTML - so it is sound on any page
        the rendered pass visited. `orphaned_without_js` is a claim about the
        SITE, because orphaned means "not reachable by any initial-HTML path
        from any page": with five of twelve pages rendered, a destination
        that looks render-only from the sample may be linked in the initial
        HTML of one of the seven that were not. So those emit only when the
        rendered pass covered the whole crawl, and are `not_assessable`
        otherwise, naming the coverage. No bounded restatement - a hedged
        site claim still reads as a site answer.
        """
        rendered = context.get("rendered_anchors")
        if not rendered:
            return []
        cover = context.get("rendered_coverage") or {}
        seen, total = cover.get("rendered", 0), cover.get("pages", 0)
        whole_site = bool(total) and seen >= total

        html = [p for p in crawl.pages
                if (p.content_type or "").startswith("text/html")]
        host = urlsplit(crawl.start_url).netloc.lower()

        def internal(url: str) -> bool:
            try:
                net = urlsplit(url).netloc.lower()
            except ValueError:
                return False
            return not net or net == host

        # Every destination the initial HTML reaches, from any page.
        initial_any: dict[str, str] = {}
        for page in html:
            for link in (getattr(page, "link_details", None) or []):
                target = link.get("url") or ""
                if target and internal(target):
                    initial_any.setdefault(_norm(target), page.url)

        out: list[Finding] = []
        for url, anchors in sorted(rendered.items()):
            page = next((p for p in html if p.url == url), None)
            initial_here = {_norm(l.get("url") or "")
                            for l in (getattr(page, "link_details", None) or [])}
            extra = [a for a in anchors
                     if internal(a.get("url") or "")
                     and _norm(a.get("url") or "") not in initial_here]
            if not extra:
                continue

            evidence: dict = {
                "render_only": len(extra),
                "rendered_coverage": f"{seen} of {total} pages",
            }
            if whole_site:
                orphaned = [a for a in extra
                            if _norm(a.get("url") or "") not in initial_any]
                evidence["orphaned_without_js"] = len(orphaned)
                evidence["destinations"] = [
                    {"url": a["url"],
                     "first_reachable_via": (
                         f"initial html: {urlsplit(initial_any[_norm(a['url'])]).path or '/'}"
                         if _norm(a["url"]) in initial_any else "render only")}
                    for a in extra[:20]]
                severity = (Severity.HIGH if orphaned else Severity.MEDIUM)
            else:
                # Named, not guessed. The row says which question it cannot
                # answer and why, rather than answering it from a sample.
                evidence["not_assessable"] = {
                    "orphaned_without_js": "the rendered pass covered "
                                           f"{seen} of {total} pages, and "
                                           "orphaned is a claim about every "
                                           "page",
                    "destinations": "same reason",
                }
                severity = Severity.MEDIUM

            path = urlsplit(url).path or "/"
            out.append(Finding(
                dimension=self.code, check_id="links-behind-js",
                severity=severity,
                summary=f"{path} carries {len(extra)} internal link"
                        f"{'' if len(extra) == 1 else 's'} that appear only "
                        "after the page renders.",
                subject=path, affected_urls=[url], evidence=evidence,
                recommendation="Serve these links in the initial HTML, or "
                               "provide the same destinations in a crawlable "
                               "form, so a reader that does not run scripts "
                               "can reach them."))
        return out

    def _render_only(self, crawl, context: dict) -> list[Finding]:
        """Body text present only after JavaScript, per page (brief v18 step AZ).

        crawl.md's `render-only` names five signals — title, h1, body, links,
        JSON-LD. Links stay with `links-behind-js` (the operator's split,
        2026-09-09), which already carries the router-only-anchor signal with
        its whole-site orphan guard; title/h1/JSON-LD parity waits on the
        rendered pass recording those elements. What ships here is the body:
        the initial HTML is a near-empty shell while the rendered DOM holds real
        content, so a retrieval agent that does not run scripts reads a blank
        page.

        Sample-scoped, and it says so in its own summary. The rendered word
        count is `pagefacts.rendered_words` over the page's rendered text
        blocks (`text_blocks`, captured by the a11y pass), which counts each
        piece of text once: the blocks nest, and summing them counted a nav's
        words again for every link inside it. This summed them until item 145's
        BH report found `AIS/content-behind-js` answering the same question
        about the same blocks differently. The initial count is `extract_facts`'
        `word_count` off the crawl's raw HTML — the same reader the thin-content
        check uses. This is a claim about ONE visited page — "this page's body is
        in the rendered DOM and not the initial HTML" — sound wherever the
        rendered pass reached, so it needs no site-wide guard; a page the pass
        did not visit simply raises nothing rather than a hedged site answer."""
        blocks_by_url = context.get("text_blocks")
        if not blocks_by_url:
            return []
        cover = context.get("rendered_coverage") or {}
        seen, total = cover.get("rendered", 0), cover.get("pages", 0)

        raw_words = {}
        for page in html_pages(crawl.pages):
            raw_words[page.url] = extract_facts(page).word_count

        out: list[Finding] = []
        for url, blocks in sorted(blocks_by_url.items()):
            rendered = rendered_words(blocks)
            initial = raw_words.get(url)
            if initial is None:
                continue  # rendered a page the crawl's raw set does not hold
            if initial <= RENDER_ONLY_RAW_MAX and rendered >= RENDER_ONLY_RENDERED_MIN:
                path = urlsplit(url).path or "/"
                scope = (f" (assessed on the {seen} of {total} page(s) the "
                         "rendered pass visited)" if total else "")
                out.append(Finding(
                    dimension=self.code, check_id="render-only",
                    severity=Severity.MEDIUM,
                    summary=f"{path} carries {rendered} words of body text that "
                            f"appear only after the page renders — the initial "
                            f"HTML has {initial}"
                            f"{scope}.",
                    subject=path, affected_urls=[url],
                    evidence={"initial_html_words": initial,
                              "rendered_words": rendered,
                              "rendered_coverage": f"{seen} of {total} pages"},
                    recommendation="Server-render or pre-render the body so a "
                                   "reader that does not run scripts — most AI "
                                   "retrieval agents — gets the content, not an "
                                   "empty shell."))
        return out

    #: The share of this dimension answered without fetching a page —
    #: robots.txt, the sitemap and llms.txt are retrieved in their own right.
    #: The remainder is page-derived, so it drops out when nothing was
    #: fetched rather than scoring full marks on an empty crawl.
    SITE_SHARE = 0.35

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        page = scoring.page_coverage(context)
        return scoring.subscore(
            self.code, findings, self.default_weight, context,
            coverage=self.SITE_SHARE + (1 - self.SITE_SHARE) * page)

    # -- site level ---------------------------------------------------------

    def _site_checks(self, crawl: CrawlResult, site=None) -> list[Finding]:
        findings: list[Finding] = []
        start = crawl.start_url

        if crawl.robots_status != 200:
            findings.append(Finding(
                dimension=self.code, check_id="robots-missing", severity=Severity.HIGH,
                summary="robots.txt is missing or unreadable.",
                subject="site", affected_urls=[start],
                evidence={"robots_status": crawl.robots_status},
                recommendation="Serve a robots.txt at the site root, even a permissive one, "
                               "so crawlers get explicit guidance.",
            ))

        # `ai-crawler-blocked`: robots.txt denies an AI agent (item 137, brief
        # v18 step AZ, re-homed from AIS). Only when a robots.txt was read; its
        # absence is `robots-missing` above, not this. One row per agent with
        # its class (item 145 step BG), so a reader can tell a blocked index
        # agent from a blocked training agent. Severity is set here, where the
        # row is raised: with `ai_crawler_policy = block` the block is the
        # policy working, LOW and not a blocker; not stated, or `allow`, keeps
        # 137's HIGH blocker, because nothing says the block was chosen.
        if crawl.robots_txt:
            policy = RobotsPolicy(robots_url_for(start), crawl.robots_status,
                                  crawl.robots_txt)
            stated = (getattr(site, "ai_crawler_policy", None) or "").strip().lower() or None
            chosen = stated == "block"
            if chosen:
                why = "The site record says blocking AI crawlers is intended, so this is the policy working."
            elif stated == "allow":
                why = "The site record says AI crawlers are allowed, so this block contradicts it."
            else:
                why = "The site record states no AI crawler policy; confirm whether this block is intended."
            for bot, _ua, klass in UA_MATRIX_AGENTS:
                if klass not in BLOCK_CONSEQUENCE or policy.allows(start, bot):
                    continue
                findings.append(Finding(
                    dimension=self.code, check_id="ai-crawler-blocked",
                    severity=Severity.LOW if chosen else Severity.HIGH,
                    summary=f"robots.txt blocks {bot} ({klass}): "
                            f"{BLOCK_CONSEQUENCE[klass]}. {why}",
                    subject=f"ai-crawler-access:{bot}", affected_urls=[start],
                    evidence={"agent": bot, "class": klass,
                              "ai_crawler_policy": stated or "unstated",
                              # Read by triage's Blocker column: a registered
                              # blocker check, this row waived by the policy.
                              "blocker": not chosen,
                              "checked": list(AI_CRAWLERS)},
                    recommendation=("Nothing to change unless the policy has." if chosen else
                                    f"If {bot} should read the site, remove its Disallow from "
                                    "robots.txt; if the block is wanted, set the AI crawler "
                                    "policy to block on the site record."),
                ))

        # "No usable sitemap" is the union of three shapes: nothing declared and
        # the probed /sitemap.xml did not respond; a sitemap declared in robots
        # that could not be reached; a declared index whose only children failed.
        # None of them read a sitemap document and none is a broken-but-present
        # sitemap (`sitemap-invalid` owns those), so they are one finding, with a
        # summary that says which shape it is. A declared sitemap that returns an
        # HTTP error is invalid, not missing — the operator promised one and the
        # server answered wrongly — so it is excluded here via `_invalid_sitemaps`.
        read_ok = any(s.status == 200 and not s.error and not s.is_index
                      for s in crawl.sitemaps)
        declared_urls = [s.url for s in crawl.sitemaps if s.declared]
        if not crawl.sitemap_entries and not read_ok and not self._invalid_sitemaps(crawl):
            if declared_urls:
                summary = ("The sitemap declared in robots.txt could not be read "
                           f"({declared_urls[0]}"
                           + (f" and {len(declared_urls) - 1} other(s)"
                              if len(declared_urls) > 1 else "")
                           + "), so no sitemap is available to crawlers.")
            else:
                summary = ("No XML sitemap was found (none declared in robots.txt "
                           "and /sitemap.xml did not respond).")
            findings.append(Finding(
                dimension=self.code, check_id="sitemap-missing", severity=Severity.MEDIUM,
                summary=summary,
                subject="site", affected_urls=[start],
                evidence={"sitemap_urls": crawl.sitemap_urls,
                          "declared": declared_urls},
                recommendation="Publish an XML sitemap and declare it in robots.txt.",
            ))
        else:
            # `unreachable`: a URL the sitemap publishes that the crawl could
            # not reach (brief v18 step AZ). This is the set the check called
            # `sitemap-coverage` used to emit; `crawl.md` reassigns the id, and
            # `sitemap-coverage` now means the reverse — reached pages absent
            # FROM the sitemap, in `_sitemap_health`.
            #
            # Attempts, deliberately, not `eligible()`: "did the crawler visit
            # this sitemap entry", where a 404 or a PDF *was* visited and
            # reporting it as absent would name the wrong defect.
            crawled = {urlsplit(p.url).path or "/" for p in crawl.pages}
            # Excluded, not unreachable: a URL the site disallowed in robots is
            # a deliberate choice with its own checks. `robots_blocked` is
            # appended to the result rather than to `crawl.pages`, so without
            # this exclusion a disallowed sitemap URL landed in `missing` and
            # read as the site failing to link a page it told crawlers to skip.
            blocked = {urlsplit(u).path or "/" for u in crawl.robots_blocked}
            on_site = [u for u in crawl.sitemap_entries
                       if urlsplit(u).netloc == urlsplit(start).netloc]
            unreached = [u for u in on_site
                         if (urlsplit(u).path or "/") not in crawled
                         and (urlsplit(u).path or "/") not in blocked]

            # Reachability is a claim about the whole site, so only a crawl
            # that tried to reach the whole site can make it. Three ways it
            # cannot, and they are not the same: budget (`truncated_by`), scope
            # (`nav`), or a pulse (`T1`). A nav crawl is not truncated — it
            # reached everything it set out to — so a 20-page nav crawl against
            # a 271-URL sitemap must not report "251 unreachable"; that is the
            # scope doing its job, described as a site defect.
            partial = (crawl.truncated_by is not None
                       or crawl.scope != "site"
                       or crawl.tier is Tier.T1)
            if partial and on_site:
                why = ("this audit was scoped to the navigation"
                       if crawl.scope != "site"
                       else "this was a pulse, which fetches three pages by design"
                       if crawl.tier is Tier.T1
                       else f"the crawl stopped early ({crawl.truncated_by})")
                reached = sum(1 for u in on_site
                              if (urlsplit(u).path or "/") in crawled)
                findings.append(Finding(
                    dimension=self.code, check_id="unreachable-not-assessed",
                    severity=Severity.INFO, scope_statement=True,
                    summary=f"Reachability not assessed — {why}. "
                            f"{reached} of {len(on_site)} sitemap URLs were "
                            "crawled, so the rest are unvisited rather than "
                            "unreachable.",
                    subject="unreachable", affected_urls=[],
                    evidence={"sitemap_entries": len(on_site), "crawled": reached,
                              "scope": crawl.scope, "tier": crawl.tier.value,
                              "truncated_by": crawl.truncated_by},
                    recommendation="Run a full crawl at T2 or T3 to judge whether "
                                   "sitemap URLs are genuinely unreachable.",
                ))
            elif unreached:
                findings.append(Finding(
                    dimension=self.code, check_id="unreachable", severity=Severity.MEDIUM,
                    summary=f"{len(unreached)} of {len(on_site)} sitemap URL(s) are "
                            "published but the crawl could not reach them — no "
                            "internal link path, and not disallowed in robots.",
                    subject="unreachable", affected_urls=unreached[:20],
                    # The frame the list was cut from (Q-26): the summary states
                    # the full count and only twenty are stored.
                    affected_total=len(unreached),
                    evidence={"unreached_count": len(unreached),
                              "sitemap_entries": len(on_site), "sample": unreached[:20]},
                    recommendation="Link every published page from the site's own "
                                   "navigation or body, or remove dead entries "
                                   "from the sitemap.",
                ))

        findings += self._sitemap_health(crawl)

        # `not-https` and `security-headers` were raised here until item 143
        # step BD moved Security & transport to its own dimension (`sec.py`).
        return findings

    @staticmethod
    def _invalid_sitemaps(crawl: CrawlResult) -> list[tuple[str, str]]:
        """Sitemaps that were retrieved and are genuinely broken — as opposed
        to simply absent, which is `sitemap-missing`'s to report.

        A sitemap is invalid when it: parsed as a 200 body that would not parse
        (malformed XML); exceeds the 50,000-URL protocol cap; or was **declared**
        (robots pointed at it, or a sitemap index did) yet returns an HTTP error.
        A **probed** `/sitemap.xml` that 404s or will not connect is not invalid
        — nothing claimed it existed — and a pure transport failure (no HTTP
        status came back) is unreachability, not malformation; both fall to
        `sitemap-missing`. `disallowed by robots.txt` carries no HTTP status and
        so is excluded here too."""
        bad: list[tuple[str, str]] = []
        for s in crawl.sitemaps:
            if s.status == 200 and s.error:
                bad.append((s.url, f"unparseable: {s.error}"))
            elif s.entry_count > SITEMAP_MAX_URLS:
                bad.append((s.url, f"{s.entry_count} URLs, over the {SITEMAP_MAX_URLS:,} cap"))
            elif s.declared and s.status is not None and s.status >= 400:
                bad.append((s.url, f"HTTP {s.status}"))
        return bad

    def _sitemap_health(self, crawl: CrawlResult) -> list[Finding]:
        """Sitemap files judged for malformation and freshness (brief v18 step
        AZ). Both read the sitemap XML itself, in full whatever the page
        budget, so neither carries the partial-crawl caveat `sitemap-coverage`
        needs — a truncated page crawl does not truncate the sitemap parse."""
        findings: list[Finding] = []

        bad = self._invalid_sitemaps(crawl)
        if bad:
            findings.append(Finding(
                dimension=self.code, check_id="sitemap-invalid", severity=Severity.HIGH,
                summary=f"{len(bad)} sitemap file(s) are invalid: "
                        + "; ".join(f"{u} ({why})" for u, why in bad[:5])
                        + ("…" if len(bad) > 5 else "") + ".",
                subject="site", affected_urls=[u for u, _ in bad[:20]],
                affected_total=len(bad),
                evidence={"invalid": [{"url": u, "reason": why} for u, why in bad],
                          "size_50mb": "not judged — the crawl does not keep each "
                                       "file's byte size"},
                recommendation="Fix or remove the sitemap so every declared file "
                               "parses, returns 200, and stays under 50,000 URLs.",
            ))

        entries = [u for u in crawl.sitemap_entries
                   if urlsplit(u).netloc == urlsplit(crawl.start_url).netloc]

        # sitemap-404s and sitemap-noindex: a URL the sitemap promises is
        # indexable, judged against what the crawl actually got when it
        # fetched it. Only URLs the crawl REACHED are judged — an unfetched
        # declared URL is `sitemap-coverage`'s to speak to, not this one — so
        # there is no partial-crawl guessing: every row is a definite status
        # or a definite directive the crawler read on the page.
        def _p(u: str) -> str:
            return (urlsplit(u).path or "/").rstrip("/").lower() or "/"

        status_by_path = {_p(page.url): page.status for page in crawl.pages}
        noindex_paths = set()
        for page in html_pages(crawl.pages):
            f = extract_facts(page)
            if f.meta_robots and "noindex" in f.meta_robots.lower():
                noindex_paths.add(_p(page.url))

        dead = [u for u in entries if (status_by_path.get(_p(u)) or 0) >= 400]
        if dead:
            findings.append(Finding(
                dimension=self.code, check_id="sitemap-404s", severity=Severity.MEDIUM,
                summary=f"{len(dead)} URL(s) declared in the sitemap return an "
                        "error when fetched.",
                subject="site", affected_urls=dead[:20], affected_total=len(dead),
                evidence={"dead": [{"url": u, "status": status_by_path.get(_p(u))}
                                   for u in dead[:20]], "count": len(dead)},
                recommendation="Remove dead URLs from the sitemap, or fix/redirect "
                               "them — a sitemap that lists errors wastes crawl budget.",
            ))

        noindexed = [u for u in entries if _p(u) in noindex_paths]
        if noindexed:
            findings.append(Finding(
                dimension=self.code, check_id="sitemap-noindex", severity=Severity.MEDIUM,
                summary=f"{len(noindexed)} URL(s) in the sitemap carry a noindex "
                        "tag — the sitemap says index them, the page says do not.",
                subject="site", affected_urls=noindexed[:20],
                affected_total=len(noindexed),
                evidence={"noindexed": noindexed[:20], "count": len(noindexed)},
                recommendation="Decide per URL: if it should rank, remove the noindex; "
                               "if not, remove it from the sitemap. The two must agree.",
            ))

        # sitemap-coverage: reached indexable pages the sitemap does NOT list
        # (brief v18 step AZ — the reverse of what this id meant before AZ,
        # which `unreachable` now carries). A page the crawl fetched that
        # returns 200, renders HTML and is not noindexed, yet is absent from
        # the sitemap: the sitemap is incomplete. Only where a sitemap was
        # actually read — a 200 sitemap document, even an empty one, of which
        # "every page is absent" is exactly the right thing to say. A probed
        # `/sitemap.xml` that 404s is not a sitemap, so its absence is
        # `sitemap-missing`'s, not "every page you have is missing from it".
        read_ok = any(s.status == 200 and not s.error and not s.is_index
                      for s in crawl.sitemaps)
        if read_ok or crawl.sitemap_entries:
            declared = {_p(u) for u in entries}
            absent = [page.url for page in html_pages(crawl.pages)
                      if page.status == 200
                      and _p(page.url) not in declared
                      and _p(page.url) not in noindex_paths]
            if absent:
                findings.append(Finding(
                    dimension=self.code, check_id="sitemap-coverage",
                    severity=Severity.MEDIUM,
                    summary=f"{len(absent)} indexable page(s) the crawl reached are "
                            "absent from the sitemap.",
                    subject="site", affected_urls=absent[:20], affected_total=len(absent),
                    evidence={"absent": absent[:20], "count": len(absent)},
                    recommendation="Add every indexable page to the sitemap, or "
                                   "regenerate it from the CMS so it lists them all.",
                ))

        # sitemap-lastmod-stale: the <lastmod> is useless to a crawler when it
        # is absent everywhere, identical everywhere (auto-stamped on build),
        # or in the future.
        if len(entries) > 1:
            stamped = {u: crawl.sitemap_lastmod[u] for u in entries
                       if crawl.sitemap_lastmod.get(u)}
            reason = None
            if not stamped:
                reason = "no <lastmod> on any entry"
            elif len(stamped) == len(entries) and len(set(stamped.values())) == 1:
                reason = ("every entry carries the same <lastmod> "
                          f"({next(iter(stamped.values()))})")
            elif (future := [u for u, d in stamped.items() if _lastmod_in_future(d)]):
                reason = f"{len(future)} entry(ies) carry a <lastmod> in the future"
            if reason:
                findings.append(Finding(
                    dimension=self.code, check_id="sitemap-lastmod-stale",
                    severity=Severity.LOW,
                    summary=f"Sitemap <lastmod> is unreliable: {reason}.",
                    subject="site", affected_urls=[crawl.start_url],
                    evidence={"entries": len(entries), "with_lastmod": len(stamped),
                              "reason": reason},
                    recommendation="Stamp each URL's <lastmod> from its real last-"
                                   "modified date so crawlers can prioritise changes.",
                ))
        return findings

    # -- page level ---------------------------------------------------------

    def _link_checks(self, crawl: CrawlResult) -> list[Finding]:
        """Internal links the site writes with campaign tracking parameters.

        Measured on stored run `fe97cc61` (www.acme.com.au, T3): the sitemap
        declares 272 entries and not one contains a `?`, yet eleven
        parameterised URLs were fetched and every one records
        `discovered_via: "link"`. The site links to itself with campaign
        parameters, in its own markup, and a search engine follows those links
        exactly as this crawler does. Two costs, and the second is the one a
        client has never been told about:

        - a visitor who arrived from a paid campaign and then clicks an
          internal `?utm_source=` link is re-stamped with that link's
          parameters, so the campaign that won the visit loses the credit;
        - the link manufactures a crawlable duplicate out of the site's own
          navigation, spending crawl budget and splitting internal link
          equity across spellings of one page.

        **Grouped per source page, not per tagged target.** Per target reads
        better — "these six pages all link to /apply with a tag" — and it is
        wrong for a reason that is not presentational. A finding's
        `affected_urls` is what `_apply_states` may clear it on, and the rule
        there is `pages & crawled`: ANY named page revisited is enough. A
        per-target finding names every source page, so a verify or a page
        refresh that re-read one of them could clear a finding about links on
        pages nobody looked at. Per source page there is exactly one, so the
        finding can only be cleared by re-reading the page whose markup is the
        defect. It is also the unit of the fix: one page, one template, one
        edit.

        One finding per link was the other option and is noise — six of the
        twenty parameterised links in that run sit on two pages.
        """
        findings: list[Finding] = []
        for page in html_pages(crawl.pages):
            tagged: list[dict] = []
            for link in page.link_details:
                # The link as written, which is the subject here — not the
                # crawl's identity for its target. Since relay item 101
                # `normalise_url` strips tracking parameters, so `link["url"]`
                # cannot carry one and reading it here would search a
                # population of zero while passing; `href` is the spelling the
                # markup wrote and is what this check is about.
                # `tests/test_internal_links_carry_tracking_parameters.py
                # ::test_the_parser_still_hands_the_check_a_tagged_url` is the
                # guard that keeps the two apart.
                #
                # The fallback is not defensive padding: link details built
                # before 0.10.0 — stored evidence, and the hand-built dicts in
                # that file's 404 case — have no `href`, and for those `url`
                # *is* the raw spelling, because nothing was being stripped.
                params = tracking_params_in(link.get("href") or link["url"])
                if not params:
                    continue
                raw = link.get("href") or link["url"]
                tagged.append({
                    "target": raw,
                    "clean_target": strip_tracking_params(raw),
                    "anchor": link.get("anchor", ""),
                    "region": link.get("region") or "body",
                    "rel": link.get("rel", ""),
                    "params": [k for k, _ in params],
                    "empty_valued": [k for k, v in params if not v],
                })
            if not tagged:
                continue

            path = urlsplit(page.url).path or "/"
            n = len(tagged)
            keys = sorted({k for t in tagged for k in t["params"]})
            empty = sorted({k for t in tagged for k in t["empty_valued"]})
            summary = (
                f"{n} internal link{'' if n == 1 else 's'} on {path} "
                f"{'points' if n == 1 else 'point'} at this site with campaign "
                f"tracking parameters attached ({', '.join(keys)}).")
            if empty:
                # Said in the summary rather than left in the evidence blob.
                # A malformed link is a defect in their markup rather than
                # merely an unwise one, and a statement about a value that
                # reaches only a panel nobody opens has not been made.
                summary += (
                    f" {' and '.join(empty)} "
                    f"{'is' if len(empty) == 1 else 'are'} written with no "
                    "value, so the site's own templating did not substitute "
                    "one and the visit is attributed to an empty source.")
            findings.append(Finding(
                dimension=self.code, check_id="internal-link-tracking-params",
                severity=Severity.MEDIUM, summary=summary,
                subject=path, affected_urls=[page.url],
                # Capped with the untruncated total beside it: this is
                # crawl-derived and a page free to carry four hundred tagged
                # links must not be able to decide the size of a stored blob
                # or the height of a panel.
                evidence={"links": tagged[:LINK_EVIDENCE_CAP],
                          "links_total": n,
                          "parameters": keys,
                          "malformed": empty},
                recommendation=(
                    "Point these internal links at the clean URL — the same "
                    "target with the tracking parameters removed. Campaign "
                    "parameters belong on external placements the site does "
                    "not control; on the site's own navigation each one "
                    "overwrites the visitor's original acquisition source and "
                    "manufactures a crawlable duplicate of a page the site "
                    "already has."),
            ))
        return findings

    def _page_checks(self, crawl: CrawlResult,
                     traces: dict | None = None) -> list[Finding]:
        findings: list[Finding] = []
        for page in crawl.pages:
            path = urlsplit(page.url).path or "/"
            if page.status >= 400:
                findings.append(Finding(
                    dimension=self.code, check_id="http-status-error",
                    severity=Severity.CRITICAL if page.status >= 500 else Severity.HIGH,
                    summary=f"{page.status} response at {path}.",
                    subject=path, affected_urls=[page.url],
                    evidence={"status": page.status, "requested": page.requested_url},
                    recommendation="Fix or redirect the broken URL; update internal links "
                                   "that point at it.",
                ))
            if len(page.redirect_chain) >= 2:
                findings.append(Finding(
                    dimension=self.code, check_id="redirect-chain", severity=Severity.MEDIUM,
                    summary=f"Redirect chain of {len(page.redirect_chain)} hops before "
                            f"reaching {path}.",
                    subject=urlsplit(page.requested_url).path or "/",
                    affected_urls=[page.requested_url, page.url],
                    evidence={"chain": page.redirect_chain, "final": page.url},
                    recommendation="Point the original URL directly at the final "
                                   "destination in one hop.",
                ))
            # A redirect that lands on an error (item 137, brief v18 step BA).
            # A crawl-state fact: the chain was followed and its end is a 4xx/5xx,
            # so the redirect points at a page that is not there. HIGH per the
            # brief; http-status-error also names the dead URL, but this names
            # the broken redirect into it, which is the thing to fix.
            if page.redirect_chain and page.status >= 400:
                findings.append(Finding(
                    dimension=self.code, check_id="redirect-to-404", severity=Severity.HIGH,
                    summary=f"A redirect from {urlsplit(page.requested_url).path or '/'} "
                            f"ends at a {page.status} — the destination is not there.",
                    subject=urlsplit(page.requested_url).path or "/",
                    affected_urls=[page.requested_url, page.url],
                    evidence={"chain": page.redirect_chain, "final": page.url,
                              "final_status": page.status},
                    recommendation="Point the redirect at a live page, or remove it and "
                                   "return the correct status at the original URL.",
                ))
            # A temporary redirect on what should be a permanent move (item 137,
            # brief v18 step BA; the capture that unblocked it is FEATURES F-13).
            # Any hop that answered 302/303/307 is temporary; a permanent move
            # should be a 301/308. LOW. Empty redirect_statuses (a run crawled
            # before the capture) fires nothing, which is the deferral resolving.
            temporary = sorted({s for s in (page.redirect_statuses or [])
                                if s in (302, 303, 307)})
            if temporary:
                findings.append(Finding(
                    dimension=self.code, check_id="redirect-temporary", severity=Severity.LOW,
                    summary=f"The redirect to {path} uses a temporary status "
                            f"({', '.join(map(str, temporary))}) — a search engine keeps "
                            "crediting the old URL until it is made permanent.",
                    subject=urlsplit(page.requested_url).path or "/",
                    affected_urls=[page.requested_url, page.url],
                    evidence={"chain": page.redirect_chain,
                              "statuses": page.redirect_statuses, "final": page.url},
                    recommendation="If the move is permanent, return 301 (or 308) instead "
                                   "of the temporary status so the destination is credited.",
                ))

        # `noindex-page` was one HIGH blocker on any noindex page, with a
        # summary that asserted "internally linked" without checking inlinks
        # (item 137, brief v18 step BA split it). Two precise checks now: a
        # noindex page that IS linked (the real problem — a page you point at
        # and tell Google to drop) and one merely declared in the sitemap.
        inlinks = crawl.inlinks()
        sitemap_paths = {_norm_path(u) for u in crawl.sitemap_entries}
        for page in html_pages(crawl.pages):
            facts = extract_facts(page)
            findings.extend(_viewport_checks(self.code, facts, page.url))
            # The six that need the render (brief 160 steps 1-3). Silent where
            # the page carries no trace: 3b's shape -- the instrument that
            # looked answers, and item 157's `not_assessed` covers the rest on
            # the screen rather than a proxy guessing here.
            findings.extend(_mobile_render_checks(
                self.code, facts, page.url, (traces or {}).get(page.url)))
            findings.extend(_head_divergent(
                self.code, facts, page.url, (traces or {}).get(page.url)))
            robots = f"{facts.meta_robots or ''} {page.x_robots_tag or ''}".lower()
            if "noindex" in robots:
                # Distinct source pages, self excluded. The brief's "nav or >= 3
                # pages" is implemented as the >= 3 arm alone: the crawl has no
                # nav/body link distinction, and a nav link is on ~every page,
                # so the count arm subsumes it (channel 20260910-1430).
                sources = {u for u in inlinks.get(page.url, []) if u != page.url}
                if len(sources) >= MIN_INLINKS:
                    findings.append(Finding(
                        dimension=self.code, check_id="noindex-linked", severity=Severity.HIGH,
                        summary=f"{facts.path} carries a noindex tag but is linked from "
                                f"{len(sources)} pages — confirm this is intentional.",
                        subject=facts.path, affected_urls=[page.url],
                        evidence={"meta_robots": facts.meta_robots,
                                  "x_robots_tag": page.x_robots_tag, "inlinks": len(sources)},
                        recommendation="Remove the noindex if the page should rank; otherwise "
                                       "remove the internal links that point at it.",
                    ))
                if _norm_path(page.url) in sitemap_paths:
                    findings.append(Finding(
                        dimension=self.code, check_id="noindex-in-sitemap", severity=Severity.LOW,
                        summary=f"{facts.path} is declared in the sitemap but carries a noindex "
                                "tag — the sitemap invites indexing the page refuses.",
                        subject=facts.path, affected_urls=[page.url],
                        evidence={"meta_robots": facts.meta_robots,
                                  "x_robots_tag": page.x_robots_tag},
                        recommendation="Drop the URL from the sitemap, or remove the noindex if "
                                       "the page should be indexed — one or the other.",
                    ))
            # meta robots and X-Robots-Tag disagree on indexation (item 137,
            # brief v18 step BA). Both present and one noindexes while the other
            # does not: the two mechanisms give a crawler contradictory
            # instructions, and which wins is engine-specific. MEDIUM.
            if facts.meta_robots and page.x_robots_tag:
                meta_ni = "noindex" in facts.meta_robots.lower()
                xr_ni = "noindex" in page.x_robots_tag.lower()
                if meta_ni != xr_ni:
                    findings.append(Finding(
                        dimension=self.code, check_id="meta-robots-conflict",
                        severity=Severity.MEDIUM,
                        summary=f"{facts.path} disagrees with itself on indexation: "
                                f"meta robots says {'noindex' if meta_ni else 'index'} "
                                f"and X-Robots-Tag says {'noindex' if xr_ni else 'index'}.",
                        subject=facts.path, affected_urls=[page.url],
                        evidence={"meta_robots": facts.meta_robots,
                                  "x_robots_tag": page.x_robots_tag},
                        recommendation="Make the two instructions agree — decide whether the "
                                       "page should be indexed and set both to match.",
                    ))
        return findings


registry.register(TechnicalModule())
