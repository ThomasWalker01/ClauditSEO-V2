"""What the site says about itself, read before any scan is chosen.

Fetches `robots.txt`, the sitemap it declares, and the entry page's navigation,
then reports how many pages each scan scope would visit and what the two
sources disagree about. No model calls: this is HTTP and parsing, and its whole
value is that the page counts a scan offers are *measured* rather than
estimated.

**Why it is separate from a crawl.** A crawl is the expensive thing the
operator is deciding whether to buy. This runs first, costs four to six
requests, and answers the question the scan screen cannot otherwise answer:
"how big is each of these, here, on this site". It reads one page and stops.

**The disagreement is the point.** A sitemap and a navigation are two claims
about what a site contains, written by different tools at different times.
Where they differ is a real defect, and reading both is what this step is
already doing to count the pages - so the finding costs nothing beyond the
counting.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlsplit

from clauditseo.crawler.crawl import (
    _read_sitemaps,
    crawl_start_url,
    extract_link_details,
    normalise_url,
)
from clauditseo.crawler.fetch import Fetcher
from clauditseo.crawler.robots import RobotsPolicy, robots_url_for
from clauditseo.crawler.types import USER_AGENT, CrawlResult, Tier

#: The sitemap entry ceiling. Deliberately the crawler's full figure and not
#: its T1 head sample: the precheck's entire job is the true total, so reading
#: only the head would answer a different question.
SITEMAP_LIMIT = 5000

#: How many published URLs the payload carries for the chooser's picker. A
#: picker is a convenience, not the record: the count above it is the truth,
#: and a row that shipped five thousand URLs to draw a dropdown would make
#: every page load pay for a control most operators never open.
PICKER_LIMIT = 500

#: One page fetch, a robots fetch and a handful of sitemaps. The bound exists
#: so a hung host cannot hold the request open; it is not a crawl budget.
DEADLINE_S = 30.0

#: Regions whose links count as navigation. `aside` is excluded deliberately —
#: a sidebar of related links is not the site's statement about its own shape.
#: Note `nav` here already includes `<header>`: the crawler's parser folds the
#: two together (`crawler/crawl.py`, `_LinkParser.handle_starttag`), and this
#: module reports what that parser can actually distinguish rather than
#: implying a header/nav split that does not exist upstream.
NAV_REGIONS = ("nav", "footer")

#: Sitemap outcomes. `ok` is the only one under which a page total is known,
#: and the only one under which the disagreement findings mean anything.
SITEMAP_STATES = ("ok", "absent", "unreachable", "malformed", "blocked_by_robots")


@dataclass
class PrecheckResult:
    entry_url: str
    checked_at: str
    took_ms: int
    sitemap_state: str
    sitemap_files: int = 0
    #: `None`, never 0, whenever `sitemap_state` is not `ok`. A zero here would
    #: be read as "this site has no pages", which is a different claim from
    #: "nobody could tell us", and would send the operator to fix the wrong
    #: thing.
    sitemap_urls: int | None = None
    sitemap_truncated: bool = False
    #: Distinct URLs whose *best* region is nav (which includes `<header>`)
    #: or footer. There is deliberately no "in both" figure: the crawler's
    #: `extract_link_details` keys its deduplication on the link's spelling and
    #: anchor, so a URL appearing in both the header and the footer survives
    #: once, carrying whichever region it was seen in first. The overlap is not
    #: observable from here, and a number that cannot be derived is not
    #: reported.
    nav_count: int = 0
    footer_count: int = 0
    nav_unique: int = 0
    #: In the sitemap, linked from neither nav nor footer of the entry page.
    not_linked: list[str] = field(default_factory=list)
    #: Linked from nav or footer, absent from the sitemap.
    not_in_sitemap: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: The URLs behind the counts, so the chooser can offer them rather than
    #: asking the operator to type one. Already fetched — returning them costs
    #: nothing and not returning them made the Page row a free-text box for a
    #: list the product was already holding.
    nav_urls: list[str] = field(default_factory=list)
    #: Published pages, capped for the payload. The cap is stated in
    #: `page_urls_capped` rather than left for a reader to infer from a round
    #: number, because a picker silently missing its last entries is worse
    #: than one that says it is showing the first N.
    page_urls: list[str] = field(default_factory=list)
    page_urls_capped: bool = False

    @property
    def findings_meaningful(self) -> bool:
        """Whether the two disagreement lists say anything.

        With no readable sitemap there is nothing to disagree with, and
        reporting "every nav page is missing from the sitemap" on a site whose
        sitemap 404s is noise stacked on top of a different problem.
        """
        return self.sitemap_state == "ok"

    def scopes(self) -> dict[str, dict]:
        """Page counts per scan scope, in the vocabulary the scan screen uses.

        `site` is absent here on purpose. Its cap is currently a crawler tier
        budget and will be set by the scan-scope work; quoting a number this
        module did not measure would be exactly the estimate the precheck
        exists to replace.
        """
        return {
            "page": {"pages": 1, "basis": "a URL you name"},
            # "N in the navigation, M OF THEM in the footer" (audit F9): the
            # footer's links are inside `nav_unique`, not additional to it, so
            # "15 in navigation, 1 in the footer" under a figure of 15 read as
            # 16. `nav_pages` is the union both counts come from.
            "nav": {"pages": self.nav_unique,
                    "basis": f"{self.nav_count} in the navigation, "
                             f"{self.footer_count} of them in the footer"},
            # The site's size, not the sitemap's: the union of what the
            # sitemap declares and what the entry page's nav reached (audit
            # F10). It was `sitemap_urls` alone - 49 on twenty22, on a screen
            # whose header says the site has 53 and whose own panel names the
            # 4 pages found and not declared - and the registry says Full "is
            # the only scan whose coverage can reach 100%", which at 49 of 53
            # it cannot. `population.tsx` gives the rule: "divide by the
            # declaration and coverage rises when the declaration fails."
            "full": {"pages": None if self.sitemap_urls is None
                              else self.sitemap_urls + len(self.not_in_sitemap),
                     "basis": self._full_basis()},
        }

    def _full_basis(self) -> str:
        if self.sitemap_state != "ok":
            return {
                "absent": "no sitemap declared or found",
                "unreachable": "the sitemap could not be fetched",
                "malformed": "the sitemap could not be parsed",
                "blocked_by_robots": "robots.txt disallows the sitemap",
            }.get(self.sitemap_state, self.sitemap_state)
        files = f"{self.sitemap_files} file" + ("s" if self.sitemap_files != 1 else "")
        # The basis names both halves of the union the figure now is (audit
        # F10): "sitemap, 7 files" described a number that is no longer the
        # sitemap's alone.
        extra = len(self.not_in_sitemap)
        return (f"sitemap, {files}"
                + (f" + {extra} found in the navigation" if extra else "")
                + (f", capped at {SITEMAP_LIMIT}" if self.sitemap_truncated else ""))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scopes"] = self.scopes()
        d["findings_meaningful"] = self.findings_meaningful
        return d


def _diff_key(url: str) -> str:
    """The identity two *sources* are compared under, which is looser than the
    identity the crawler fetches under.

    `normalise_url` settles scheme case, default ports and tracking parameters,
    and deliberately keeps a trailing slash: `/a` and `/a/` may serve different
    content, so a crawler must not merge them. A sitemap generator and a
    hand-written menu routinely disagree about that slash on the same page,
    and merging them here is the difference between reporting one orphan and
    reporting eleven that do not exist.

    The risk is stated rather than hidden: on a site that really does serve
    different content at `/a` and `/a/`, this under-reports. That is the safer
    error. A false orphan sends the operator to fix a page that is fine; a
    missed one is found by the next real crawl.
    """
    n = normalise_url(url)
    parts = urlsplit(n)
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return f"{parts.scheme}://{parts.netloc}{path}" + (
        f"?{parts.query}" if parts.query else "")


def _sitemap_state(result: CrawlResult, candidates: list[str]) -> str:
    """One word for how the sitemap read went.

    Derived from the per-sitemap records the crawler already keeps —
    `SitemapRecord` exists precisely so "absent" can be told from "unreachable"
    from "malformed", and this function is the first caller to use that
    distinction rather than collapse it.
    """
    if not candidates:
        return "absent"
    if result.robots_blocked and not result.sitemaps:
        return "blocked_by_robots"
    if not result.sitemaps:
        return "unreachable"
    if any(r.entry_count > 0 or r.is_index for r in result.sitemaps):
        return "ok"
    seen = [r.status for r in result.sitemaps if r.status is not None]
    # Order matters. A 2xx that yielded nothing is a sitemap we read and could
    # not understand; anything else that is not a plain 404 is one we never
    # read at all. Collapsing the two would tell the operator to go and fix a
    # file that may be perfectly well-formed and merely unserved.
    if any(200 <= st < 300 for st in seen):
        return "malformed"
    if seen and all(st == 404 for st in seen):
        return "absent"
    if any(st == 0 or st >= 400 for st in seen):
        return "unreachable"
    return "absent"


def run_precheck(domain: str, start_url: str | None = None, *,
                 timeout_s: float = 10.0, delay_s: float = 0.5,
                 now: str | None = None) -> PrecheckResult:
    """Read robots, the sitemap and the entry page's navigation. One page only.

    `now` is injectable so a test can assert the stamp without freezing time.
    """
    started = time.monotonic()
    entry = start_url or crawl_start_url(domain)
    warnings: list[str] = []

    fetcher = Fetcher(timeout_s=timeout_s)
    try:
        # --- robots, and the sitemaps it declares -------------------------
        robots_url = robots_url_for(entry)
        robots_page = fetcher.fetch(robots_url)
        policy = RobotsPolicy(robots_url, robots_page.status, robots_page.content)
        declared = bool(policy.sitemaps)
        candidates = list(policy.sitemaps) or [urljoin(entry, "/sitemap.xml")]

        result = CrawlResult(start_url=entry, tier=Tier.T2)
        result.robots_txt = robots_page.content
        result.robots_status = robots_page.status
        _read_sitemaps(fetcher, candidates, policy, result, SITEMAP_LIMIT,
                       delay_s, time.monotonic() + DEADLINE_S, declared=declared)

        state = _sitemap_state(result, candidates)
        sitemap_pages = {_diff_key(u): normalise_url(u)
                         for u in result.sitemap_entries}

        # --- the entry page's navigation ----------------------------------
        entry_page = fetcher.fetch(entry)
        if entry_page.status != 200 or not entry_page.content:
            # Fail loudly rather than reporting nav: 0. A count of zero is a
            # claim about the site; a failed fetch is a claim about the fetch.
            raise PrecheckError(
                f"the entry page {entry} could not be read "
                f"(HTTP {entry_page.status or 'no response'})")

        by_region: dict[str, set[str]] = {"nav": set(), "footer": set()}
        nav_by_key: dict[str, str] = {}
        for link in extract_link_details(entry_page):
            region = link.get("region", "body")
            if region in by_region:
                by_region[region].add(link["url"])
                nav_by_key[_diff_key(link["url"])] = link["url"]

        nav, footer = by_region["nav"], by_region["footer"]
        nav_pages = nav | footer

        if len(nav_pages) < 3:
            warnings.append(
                "fewer than three navigation links were found. A site that "
                "builds its menu in JavaScript renders none to a fetcher, so "
                "this is more often a rendering artefact than a finding.")

    finally:
        fetcher.close()

    took = int((time.monotonic() - started) * 1000)
    out = PrecheckResult(
        entry_url=entry,
        checked_at=now or _stamp(),
        took_ms=took,
        sitemap_state=state,
        sitemap_files=len(result.sitemaps),
        sitemap_urls=len(sitemap_pages) if state == "ok" else None,
        sitemap_truncated=len(result.sitemap_entries) >= SITEMAP_LIMIT,
        nav_count=len(nav),
        footer_count=len(footer),
        nav_unique=len(nav_pages),
        warnings=warnings,
        nav_urls=sorted(nav_pages),
        page_urls=sorted(sitemap_pages.values())[:PICKER_LIMIT],
        page_urls_capped=len(sitemap_pages) > PICKER_LIMIT,
    )
    if out.findings_meaningful:
        out.not_linked = sorted(url for key, url in sitemap_pages.items()
                                if key not in nav_by_key)
        out.not_in_sitemap = sorted(url for key, url in nav_by_key.items()
                                    if key not in sitemap_pages)
    return out


def _stamp() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat(timespec="seconds")


class PrecheckError(RuntimeError):
    """The precheck could not reach far enough to say anything true."""
