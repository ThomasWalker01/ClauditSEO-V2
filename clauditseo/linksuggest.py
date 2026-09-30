"""Internal link suggestions from the crawl's own graph.

Deterministic on purpose: which pages are under-linked is arithmetic on the
link graph, and which pages should link to them is measurable topical overlap
— neither needs a model, so neither should cost tokens or vary between runs.

The output is a suggestion, not an instruction, and the honesty rules are the
usual ones: every candidate source is a real crawled page, every anchor is
derived from the target's own title rather than invented, and a page whose
overlap is too weak to justify a link is not padded into the list.
"""

from __future__ import annotations

import re

STOPWORDS = {
    "the", "and", "for", "with", "your", "our", "you", "are", "how", "what",
    "why", "when", "from", "this", "that", "can", "get", "all", "more", "to",
    "of", "in", "on", "a", "an", "is", "it", "at", "by", "or", "we", "us",
    "vs", "au", "com", "www", "https", "http",
}
MIN_INLINKS = 3          # fewer than this (homepage excluded) = under-linked
MAX_TARGETS = 20
MAX_SOURCES = 3
MIN_OVERLAP = 2          # shared meaningful tokens before a link is argued for


def _tokens(*texts: str | None) -> set[str]:
    out: set[str] = set()
    for text in texts:
        if not text:
            continue
        out.update(w for w in re.findall(r"[a-z0-9]+", text.lower())
                   if len(w) > 2 and w not in STOPWORDS)
    return out


def _anchor_from_title(title: str | None, url: str) -> str:
    """The target's own title, brand suffix stripped — never an invented
    phrase. Falls back to the last path segment humanised."""
    if title:
        head = re.split(r"\s*[|–—-]\s+", title)[0].strip()
        if 2 <= len(head.split()) <= 10:
            return head
        if head:
            return head[:60]
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").replace("_", " ") or url


def suggest_links(evidence: dict) -> list[dict]:
    """Under-linked pages with ranked source candidates.

    A page's inlink count comes from the crawled outlink graph; imported
    crawls without outlinks simply yield no suggestions rather than wrong
    ones. The homepage is excluded — it is linked from everywhere by design,
    and when it is not, that is an architecture finding, not a link tip.
    """
    pages = [p for p in evidence.get("pages", [])
             if p.get("status") == 200 and "html" in (p.get("content_type") or "")]
    if not pages:
        return []
    start = evidence.get("start_url")

    inlinks: dict[str, int] = {}
    linked_from: dict[str, set[str]] = {}
    has_graph = False
    for page in pages:
        for target in page.get("outlinks") or []:
            has_graph = True
            inlinks[target] = inlinks.get(target, 0) + 1
            linked_from.setdefault(target, set()).add(page.get("url", ""))
    if not has_graph:
        return []

    by_url = {p.get("url"): p for p in pages}
    weak = sorted(
        (p for p in pages
         if p.get("url") != start
         and inlinks.get(p.get("url"), 0) < MIN_INLINKS),
        key=lambda p: (inlinks.get(p.get("url"), 0),
                       p.get("click_depth") or 0))[:MAX_TARGETS]

    out: list[dict] = []
    for target in weak:
        t_url = target.get("url", "")
        t_tokens = _tokens(target.get("title"), target.get("h1"))
        if not t_tokens:
            continue
        scored = []
        for source in pages:
            s_url = source.get("url", "")
            if s_url == t_url or s_url in linked_from.get(t_url, set()):
                continue          # already links there: nothing to suggest
            overlap = t_tokens & _tokens(source.get("title"), source.get("h1"))
            if len(overlap) >= MIN_OVERLAP:
                scored.append((len(overlap), source, sorted(overlap)))
        scored.sort(key=lambda s: (-s[0], s[1].get("click_depth") or 9))
        # A weak page with no confident source is still worth reporting: the
        # under-linking is a fact, and an empty source list says "no obvious
        # home for this link" rather than inventing one.
        out.append({
            "url": t_url,
            "title": target.get("title"),
            "inlinks": inlinks.get(t_url, 0),
            "depth": target.get("click_depth"),
            "anchor": _anchor_from_title(target.get("title"), t_url),
            "sources": [{
                "url": s.get("url"),
                "title": s.get("title"),
                "shared": shared,
            } for _, s, shared in scored[:MAX_SOURCES]],
        })
    return out
