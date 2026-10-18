"""The A11Y dimension, one barrier at a time.

Each case is written as the smallest page that exhibits exactly one defect,
and every check is also given a page that should *not* trip it — a checker
that fires on correct markup is worse than no checker, because the operator
learns to skim past it.
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Tier
from clauditseo.modules.a11y import AccessibilityModule
from clauditseo.modules.pagefacts import extract_facts

MOD = AccessibilityModule()


def raw(html: str, url="https://x.test/") -> Page:
    return Page(url=url, requested_url=url, status=200,
                content_type="text/html; charset=utf-8", content=html)


def page(body: str, *, lang: str = ' lang="en-AU"', url="https://x.test/") -> Page:
    return raw(f"<html{lang}><body><main>{body}</main></body></html>", url)


def run_on(*pages: Page, **context) -> set[str]:
    """Static checks only unless a case asks otherwise.

    Playwright may well be installed in the environment running these tests,
    and if it is, the rendered pass would try to load https://x.test/ over
    the network — making the suite slow, flaky and dependent on what a
    DNS resolver does with a domain that should not resolve. The rendered
    path has its own tests in test_axe.py, driven from a recorded result.
    """
    context.setdefault("skip_axe", True)
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=list(pages))
    return {f.check_id for f in MOD.run([], Tier.T2, {"crawl": crawl, **context})}


def ids_for(html_body: str, **kw) -> set[str]:
    return run_on(page(html_body, **kw))


# ---- language --------------------------------------------------------------

def test_a_page_with_no_lang_is_flagged():
    assert "html-lang-missing" in ids_for("<p>hi</p>", lang="")


def test_a_page_that_declares_its_language_is_not():
    assert "html-lang-missing" not in ids_for("<p>hi</p>")


# ---- form labelling --------------------------------------------------------

@pytest.mark.parametrize("markup,labelled", [
    ('<label for="e">Email</label><input id="e">',           True),
    ('<label>Email <input></label>',                          True),
    ('<input aria-label="Email">',                            True),
    ('<input aria-labelledby="lbl"><span id="lbl">Email</span>', True),
    ('<input title="Email">',                                 True),
    ('<input type="hidden">',                                 True),
    ('<input type="submit" value="Send">',                    True),
    # The one that matters: a placeholder looks like a label and is not one.
    ('<input placeholder="Email">',                           False),
    ('<input id="e">',                                        False),
    ('<select><option>a</option></select>',                   False),
    ('<textarea></textarea>',                                 False),
    # for= pointing at a control that does not exist leaves it unlabelled.
    ('<label for="nope">Email</label><input id="e">',         False),
])
def test_form_control_labelling(markup, labelled):
    fired = "form-control-unlabelled" in ids_for(markup)
    assert fired is (not labelled), markup


# ---- link and button names -------------------------------------------------

@pytest.mark.parametrize("markup,named", [
    ('<a href="/a">Pricing</a>',                              True),
    ('<a href="/a" aria-label="Pricing">&nbsp;</a>',          True),
    ('<a href="/a"><img src="i.png" alt="Pricing"></a>',      True),
    ('<a href="/a"><span><b>Pricing</b></span></a>',          True),
    ('<a href="/a"><img src="i.png" alt=""></a>',             False),
    ('<a href="/a"><img src="i.png"></a>',                    False),
    ('<a href="/a"></a>',                                     False),
])
def test_link_accessible_name(markup, named):
    fired = "link-name-missing" in ids_for(markup)
    assert fired is (not named), markup


def test_a_link_inside_a_heading_does_not_steal_the_heading_capture():
    """The name stack runs alongside the single-slot heading capture; if it
    shared it, one would consume the other's text."""
    facts = extract_facts(page('<h2>Our <a href="/p">pricing</a> explained</h2>'))
    assert facts.headings == [(2, "Our pricing explained")]
    assert facts.links[0]["text"] == "pricing"


def test_generic_link_text_is_flagged_but_only_when_it_is_the_whole_name():
    assert "link-text-generic" in ids_for('<a href="/a">Read more</a>')
    assert "link-text-generic" in ids_for('<a href="/a">click here</a>')
    assert "link-text-generic" not in ids_for('<a href="/a">Read more about roofing</a>')


def test_button_without_a_name():
    assert "button-name-missing" in ids_for("<button></button>")
    assert "button-name-missing" not in ids_for("<button>Send</button>")
    assert "button-name-missing" not in ids_for('<button aria-label="Close">×</button>')


# ---- identifiers and aria --------------------------------------------------

def test_duplicate_ids():
    assert "duplicate-id" in ids_for('<div id="x"></div><div id="x"></div>')
    assert "duplicate-id" not in ids_for('<div id="x"></div><div id="y"></div>')


def test_aria_reference_must_resolve():
    assert "aria-reference-broken" in ids_for('<div aria-describedby="ghost">t</div>')
    assert "aria-reference-broken" not in ids_for(
        '<div aria-describedby="real">t</div><span id="real">note</span>')


def test_positive_tabindex_only():
    assert "tabindex-positive" in ids_for('<div tabindex="3">t</div>')
    assert "tabindex-positive" not in ids_for('<div tabindex="0">t</div>')
    assert "tabindex-positive" not in ids_for('<div tabindex="-1">t</div>')


# ---- frames, tables, landmarks ---------------------------------------------

def test_iframe_needs_a_title():
    assert "iframe-title-missing" in ids_for('<iframe src="/m"></iframe>')
    assert "iframe-title-missing" not in ids_for('<iframe src="/m" title="Map"></iframe>')


def test_data_table_needs_headers_but_a_layout_table_may_say_so():
    rows = "<tr><td>a</td></tr><tr><td>b</td></tr>"
    assert "table-headers-missing" in ids_for(f"<table>{rows}</table>")
    assert "table-headers-missing" not in ids_for(
        f"<table><tr><th>h</th></tr>{rows}</table>")
    assert "table-headers-missing" not in ids_for(
        f'<table role="presentation">{rows}</table>')
    # A single-row table is not evidence of a data table.
    assert "table-headers-missing" not in ids_for("<table><tr><td>a</td></tr></table>")


def test_main_landmark():
    bare = raw('<html lang="en"><body><div>no landmark</div></body></html>')
    assert "landmark-main-missing" in run_on(bare)
    assert "landmark-main-missing" not in ids_for("<p>inside main</p>")


# ---- honesty ---------------------------------------------------------------

def test_a_run_without_a_renderer_says_contrast_was_not_assessed():
    """The dimension must not let a page with unreadable text score clean."""
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2,
                        pages=[page("<p>hi</p>")])
    found = MOD.run([], Tier.T2, {"crawl": crawl, "skip_axe": True})
    note = [f for f in found if f.check_id == "contrast-not-assessed"]
    assert len(note) == 1
    assert "contrast" in note[0].summary.lower()


def test_the_note_disappears_once_axe_has_run():
    assert "contrast-not-assessed" not in run_on(page("<p>hi</p>"), axe_ran=True)


def test_a_clean_page_raises_nothing_but_the_renderer_note():
    clean = """
      <label for="e">Email</label><input id="e">
      <a href="/pricing">Pricing and plans</a>
      <button>Send enquiry</button>
      <table><tr><th>Suburb</th></tr><tr><td>Ballarat</td></tr></table>
      <iframe src="/map" title="Where we are"></iframe>
    """
    assert ids_for(clean) == {"contrast-not-assessed"}


# ---- it does not duplicate other dimensions --------------------------------

def test_it_leaves_alt_text_and_headings_to_onp():
    """Both are accessibility failures, and both already have an owner.
    Raising them here too would deduct twice for one defect."""
    fired = ids_for('<img src="a.png"><h1>a</h1><h3>skipped h2</h3>')
    assert "img-alt-missing" not in fired
    assert "heading-skip" not in fired


def test_markup_inside_noscript_is_not_a_barrier_anyone_meets():
    """A tag manager's noscript iframe has no title and never renders for a
    user running JavaScript. Flagging it would send an operator to fix
    something invisible, and a rendered checker would not agree."""
    assert "iframe-title-missing" in ids_for('<iframe src="/m"></iframe>')
    assert "iframe-title-missing" not in ids_for(
        '<noscript><iframe src="https://gtm.example/ns.html"></iframe></noscript>')
    assert "form-control-unlabelled" not in ids_for(
        "<noscript><input name=q></noscript>")
    # and the surrounding page is still checked normally
    assert "iframe-title-missing" in ids_for(
        '<noscript><iframe src="/gtm"></iframe></noscript><iframe src="/real"></iframe>')
