"""Mobile and bot parity: the document each device and Googlebot is served,
retrieved rather than inferred (item 151).

Operator ruling, 2026-09-10: a phone's display is retrieved as a mobile device
and does not simply accept the desktop words. So a sample of the crawl's pages
is fetched again under three user agents - desktop Chrome, iPhone Safari and
Googlebot-smartphone - and the documents are compared.

**The document, not a field list.** The check that prompted this found one
divergence in six sites, and it was Birch serving Googlebot-smartphone a body
60% smaller with title and description intact. A probe comparing four head
fields would have called that clean. So each fetch is reduced to status, final
URL, size, a main-region hash, word count, internal link count and a JSON-LD
hash, and the
named fields (title, description, canonical, robots, h1) are named when they
differ.

**Two pairs, kept apart.** `device` is iPhone against desktop: dynamic serving.
`bot` is Googlebot-smartphone against the iPhone - the same device class, so a
difference is the bot and not the phone (against desktop where the iPhone
fetch failed). Birch's case is a bot difference with no device difference,
which is why it is its own pair.

**A sample, not a dual crawl.** `perf.sample`'s rule - every page of a T1
pulse, one per URL template at T2/T3 - capped at `SAMPLE_CAP`, so the cost is
a handful of requests however large the tier's page budget. A site whose
previous run diverged is probed on every readable page (`mode="full"`).

**What it cannot see.** No JavaScript runs. A title rewritten client-side is
invisible to these fetches exactly as to the crawl's own; this covers dynamic
serving and bot-specific serving of the served HTML, and says so on the block.

A clean result is stored, not discarded: "mobile parity: no divergence across
N pages" is a measurement, and the book-wide divergence rate only exists if
the negatives are written down.
"""

from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urlsplit

from .fetch import Fetcher
from .types import Page

#: The three agents, as (key, user-agent string). Googlebot-smartphone is the
#: third agent, not an optional extra: it is the one that found the only
#: divergence in the check that prompted this item.
PARITY_AGENTS: tuple[tuple[str, str], ...] = (
    ("desktop",
     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    ("iphone",
     "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"),
    ("googlebot-smartphone",
     "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 "
     "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
)

#: Pages probed in sample mode. Three agents each, so at most 3 x SAMPLE_CAP
#: fetches whatever the tier's `max_pages` is.
SAMPLE_CAP = 5

#: Page rows kept in the evidence in full mode; the counts cover every page.
STORED_PAGES_CAP = 200

#: Fields whose difference is a different document to an indexer: HIGH.
NAMED_FIELDS = ("status", "final_url", "title", "meta_description",
                "canonical", "meta_robots")
#: Named when they differ, but not on their own a different indexable answer.
NAMED_ALSO = ("h1",)

#: Size tolerances. Rotating copy, nonces and a cache timestamp move a body by
#: a few hundred bytes (twenty22: 144,125 / 144,313 / 144,335); a lighter
#: template moves it by tens of percent (Birch: 533,687 / 216,745).
BYTES_REL = 0.20
WORDS_REL, WORDS_ABS = 0.10, 20
LINKS_REL, LINKS_ABS = 0.10, 3
#: A main-region hash difference counts only with main-region word counts
#: more than this far apart - rotating testimonials of a similar length move
#: the hash and nothing an indexer weighs.
MAIN_WORDS_REL = 0.02

JS_STATEMENT = ("No JavaScript was executed: these are served-HTML fetches, so a "
                "title or copy rewritten client-side is not seen by this probe.")

_WS = re.compile(r"\s+")


def _clean(value) -> str:
    return _WS.sub(" ", str(value or "")).strip()


def document(page: Page) -> dict:
    """What the parity comparison reads from one fetch. Small enough to store:
    the evidence keeps no bodies."""
    from ..modules.pagefacts import extract_facts
    from .crawl import extract_link_details, normalise_url
    from .ua_matrix import fingerprint

    body = page.content or ""
    doc = {"status": page.status or None,
           "final_url": normalise_url(page.url) if page.url else None,
           "bytes": len(body.encode("utf-8")),
           "error": page.error}
    if page.status != 200 or not (page.content_type or "").startswith("text/html"):
        return doc
    facts = extract_facts(page)
    main = _clean(facts.main_text).lower()
    h1 = next((text for level, text in facts.headings if level == 1), None)
    doc.update({
        "title": _clean(fingerprint(body)["title"]),
        "meta_description": _clean(facts.meta_description),
        "canonical": _clean(facts.canonical or page.link_header_canonical),
        "meta_robots": _clean(" ".join(filter(None, [facts.meta_robots,
                                                     page.x_robots_tag]))).lower(),
        "h1": _clean(h1),
        "words": facts.word_count,
        "main_words": len(main.split()),
        "main_hash": hashlib.sha1(main.encode("utf-8")).hexdigest()[:16],
        "internal_links": len({link["url"] for link in extract_link_details(page)}),
        # Structured data (item 153's third question): the JSON-LD blocks,
        # whitespace-insensitive and order-insensitive, as a count and a hash.
        "jsonld_blocks": len(facts.jsonld_blocks),
        "jsonld_hash": hashlib.sha1("\n".join(sorted(
            _WS.sub("", b) for b in facts.jsonld_blocks)).encode("utf-8")).hexdigest()[:16],
    })
    return doc


def _rel(a: float, b: float) -> float:
    top = max(a, b)
    return abs(a - b) / top if top else 0.0


def compare(base: dict | None, other: dict | None) -> dict:
    """One pair of documents. `verdict` is `same`, `named` (a NAMED_FIELDS
    difference), `size` (the named fields agree but the document does not), or
    `not_assessed` where either fetch reached nothing - a timeout is not a
    divergence. A refusal status is: Googlebot answered 403 where a browser got
    200 is a different document."""
    if not base or not other or not base.get("status") or not other.get("status"):
        return {"verdict": "not_assessed", "named": [], "size": []}
    named = [{"field": f, "base": base.get(f), "other": other.get(f)}
             for f in NAMED_FIELDS + NAMED_ALSO if base.get(f) != other.get(f)]
    size = []
    if _rel(base["bytes"], other["bytes"]) > BYTES_REL:
        size.append({"field": "bytes", "base": base["bytes"], "other": other["bytes"]})
    if "words" in base and "words" in other:
        if (abs(base["words"] - other["words"]) >= WORDS_ABS
                and _rel(base["words"], other["words"]) > WORDS_REL):
            size.append({"field": "words", "base": base["words"], "other": other["words"]})
        if (abs(base["internal_links"] - other["internal_links"]) >= LINKS_ABS
                and _rel(base["internal_links"], other["internal_links"]) > LINKS_REL):
            size.append({"field": "internal_links", "base": base["internal_links"],
                         "other": other["internal_links"]})
        if (base["main_hash"] != other["main_hash"]
                and _rel(base["main_words"], other["main_words"]) > MAIN_WORDS_REL):
            size.append({"field": "main_hash", "base": base["main_hash"],
                         "other": other["main_hash"]})
        # A stored block from before the field existed has no hash to compare.
        if (base.get("jsonld_hash") and other.get("jsonld_hash")
                and base["jsonld_hash"] != other["jsonld_hash"]):
            size.append({"field": "structured_data",
                         "base": f"{base['jsonld_blocks']} block(s) {base['jsonld_hash']}",
                         "other": f"{other['jsonld_blocks']} block(s) {other['jsonld_hash']}"})
    high = [n for n in named if n["field"] in NAMED_FIELDS]
    verdict = "named" if high else "size" if (size or named) else "same"
    return {"verdict": verdict, "named": named, "size": size}


def sample_urls(pages, tier, start_url: str, mode: str = "sample") -> tuple[list[str], str]:
    """Which pages are probed, and the sentence that states it. `perf.sample`'s
    rule, so the Speed trace and this probe sample a site the same way; the
    home page first where it was reached, then capped."""
    from clauditseo import perf

    readable = [p for p in pages if getattr(p, "status", None) == 200
                and (getattr(p, "content_type", "") or "").startswith("text/html")]
    if mode == "full":
        urls = [p.url for p in readable]
        return urls, (f"every readable page ({len(urls)}): the previous run found "
                      "a divergence, so this run fetches all of them")
    urls, rule = perf.sample(readable, tier)
    home = next((p.url for p in readable
                 if (urlsplit(p.url).path or "/").rstrip("/") ==
                 (urlsplit(start_url).path or "/").rstrip("/")), None)
    if home:
        urls = [home] + [u for u in urls if u != home]
    if len(urls) > SAMPLE_CAP:
        rule += f"; capped at {SAMPLE_CAP} for the parity probe"
    return urls[:SAMPLE_CAP], rule


def _pair_summary(rows: list[dict], key: str) -> dict:
    verdicts = [r[key]["verdict"] for r in rows]
    assessed = [v for v in verdicts if v != "not_assessed"]
    named, size = verdicts.count("named"), verdicts.count("size")
    return {"assessed": len(assessed), "named": named, "size": size,
            "verdict": ("not assessed" if not assessed
                        else "divergence" if named or size else "no divergence")}


def probe(pages, tier, start_url: str, timeout_s: float, deadline: float,
          delay_s: float = 0.0, mode: str = "sample",
          fetcher_factory=Fetcher) -> dict:
    """Fetch the sample under each agent, one URL at a time across all three
    so a page's documents are taken within seconds of each other, and compare.

    Returns a plain dict for the JSON evidence snapshot. Deadline-bounded:
    where the crawl's clock runs out the block says `truncated_by` and counts
    only what was compared."""
    urls, rule = sample_urls(pages, tier, start_url, mode)
    fetchers = {key: fetcher_factory(timeout_s, user_agent=ua) for key, ua in PARITY_AGENTS}
    rows: list[dict] = []
    fetches = 0
    truncated = None
    try:
        for url in urls:
            if time.monotonic() > deadline:
                truncated = "wall_clock"
                break
            docs = {}
            for key, _ua in PARITY_AGENTS:
                if delay_s:
                    time.sleep(delay_s)
                docs[key] = document(fetchers[key].fetch(url))
                fetches += 1
            browser = docs["iphone"] if docs["iphone"].get("status") else docs["desktop"]
            rows.append({"url": url, "documents": docs,
                         "device": compare(docs["desktop"], docs["iphone"]),
                         "bot": compare(browser, docs["googlebot-smartphone"]),
                         "bot_compared_with": ("iphone" if browser is docs["iphone"]
                                               else "desktop")})
    finally:
        for f in fetchers.values():
            f.close()

    device, bot = _pair_summary(rows, "device"), _pair_summary(rows, "bot")
    n = len(rows)
    diverged = sum(1 for r in rows if r["device"]["verdict"] in ("named", "size")
                   or r["bot"]["verdict"] in ("named", "size"))
    if not n or (device["verdict"] == "not assessed" and bot["verdict"] == "not assessed"):
        statement = "mobile parity: not assessed - no page was compared"
    elif diverged:
        statement = f"mobile parity: divergence on {diverged} of {n} page(s)"
    else:
        statement = f"mobile parity: no divergence across {n} page(s)"
    return {
        "mode": mode,
        "sample_rule": rule,
        "agents": dict(PARITY_AGENTS),
        "probed": n,
        "fetches": fetches,
        "truncated_by": truncated,
        "device": device,
        "bot": bot,
        "diverged": diverged,
        "statement": statement,
        "javascript_executed": False,
        "covers": ("dynamic serving and bot-specific serving of the served HTML. "
                   + JS_STATEMENT),
        "thresholds": {"bytes_rel": BYTES_REL, "words_rel": WORDS_REL,
                       "words_abs": WORDS_ABS, "links_rel": LINKS_REL,
                       "links_abs": LINKS_ABS, "main_words_rel": MAIN_WORDS_REL},
        "pages": rows[:STORED_PAGES_CAP],
    }


def diverged(block: dict | None) -> bool:
    """Whether a stored parity block found anything, which is what moves the
    next run of the site to `mode="full"`."""
    return bool(block) and bool(block.get("diverged"))
