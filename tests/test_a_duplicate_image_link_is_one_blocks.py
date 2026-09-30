"""Item 225 (Images, change 1): two images linking one place is one block's
work, not the site's furniture.

`img-duplicate-links` counted every linked image on a page against every
other. The logo linking home in the header, and again in the footer, is one
href twice on every page - on twenty22 T3 the check fired on 31 of 45 pages,
31 of the part's 35 open items, and the "show all 31" buried the site's real
image list. It now counts per region and leaves the logo and the header and
footer out; two cards in the body linking one page still raise it.
"""

from __future__ import annotations

from clauditseo.crawler.types import Page
from clauditseo.modules.onp import OnPageModule
from clauditseo.modules.pagefacts import extract_facts

HOME = "https://dup.fixture/"


def _found(body: str) -> list:
    html = f"<html lang='en'><head><title>Dup</title></head><body>{body}</body></html>"
    facts = extract_facts(Page(url=HOME, requested_url=HOME, status=200,
                               content_type="text/html", content=html))
    return [f for f in OnPageModule()._image_checks([facts])
            if f.check_id == "img-duplicate-links"]


CHROME = ("<header><a href='/'><img src='logo.svg' alt='Dup home' width='120' height='40'></a>"
          "<a href='/'><img src='mark.png' alt='' width='200' height='80'></a></header>"
          "<main><p>Dup runs events across the country for companies of every size.</p></main>"
          "<footer><a href='/'><img src='logo-footer.svg' alt='Dup' width='120' height='40'></a>"
          "<a href='/'><img src='badge.png' alt='' width='200' height='80'></a></footer>")

CARDS = ("<main><a href='/events'><img src='card-a.png' alt='a' width='400' height='300'></a>"
         "<a href='/events'><img src='card-b.png' alt='b' width='400' height='300'></a></main>")


def test_the_header_and_footer_linking_home_is_not_raised():
    assert _found(CHROME) == []


def test_two_body_images_linking_one_page_still_are():
    got = _found(CARDS)
    assert len(got) == 1, got
    assert got[0].evidence["href"] == "/events" and got[0].evidence["images"] == 2
    assert got[0].evidence["region_class"] == "body"


def test_the_chrome_does_not_join_a_body_pair():
    """A body image linking home beside the header logo linking home is one
    link in the body, not two."""
    body_home = "<main><a href='/'><img src='hero.png' alt='h' width='800' height='400'></a></main>"
    assert _found(CHROME + body_home) == []
