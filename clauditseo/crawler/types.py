from __future__ import annotations

from clauditseo import BOT_NAME

from collections.abc import Iterable
from dataclasses import dataclass, field

from clauditseo.engine.types import Tier

# What every site we crawl sees in its logs, and the one place the product
# name reaches somebody else's server. Built from the shared constant so it
# cannot drift from the name on the report the same crawl produces.
USER_AGENT = f"{BOT_NAME}/0.1 (self-hosted SEO audit; polite)"


@dataclass(frozen=True)
class TierBudget:
    max_pages: int
    request_timeout_s: float
    wall_clock_s: float
    delay_s: float          # pause between requests to the same host


# T3 is "unbounded" in spirit but still hard-capped so a misconfigured crawl
# can never run away.
TIER_BUDGETS: dict[Tier, TierBudget] = {
    Tier.T1: TierBudget(max_pages=3, request_timeout_s=10, wall_clock_s=120, delay_s=0.5),
    Tier.T2: TierBudget(max_pages=100, request_timeout_s=15, wall_clock_s=900, delay_s=0.5),
    Tier.T3: TierBudget(max_pages=500, request_timeout_s=20, wall_clock_s=3600, delay_s=0.5),
}


@dataclass
class Page:
    url: str                      # final URL after redirects
    requested_url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    content: str = ""
    content_type: str = ""
    elapsed_ms: float = 0.0
    redirect_chain: list[str] = field(default_factory=list)  # intermediate URLs, in order
    #: The status code of each redirect hop, parallel to `redirect_chain`
    #: (item 137, FEATURES F-13). Kept apart from the URLs so a 302 can be told
    #: from a 301 without changing the list every other reader treats as URLs;
    #: empty on a run crawled before it was captured.
    redirect_statuses: list[int] = field(default_factory=list)
    error: str | None = None
    # Evidence the indexability and crawl tools need, captured at
    # fetch time because it cannot be reconstructed from stored findings.
    outlinks: list[str] = field(default_factory=list)   # internal, normalised
    # Same links with their anchor text and rel attributes: the internal
    # link graph is only half the story without what the links actually say.
    link_details: list[dict] = field(default_factory=list)
    discovered_via: str = "link"                        # start | link | sitemap

    @property
    def x_robots_tag(self) -> str | None:
        return self.headers.get("x-robots-tag")

    @property
    def link_header_canonical(self) -> str | None:
        """rel=canonical delivered as an HTTP Link header rather than markup —
        invisible to a head-only check but binding on crawlers."""
        header = self.headers.get("link") or ""
        for part in header.split(","):
            if 'rel="canonical"' in part.replace("'", '"').replace(" ", "") \
                    or "rel=canonical" in part.replace(" ", ""):
                start, _, rest = part.partition("<")
                target, _, _ = rest.partition(">")
                if target:
                    return target.strip()
        return None


def page_is_eligible(page: Page) -> bool:
    """Whether a page-scoped check could have read this page.

    A `Page` object survives a failed fetch — a DNS failure leaves one with
    `status=0`, an empty content type and an `error` — so the length of a page
    list is the number of URLs **attempted**, never the number fetched. Three
    404s and a PDF are attempts too.

    Every count that means "fetched" comes through here. It used to be spelled
    out in `scoring.eligible_pages` alone while six other places counted
    `len(pages)` instead, and the two disagreed exactly where it mattered: on
    a crawl that resolved nothing, which is the case every "did we measure
    this" sentence is written for.
    """
    return stored_page_is_eligible({"status": page.status,
                                    "content_type": page.content_type})


def stored_page_is_eligible(page: dict) -> bool:
    """The same rule, asked of a page read back out of `crawl_evidence`.

    A crawl's `Page` objects do not survive the run; the evidence blob keeps
    `status` and `content_type` for each of them, which is everything the rule
    above needs. `_scope` derives a run's readable-page count through here for
    runs stored before engine 0.9.0 wrote `stats["eligible"]`, rather than
    falling through to `stats["fetched"]` — which is attempts.

    Written as the one implementation and called by `page_is_eligible` rather
    than beside it, for the reason that docstring gives: this rule spelled out
    in two places is how six places came to count `len(pages)` instead.
    """
    return (page.get("status") == 200
            and str(page.get("content_type") or "").startswith("text/html"))


def eligible(pages: Iterable[Page]) -> list[Page]:
    """The pages of a crawl a page-scoped check can actually apply to."""
    return [p for p in pages if page_is_eligible(p)]


@dataclass
class TransportProbe:
    """One-off TLS and HTTP→HTTPS facts for the origin. Separate from the
    page crawl because it is a property of the host, not of any page, and
    because a security brief must not be left guessing at transport."""
    host: str
    tls_version: str | None = None
    cipher: str | None = None
    #: The lowest version the server accepted, and whether every version
    #: below it was actually offered and refused. `tls_version` is the
    #: ceiling one handshake reached; these two are the floor, which is what
    #: "is this site still on old TLS?" actually asks.
    tls_floor: str | None = None
    tls_floor_certain: bool = False
    #: Per version: accepted | rejected | not-offered | failed.
    tls_offered: dict[str, str] = field(default_factory=dict)
    cert_not_after: str | None = None
    cert_subject_alt_names: list[str] = field(default_factory=list)
    http_redirects_to_https: bool | None = None
    http_redirect_chain: list[str] = field(default_factory=list)
    http_version: str | None = None
    #: The protocol ALPN settled on when h2 and http/1.1 were both offered
    #: (item 143 step BD): "h2", "http/1.1", or None where the server named
    #: none. h3 runs over QUIC and is not asked here; Alt-Svc says whether
    #: it is offered.
    alpn: str | None = None
    #: The leaf certificate's key and signature, read from its DER: "rsa" /
    #: "ec" / "ed25519" / an OID, its size in bits, and the signature
    #: algorithm's name or OID.
    cert_key_type: str | None = None
    cert_key_bits: int | None = None
    cert_signature: str | None = None
    error: str | None = None


@dataclass
class SitemapRecord:
    """Per-sitemap fetch outcome, so 'sitemap-missing' can distinguish absent
    from unreachable from malformed.

    `declared` says the operator pointed at this URL — a `Sitemap:` line in
    robots.txt, or an entry inside a sitemap index the crawl read — as opposed
    to the bare `/sitemap.xml` the crawler probes when nothing was declared. A
    declared sitemap that 404s is a broken promise ('sitemap-invalid'); a
    probed one that 404s is simply the absence of a sitemap ('sitemap-missing').
    """
    url: str
    status: int | None = None
    entry_count: int = 0
    is_index: bool = False
    error: str | None = None
    declared: bool = False


@dataclass
class CrawlResult:
    start_url: str
    tier: Tier
    pages: list[Page] = field(default_factory=list)
    robots_txt: str | None = None
    robots_status: int | None = None
    llms_txt: str | None = None
    llms_txt_status: int | None = None
    robots_blocked: list[str] = field(default_factory=list)  # URLs we declined to fetch
    sitemap_urls: list[str] = field(default_factory=list)    # sitemap locations declared
    sitemap_entries: list[str] = field(default_factory=list) # URLs listed in sitemaps we read
    # Declared <lastmod> per URL, kept apart from the entry list so a freshness
    # judgement can weigh it against the other date signals rather than trust it.
    sitemap_lastmod: dict[str, str] = field(default_factory=dict)
    sitemaps: list[SitemapRecord] = field(default_factory=list)
    # URL forms that resolved to a page already fetched under another form —
    # the raw material for duplicate-URL-form findings.
    duplicate_forms: dict[str, list[str]] = field(default_factory=dict)
    transport: TransportProbe | None = None
    truncated_by: str | None = None                          # max_pages | wall_clock | None
    # Whether the frontier itself was restricted, as opposed to the crawl
    # running out of budget. A nav-scoped crawl is not truncated — it reached
    # everything it set out to reach — so `truncated_by` stays None, and any
    # check that compares the crawl against the whole site has to know the
    # difference. Sitemap coverage reported 252 unreachable URLs on a 20-page
    # nav crawl of a 271-URL sitemap, which is the scope working exactly as
    # asked and the check describing it as a site defect.
    scope: str = "site"                                      # site | nav
    # Per-agent UA-string treatment (item 137 task 4): robots verdict, home and
    # probe statuses, CDN/WAF header hints. One row per named agent; empty on a
    # T1 pulse or a nav/verify crawl, which do not run the matrix pass.
    ua_matrix: list[dict] = field(default_factory=list)
    #: The well-known path sweep (item 143 step BD, `crawler/wellknown.py`):
    #: every path fetched once with its status and first bytes, and the site's
    #: own not-found answer. None where the crawl did not run it - which is
    #: not the same as a site with nothing exposed.
    well_known: dict | None = None
    #: SEC's DNS lookups (`crawler/dnsq.py`), or `{"available": False, reason}`
    #: where the extra is not installed; None where the crawl did not ask.
    dns: dict | None = None
    #: The mobile and bot parity probe (item 151, `crawler/parity.py`): the
    #: documents desktop, iPhone and Googlebot-smartphone were served for a
    #: sample of pages, compared. None where the crawl did not run it - which
    #: is not the same as a site that was probed and showed no divergence.
    mobile_parity: dict | None = None
    stats: dict = field(default_factory=dict)

    def inlinks(self) -> dict[str, list[str]]:
        """URL -> pages linking to it. Powers inlink counts, sample sources
        and orphan detection, none of which are recoverable after the crawl."""
        graph: dict[str, list[str]] = {}
        for page in self.pages:
            for target in page.outlinks:
                graph.setdefault(target, []).append(page.url)
        return graph
