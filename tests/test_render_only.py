"""`TEC/render-only` — body text present only after the page renders.

Brief v18 step AZ. crawl.md names five render-parity signals; the operator's
split (2026-09-09) keeps the LINK signal with `TEC/links-behind-js` (which
already carries the router-only-anchor finding and its whole-site orphan guard)
and gives `render-only` the non-link parity. What ships here is the body: the
initial HTML is a near-empty shell while the rendered DOM holds real content,
so a retrieval agent that does not run scripts reads a blank page.

A per-page claim, sound on any page the rendered pass visited, sample-scoped and
saying so in its own summary. Rendered word count is `pagefacts.rendered_words` over the
page's `text_blocks` (the a11y pass's capture), which counts nested blocks once; the initial count is
`extract_facts`' `word_count` off the raw HTML — the same reader thin-content
uses. title/h1/JSON-LD parity is not built yet (the rendered pass does not
record those), so this file is the body signal only.
"""

from __future__ import annotations

from clauditseo.crawler.types import CrawlResult, Page, Tier
from clauditseo.engine.types import Site
from clauditseo.modules.tec import (RENDER_ONLY_RAW_MAX,
                                     RENDER_ONLY_RENDERED_MIN, TechnicalModule)

BASE = "https://render.test"

# Enough words that `extract_facts` counts a real body; kept as a helper so a
# test can dial the initial-HTML word count above or below the shell floor.
WORD = "content"


def _page(path: str, words: int) -> Page:
    body = "<p>" + " ".join([WORD] * words) + "</p>" if words else ""
    return Page(url=BASE + path, requested_url=BASE + path, status=200,
                content_type="text/html; charset=utf-8",
                content=f"<html><head><title>T</title></head><body>{body}</body></html>")


def _blocks(words: int) -> list:
    """One rendered text block carrying `words` words, shaped like the a11y
    pass's `text_blocks` entries (name/hash dropped; only `words` is read)."""
    return [{"words": words, "landmark": "main"}] if words else []


def _run(pages, text_blocks, seen, total):
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages.extend(pages)
    ctx = {"crawl": crawl, "site": Site(domain="render.test"),
           "text_blocks": text_blocks,
           "rendered_coverage": {"rendered": seen, "pages": total}}
    return {f.subject: f for f in TechnicalModule().run(list(crawl.pages), Tier.T2, ctx)
            if f.check_id == "render-only"}


def test_an_empty_shell_with_a_rendered_body_is_render_only():
    pages = [_page("/", 5), _page("/a", 300)]
    got = _run(pages, {BASE + "/": _blocks(400)}, seen=2, total=2)
    assert "/" in got, got
    f = got["/"]
    assert f.severity.value == "medium"
    assert f.evidence["initial_html_words"] == 5
    assert f.evidence["rendered_words"] == 400


def test_the_summary_states_the_sample_scope():
    pages = [_page("/", 3)]
    got = _run(pages, {BASE + "/": _blocks(250)}, seen=1, total=4)
    assert "1 of 4 page(s) the rendered pass visited" in got["/"].summary, got["/"].summary


def test_a_page_that_serves_its_body_in_the_initial_html_is_not_render_only():
    """The initial HTML already carries the words, so nothing is render-only —
    even though the rendered DOM re-reports them."""
    pages = [_page("/", 300)]
    got = _run(pages, {BASE + "/": _blocks(320)}, seen=1, total=1)
    assert got == {}


def test_a_genuinely_thin_page_is_low_on_both_sides_and_says_nothing():
    """Below the rendered minimum: a thin page is thin in the DOM too, and that
    is thin-content's to report, not render-only's."""
    pages = [_page("/", 8)]
    got = _run(pages, {BASE + "/": _blocks(20)}, seen=1, total=1)
    assert got == {}


def test_the_floor_and_the_minimum_are_the_two_edges():
    """Just inside both thresholds fires; nudging the initial over the floor,
    or the rendered under the minimum, does not."""
    pages = [_page("/edge", RENDER_ONLY_RAW_MAX)]
    fire = _run(pages, {BASE + "/edge": _blocks(RENDER_ONLY_RENDERED_MIN)}, 1, 1)
    assert "/edge" in fire

    over_floor = [_page("/x", RENDER_ONLY_RAW_MAX + 1)]
    assert _run(over_floor, {BASE + "/x": _blocks(RENDER_ONLY_RENDERED_MIN)}, 1, 1) == {}

    under_min = [_page("/y", RENDER_ONLY_RAW_MAX)]
    assert _run(under_min, {BASE + "/y": _blocks(RENDER_ONLY_RENDERED_MIN - 1)}, 1, 1) == {}


def test_no_rendered_pass_raises_nothing():
    """Without a rendered sample there is no parity to judge — the check is
    silent, not a false clean."""
    pages = [_page("/", 5)]
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages.extend(pages)
    ctx = {"crawl": crawl, "site": Site(domain="render.test")}
    got = [f for f in TechnicalModule().run(list(crawl.pages), Tier.T2, ctx)
           if f.check_id == "render-only"]
    assert got == []


def test_render_only_files_under_crawl():
    from clauditseo import anatomy
    assert anatomy.categorise("render-only", "TEC") == "crawl"

def test_nested_blocks_are_counted_once(monkeypatch):
    """The a11y pass's blocks nest: a nav `li` holds its links' words and each
    link is a block too. Summed, a shell page's rendered count is inflated by
    every wrapper, which is how the same page could be render-dependent to this
    check and not to `AIS/content-behind-js` — the two asked the same question
    of the same blocks and had two answers (item 145's BH report, open item 5).
    `pagefacts.rendered_words` owns the count for both now.

    Twelve words of real text in a nav whose four links repeat them, and the
    threshold is between the two readings: summed it is over, counted once it
    is under, so the assertion is the behaviour and not the arithmetic.
    """
    nav = {"words": RENDER_ONLY_RENDERED_MIN - 1, "landmark": "nav",
           "rect": {"x": 0, "y": 0, "w": 600, "h": 40}}
    inside = [{"words": 30, "landmark": "nav",
               "rect": {"x": 10 + i * 100, "y": 5, "w": 90, "h": 30}} for i in range(4)]
    blocks = [nav, *inside]
    assert sum(b["words"] for b in blocks) >= RENDER_ONLY_RENDERED_MIN, (
        "the fixture only holds if summing would clear the floor")
    got = _run([_page("/", 4)], {BASE + "/": blocks}, seen=1, total=1)
    assert got == {}, (
        "the nav's own words were counted again for every link inside it")


def test_one_owner_for_the_rendered_word_count():
    """Held on the source: two checks reading one helper is the fix, and a
    second local sum here would quietly restore the disagreement."""
    from pathlib import Path

    tec = (Path(__file__).resolve().parents[1] / "clauditseo" / "modules"
           / "tec.py").read_text(encoding="utf-8")
    body = tec[tec.index("def _render_only("):tec.index("#: The share of this dimension")]
    assert "rendered_words(blocks)" in body
    assert "sum(int(b.get(" not in body, "the local sum is what double-counted"
