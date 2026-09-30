"""LNK — Links on the page.

Eight checks about the site's own linking, all of them arithmetic on a
graph the crawler already records. `extract_link_details` carries the
anchor, the `rel` and the region for every internal `<a href>`, and
`click_depth` walks the graph from the start URL; nothing here needs a
model, so nothing here costs tokens (brief v17 step AW).

**Weighted at half of ONP** (operator, 2026-09-06; `QUESTIONS.md` Q-50).
Zero was the safe default and was the wrong answer: a dimension at weight
zero is the product saying internal linking does not affect ranking, which
is not what anybody here believes — accessibility is zero-weighted because
its ranking effect is weak and indirect, and linking's is neither. Half of
ONP because it is a smaller lever than what is on the page and a real one.
Every existing composite moves, which is what the trend's break annotation
is for.

**Nav and footer links are counted once for the site, not per page.** A
navigation that points at every page from every page would satisfy
`inlinks-low` everywhere, and no site would ever have an under-linked
page. The region the parser records is what makes the distinction
possible, and `inlinks-low` is about body copy — a link a reader would
follow, next to the idea it belongs to.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from clauditseo.crawler.types import CrawlResult
from clauditseo.engine import registry, scoring
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier

#: Fewer body inlinks than this and a page is under-linked. The prompt
#: states the same default and says which value it applied.
MIN_INLINKS = 3
#: More clicks from home than this and a page is deep. Crawl reports depth;
#: this part owns the fix, which is a link.
MAX_DEPTH = 3
#: The regions whose links point at every page from every page. Counted
#: once for the site rather than once per page.
TEMPLATE_REGIONS = {"nav", "footer"}

#: Anchors that say nothing about their target. A bare URL is included
#: because it names the address rather than the page.
GENERIC_ANCHORS = {
    "click here", "click", "here", "read more", "learn more", "more",
    "find out more", "see more", "this", "this page", "link", "view",
    "continue", "continue reading", "details", "more info", "more information",
}
_URL_ANCHOR = re.compile(r"^(https?://|www\.|/)\S*$", re.I)

#: What the crawler writes where a link's text is an image. `[image, no
#: alt]` is the *absence* of anchor text, not a phrase somebody chose, and
#: `img-alt-missing` is the check about it. Counted as an anchor it made
#: `anchor-duplicate-target` report that one phrase pointed at eleven
#: different pages on Acme - telling a client that words they never
#: wrote are overloaded.
_PLACEHOLDER_ANCHOR = re.compile(r"^\[image(,| alt:)", re.I)

DEFAULT_SEVERITY: dict[str, Severity | dict[str, Severity]] = {
    "orphan": Severity.HIGH,
    "broken-internal": Severity.HIGH,
    "inlinks-low": Severity.MEDIUM,
    "redirect-chain": Severity.MEDIUM,
    "anchor-generic": Severity.LOW,
    "anchor-duplicate-target": Severity.LOW,
    "depth-deep": Severity.LOW,
    "nofollow-internal": Severity.LOW,
    # The four only a brief can answer. Registered here with the rest so
    # one table holds every LNK check's severity — the prompt reads these
    # defaults and may raise one only with a reason in `note`.
    "link-suggestion": Severity.MEDIUM,
    "anchor-entity": Severity.MEDIUM,
    "hub-spoke-gap": Severity.MEDIUM,
    "anchor-flow": Severity.LOW,
    # Item 136q. Structural, not a model call: it compares the record's own
    # entity list against the initial-HTML anchor graph.
    "hub-unlinked": Severity.MEDIUM,
}

#: The site-record fields that name an entity with a hub of its own. The
#: brand is handled apart: its hub is `id_page_uri`, not a `url` on a list
#: entry.
#:
#: `locations` is typed `str` on the record and the item calls it
#: `locations[]`; both spellings are read below, because what the operator
#: typed is what the check has to work with.
ENTITY_FIELDS = ("sub_services", "locations", "authors")

#: What no sweep can emit: each needs the site's hub map, an entity triple
#: or a judgement about the words. `checks.check_costs()` reads this, so
#: these four are `model` and the other eight are `free` with no second
#: list to disagree.
BRIEF_ONLY_CHECKS: frozenset[str] = frozenset({
    "link-suggestion", "anchor-entity", "hub-spoke-gap", "anchor-flow",
})


def _entity_rows(site) -> tuple[list[dict], list[str]]:
    """(entities with a hub, names of entities without one).

    An entity is a name and the URL that owns it. The record spells these
    three ways - a list of dicts, a list of strings, or one string - so all
    three are read rather than one being declared correct: the operator
    typed whatever the Admin form accepted, and a check that only understood
    the tidiest spelling would report a well-filled record as empty.

    An entry with no URL is not a failure of the site. It is a question the
    record cannot answer, and it comes back in the second list so the row
    can say which entities were skipped rather than counting them as
    connected.
    """
    have: list[dict] = []
    missing: list[str] = []

    def take(value, kind: str) -> None:
        if not value:
            return
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                name = (item.get("name") or item.get("entity") or "").strip()
                url = (item.get("url") or item.get("hub") or "").strip()
            else:
                name, url = str(item).strip(), ""
            if not name:
                continue
            if url:
                have.append({"entity": name, "hub": url, "kind": kind})
            else:
                missing.append(name)

    for field in ENTITY_FIELDS:
        take(getattr(site, field, None), field)
    # The brand is an entity like any other and its hub is the identity page.
    brand = (getattr(site, "brand", None) or "").strip()
    if brand:
        hub = (getattr(site, "id_page_uri", None) or "").strip()
        (have.append({"entity": brand, "hub": hub, "kind": "brand"})
         if hub else missing.append(brand))
    return have, missing


_TAG = re.compile(r"<[^>]+>")
_SCRIPTY = re.compile(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", re.I | re.S)


def _visible(html: str) -> str:
    """The words a reader sees, roughly. Script and style removed first so
    a name in a JSON-LD block is not read as body copy."""
    return _TAG.sub(" ", _SCRIPTY.sub(" ", html or ""))


def _mentions(text: str, name: str) -> bool:
    """Whether a page names an entity, on a word boundary.

    Substring matching would have `Birch` inside `Birchwood` and every page of
    a site called `Ace` mentioning every entity.
    """
    if not name:
        return False
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text or "",
                     re.I) is not None


def _path(url: str) -> str:
    try:
        return urlsplit(url).path or "/"
    except ValueError:
        return url


def _is_generic(anchor: str) -> bool:
    text = " ".join((anchor or "").split()).strip().lower().strip(".!?:;—-")
    if not text:
        return True
    return text in GENERIC_ANCHORS or bool(_URL_ANCHOR.match(text))


#: Item 240: every links check is a statement about the graph (see
#: `onp.CROSS_PAGE_CHECKS`), so every one is cross-page.
CROSS_PAGE_CHECKS: frozenset[str] = frozenset(DEFAULT_SEVERITY)


class LinksModule:
    code = "LNK"
    name = "Links on the page"
    default_weight = scoring.DEFAULT_WEIGHTS["LNK"]
    #: Every check here is a statement about the graph: how many pages link
    #: at this one, how far it is from home, whether one anchor is used for
    #: two targets. Re-reading a single page cannot move any of them - the
    #: answer lives in the other pages - so a page refresh must not be
    #: offered for this dimension. `registry.page_blind_dims` reads this.
    measured_per_page = False

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages: list, tier: Tier, context: dict) -> list[Finding]:
        crawl: CrawlResult = context["crawl"]
        # Imported here rather than at module scope: `crawler.evidence`
        # imports `modules.loc`, so a top-level import would close the
        # cycle `modules -> crawler.evidence -> modules`. Every module is
        # loaded by the time a run calls this.
        from clauditseo.crawler.evidence import click_depth

        html = [p for p in crawl.pages
                if (p.content_type or "").startswith("text/html")]
        if not html:
            # Nothing was fetched. Every sentence below would be an absence
            # stated as a defect on the client's site, and the run's scope
            # limit already says nothing was reached.
            return []
        by_url = {p.url: p for p in crawl.pages}
        start = crawl.start_url
        # Item 227: a page that answered an error is not a page to link to.
        # It stays in `by_url`, so `broken-internal` still sees it as the
        # target it is; but counted as a page, it was an orphan, an
        # under-linked page and a deep one - the product's one instruction to
        # link to a 404 (`/on-page-seo/`, `/cdn-cgi/l/email-protection` on
        # twenty22).
        errored = {p.url for p in crawl.pages if p.status and p.status >= 400}
        live = [p for p in html if p.url not in errored]

        findings: list[Finding] = []

        def raise_(check_id: str, summary: str, urls: list[str],
                   recommendation: str) -> None:
            # The subject is the check itself, because every one of these
            # is a statement about the graph rather than about a page: "3
            # pages nothing links to" is one fact that gains and loses
            # pages between runs, and a subject naming today's pages would
            # close the finding and open a new one every time the list
            # moved. The affected pages travel in `affected_urls`, which
            # is where the record already reads them.
            findings.append(Finding(
                dimension=self.code, check_id=check_id,
                severity=DEFAULT_SEVERITY[check_id],
                summary=summary, subject=check_id, affected_urls=urls,
                recommendation=recommendation))

        # --- the graph, once -------------------------------------------
        body_inlinks: dict[str, int] = {}
        any_inlinks: dict[str, int] = {}
        anchors: dict[str, set[str]] = {}
        seen_as: dict[str, str] = {}                 # folded -> as written
        generic: list[tuple[str, str, str]] = []     # source, anchor, target
        nofollow: list[tuple[str, str]] = []         # source, target
        for page in html:
            for link in page.link_details:
                target = link.get("url") or ""
                if not target:
                    continue
                template = (link.get("region") or "body") in TEMPLATE_REGIONS
                any_inlinks[target] = any_inlinks.get(target, 0) + 1
                if not template:
                    body_inlinks[target] = body_inlinks.get(target, 0) + 1
                anchor = " ".join((link.get("anchor") or "").split())
                if _PLACEHOLDER_ANCHOR.match(anchor):
                    # An image link with no alt has no anchor text at all.
                    # It is not generic and it is not a duplicate: it is
                    # missing, and that is `img-alt-missing`.
                    anchor = ""
                if anchor and not template:
                    # Keyed on the folded spelling because "Our team" and
                    # "our team" are one phrase to a reader, but the
                    # finding quotes the anchor as the markup wrote it -
                    # an operator searching their own source for a phrase
                    # this report lower-cased would not find it.
                    seen_as.setdefault(anchor.lower(), anchor)
                    anchors.setdefault(anchor.lower(), set()).add(target)
                    if _is_generic(anchor):
                        generic.append((page.url, anchor, target))
                if "nofollow" in (link.get("rel") or "").lower():
                    nofollow.append((page.url, target))

        # --- orphan, then under-linked ---------------------------------
        # A page with no inlink of any kind, the start URL excepted: the
        # crawl began there, and "nothing links to the home page" is a
        # statement about the crawl rather than about the site.
        orphans = sorted(p.url for p in live
                         if p.url != start and not any_inlinks.get(p.url))
        if orphans:
            raise_("orphan",
                   f"{len(orphans)} page{'' if len(orphans) == 1 else 's'} "
                   "no other page links to",
                   orphans,
                   "Link to each of these from a page a reader would follow "
                   "it from — a hub page on the same topic, in body copy.")

        thin = sorted(p.url for p in live
                      if p.url != start and p.url not in orphans
                      and body_inlinks.get(p.url, 0) < MIN_INLINKS)
        if thin:
            raise_("inlinks-low",
                   f"{len(thin)} page{'' if len(thin) == 1 else 's'} with "
                   f"fewer than {MIN_INLINKS} internal links from body copy "
                   "(navigation and footer links are counted once for the "
                   "site, not once per page)",
                   thin,
                   f"Add body links until each has at least {MIN_INLINKS}, "
                   "from pages on the same topic.")

        # --- the anchors ------------------------------------------------
        if generic:
            shown = sorted({a for _, a, _ in generic})[:8]
            raise_("anchor-generic",
                   f"{len(generic)} internal link"
                   f"{'' if len(generic) == 1 else 's'} whose anchor text "
                   "says nothing about the page it points at: "
                   + ", ".join(f"“{a}”" for a in shown),
                   sorted({s for s, _, _ in generic}),
                   "Replace each with words drawn from the target page's own "
                   "title or H1.")

        dupes = sorted((a, targets) for a, targets in anchors.items()
                       if len(targets) > 1)
        if dupes:
            words = ", ".join(f"“{seen_as.get(a, a)}” → {len(t)} pages"
                              for a, t in dupes[:6])
            raise_("anchor-duplicate-target",
                   f"{len(dupes)} anchor phrase"
                   f"{'' if len(dupes) == 1 else 's'} pointing at more than "
                   f"one page: {words}",
                   sorted({t for _, targets in dupes for t in targets}),
                   "One phrase should name one page. Give each target its "
                   "own anchor, drawn from that page's title.")

        if nofollow:
            raise_("nofollow-internal",
                   f"{len(nofollow)} internal link"
                   f"{'' if len(nofollow) == 1 else 's'} carrying "
                   "rel=nofollow",
                   sorted({s for s, _ in nofollow}),
                   "Remove rel=nofollow from links to your own pages; it "
                   "tells search engines not to follow your own site.")

        # --- the targets ------------------------------------------------
        broken: dict[str, int] = {}
        chains: list[str] = []
        for target in sorted(any_inlinks):
            page = by_url.get(target)
            if page is None:
                continue
            if page.status and page.status >= 400:
                broken[target] = page.status
            # Two hops or more: the chain records every URL it passed
            # through, so a single redirect is two entries.
            if len(page.redirect_chain or []) > 2:
                chains.append(target)
        if broken:
            words = ", ".join(f"{_path(u)} ({s})" for u, s in
                              sorted(broken.items())[:6])
            raise_("broken-internal",
                   f"{len(broken)} internal link target"
                   f"{'' if len(broken) == 1 else 's'} returning an error: "
                   f"{words}",
                   sorted(broken),
                   "Point each link at a page that exists, or remove it.")
        if chains:
            raise_("redirect-chain",
                   f"{len(chains)} internal link target"
                   f"{'' if len(chains) == 1 else 's'} reached through more "
                   "than one redirect",
                   sorted(chains),
                   "Link straight to the final URL.")

        # --- depth ------------------------------------------------------
        depths = click_depth(start, [{"url": p.url, "outlinks": p.outlinks}
                                     for p in crawl.pages])
        deep = sorted(url for url, d in depths.items()
                      if d > MAX_DEPTH and url in by_url and url not in errored)
        if deep:
            raise_("depth-deep",
                   f"{len(deep)} page{'' if len(deep) == 1 else 's'} more "
                   f"than {MAX_DEPTH} clicks from the home page",
                   deep,
                   "Link to them from a page nearer the top — usually the "
                   "hub for their topic.")
        findings += self._hub_links(html, context.get("site"))
        return findings

    # --- item 136q ------------------------------------------------------

    def _hub_links(self, html: list, site) -> list[Finding]:
        """Pages that name one of the record's entities and neither link to
        its hub nor are linked from it.

        **The record is the authority, and this check has no opinion of its
        own about what an entity is.** It reads `sub_services`, `locations`
        and `authors` for a name and a URL, and the brand for `id_page_uri`.
        Nothing here infers an entity from the site's own words, which is
        the line the AI-surface brief draws and this is the structural half
        of it.

        Initial HTML only. `page.link_details` is the parsed anchor set, not
        the rendered one, which is what the item asks for: a link that only
        appears after render is `TEC/links-behind-js` and saying it twice
        would put one page on two rows for one cause.

        Either direction counts. A spoke linking up to its hub and a hub
        linking down to its spoke are both a connection; requiring the first
        would report a well-built hub page as a fault on every spoke.
        """
        if site is None:
            return []
        entities, no_hub = _entity_rows(site)
        if not entities:
            return []

        by_url = {p.url: p for p in html}
        out: list[Finding] = []
        for ent in entities:
            hub, name = ent["hub"], ent["entity"]
            hub_page = by_url.get(hub) or by_url.get(hub.rstrip("/"))
            # What the hub itself links at, so a hub-down link counts.
            from_hub = {(l.get("url") or "") for l in
                        (getattr(hub_page, "link_details", None) or [])}
            disconnected, misnamed = [], []
            for page in html:
                if page.url == hub or _path(page.url) == _path(hub):
                    continue
                # Tags stripped first: `content` is raw HTML, and a name
                # sitting in an attribute is not the page saying it. A
                # `href="/bridging-finance"` would otherwise make every page
                # that links somewhere near the entity "mention" it.
                if not _mentions(_visible(getattr(page, "content", "")), name):
                    continue
                links = getattr(page, "link_details", None) or []
                to_hub = [l for l in links
                          if _path(l.get("url") or "") == _path(hub)]
                if to_hub:
                    # A link exists. Its anchor may still name something
                    # else, which is a different and weaker observation -
                    # reported beside the row rather than as a fault.
                    for l in to_hub:
                        anchor = " ".join((l.get("anchor") or "").split())
                        if anchor and not _mentions(anchor, name):
                            misnamed.append({"page": page.url, "anchor": anchor})
                    continue
                if page.url in from_hub or _path(page.url) in {
                        _path(u) for u in from_hub}:
                    continue
                disconnected.append(page.url)

            if not disconnected:
                continue
            evidence = {"entity": name, "hub": hub,
                        "disconnected": sorted(disconnected)}
            if misnamed:
                evidence["anchors_naming_something_else"] = misnamed
            if no_hub:
                # Said on the row rather than dropped: an entity the record
                # gave no URL is a question nobody can answer, and a reader
                # counting rows would otherwise read its silence as a pass.
                evidence["not_assessable"] = sorted(set(no_hub))
            out.append(Finding(
                dimension=self.code, check_id="hub-unlinked",
                severity=DEFAULT_SEVERITY["hub-unlinked"],
                summary=f"{len(disconnected)} page"
                        f"{'' if len(disconnected) == 1 else 's'} name "
                        f"{name} and neither link to {_path(hub)} nor are "
                        "linked from it.",
                subject=f"hub-unlinked:{name}",
                affected_urls=sorted(disconnected), evidence=evidence,
                recommendation=f"Link each page to {_path(hub)}, or link "
                               f"{_path(hub)} to it, so the pages about "
                               f"{name} form one cluster."))
        return out

    def score(self, findings: list[Finding], context: dict) -> SubScore:
        # Wholly crawl-derived: every check reads the graph the crawl
        # built, so a crawl that fetched nothing measured none of this.
        return scoring.subscore(self.code, findings, self.default_weight, context,
                                coverage=scoring.page_coverage(context))


registry.register(LinksModule())
