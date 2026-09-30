"""`poor-extractability` must not read "well structured" off a page it could
not see.

Relay item 025. The check gates on `facts.word_count >= 500`, and
`extract_facts` reads the raw fetched HTML. A site whose content renders
client-side returns a shell — a few dozen words — so the page never reaches
500, the check never fires, and the silence reads as a clean result. **The
worse the rendering problem, the cleaner the answer.**

`AiSurfaceModule.score` already refuses coverage 1.0 for a crawl that fetched
no page, and its comment says why. This is the per-page sibling: the crawl
fetched everything successfully, coverage is legitimately full, and the pages
are empty of content. Full coverage over unqualified input.

Four states, and three of them used to share silence:

  1. long and structured          -> nothing to report          (silence)
  2. short, check does not apply  -> nothing to report          (silence)
  3. raw HTML carries almost      -> the check had NO INPUT     (was silence,
     nothing, scripts present         and is not a pass          now reported)
  4. long and unstructured        -> poor-extractability

Not added to `tests/fixtures/golden_site.py`: that fixture is ground truth for
the labelled corpus, and a new page there changes what every golden expectation
asserts. This is one module's behaviour, so it is tested against a page built
here.
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Site, Tier
from clauditseo.modules.ais import AiSurfaceModule

SITE = "https://x.test"


def _page(body: str, *, path: str = "/", head: str = "") -> Page:
    url = SITE + path
    return Page(url=url, requested_url=url, status=200,
                content_type="text/html", elapsed_ms=10.0, headers={},
                content=f"<html><head>{head}</head><body>{body}</body></html>")


def _run(*pages: Page) -> list:
    crawl = CrawlResult(start_url=SITE + "/", tier=Tier.T2, pages=list(pages))
    return AiSurfaceModule().run(
        [], Tier.T2, {"crawl": crawl, "site": Site(domain="x.test")})


def _ids(findings) -> list[str]:
    return [f.check_id for f in findings]


#: An app shell: almost no text, and the content arrives from a script.
SHELL = _page(
    "<div id='root'></div>",
    head="<script src='https://cdn.x.test/app.js'></script>")

#: The same page as a reader would see it after rendering — long, and with no
#: subheadings. This is what the check exists to catch, and what it never sees.
RENDERED = _page("<h1>Guide</h1><p>" + ("word " * 900) + "</p>")


def test_a_client_rendered_shell_is_not_reported_as_well_structured():
    """The failing state, and the reason this item exists.

    The shell and the rendered page are the same URL. The check judges the
    first and says nothing; a reader takes that silence for the second.
    """
    ids = _ids(_run(SHELL))

    assert "poor-extractability" not in ids, (
        "the raw HTML is 3 words — the check genuinely does not apply to it")
    assert "extractability-not-assessed" in ids, (
        "a page whose raw HTML carries almost nothing, with scripts that "
        "could supply the rest, must say the check had no input rather than "
        f"pass in silence: {ids}")


def test_the_same_page_rendered_is_what_the_check_would_have_caught():
    """Proves the silence above is a false negative and not a correct pass:
    the identical content, present in the raw HTML, fires the check."""
    assert "poor-extractability" in _ids(_run(RENDERED))


def test_a_genuinely_short_page_stays_silent():
    """State 2, which must not become noise. Short, no scripts, renders as it
    is — the check does not apply and there is nothing to say."""
    ids = _ids(_run(_page("<h1>Contact</h1><p>Call us on the number above.</p>")))

    assert "extractability-not-assessed" not in ids, ids
    assert "poor-extractability" not in ids


def test_a_long_structured_page_stays_silent():
    """State 1, unchanged.

    Scoped to the two extractability checks rather than asserting an empty
    list: this fixture has no llms.txt, so the module correctly also reports
    `llms-txt-missing`, which is not this item's subject.
    """
    body = "<h1>Guide</h1>" + "".join(
        f"<h2>Part {i}</h2><p>{'word ' * 200}</p>" for i in range(4))
    ids = _ids(_run(_page(body)))

    assert [i for i in ids if "extractab" in i] == [], ids


def test_the_unassessed_finding_says_what_it_could_not_see():
    """Evidence a later round can act on, not just a label."""
    note = next(f for f in _run(SHELL)
                if f.check_id == "extractability-not-assessed")

    assert note.evidence["word_count"] < 50
    assert note.evidence["script_count"] >= 1
    assert note.affected_urls == [SITE + "/"]


@pytest.mark.parametrize("check", ["poor-extractability",
                                   "extractability-not-assessed"])
def test_both_checks_are_filed_under_a_category(check):
    """A new check with no category lands in `workflow` and vanishes from the
    tree an operator reads — round 032 learned this the same way."""
    from clauditseo import anatomy

    assert check in anatomy.CHECK_CATEGORY, (
        f"{check} has no category; add it to anatomy.CHECK_CATEGORY")
