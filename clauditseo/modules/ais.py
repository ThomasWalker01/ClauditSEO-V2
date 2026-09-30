"""AIS — AI-Surface dimension.

How the site presents to AI assistants: llms.txt and structural answer-
extractability. The meaning-level extractability call is the AIS-J analyst's
job (P5). Robots access for the AI user agents was `ai-crawler-blocked`,
re-homed to TEC as a crawl-access rule (item 137, brief v18 step AZ).
"""

from __future__ import annotations

import re

from clauditseo.crawler.types import CrawlResult
from clauditseo.crawler.ua_matrix import BLOCK_CONSEQUENCE, REFUSAL_STATUSES, agent_class, probe_urls
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier

from .pagefacts import extract_facts, html_pages, rendered_words

#: The part's registered severities, from `ai-surface.md` (item 145): the
#: free checks this module raises and the analysis checks only the brief
#: emits. `entity-unnamed` has no default in the prompt; MEDIUM is this
#: product's, as the module raises it.
DEFAULT_SEVERITY: dict[str, Severity] = {
    "edge-blocks-ai-ua": Severity.HIGH, "ua-sensitive": Severity.HIGH,
    "entity-unresolvable": Severity.HIGH, "content-behind-js": Severity.HIGH,
    "id-page-absent": Severity.MEDIUM, "entity-type-generic": Severity.MEDIUM,
    "entity-footprint-unlinked": Severity.MEDIUM, "entity-unnamed": Severity.MEDIUM,
    "entity-enrichment": Severity.MEDIUM, "entity-alignment": Severity.MEDIUM,
    "answer-liftable": Severity.MEDIUM, "llms-txt-stale": Severity.MEDIUM,
    "llms-txt-coverage": Severity.MEDIUM, "llms-txt-conflict": Severity.MEDIUM,
    "llms-txt-thin": Severity.LOW,
    "ai-crawler-allowed-unstated": Severity.INFO, "llms-txt-missing": Severity.INFO,
    "llms-txt-authored": Severity.INFO, "noai-meta": Severity.INFO,
    "ai-experience-unmeasured": Severity.INFO,
}
#: Free checks that cannot be answered while a site-record field is empty
#: (channel 20260915-2045): with no row on a run and every named field empty,
#: `runs.not_assessed_payload` reports the check not assessed, naming the field,
#: rather than letting the silence read as a pass (157). One check today; the
#: table is where the others go when they are asked for.
RECORD_FIELDS: dict[str, tuple[str, ...]] = {"entity-unresolvable": ("sameas_sources",)}

#: The analysis checks: judged by the AI surface brief, raised by no sweep.
BRIEF_ONLY_CHECKS = frozenset({
    "llms-txt-coverage", "llms-txt-thin", "llms-txt-conflict", "llms-txt-authored",
    "id-page-absent", "entity-type-generic", "entity-footprint-unlinked",
    "entity-alignment", "entity-enrichment", "answer-liftable"})

EXTRACTABILITY_MIN_WORDS = 500

#: Below this, the raw HTML carries too little to judge structure either way.
#: Not a second extractability threshold and deliberately nowhere near 500 —
#: lowering that one would trade a false negative for a false positive on thin
#: pages that render perfectly well. This asks a different question: was there
#: anything to read? `cnt.py`'s `THIN_WORDS = 150` is the closest precedent,
#: and it excludes zero on purpose; here zero is the strongest case, not the
#: excluded one.
EXTRACTABILITY_SHELL_WORDS = 50

#: `edge-blocks-ai-ua`'s "materially shorter": a 200 to an AI agent whose body
#: is under this share of the crawl's own body for the same URL. A challenge or
#: interstitial served with a 200 is the case a status column cannot see.
EDGE_SHORT_BODY_RATIO = 0.5

#: Response headers that name a challenge outright, whatever the status.
CHALLENGE_HEADERS = ("cf-mitigated",)


#: `ai-experience-unmeasured`'s sentence, verbatim from `ai-surface.md`'s
#: Block 2 so the free row and the brief's readable line say the same thing.
UNMEASURED = ("Whether any AI system fetches, indexes, cites or summarises this "
              "site is not observable from a crawl; nothing above claims it is.")

#: `content-behind-js`: the share of a page's rendered words present in its
#: initial HTML below which the row fires (the prompt's registry default).
CONTENT_BEHIND_JS_SHARE = 0.50
#: Below this many rendered words there is too little text for a share to
#: mean anything; a contact page of forty words is not a render dependency.
CONTENT_BEHIND_JS_MIN_WORDS = 100

#: The directive tokens `noai-meta` reads, in meta robots or X-Robots-Tag.
NOAI_TOKENS = ("noai", "noimageai")

_MD_LINK = re.compile(r"\]\((https?://[^)\s]+)\)")
_BARE_URL = re.compile(r"(?<![(\[])\bhttps?://[^\s)<>\]]+")


def _norm(url: str) -> str:
    from urllib.parse import urlsplit
    s = urlsplit(url.strip())
    return f"{s.netloc.lower().removeprefix('www.')}{(s.path or '/').rstrip('/') or '/'}"


def ua_differences(crawl: CrawlResult) -> list[dict]:
    """AI agents served a materially different document from the crawl's own
    at the same URL (`ua-sensitive`), by the parity probe's comparison and
    thresholds. Scoped to the UA strings the matrix used. A URL where the
    edge refused the agent is not a served difference (`edge-blocks-ai-ua`
    owns it), and the search agents are `bot-parity`'s."""
    from clauditseo.crawler.parity import compare, document
    served = {p.url: p for p in crawl.pages}
    blocked = {(h["agent"], r["url"]) for h in edge_blocks(crawl) for r in h["responses"]}
    out = []
    for row in getattr(crawl, "ua_matrix", None) or []:
        klass = row.get("agent_class") or agent_class(row.get("agent") or "")
        if klass in (None, "search") or row.get("sent") is False:
            continue
        diffs = []
        for url, doc in (row.get("docs") or {}).items():
            base = served.get(url)
            if base is None or (row["agent"], url) in blocked or doc.get("status") != 200:
                continue
            got = compare(document(base), doc)
            if got["verdict"] in ("named", "size"):
                diffs.append({"url": url, "verdict": got["verdict"],
                              "named": got["named"], "size": got["size"]})
        if diffs:
            out.append({"agent": row["agent"], "class": klass, "urls": diffs})
    return out


def llms_txt_urls(text: str | None) -> list[str]:
    """The URLs an llms.txt lists, link lines first, in file order, once each."""
    seen, out = set(), []
    for m in [*_MD_LINK.finditer(text or ""), *_BARE_URL.finditer(text or "")]:
        url = m.group(1) if m.re is _MD_LINK else m.group(0)
        url = url.rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def edge_blocks(crawl: CrawlResult) -> list[dict]:
    """Every AI agent the edge refused at a URL robots.txt permits, from the UA
    matrix (item 145 step BG): a status other than 200, a challenge header, or
    a body materially shorter than the crawl's own. One entry per agent, with
    each response that showed it. Search agents are `ua-server-refusal`'s, and
    a robots token is never sent, so neither is read here."""
    matrix = getattr(crawl, "ua_matrix", None) or []
    urls = [crawl.start_url] + probe_urls(crawl.start_url, crawl.pages)
    served = {p.url: p for p in crawl.pages}
    out = []
    for row in matrix:
        klass = row.get("agent_class") or agent_class(row.get("agent") or "")
        if (klass in (None, "search") or row.get("sent") is False
                or row.get("robots") != "allow"):
            continue
        statuses = [row.get("home_status"), *(row.get("probe_status") or [])]
        lengths = [row.get("home_body_len"), *(row.get("probe_body_len") or [])]
        headers = [row.get("headers") or {}, *(row.get("probe_headers") or [])]
        seen = []
        for i, (url, status) in enumerate(zip(urls, statuses)):
            if status is None:            # nothing came back; not a block
                continue
            sig = headers[i] if i < len(headers) else {}
            ref = served.get(url)
            ref_len = len((ref.content or "").encode("utf-8")) if ref and ref.status == 200 else None
            got_len = lengths[i] if i < len(lengths) else None
            if any(h in sig for h in CHALLENGE_HEADERS):
                reason = "challenge"
            elif status != 200 and (ref_len is not None or status in REFUSAL_STATUSES):
                reason = "status"
            elif (status == 200 and ref_len and got_len is not None
                  and got_len < ref_len * EDGE_SHORT_BODY_RATIO):
                reason = "short body"
            else:
                continue
            seen.append({"url": url, "status": status, "reason": reason,
                         "body_len": got_len, "browser_body_len": ref_len,
                         "signature": sig})
        if seen:
            out.append({"agent": row.get("agent"), "class": klass, "responses": seen})
    return out


def _unassessable(facts) -> bool:
    """The page returned a shell and the content arrives from somewhere else.

    Both halves are required. Thin HTML *with* scripts is a page whose content
    most likely rendered client-side, so the crawl saw a fraction of it and
    `poor-extractability` had no input. Thin HTML with **no** scripts is just a
    short page — the check does not apply, and there is nothing to report.
    Without the second half every contact page in the corpus becomes a finding.
    """
    return (facts.word_count < EXTRACTABILITY_SHELL_WORDS
            and bool(facts.script_srcs))


class AiSurfaceModule:
    code = "AIS"
    name = "AI-Surface"
    default_weight = scoring.DEFAULT_WEIGHTS["AIS"]
    #: **The second argued one, and it departs from what Q-17's answer
    #: predicted for this dimension** — the answer expected AIS to declare
    #: itself site-only, on the strength of 0 page-naming findings against 11
    #: site-scoped in the operator's database. Declared True here, because
    #: the source says otherwise and the source is what Q-17 chose option (C)
    #: to read:
    #:
    #:   * `extractability-not-assessed` and `poor-extractability` both come
    #:     from `extract_facts(page)` over a single document — a word count,
    #:     a script count and a heading list — and are attributed to
    #:     `page.url`. Re-reading that one URL re-measures both exactly.
    #:   * `llms-txt-missing` is site-scoped outright.
    #:
    #: (`ai-crawler-blocked` was the fourth, a robots.txt property re-homed to
    #: TEC at item 137; its departure does not weaken the case — the two
    #: genuinely per-page checks are what carry it.)
    #:
    #: Two of three are genuinely per-page, so the offer stands. The 0/11
    #: split is a property of the sample, not of the dimension: a corpus of
    #: sites that all lack an llms.txt produces 11 `llms-txt-missing` rows
    #: and nothing else, and neither extractability check fires unless a page
    #: is a script-driven shell or runs 500+ words with no subheadings. That
    #: is the same mistake in the same shape as the fixture reading Q-17
    #: rejected for PRF (KI-55), one level up — a corpus standing in for the
    #: tree.
    #:
    #: Declaring False here would also regress a guarded decision already in
    #: the tree: `tests/test_a_page_refresh_is_offered_only_where_a_page_can
    #: _change_it.py` asserts this dimension keeps its page control and
    #: argues why, from the same two checks.
    measured_per_page = True

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        findings: list[Finding] = []

        if crawl.llms_txt_status != 200:
            findings.append(Finding(
                dimension=self.code, check_id="llms-txt-missing", severity=Severity.INFO,
                summary="No llms.txt file found.",
                subject="llms-txt", affected_urls=[],
                evidence={"status": crawl.llms_txt_status},
                recommendation="Consider publishing an llms.txt summarising the site's "
                               "key pages for AI assistants.",
            ))

        # `edge-blocks-ai-ua` (item 145 step BG): free, HIGH, never held and
        # never softened by `ai_crawler_policy`, which declares intent for
        # robots.txt, not for the edge. It names no vendor unless a header
        # does, and never calls the block intentional.
        # The operator's per-agent edge declaration (channel 20260915-1430)
        # is what waives a row to LOW; `ai_crawler_policy` never does.
        site = context.get("site")
        declared_agents = {t.strip() for t in
                           (getattr(site, "ai_edge_blocked_agents", None) or "").split(",")
                           if t.strip()}
        for hit in edge_blocks(crawl):
            first = hit["responses"][0]
            vendor = (first["signature"].get("server") or "").strip()
            declared = hit["agent"] in declared_agents
            hit = {**hit, "declared": declared,
                   # Where the probe stood: our own address, not the vendor's.
                   "vantage": "unverified-ip",
                   "field": "not pulled"}
            findings.append(Finding(
                dimension=self.code, check_id="edge-blocks-ai-ua",
                severity=Severity.LOW if declared else Severity.HIGH,
                summary=(f"{hit['agent']} ({hit['class']}) is permitted by robots.txt, but "
                         f"{first['url']} answered it with "
                         + (f"status {first['status']}" if first["reason"] == "status" else
                            "a challenge" if first["reason"] == "challenge" else
                            f"{first['body_len']} bytes against {first['browser_body_len']} to the crawl")
                         + (f" (server: {vendor})" if vendor else "")
                         + f": {BLOCK_CONSEQUENCE[hit['class']]}. "
                         + (f"The site record says {hit['agent']} is blocked at the firewall "
                            "deliberately, so this is the policy working." if declared else
                            "Measured under this crawler's name from an unverified IP; whether "
                            "the vendor's real crawler is exempted at the firewall is not "
                            "measurable without field data.")),
                subject=f"edge-ua:{hit['agent']}", affected_urls=[r["url"] for r in hit["responses"]],
                evidence=hit,
                recommendation=("Nothing to change unless the policy has." if declared else
                                "Find where this crawler is refused (CDN, WAF, bot manager or "
                                "origin rule) and decide whether that refusal is wanted; if it "
                                "is, tick the crawler under Blocked at the firewall on purpose."),
            ))

        for page in html_pages(crawl.pages):
            facts = extract_facts(page)
            subheadings = [h for h in facts.headings if h[0] >= 2]
            if _unassessable(facts):
                findings.append(Finding(
                    dimension=self.code, check_id="extractability-not-assessed",
                    severity=Severity.INFO,
                    summary=f"{facts.path} returned {facts.word_count} words of "
                            f"HTML and loads {len(facts.script_srcs)} script(s), "
                            "so its content most likely renders in the browser. "
                            "Extractability was not assessed on this page — this "
                            "is not a pass.",
                    subject=facts.path, affected_urls=[page.url],
                    evidence={"word_count": facts.word_count,
                              "script_count": len(facts.script_srcs),
                              "script_srcs": facts.script_srcs[:5]},
                    recommendation="Server-render or pre-render the page's main "
                                   "content. An assistant that does not execute "
                                   "JavaScript sees what this crawl saw.",
                ))
            elif facts.word_count >= EXTRACTABILITY_MIN_WORDS and not subheadings:
                findings.append(Finding(
                    dimension=self.code, check_id="poor-extractability",
                    severity=Severity.LOW,
                    summary=f"{facts.path} runs {facts.word_count} words with no "
                            "subheadings — hard for an assistant to lift a "
                            "self-contained answer from.",
                    subject=facts.path, affected_urls=[page.url],
                    evidence={"word_count": facts.word_count,
                              "heading_levels": [h[0] for h in facts.headings]},
                    recommendation="Structure long content with descriptive H2/H3 "
                                   "sections that each answer one question.",
                ))
        site = context.get("site")
        findings += self._directive_checks(crawl)
        findings += self._ua_sensitive(crawl)
        findings += self._content_behind_js(crawl, context)
        findings += self._llms_txt_stale(crawl)
        findings += self._entity_unresolvable(crawl, site)
        findings += self._entity_unnamed(crawl, site)
        # Always, and never scored: INFO carries no weight (scoring.py).
        findings.append(Finding(
            dimension=self.code, check_id="ai-experience-unmeasured",
            severity=Severity.INFO, summary=UNMEASURED, subject="site",
            # The start URL, as every site-level row here names it: a verify
            # of the home page re-raises this row, so it is still present.
            affected_urls=[crawl.start_url], evidence={"field": "not connected"},
            recommendation="Nothing to change: this row states a limit of the audit."))
        return findings

    # --- item 145 step BG: the free checks the prompt names -----------------

    def _directive_checks(self, crawl: CrawlResult) -> list[Finding]:
        """`ai-crawler-allowed-unstated` and `noai-meta`: directives, stated
        as facts. One site row lists every AI agent robots.txt says nothing
        to, with its class; a noai directive is one row per page."""
        from clauditseo.crawler.robots import RobotsPolicy, robots_url_for
        from clauditseo.crawler.ua_matrix import UA_MATRIX_AGENTS
        out: list[Finding] = []
        if crawl.robots_txt:
            policy = RobotsPolicy(robots_url_for(crawl.start_url), crawl.robots_status,
                                  crawl.robots_txt)
            unstated = [{"agent": t, "class": c} for t, _ua, c in UA_MATRIX_AGENTS
                        if c != "search" and not policy.names(t)]
            if unstated:
                out.append(Finding(
                    dimension=self.code, check_id="ai-crawler-allowed-unstated",
                    severity=Severity.INFO,
                    summary=(f"robots.txt has no rule for {len(unstated)} AI "
                             "crawler(s), so each falls to the `*` group: "
                             + ", ".join(f"{u['agent']} ({u['class']})" for u in unstated)
                             + ". The site has not decided for these."),
                    subject="site", affected_urls=[crawl.start_url],
                    evidence={"agents": unstated},
                    recommendation="If the site has a view on any of these crawlers, "
                                   "state it in robots.txt; if not, nothing to change."))
        for page in html_pages(crawl.pages):
            facts = extract_facts(page)
            said = " ".join(filter(None, [facts.meta_robots, page.x_robots_tag])).lower()
            tokens = [t for t in NOAI_TOKENS if re.search(rf"\b{t}\b", said)]
            if tokens:
                out.append(Finding(
                    dimension=self.code, check_id="noai-meta", severity=Severity.INFO,
                    summary=f"{facts.path} carries {', '.join(tokens)} in its "
                            "robots directives.",
                    subject=facts.path, affected_urls=[page.url],
                    evidence={"tokens": tokens, "meta_robots": facts.meta_robots,
                              "x_robots_tag": page.x_robots_tag},
                    recommendation="A rule, stated as fact: keep it if it is "
                                   "intended."))
        return out

    def _ua_sensitive(self, crawl: CrawlResult) -> list[Finding]:
        out: list[Finding] = []
        for hit in ua_differences(crawl):
            first = hit["urls"][0]
            fields = [d["field"] for d in first["named"] + first["size"]]
            out.append(Finding(
                dimension=self.code, check_id="ua-sensitive", severity=Severity.HIGH,
                summary=(f"{hit['agent']} ({hit['class']}) was served a different "
                         f"document from the crawl's own at {first['url']}: "
                         f"{', '.join(fields)} differ. Measured for this crawler name "
                         "from one place."),
                subject=f"ua-sensitive:{hit['agent']}",
                affected_urls=[u["url"] for u in hit["urls"]], evidence=hit,
                recommendation="Find what varies the response by crawler name (a "
                               "plugin, a cache variant, a firewall rule) and decide "
                               "whether this crawler should get the same page."))
        return out

    def _content_behind_js(self, crawl: CrawlResult, context: dict) -> list[Finding]:
        """The share of a page's rendered words already in its initial HTML,
        below the threshold. Reads the a11y pass's rendered text blocks (the
        ones `render-only` reads); no new capture. Sample-scoped, and says so."""
        blocks_by_url = context.get("text_blocks") or {}
        cover = context.get("rendered_coverage") or {}
        out: list[Finding] = []
        raw = {p.url: extract_facts(p) for p in html_pages(crawl.pages)}
        for url, blocks in sorted(blocks_by_url.items()):
            facts = raw.get(url)
            rendered = rendered_words(blocks)
            if facts is None or rendered < CONTENT_BEHIND_JS_MIN_WORDS:
                continue
            share = min(facts.word_count / rendered, 1.0)
            if share >= CONTENT_BEHIND_JS_SHARE:
                continue
            out.append(Finding(
                dimension=self.code, check_id="content-behind-js", severity=Severity.HIGH,
                summary=(f"{facts.path}: {round(share * 100)}% of the text a browser "
                         f"renders ({facts.word_count} of {rendered} words) is in the "
                         "initial HTML, so a reader that does not run scripts gets "
                         "the rest of the page without it"
                         + (f" (the rendered pass visited {cover.get('rendered')} of "
                            f"{cover.get('pages')} pages)." if cover.get("pages") else ".")),
                subject=facts.path, affected_urls=[url],
                evidence={"initial_words": facts.word_count, "rendered_words": rendered,
                          "share": round(share, 3),
                          "threshold": CONTENT_BEHIND_JS_SHARE},
                recommendation="Serve the page's main text in the initial HTML."))
        return out

    def _llms_txt_stale(self, crawl: CrawlResult) -> list[Finding]:
        if crawl.llms_txt_status != 200 or not crawl.llms_txt:
            return []
        from urllib.parse import urlsplit
        host = urlsplit(crawl.start_url).netloc.lower().removeprefix("www.")
        by_requested = {}
        for p in crawl.pages:
            by_requested[_norm(p.requested_url or p.url)] = p
            by_requested.setdefault(_norm(p.url), p)
        stale = []
        for url in llms_txt_urls(crawl.llms_txt):
            if urlsplit(url).netloc.lower().removeprefix("www.") != host:
                continue
            page = by_requested.get(_norm(url))
            if page is None:
                stale.append({"url": url, "reason": "not in the crawl"})
            elif page.status != 200:
                stale.append({"url": url, "reason": f"status {page.status}"})
            elif _norm(page.url) != _norm(url):
                stale.append({"url": url, "reason": f"redirects to {page.url}"})
        if not stale:
            return []
        return [Finding(
            dimension=self.code, check_id="llms-txt-stale", severity=Severity.MEDIUM,
            summary=(f"/llms.txt lists {len(stale)} URL(s) that do not answer as listed: "
                     + "; ".join(f"{s['url']} ({s['reason']})" for s in stale[:5])
                     + (" …" if len(stale) > 5 else "")
                     + (f" The crawl stopped at {len(crawl.pages)} pages, so 'not in "
                        "the crawl' can mean not reached." if crawl.truncated_by else "")),
            subject="llms-txt", affected_urls=[f"{crawl.start_url.rstrip('/')}/llms.txt"],
            evidence={"stale": stale, "truncated_by": crawl.truncated_by},
            recommendation="Update or remove the listed URLs in /llms.txt.")]

    def _entity_unresolvable(self, crawl: CrawlResult, site) -> list[Finding]:
        """The business entity's node has no `@id`, or no `sameAs` to any
        identifier the record lists. Read off the home page's graph model
        (Structured data's), not a second parse of the markup."""
        import json

        from clauditseo import schema_graph
        from urllib.parse import urlsplit
        start_key = _norm(crawl.start_url)
        home = next((p for p in html_pages(crawl.pages)
                     if _norm(p.url) == start_key or _norm(p.requested_url or "") == start_key), None)
        if home is None:
            return []
        facts = extract_facts(home)
        blocks = []
        for raw in facts.jsonld_blocks:
            try:
                blocks.append({"source": "inline", "json": json.loads(raw)})
            except (TypeError, ValueError):
                continue
        host = urlsplit(home.url).netloc.lower().removeprefix("www.")
        model = schema_graph.build_model(blocks, None, {"host": host, "page": facts.path,
                                                        "page_type": "home"}, [])
        entity = model.node(model.entity_key) if model.entity_key else None
        sources = [str(s).strip() for s in (getattr(site, "sameas_sources", None) or [])
                   if str(s).strip()]
        problems, same_as = [], []
        if entity is None:
            problems.append("the home page's structured data has no business entity node")
        else:
            if not entity.id:
                problems.append(f"the {'/'.join(entity.types) or 'entity'} node has no @id")
            raw_same = (entity.raw or {}).get("sameAs") or []
            same_as = [str(x) for x in (raw_same if isinstance(raw_same, list) else [raw_same])
                       if str(x).strip()]
            # Channel 20260915-2045, (c): a node with no sameAs pins nothing,
            # whatever the record lists; a node with pins is judged against
            # the record only when the record has entries, and is not assessed
            # (not passed) while it is empty (`RECORD_FIELDS`).
            if not same_as:
                problems.append("its sameAs pins nothing")
            elif sources and not any(_norm(s) == _norm(x) for s in sources for x in same_as):
                problems.append("its sameAs pins none of the identifiers the site "
                                "record lists")
        if not problems:
            return []
        return [Finding(
            dimension=self.code, check_id="entity-unresolvable", severity=Severity.HIGH,
            summary=("The business entity cannot be resolved by a machine reader: "
                     + "; ".join(problems) + ". Structured data owns the markup fix."),
            subject="entity", affected_urls=[home.url],
            evidence={"entity": entity.as_dict() if entity else None,
                      "same_as": same_as, "sameas_sources": sources,
                      "problems": problems},
            recommendation=("Give the entity node a stable @id and pin sameAs to "
                            "the identifiers on the site record." if sources else
                            "Pin sameAs to the entity's authoritative profiles and list "
                            "them in sameas_sources on the site record so the automatic "
                            "checks can verify them."))]

    def _entity_unnamed(self, crawl: CrawlResult, site) -> list[Finding]:
        """A record entity that no page names in its URL, title or H1, by the
        test Content's page verdict uses (`cnt.entity_at_top`)."""
        from clauditseo.modules.cnt import entity_at_top
        from clauditseo.modules.links import _entity_rows
        if site is None:
            return []
        have, missing = _entity_rows(site)
        entities = [(e["entity"], e.get("kind")) for e in have] + [(n, None) for n in missing]
        if not entities:
            return []
        facts = [extract_facts(p) for p in html_pages(crawl.pages)]
        out: list[Finding] = []
        for name, kind in entities:
            if any(entity_at_top(f, name) for f in facts):
                continue
            out.append(Finding(
                dimension=self.code, check_id="entity-unnamed", severity=Severity.MEDIUM,
                summary=(f"{name} is on the site record but no crawled page names it "
                         f"in its URL, title or H1 ({len(facts)} pages read)."),
                subject=f"entity:{name}", affected_urls=[crawl.start_url],
                evidence={"entity": name, "kind": kind, "pages_read": len(facts)},
                recommendation=f"Name {name} where a machine looks first on the page "
                               "that owns it: the URL, the title and the H1."))
        return out


    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # This dimension measures page content, so a crawl that fetched no
        # page measured none of it. Without this it inherited coverage 1.0
        # and reported 100 at full weight from nothing.
        return scoring.subscore(self.code, findings, self.default_weight, context,
                                coverage=scoring.page_coverage(context))


registry.register(AiSurfaceModule())
