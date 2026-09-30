"""Polite breadth-first crawler.

Politeness contract (also asserted by gate G1 tests):
- robots.txt is fetched first and honoured for every page URL;
- an identifiable user agent on every request;
- a fixed delay between requests to the host;
- hard budgets per tier: max pages, per-request timeout, wall clock.

The crawler also captures the evidence downstream tools cannot reconstruct
later: the internal link graph, per-sitemap fetch outcomes, and the URL forms
that collapsed onto an already-fetched page.
"""

from __future__ import annotations

import heapq
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import (parse_qsl, unquote_plus, urldefrag, urljoin, urlsplit,
                          urlunsplit)

from clauditseo.engine.types import Tier

from .fetch import Fetcher
from .robots import RobotsPolicy, robots_url_for
from .types import (TIER_BUDGETS, USER_AGENT, CrawlResult, Page, SitemapRecord,
                    TierBudget, eligible)

SITEMAP_HEAD_ENTRIES = 50      # T1 reads only the head of a sitemap
SITEMAP_FULL_ENTRIES = 5000    # deeper tiers read the lot, within reason
MAX_SITEMAPS = 20


def crawl_start_url(domain: str) -> str:
    """The one place a stored domain becomes a URL the crawler can use.

    A `sites` row may hold either an absolute URL or a bare authority, and
    five of the six live rows hold the bare form. `normalise_url` on a bare
    authority yields `http:www.acme.com.au` — no `//`, so `urlsplit` finds
    no netloc — from which `robots_url_for` builds `http:///robots.txt` and
    the sitemap URL `http:/sitemap.xml`. Nothing is fetched, and TEC reports
    the absence it manufactured as `The site is not served over HTTPS.` at
    `confidence: high`.

    The rule was implemented at `launch_audit` and re-derived at `cli.py`,
    then omitted by the two narrow-run entry points added later (CQ-95). It
    lives here so the next entry point inherits it rather than deciding.

    A domain that already carries a scheme is returned untouched: `http://`
    on a staging target is the operator's choice, not a mistake to correct.
    A *scheme* is `http://` or `https://`, not the four characters `http` —
    `startswith("http")`, which both original sites used, hands the real
    domain `httpwatch.com` to the crawler bare and reproduces CQ-95 through
    a narrower door.

    The test is case-insensitive, because a scheme is (CQ-102). Read
    case-sensitively, `HTTPS://x` is not a scheme, so it comes back as
    `https://HTTPS://x/` — whose hostname is `https`, a host that does not
    exist. That netloc is *non-empty*, so the no-host refusal in `crawl()`
    cannot see it either: two defects, two fixes. A domain carrying a scheme
    is still returned untouched rather than folded, since `normalise_url`
    lower-cases the scheme downstream and the operator's spelling is theirs.
    """
    d = domain.strip()
    return d if d.lower().startswith(("http://", "https://")) else f"https://{d}/"


def site_host(domain: str) -> str:
    """The one place a stored `sites.domain` becomes the host it names.

    `crawl_start_url` above answers "what URL do I crawl"; this answers "what
    host is this record about", which four call sites were each answering
    for themselves with the same two lines:

        domain = site_domain.strip().lower()
        if domain.startswith("http"):
            domain = urlsplit(domain).hostname or domain

    `api/app.py` at `_host_matches_site`, `_probe_target` and
    `_validate_start_url`, and `reporting/generate.py` where the deliverable's
    filename is slugged. All four carried the defect `crawl_start_url`'s own
    docstring diagnoses by name and fixed only for itself: a *scheme* is
    `http://` or `https://`, not the four characters `http`, so `httpwatch.com`
    and `httpsecure.com.au` are handed to `urlsplit` as though they carried
    one. Three of the four survived on their `or domain` fallback and merely
    re-derived the input; `_probe_target` fell back with `or ""` and lost the
    host entirely, so `POST /api/runs/{id}/probes/{probe}` answered 422 "this
    run has no site host to probe" about a site whose host was in the record.
    That is CQ-132, and it is the fifth copy of CQ-95.

    **It never raises, and that is the second half.** `urlsplit` raises
    `ValueError: Invalid IPv6 URL` for an unbalanced bracket, and nothing at
    any call site caught it: `SiteIn.domain` is `Field(min_length=3)` with no
    shape check (CQ-108), so `a]b` is storable and then crashed the route
    reading it into a 500 with no `detail` (CQ-120). A reader of stored data
    does not get to assume the data is well-formed -- validating it on the way
    in is a different fix, still open, and gated on what happens to the rows
    already there.

    The fallback is `""` rather than the input, unified across the four. With
    the scheme test correct, an empty `hostname` from a scheme-carrying string
    means there was no authority to find (`https://` alone), and handing back
    `https://` as though it were a host is how the three lucky call sites were
    lucky rather than right. A bare authority is returned as given, port and
    all: `_probe_target`'s answer is dialled by `probes._host_port`, and
    stripping a port here would silently move a probe of `example.com:8443`
    onto 443.
    """
    d = domain.strip()
    if not d.lower().startswith(("http://", "https://")):
        return d.lower()
    try:
        return (urlsplit(d).hostname or "").lower()
    except ValueError:
        return ""


#: Query keys an ad platform, a mailer or a social share appends to a link
#: that already resolved. The server never reads them; they exist so an
#: analytics tool can attribute the visit.
#:
#: The set and the `utm_` prefix are the two shapes of one rule, which is why
#: `is_tracking_param` exists rather than two membership tests at each call
#: site. Both are deliberately narrow: a key is here only if it cannot change
#: what is served. `product_type`, `redirect_to`, `add-to-cart`, `_wpnonce`
#: and `slug` all can, and all appear in this database's stored crawls — the
#: two real sites carry 647 parameterised internal links between them and 636
#: of those are functional.
#:
#: `partnerid` is deliberately absent though run `fe97cc61` carries one. It
#: looks like attribution and may be, but unlike `gclid` a server can
#: legitimately vary on it, and a check that tells a client to delete a
#: parameter their application form reads is worse than one that misses it.
#:
#: Placed here rather than in the module that reads it because `normalise_url`
#: below strips exactly this set (relay item 101, `QUESTIONS.md` Q-25 and
#: Q-29). One list, so the crawler's identity for a URL and the clean URL a
#: finding quotes back to the site cannot disagree about what a tracking
#: parameter is.
#:
#: Re-derived from the tree rather than from the list the item named
#: (DISCIPLINE rule 3). Across all 15 stored crawl-evidence snapshots the
#: query keys the product has fetched a page under are `redirect_to` x27,
#: `utm_source` / `utm_medium` / `utm_campaign` x25 each, `gclid` x8,
#: `utm_term` x6, `product_type` x5, `gad_source` x2, `gad_campaignid` x2,
#: `gbraid` x2 and `slug` x1. `gbraid` and `wbraid` are `gclid` under the iOS
#: privacy rules and the `gad_*` pair is Google Ads auto-tagging; the item
#: enumerated its list from stored *findings*, a narrower population, and so
#: named none of the three. Without them the one auto-tagged URL in run
#: `fe97cc61` does not fold and nine of the ten observed duplicates collapse
#: rather than ten.
TRACKING_PARAMS = frozenset({
    "gclid", "fbclid", "msclkid", "dclid", "yclid", "ttclid", "twclid",
    "igshid", "mc_cid", "mc_eid", "_hsenc", "_hsmi",
    "gbraid", "wbraid", "gad_source", "gad_campaignid",
})
TRACKING_PREFIXES = ("utm_",)


def is_tracking_param(key: str) -> bool:
    """One place the two shapes of the rule are read together."""
    k = key.lower()
    return k in TRACKING_PARAMS or k.startswith(TRACKING_PREFIXES)


def tracking_params_in(url: str) -> list[tuple[str, str]]:
    """The tracking keys a URL carries, in the order its markup wrote them,
    each with the value as written.

    Order is preserved rather than sorted because the finding quotes the link
    back to whoever has to edit it, and a reordered query is not the string
    they will search their template for.

    `keep_blank_values=True` is load-bearing, not tidiness: the site under
    audit emits `?utm_source=&utm_medium=PressRelease…` in its own markup, and
    the default drops a blank-valued key — which is the one case the check
    most needs to report, since an empty value is the site's own templating
    having failed to substitute.
    """
    query = urlsplit(url).query
    if not query:
        return []
    return [(k, v) for k, v in parse_qsl(query, keep_blank_values=True)
            if is_tracking_param(k)]


def _query_without_tracking(query: str) -> str:
    """The query string with its tracking pairs dropped and every other pair
    left byte for byte as written.

    The one place the removal happens, read by `strip_tracking_params` and by
    `normalise_url` alike, so the URL a finding quotes back to the site and
    the URL the crawler files the page under cannot disagree about what a
    tracking parameter is.

    Kept pairs are copied out of the original substring rather than parsed and
    re-encoded, because re-encoding would reorder or re-escape them and so
    manufacture a second spelling of the URL this is meant to canonicalise.
    Splitting on `&` also keeps a blank-valued key — the site under audit
    emits `?utm_source=&utm_medium=PressRelease…` in its own markup, and
    `parse_qsl` drops that pair by default, which is the one case the removal
    most needs to catch.
    """
    return "&".join(
        seg for seg in query.split("&")
        if seg and not is_tracking_param(unquote_plus(seg.split("=", 1)[0])))


def strip_tracking_params(url: str) -> str:
    """The same URL with its tracking keys removed and everything else left
    byte for byte as written.

    This is what the clean URL an internal link *should* have pointed at looks
    like, computed for the finding that quotes both spellings back to whoever
    edits the template. `normalise_url` now applies the same removal for its
    own bookkeeping (relay 101), so the two agree by construction rather than
    by coincidence — but they are still separate calls, because this one
    preserves the fragment and the scheme exactly as the markup wrote them and
    a crawl identity must not.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       _query_without_tracking(parts.query), parts.fragment))


def _canonical_spelling(url: str, *, strip_tracking: bool) -> str:
    """`normalise_url` with the one removal made optional, so the caller that
    needs the URL as the markup wrote it can have it without a second copy of
    the scheme, host, port and path rules."""
    parts = urlsplit(urldefrag(url).url)
    scheme = (parts.scheme or "http").lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host + (f":{port}" if port and not default_port else "")
    query = _query_without_tracking(parts.query) if strip_tracking else parts.query
    return urlunsplit((scheme, netloc, parts.path or "/", query, ""))


def normalise_url(url: str) -> str:
    """A single canonical spelling for the crawler's own bookkeeping.

    Without this, an on-page link to the bare origin (https://site.com.au)
    and the start URL (https://site.com.au/) are different strings, so the
    homepage is fetched twice and then reported as a duplicate of itself.
    Only spellings that cannot change what is served are normalised: scheme
    and host case, default ports, empty path, fragment. Path case is
    preserved because it can genuinely address different content.

    So is the query, with the one exception the same test carves out. This
    docstring used to argue for the whole query on the ground that it "can
    genuinely address different content", and that is true of `product_type`,
    `redirect_to` and `slug`. It is false of `gclid`: an ad platform appends
    it to a link that already resolved and the server never reads it. Those
    keys are spelling by exactly the criterion already applied to scheme case
    and default ports, so they are removed and everything else is preserved
    byte for byte — `TRACKING_PARAMS` above is the set and records how it was
    derived.

    Measured over stored run `fe97cc61ab52468ebb0c4bff36ac69f7` (235 pages,
    T3): ten fetched URLs carried nothing but tracking parameters, so 235
    distinct URLs become 225 and about 4% of a paid crawl stops re-fetching
    pages it already had. No clean path is lost — every one of the ten
    collapses onto a URL that same crawl already held.

    `extract_link_details` keeps the unstripped spelling beside this one, as
    `href`, because the link as the markup wrote it is the subject of TEC's
    `internal-link-tracking-params` and is not recoverable from the result.
    """
    return _canonical_spelling(url, strip_tracking=True)


#: How much of a heading travels with a link that follows it.
POSITION_CAP = 90


class _LinkParser(HTMLParser):
    """Collects each anchor with its text, its rel, where it sits and the
    heading it follows, so a brief can tell a contextual link from
    boilerplate and can say where a new link belongs.

    `position` is the nearest *preceding* heading, whatever its level
    (brief v17 step AW; operator, 2026-09-06). It is a join rather than a
    new capture - this parser already walks headings and links in
    document order - and what a writer means by "where does this link
    sit" is the section they are reading, which is whatever heading last
    opened.
    """

    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict] = []
        self._current: dict | None = None
        self._text: list[str] = []
        self._region = "body"
        self._region_stack: list[str] = []
        #: The heading last closed, and the buffer collecting one now.
        self._heading = ""
        self._in_heading: str | None = None
        self._heading_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("nav", "header", "footer", "aside"):
            self._region_stack.append(self._region)
            self._region = "nav" if tag in ("nav", "header") else tag
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_heading = tag
            self._heading_text = []
        elif tag == "a":
            a = dict(attrs)
            if a.get("href"):
                self._current = {"href": a["href"], "rel": a.get("rel") or "",
                                 "region": self._region,
                                 "position": self._heading}
                self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("nav", "header", "footer", "aside") and self._region_stack:
            self._region = self._region_stack.pop()
        elif tag == self._in_heading:
            text = " ".join("".join(self._heading_text).split())[:POSITION_CAP]
            # The level travels with it: "h2 What it costs" is what a
            # writer is told to place a link after, and the bare text
            # would not say whether that is a section or a sub-section.
            self._heading = f"{tag} {text}" if text else ""
            self._in_heading = None
        elif tag == "a" and self._current is not None:
            self._current["anchor"] = " ".join("".join(self._text).split())[:120]
            self.links.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data)
        if self._in_heading is not None:
            self._heading_text.append(data)

    def handle_startendtag(self, tag, attrs):
        if tag == "img" and self._current is not None:
            alt = dict(attrs).get("alt")
            self._text.append(f"[image alt: {alt}]" if alt else "[image, no alt]")


def extract_link_details(page: Page) -> list[dict]:
    """Internal links with anchor text, rel and page region. A real <a href>
    only — click handlers and router bindings are not crawlable and must not
    be counted as though they were."""
    if not page.content or not page.content_type.startswith("text/html"):
        return []
    parser = _LinkParser()
    try:
        parser.feed(page.content)
    except Exception:
        return []
    base_host = urlsplit(page.url).hostname
    seen: set[str] = set()
    out: list[dict] = []
    for link in parser.links:
        href = link["href"].strip()
        if href.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        target = urljoin(page.url, href)
        # Two spellings, and both are needed. `url` is the crawler's identity
        # for the target, so an ad-tagged link and the clean link beside it
        # enqueue once; `href` is the link as the markup wrote it, which is
        # the subject of TEC's `internal-link-tracking-params` and cannot be
        # recovered from `url` once the tag is gone
        # (`tests/test_internal_links_carry_tracking_parameters.py`).
        raw = _canonical_spelling(target, strip_tracking=False)
        absolute = normalise_url(target)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https") or parts.hostname != base_host:
            continue
        # Keyed on the raw spelling, not the stripped one: two anchors sharing
        # their text and differing only in their campaign tag are two links in
        # the markup and two attribution defects, and merging them would
        # undercount the finding that reports them. This is also the key this
        # line used before the strip existed, so the deduplication is unchanged.
        key = f"{raw}|{link.get('anchor', '')}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"url": absolute, "href": raw, "anchor": link.get("anchor", ""),
                    "rel": link.get("rel", ""), "region": link.get("region", "body"),
                    # The heading this link follows (operator, 2026-09-06),
                    # so `links.md`'s LINK GRAPH fills as written and a
                    # suggestion can say where a new link belongs.
                    "position": link.get("position", "")})
    return out


def extract_links(page: Page) -> list[str]:
    """Unique internal link targets, in discovery order."""
    urls: list[str] = []
    for link in extract_link_details(page):
        if link["url"] not in urls:
            urls.append(link["url"])
    return urls


def _parse_sitemap(content: str, limit: int) -> tuple[list[str], bool, dict[str, str]]:
    """Returns (urls, is_index, lastmod_by_url). A sitemap index lists further
    sitemaps rather than pages, and must be followed rather than counted.

    `lastmod` is kept because it is the only date a crawl can see without
    fetching every page again — but it is kept separately from the other date
    signals rather than merged into one "last updated" value, because plenty
    of CMSs stamp every entry with the build time. A freshness judgement needs
    to know which signal it is reading.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise
    is_index = root.tag.endswith("sitemapindex")
    urls: list[str] = []
    lastmod: dict[str, str] = {}
    for entry in root:
        loc = next((el.text.strip() for el in entry
                    if el.tag.endswith("loc") and el.text), None)
        if not loc:
            continue
        urls.append(loc)
        stamp = next((el.text.strip() for el in entry
                      if el.tag.endswith("lastmod") and el.text), None)
        if stamp:
            lastmod[loc] = stamp
    if not urls:                     # flat or unusually nested document
        urls = [el.text.strip() for el in root.iter()
                if el.tag.endswith("loc") and el.text]
    return urls[:limit], is_index, lastmod


def _read_sitemaps(fetcher: Fetcher, candidates: list[str], policy: RobotsPolicy,
                   result: CrawlResult, limit: int, delay: float,
                   deadline: float, declared: bool = True) -> None:
    """Breadth-first over sitemaps and sitemap indexes, recording the outcome
    of each so 'no sitemap' can be told apart from 'unreachable' and
    'malformed'.

    `declared` says the initial `candidates` were pointed at by the operator
    (a robots.txt `Sitemap:` line), not the bare `/sitemap.xml` the crawler
    probes when robots declared none. A sitemap index is itself a declaration,
    so every child queued from one is declared regardless of how the index was
    reached — the record's `declared` flag carries this to the checks."""
    queue = [(url, declared) for url in candidates[:MAX_SITEMAPS]]
    seen: set[str] = set()
    while queue and len(result.sitemaps) < MAX_SITEMAPS:
        sitemap_url, is_declared = queue.pop(0)
        if sitemap_url in seen or time.monotonic() > deadline:
            break
        seen.add(sitemap_url)
        if not policy.allows(sitemap_url, USER_AGENT):
            result.robots_blocked.append(sitemap_url)
            result.sitemaps.append(SitemapRecord(url=sitemap_url,
                                                 error="disallowed by robots.txt",
                                                 declared=is_declared))
            continue
        time.sleep(delay)
        page = fetcher.fetch(sitemap_url)
        record = SitemapRecord(url=sitemap_url, status=page.status or None,
                               declared=is_declared)
        if page.error:
            record.error = page.error
        elif page.status == 200:
            try:
                urls, is_index, lastmod = _parse_sitemap(page.content, limit)
                record.is_index = is_index
                record.entry_count = len(urls)
                if is_index:
                    # An index is a declaration of its children.
                    queue.extend((u, True) for u in urls if u not in seen)
                else:
                    result.sitemap_entries.extend(urls)
                    result.sitemap_lastmod.update(lastmod)
            except ET.ParseError as exc:
                record.error = f"malformed XML: {exc}"
        result.sitemaps.append(record)
        if sitemap_url not in result.sitemap_urls:
            result.sitemap_urls.append(sitemap_url)


#: What a link's position says about how much the site itself values the
#: page. Ranked, and used to order the frontier: a breadth-first queue with
#: no ordering spends a small budget on whatever happened to be first in the
#: HTML, which on most templates is a cookie banner and a run of social
#: icons. The site's own navigation is the closest thing to an editorial
#: statement of which pages matter.
REGION_RANK: dict[str, int] = {"nav": 0, "body": 1, "footer": 2, "aside": 3}


def crawl(
    start_url: str,
    tier: Tier,
    budget: TierBudget | None = None,
    fetcher: Fetcher | None = None,
    on_progress=None,
    nav_only: bool = False,
    only_urls: list[str] | None = None,
    should_stop=None,
    ua_matrix: bool = False,
    security_paths: bool = False,
    mobile_parity: bool | str = False,
) -> CrawlResult:
    """Fetch a site, breadth-first, ordered by what its own markup implies.

    `nav_only` crawls the entry page and the pages its navigation links to,
    and stops. That is the set a site says is important, which is a far
    better small sample than "the first N URLs encountered" — and it is what
    makes a cheap audit of a large site worth running at all.

    `only_urls` fetches exactly those URLs and follows nothing. It exists for
    verification: after fixing four titles you want those four pages looked at
    again, not a hundred. Restricting the frontier is also the only honest way
    to do it — the state machine may only clear a finding whose page was
    actually revisited, so a verification pass has to genuinely fetch them.

    The two are different restrictions and both set `scope`, because a check
    that compares the crawl against the whole site has to know it is holding
    a sample rather than a census.

    `should_stop` is asked once per page, at the top of the loop beside the
    budget and the clock (relay item 136a). It is the operator changing
    their mind, and it is answered at a page boundary rather than mid-fetch:
    a half-read page is not evidence, and killing the thread would leave the
    run row `running` for ever. The crawl returns what it had, marked
    `truncated_by="cancelled"` - the same way it reports the other two
    reasons it stopped short, because "why is this crawl smaller than I
    expected" is one question with three answers.
    """
    budget = budget or TIER_BUDGETS[tier]
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher(timeout_s=budget.request_timeout_s)
    handed = start_url
    # CQ-133's other half, and the guard sits *here* rather than beside the
    # `netloc` check below because that is where the failure said it belonged:
    # `normalise_url` calls `urlsplit` one line further up, so an unbalanced
    # bracket never reached the check. Report 064 anchored this at the
    # `netloc` test, which is one call too late -- driving
    # `crawl('https://a]b/', Tier.T1)` raises inside `normalise_url`, which
    # delegates to `_canonical_spelling` and its `urlsplit`, not at the check.
    # Named as symbols rather than as a line: the address this carried for
    # eleven reports had drifted onto a note about tracking parameters and was
    # never the raise site, and a name does not go stale when the file grows
    # (CQ-240). The cost of getting it wrong is the
    # raw parser error "Invalid IPv6 URL" -- which names neither the URL nor
    # this product -- landing in a stored `fail_run` reason, where the ASCII
    # sentence twenty lines below was written to be what the operator reads.
    try:
        urlsplit(start_url)
    except ValueError as exc:
        raise ValueError(
            # ASCII only, for the reason the message below gives.
            f"start URL {start_url!r} cannot be parsed as a URL "
            f"({exc}): check the host for an unbalanced bracket") from exc
    start_url = normalise_url(start_url)
    # CQ-103: close the class in the room rather than at the doors. `crawl` is
    # imported as `crawl_site` by `clauditseo/api/app.py:32` and
    # `clauditseo/cli.py:115`, so this is the single choke point for every
    # crawl the product launches — the five call sites in `adaptive.py`,
    # `api/app.py` and `cli.py`, and whichever entry point is added next.
    # Round 051 guarded three doors while this function went on accepting
    # what they were guarding against.
    #
    # Refused, not repaired. Given `www.acme.com.au` this cannot know
    # whether the caller meant https or a scheme the operator chose, and
    # guessing is `crawl_start_url`'s job one layer up, with the stored domain
    # in hand. A crawl with no host fetches `http:///robots.txt`, reaches
    # nothing, and TEC reports the absence it manufactured as `The site is not
    # served over HTTPS.` at `confidence: high` — so a loud failed run is the
    # cheaper outcome by a wide margin.
    if not urlsplit(start_url).netloc:
        raise ValueError(
            # ASCII only: this reaches a Windows console and a stored
            # `fail_run` reason, and cp1252 renders an em dash as a
            # replacement character in both.
            f"no host in start URL {start_url!r} (handed {handed!r}): "
            "a domain becomes a crawlable URL through crawl_start_url()")
    result = CrawlResult(
        start_url=start_url, tier=tier,
        scope="verify" if only_urls else "nav" if nav_only else "site")
    deadline = time.monotonic() + budget.wall_clock_s

    try:
        robots_page = fetcher.fetch(robots_url_for(start_url))
        result.robots_txt = robots_page.content if robots_page.status == 200 else None
        result.robots_status = robots_page.status or None
        policy = RobotsPolicy(robots_page.url, robots_page.status or None,
                              robots_page.content)

        # llms.txt (AI-surface guidance file) — one cheap metadata fetch.
        llms_url = urljoin(start_url, "/llms.txt")
        if policy.allows(llms_url, USER_AGENT):
            time.sleep(budget.delay_s)
            llms_page = fetcher.fetch(llms_url)
            result.llms_txt_status = llms_page.status or None
            if llms_page.status == 200:
                result.llms_txt = llms_page.content

        limit = SITEMAP_HEAD_ENTRIES if tier is Tier.T1 else SITEMAP_FULL_ENTRIES
        # Declared: robots pointed at these. Probed: nothing did, and the crawler
        # guesses `/sitemap.xml` — a 404 on that guess is 'no sitemap', not a
        # broken one, so the two are told apart on the record's `declared` flag.
        declared = bool(policy.sitemaps)
        candidates = list(policy.sitemaps) or [urljoin(start_url, "/sitemap.xml")]
        _read_sitemaps(fetcher, candidates, policy, result, limit,
                       budget.delay_s, deadline, declared=declared)

        # (rank, sequence, url, how it was found). heapq rather than a plain
        # FIFO so navigation links are fetched before body links wherever the
        # budget runs out; `seq` keeps insertion order stable within a rank.
        # A verification pass seeds the named pages instead of the entry
        # page: fetching the homepage to re-check a title on /contact would be
        # a request for nothing.
        if only_urls:
            seeds = [normalise_url(u) for u in only_urls]
            queue: list[tuple[int, int, str, str]] = [
                (0, i, u, "start") for i, u in enumerate(dict.fromkeys(seeds))]
            seq = len(queue)
            queued: set[str] = set(seeds)
        else:
            queue = [(0, 0, start_url, "start")]
            seq = 1
            queued = {start_url}
        fetched_finals: dict[str, str] = {}   # normalised final URL -> requested
        while queue:
            if should_stop is not None and should_stop():
                result.truncated_by = "cancelled"
                break
            if len(result.pages) >= budget.max_pages:
                result.truncated_by = "max_pages"
                break
            if time.monotonic() > deadline:
                result.truncated_by = "wall_clock"
                break
            _, _, url, source = heapq.heappop(queue)
            if not policy.allows(url, USER_AGENT):
                result.robots_blocked.append(url)
                continue
            time.sleep(budget.delay_s)
            page = fetcher.fetch(url)
            page.discovered_via = source

            # Two spellings that redirect to the same place are one page, not
            # two. Record the collapse as evidence rather than discarding it.
            final = normalise_url(page.url)
            if final in fetched_finals and final != normalise_url(url):
                result.duplicate_forms.setdefault(final, []).append(url)
                continue
            if final in fetched_finals:
                continue
            fetched_finals[final] = url

            page.link_details = extract_link_details(page)
            page.outlinks = []
            for link in page.link_details:
                if link["url"] not in page.outlinks:
                    page.outlinks.append(link["url"])
            result.pages.append(page)
            if on_progress:
                on_progress(len(result.pages))
            # Enqueue by the best region the link was seen in: a page linked
            # from both the nav and the footer is a nav page.
            best: dict[str, str] = {}
            for link in page.link_details:
                region = link.get("region") or "body"
                if link["url"] not in best or \
                        REGION_RANK.get(region, 9) < REGION_RANK.get(best[link["url"]], 9):
                    best[link["url"]] = region
            for link_url, region in best.items():
                if link_url in queued:
                    continue
                # In nav mode the navigation of the entry page is the whole
                # frontier. Following nav links onward would walk the site,
                # since every page repeats the same menu.
                if nav_only and (source != "start" or region != "nav"):
                    continue
                # Verification follows nothing: the named pages are the job.
                if only_urls is not None:
                    continue
                queued.add(link_url)
                heapq.heappush(queue, (REGION_RANK.get(region, 9), seq, link_url,
                                       region if region == "nav" else "link"))
                seq += 1

        # Host-level transport facts, once per crawl rather than per page.
        try:
            from .transport import probe
            result.transport = probe(start_url)
        except Exception:
            result.transport = None

        # The well-known path sweep (item 143 step BD): opt-in, asked for by a
        # run that includes SEC, and never on a verification or page refresh -
        # those name their pages and a site-level sweep is not what they asked.
        # Plain GETs, disclosed in the client report (143 addendum).
        if security_paths and only_urls is None:
            try:
                from .wellknown import sweep
                result.well_known = sweep(start_url)
            except Exception:
                result.well_known = None
            # Domain E's public DNS lookups, on the same opt-in: a run that
            # asks for SEC, never a verification.
            try:
                from urllib.parse import urlsplit as _us

                from .dnsq import collect
                host = (_us(start_url).hostname or "").lower()
                apex = host[4:] if host.startswith("www.") else host
                result.dns = collect(apex) if apex else None
            except Exception:
                result.dns = None

        # The UA matrix (item 137 task 4): how the server answers each named
        # crawler's user-agent string. It is 8x(1+probes) extra fetches, so it is
        # OPT-IN — the deep audit crawl asks for it (`ua_matrix=True`), and an
        # incidental crawl that happens to be T2 does not pay for it. Even when
        # asked, it runs only on a full site crawl at T2 or deeper that actually
        # reached pages: a T1 pulse, a nav/verify scope and a robots deny-all
        # (fetch nothing) each answer a narrower question the matrix must not
        # override. Deadline-bounded, and failure is not fatal to the crawl.
        if (ua_matrix and tier is not Tier.T1 and result.scope == "site"
                and result.pages):
            try:
                from .ua_matrix import build_ua_matrix
                result.ua_matrix = build_ua_matrix(
                    start_url, result.pages, policy,
                    budget.request_timeout_s, deadline, budget.delay_s)
            except Exception:
                result.ua_matrix = []

        # The mobile and bot parity probe (item 151): a sample of the reached
        # pages fetched again as desktop Chrome, iPhone Safari and
        # Googlebot-smartphone. Opt-in like the matrix, but at any tier - T1
        # probes the pulse's pages - and never on a verification, which names
        # its pages for a narrower question. `"full"` probes every readable
        # page, for a site whose previous run diverged; `True` is the sample.
        if mobile_parity and only_urls is None and eligible(result.pages):
            # The sample is a handful of fetches, so it gets a minute of its own
            # past a crawl that spent its whole clock: a crawl truncated by
            # `wall_clock` is common at T2, and a probe skipped on every one of
            # them would never accumulate. Full mode gets five, and the block
            # says `truncated_by` where that was not enough.
            parity_deadline = max(deadline, time.monotonic()
                                  + (300 if mobile_parity == "full" else 60))
            try:
                from .parity import probe as parity_probe
                result.mobile_parity = parity_probe(
                    result.pages, tier, start_url, budget.request_timeout_s,
                    parity_deadline, budget.delay_s,
                    mode="full" if mobile_parity == "full" else "sample")
            except Exception:
                result.mobile_parity = None

        result.stats = {
            # Two counts, two names, because they answer different questions
            # and only one of them may be called "fetched" downstream:
            # `fetched` is URLs attempted — a DNS failure leaves a Page — and
            # `eligible` is what a check could actually read.
            "fetched": len(result.pages),
            "eligible": len(eligible(result.pages)),
            "blocked_by_robots": len(result.robots_blocked),
            "errors": sum(1 for p in result.pages if p.error),
            "queue_remaining": len(queue),
            "duplicate_url_forms": sum(len(v) for v in result.duplicate_forms.values()),
            "sitemaps_read": len(result.sitemaps),
        }
        return result
    finally:
        if own_fetcher:
            fetcher.close()
