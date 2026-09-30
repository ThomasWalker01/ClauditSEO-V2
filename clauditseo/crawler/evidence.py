"""A compact, durable record of what a crawl saw.

Findings alone cannot feed the expert tools: an indexability brief wants
inlink counts and canonical targets, a URL-hygiene brief wants the parameter
space and the duplicate forms. None of that survives in a findings table, and
re-crawling a hundred pages every time an operator opens a tool would be
absurd. So each run stores this snapshot: derived facts only, no page bodies.

Size, measured rather than estimated. This was about 3.9 KB per page until
the outline and the image list were added for the page-anatomy view; it is
now about 13 KB, so a hundred-page crawl grew from roughly 390 KB to 1.3 MB.
The image list is most of the increase, because image URLs are long. That
was a deliberate trade: "twelve images lack alt text" cannot be acted on
without knowing which twelve, and re-fetching the page to find out would
show its current state rather than what the audit actually saw — which is
the one thing a stored finding must stay consistent with.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit
from typing import Any

from clauditseo.modules.loc import PHONE_RE
from clauditseo.modules.pagefacts import (extract_facts, identify_logo, jsonld_raw,
                                          mark_template_blocks, mark_template_images,
                                          position_key, profile_links,
                                          schema_inventory)

from .types import CrawlResult

SITEMAP_ENTRY_CAP = 2000
OUTLINK_CAP = 100
LINK_DETAIL_CAP = 60      # anchors per page kept for the architecture brief
# The outline and the image list are what turn "a heading level was skipped"
# into "this heading, here". Capped because a page with four hundred images
# would otherwise dominate the snapshot; the untruncated totals are stored
# alongside so the display can say when it is showing a subset.
HEADING_CAP = 60
HEADING_TEXT_CAP = 140
NEXT_TEXT_CAP = 320
IMAGE_CAP = 60
URL_TEXT_CAP = 300
HEADER_KEEP = (
    # Headers a security brief must see verbatim. Everything else is dropped
    # to keep the snapshot small.
    "strict-transport-security", "content-security-policy",
    "content-security-policy-report-only", "x-content-type-options",
    "referrer-policy", "permissions-policy", "x-frame-options",
    "cross-origin-opener-policy", "cross-origin-embedder-policy",
    "cross-origin-resource-policy", "cache-control", "set-cookie", "server",
    # A date signal, not a security header: the origin's own claim about when
    # the resource last changed. Frequently absent or set to "now" on dynamic
    # sites, so it is one input to a freshness judgement, never the answer.
    "last-modified",
    "x-powered-by", "x-aspnet-version", "x-generator", "x-xss-protection",
    "expect-ct", "public-key-pins", "access-control-allow-origin",
    # SEC/cors-permissive (item 143 step BD): `*` is only a defect beside this.
    "access-control-allow-credentials",
    "content-type", "x-robots-tag", "link", "vary", "alt-svc",
)


def _content_hash(text: str) -> str:
    """One page's words as one value, whitespace-collapsed and lowered.

    Normalised before hashing because a re-render that changes
    indentation has not changed the page, and a check about whether
    anybody edited it must not fire on a deploy.
    """
    import hashlib

    return hashlib.sha256(" ".join((text or "").lower().split()).encode()).hexdigest()


def home_of(start_url: str, pages: list[dict]) -> str | None:
    """The page the crawl actually began at, as the crawl knows it.

    `start_url` is what was *asked for*; the page that answered may be
    under another spelling, and on most sites it is - an apex that
    redirects to `www` is the ordinary case. Matched in three widening
    steps, each of which is still the same page:

      1. the URL itself, where the crawl kept that spelling;
      2. a page whose `requested_url` or redirect chain begins there,
         which is the redirect stated by the crawl rather than inferred;
      3. a page whose path is the start's path on the same registrable
         host, which catches a `www` swap the chain did not record.

    `None` only where the crawl fetched nothing at all.
    """
    if not pages:
        return None
    by_url = {p["url"]: p for p in pages}
    if start_url in by_url:
        return start_url
    for page in pages:
        if page.get("requested_url") == start_url:
            return page["url"]
        chain = page.get("redirect_chain") or []
        if chain and chain[0] == start_url:
            return page["url"]
    want = urlsplit(start_url)
    want_host = (want.hostname or "").removeprefix("www.")
    want_path = want.path or "/"
    for page in pages:
        got = urlsplit(page["url"])
        if ((got.hostname or "").removeprefix("www.") == want_host
                and (got.path or "/") == want_path):
            return page["url"]
    return None


def click_depth(start_url: str, pages: list[dict]) -> dict[str, int]:
    """Minimum clicks from the homepage over internal links. Computed here
    because it needs the whole graph, and no per-page record can hold it.

    Seeded from `home_of` rather than from `start_url` itself. Seeding
    from the string asked for meant that on any site redirecting apex to
    `www` - most of them - the frontier was empty and every page came back
    unreachable. Nothing read the value until `LNK/depth-deep`, so it was
    wrong quietly; the first run of `links.md` on Birch held the check and
    said why, which is how it was found.
    """
    graph = {p["url"]: p.get("outlinks", []) for p in pages}
    depths: dict[str, int] = {}
    home = home_of(start_url, pages)
    if home in graph:
        frontier = [home]
        depths[home] = 0
    else:
        frontier = []
    while frontier:
        nxt: list[str] = []
        for url in frontier:
            for target in graph.get(url, []):
                if target not in depths:
                    depths[target] = depths[url] + 1
                    nxt.append(target)
        frontier = nxt
    return depths


DATE_PROPERTIES = ("datePublished", "dateModified", "uploadDate", "dateCreated")

# Schema types a local audit must see. Kept verbatim rather than parsed into
# fields, because the local brief has to quote the current markup back as a
# "before" block, and a re-serialised copy is not what is on the page.
# Matched on properties as well as type names, because LocalBusiness has
# dozens of subtypes — Plumber, RoofingContractor, Dentist — and a block typed
# as one of them says "localbusiness" nowhere. A block carrying a telephone or
# a postal address is the thing a local audit needs to quote, whatever it calls
# itself.
LOCAL_SCHEMA_HINTS = ("localbusiness", "organization", "postaladdress",
                      "openinghours", "aggregaterating", "review", "place",
                      "geocoordinates", "telephone", "address", "areaserved",
                      "geo")
LOCAL_SCHEMA_CAP = 4000     # per page; enough for a business block, not a catalogue
NAP_CONTEXT = 90


def local_schema_blocks(jsonld_blocks: list[str]) -> list[str]:
    """JSON-LD blocks that mention a local or review type, verbatim."""
    keep = []
    for block in jsonld_blocks:
        lowered = block.lower()
        if any(hint in lowered for hint in LOCAL_SCHEMA_HINTS):
            keep.append(block[:LOCAL_SCHEMA_CAP])
    return keep


def schema_types(jsonld_blocks: list[str]) -> list[str]:
    """Every @type a page declares, flattened and deduplicated.

    Read rather than validated: the point is to show an operator what the
    page claims to be, so a missing Organization or a page describing itself
    as a WebPage and nothing else is visible without opening the source.
    """
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            t = node.get("@type")
            for value in ([t] if isinstance(t, str) else t or []):
                if isinstance(value, str) and value not in found:
                    found.append(value)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for block in jsonld_blocks:
        try:
            walk(json.loads(block))
        except (ValueError, TypeError):
            continue          # invalidity is jsonld-invalid's finding, not ours
    return found[:40]


def nap_mentions(text: str, pattern) -> list[dict[str, str]]:
    """Phone numbers as they actually appear, with the words around them.

    The brief must exhibit every conflicting variant beside its source rather
    than assert that an inconsistency exists, so the matched string is kept
    exactly as written — spacing, brackets and all — not normalised.
    """
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        raw = match.group(0)
        if raw in seen:
            continue
        seen.add(raw)
        start = max(0, match.start() - NAP_CONTEXT)
        found.append({"value": raw,
                      "context": text[start:match.end() + NAP_CONTEXT].strip()})
        if len(found) >= 6:
            break
    return found


def content_dates(jsonld_blocks: list[str]) -> dict[str, str]:
    """Dates the page asserts about its own content, from JSON-LD.

    The most trustworthy of the three date signals available to a crawl,
    because the CMS writes it about the article rather than about the file or
    the build. Still only a claim: nothing here verifies that the copy changed
    when the date says it did.
    """
    found: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in DATE_PROPERTIES and isinstance(value, str) and value.strip():
                    found.setdefault(key, value.strip()[:40])
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for block in jsonld_blocks:
        try:
            walk(json.loads(block))
        except (ValueError, TypeError):
            continue          # malformed JSON-LD is reported elsewhere, not here
    return found



#: Where each resource kind names its origin in markup (item 143 step BD).
_RESOURCE_TAGS = (
    ("script", re.compile(r"<script\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)", re.I)),
    ("frame", re.compile(r"<iframe\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)", re.I)),
    ("style", re.compile(r"<link\b(?=[^>]*\brel\s*=\s*[\"']?stylesheet)[^>]*?\bhref\s*=\s*[\"']([^\"']+)", re.I)),
    ("img", re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)", re.I)),
)


def resource_origins(pages) -> dict[str, dict[str, int]]:
    """Kind -> host -> how many HTML pages name it, from the served markup
    (item 143 step BD). What SEC/csp-policy may name: a proposed CSP's
    script, frame and default sources are held to these hosts. Fonts and
    fetch/XHR endpoints load from CSS and script, not markup, and are not
    here - the brief is told so."""
    out: dict[str, dict[str, int]] = {kind: {} for kind, _ in _RESOURCE_TAGS}
    for page in pages:
        if "html" not in (getattr(page, "content_type", "") or ""):
            continue
        html = getattr(page, "content", "") or ""
        for kind, pattern in _RESOURCE_TAGS:
            hosts = set()
            for src in pattern.findall(html):
                src = src.strip()
                if not src or src.startswith(("data:", "about:", "javascript:", "blob:")):
                    continue
                host = (urlsplit(urljoin(page.url, src)).hostname or "").lower()
                if host:
                    hosts.add(host)
            for host in hosts:
                out[kind][host] = out[kind].get(host, 0) + 1
    return out


def _consent_facts(pages, traces: dict) -> dict:
    from clauditseo.modules.sec import consent_facts
    return consent_facts(pages, traces)


def snapshot(crawl: CrawlResult, image_measurements: dict | None = None,
             perf_traces: dict | None = None,
             perf_sample: str | None = None) -> dict[str, Any]:
    """The stored evidence for one crawl.

    `image_measurements` is what `clauditseo.imaging` saw in a browser,
    keyed by url and then by image src. It is optional and stays optional:
    without it every measured field is simply absent from the inventory,
    which is what a crawl run where Playwright is not installed stores,
    and the Images brief is handed `[not measured]` rather than a value
    nobody took.

    `perf_traces` is what `clauditseo.perf` measured in a browser under the
    fixed device profile (brief v19 step BC), keyed by url. Optional and
    stored the same way: every page record carries a `perf` key so a reader
    can always ask for it, set to `{"traced": False}` where no trace was taken
    (Playwright absent, page not sampled, or the load failed). A field inside a
    trace the browser could not supply is `"unavailable"`, never omitted, so a
    consumer degrades on the value — item 154.

    `perf_sample` is that pass's own statement of WHICH pages it took — one per
    template on T2/T3, every page of the pulse on T1 (`perf.sample`). Stored at
    the top level rather than on each trace, because it is one fact about the
    run and not a property of any page, and stated on the Speed part beside the
    device profile for the same reason that one is: a figure read under
    conditions the reader cannot see is a figure they cannot check.
    """
    pages: list[dict[str, Any]] = []
    #: (record, facts) for the HTML pages, so the logo can be identified
    #: once the run's regions are settled rather than page by page.
    logo_inputs: list[tuple[dict[str, Any], Any]] = []
    for page in crawl.pages:
        record: dict[str, Any] = {
            "url": page.url,
            "requested_url": page.requested_url,
            "status": page.status,
            "content_type": page.content_type,
            "redirect_chain": page.redirect_chain,
            # Parallel to redirect_chain (item 137, F-13); absent on older runs.
            "redirect_statuses": page.redirect_statuses,
            "discovered_via": page.discovered_via,
            "outlinks": page.outlinks[:OUTLINK_CAP],
            "links": page.link_details[:LINK_DETAIL_CAP],
            "x_robots_tag": page.x_robots_tag,
            "link_header_canonical": page.link_header_canonical,
            "headers": {k: v for k, v in page.headers.items() if k in HEADER_KEEP},
            "elapsed_ms": round(page.elapsed_ms),
        }
        if page.content_type.startswith("text/html") and page.content:
            facts = extract_facts(page)
            record.update({
                "title": facts.title,
                "meta_description": facts.meta_description,
                "meta_robots": facts.meta_robots,
                "canonical": facts.canonical,
                "viewport_tags": facts.viewport_tags,
                "hreflang": facts.hreflang,
                "word_count": facts.word_count,
                "heading_levels": [lvl for lvl, _ in facts.headings],
                "h1": next((t for lvl, t in facts.headings if lvl == 1), None),
                # The outline, not just its shape. "Heading level jumps H2 to
                # H4" is not actionable without seeing which heading, and an
                # operator should not have to open the page to find out.
                "headings": [[lvl, text[:HEADING_TEXT_CAP]]
                             for lvl, text in facts.headings[:HEADING_CAP]],
                "heading_total": len(facts.headings),
                # The outline the Headings brief reads (brief v11 step AJ,
                # engine 0.12.0): each heading with whether it sits in the
                # main region and the first forty words after it, and how
                # the main region was found.
                # A hash of the page's own words (brief v17 step AX,
                # operator 2026-09-06). `CNT/stale` asks whether anybody
                # has touched the page since the last crawl, and the
                # evidence stores no body text - a page's words are the
                # largest thing a crawl sees, and keeping them per run to
                # answer one yes/no question would multiply the size of
                # every stored run. Sixty-four characters answers it.
                "content_hash": _content_hash(facts.text),
                # The first sixty words, which is what a reader and a
                # model both meet first (brief v17 step AX). Stored
                # because the page's own text is not: the Content part
                # page shows the opening verbatim, and `page_facts` had
                # been deriving it from a field the evidence has never
                # carried - so the card promised the opening and rendered
                # "the crawl recorded no body text" on every page.
                "opening": " ".join((facts.text or "").split()[:60]),
                "outline": [[h["level"], h["text"][:HEADING_TEXT_CAP], h["in_main"],
                             h["next_text"][:NEXT_TEXT_CAP]]
                            for h in facts.outline[:HEADING_CAP]],
                "main_region": facts.main_region,
                # Same reasoning for "12 images lack alt text": the fix needs
                # to know which. Kept as (src, alt) so a present-but-empty alt
                # is distinguishable from an absent one — the first is a
                # decorative image declared correctly, the second is a defect.
                "images": [[src[:URL_TEXT_CAP], alt]
                           for src, alt in facts.images[:IMAGE_CAP]],
                "image_total": len(facts.images),
                # The inventory the Images brief reads (brief v15 step AQ):
                # everything one image's own markup says about it.
                #
                # `rendered` and `css_aspect_ratio` need a layout,
                # `lcp_candidate` a paint, `weight_kb` the file itself and
                # `top_pct` the document's height. This crawler reads HTML
                # and fetches no assets, so it supplies none of them: they
                # are merged in from `image_measurements` where a browser
                # took them, and are simply absent where none ran. Absent,
                # and the prompt's own rule then applies - a field the
                # inventory does not have goes to `not_assessable` naming
                # it, rather than being estimated.
                "image_inventory": [
                    {**{k: (v[:URL_TEXT_CAP] if k == "src" and isinstance(v, str) else v)
                        for k, v in img.items() if k != "css_class"},
                     # Item 241: joined on the file a lazy loader swaps in
                     # where the markup names one, as `imaging` keys it.
                     **((image_measurements or {}).get(page.url, {})
                        .get(img.get("lazy_src") or img.get("src") or "", {}))}
                    for img in facts.image_details[:IMAGE_CAP]],
                # Kept off the record and used only to key the template
                # rule below: the class attribute is the nearest thing to a
                # selector this parser has, and it is noise on a card.
                "_image_keys": [position_key(img)
                                for img in facts.image_details[:IMAGE_CAP]],
                "content_dates": content_dates(facts.jsonld_blocks),
                "local_schema": local_schema_blocks(facts.jsonld_blocks),
                "nap_mentions": nap_mentions(facts.text, PHONE_RE),
                # The declared language, and what schema types the page
                # claims to be. Both are things an operator wants to read
                # directly, not infer from the absence of a finding.
                "lang": facts.lang,
                # Whether this route takes a customer's details (brief
                # v16h). Absent on every run taken before it, which the
                # grid reads as "not a form route" rather than as unknown -
                # stated because the difference matters for the sentence
                # that names the odd route.
                "has_post_form": facts.has_post_form,
                "schema_types": schema_types(facts.jsonld_blocks),
                "jsonld_blocks": len(facts.jsonld_blocks),
                # Every block as parsed, and the page's own visible copy
                # beside it (brief v16 step AS): markup that says what the
                # page does not is `schema-hidden-markup`, and it can only
                # be judged with both in the same record.
                "schema_inventory": schema_inventory(facts.jsonld_blocks,
                                                     getattr(facts, "jsonld_ids", []) or []),
                # And the same blocks unflattened, which is what the
                # Structured data picture is built from (brief v16a step
                # AT-b). The inventory above cannot carry a graph: it keeps
                # two levels and a list's first member, so a reference
                # inside an `itemListElement` is invisible to it and the
                # node it wires would be drawn adrift.
                "jsonld_raw": jsonld_raw(facts.jsonld_blocks,
                                         getattr(facts, "jsonld_ids", []) or []),
                "profile_links": profile_links(facts.links),
                # A tally of what an accessibility check looked at, so
                # "nothing open here" can be distinguished from "nothing was
                # examined". Counts only — the failures themselves are
                # findings.
                "a11y": {
                    "form_controls": len(facts.form_controls),
                    "labels": len(facts.label_for),
                    "links": len(facts.links),
                    "buttons": len(facts.buttons),
                    "iframes": len(facts.iframes),
                    "tables": len(facts.tables),
                    "landmarks": sorted(facts.landmarks),
                },
            })
            logo_inputs.append((record, facts))
        pages.append(record)

    # The same rule the sweep applies, from the same place: a template
    # image counted once here and once per page there would be two answers
    # to "how many problems does this part have".
    mark_template_images([(p["image_inventory"], p.pop("_image_keys", []))
                          for p in pages if "image_inventory" in p])
    # And the same rule over the structured-data blocks (brief v16 step
    # AS): an Organization node on every page is one node and one card,
    # not twelve.
    mark_template_blocks([p["schema_inventory"] for p in pages
                          if "schema_inventory" in p])
    # And the one header image that is not decorative (brief v16 step AU6),
    # after the regions are settled because a logo is a header image by
    # definition. No brand here: the crawl has no site record to ask, and
    # the signal that wants one is the last of the three rather than the
    # first. The sweep identifies it again with the brand in hand; both
    # call the same function, so the record and the finding cannot name
    # different images as the logo.
    for record, facts in logo_inputs:
        identify_logo(record["image_inventory"], facts.jsonld_blocks,
                      page_url=record["url"])

    depths = click_depth(crawl.start_url, pages)
    for record in pages:
        record["click_depth"] = depths.get(record["url"])

    # The per-page performance trace (brief v19 step BC), keyed by url. Every
    # record carries the key: the trace where one was taken, `{"traced": False}`
    # where none was (Playwright absent, the page not sampled, or the load
    # failed). Consistent-key so `test_stored_shape` reads one shape and a
    # consumer never meets a missing field.
    traces = perf_traces or {}
    for record in pages:
        record["perf"] = traces.get(record["url"]) or {"traced": False}

    transport = crawl.transport
    return {
        "start_url": crawl.start_url,
        "tier": crawl.tier.value,
        "robots_txt": crawl.robots_txt,
        "robots_status": crawl.robots_status,
        "llms_txt_status": crawl.llms_txt_status,
        # The body itself (item 145 BH): the AI surface brief assesses and
        # rewrites the file, and `llms-txt-stale` reads its URLs. Capped.
        "llms_txt": (crawl.llms_txt or "")[:50_000] or None,
        "sitemaps": [{"url": s.url, "status": s.status, "is_index": s.is_index,
                      "entry_count": s.entry_count, "error": s.error}
                     for s in crawl.sitemaps],
        "sitemap_entries": crawl.sitemap_entries[:SITEMAP_ENTRY_CAP],
        "sitemap_entry_total": len(crawl.sitemap_entries),
        "sitemap_lastmod": crawl.sitemap_lastmod,
        "duplicate_forms": crawl.duplicate_forms,
        "transport": ({
            "host": transport.host,
            "tls_version": transport.tls_version,
            # The ceiling one handshake reached, and the floor the stepped
            # probe measured. Both, because they answer different questions
            # and neither answers the other: `tls_version` is the highest
            # version both ends agreed on, so a server still accepting TLS
            # 1.0 reports TLSv1.3 exactly like one that refuses it.
            "tls_floor": transport.tls_floor,
            "tls_floor_certain": transport.tls_floor_certain,
            "tls_offered": transport.tls_offered,
            "cipher": transport.cipher,
            "cert_not_after": transport.cert_not_after,
            "cert_subject_alt_names": transport.cert_subject_alt_names,
            "http_redirects_to_https": transport.http_redirects_to_https,
            "http_redirect_chain": transport.http_redirect_chain,
            "http_version": transport.http_version,
            "alpn": transport.alpn,
            "cert_key_type": transport.cert_key_type,
            "cert_key_bits": transport.cert_key_bits,
            "cert_signature": transport.cert_signature,
            "error": transport.error,
        } if transport else None),
        "robots_blocked": crawl.robots_blocked[:100],
        "truncated_by": crawl.truncated_by,
        "stats": crawl.stats,
        # The UA matrix (item 137 task 4): one row per named agent, or empty
        # where the crawl did not run the pass (T1 pulse, nav/verify scope).
        "ua_matrix": crawl.ua_matrix,
        # The well-known path sweep, or None where it did not run (item 143).
        "well_known": crawl.well_known,
        # SEC's DNS lookups, or why there are none (item 143).
        "dns": crawl.dns,
        # The mobile and bot parity probe (item 151), or None where it did not
        # run. A clean probe is stored too: "no divergence across N pages".
        "mobile_parity": crawl.mobile_parity,
        # The hosts the markup loads scripts, frames, stylesheets and images
        # from (item 143 step BD): what a proposed CSP may name.
        "resource_origins": resource_origins(crawl.pages),
        "perf_sample": perf_sample,
        # What the traced pages show about consent (item 143 step BD, channel
        # 20260914-1415): tools, trackers, cookieless analytics. Read by the
        # Security brief for the no-consent-tool case the check leaves to it.
        "consent": _consent_facts(crawl.pages, perf_traces or {}),
        "pages": pages,
    }


def inlinks(evidence: dict) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for page in evidence.get("pages", []):
        for target in page.get("outlinks", []):
            graph.setdefault(target, []).append(page["url"])
    return graph


def html_records(evidence: dict) -> list[dict]:
    return [p for p in evidence.get("pages", [])
            if str(p.get("content_type", "")).startswith("text/html")
            and p.get("status") == 200]
