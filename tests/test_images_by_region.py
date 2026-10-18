"""Images grouped by region, and a template image counted once (brief v16
step AU).

The three clauses AU names: landmarks decide the region; where a page
declares none, position does; and an image the site repeats is one finding
over every page it is on rather than one per page. The last is the one the
step exists for - a missing alt on a footer icon was 248 findings, 248 fix
cards and a badge reading 248 on a site with one problem.
"""

from __future__ import annotations

from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import CrawlResult, Page, Tier
from clauditseo.modules.onp import OnPageModule
from clauditseo.modules.pagefacts import (TEMPLATE_MIN_PAGES, extract_facts,
                                          identify_logo, schema_logo)

BASE = "https://regions.fixture"

#: A page with every landmark declared, including the two traps: a `<nav>`
#: inside the `<footer>`, and a `role="banner"` on a `<div>` - which the
#: region stack used to push and never pop, so every image after it on the
#: page reported the banner as its region.
LANDMARKS = (
    "<html><body>"
    "<div role='banner'><a href='/'><img src='/logo.svg' alt='Regions' width='200' "
    "height='50'></a><nav><img src='/menu.svg' alt='Menu' width='24' height='24'>"
    "</nav></div>"
    "<main><img src='/hero-{n}.jpg' alt='Hero'><img src='/cta.png' alt='Book now'></main>"
    "<footer><nav><img src='/x.png' alt='Facebook' width='30' height='30'></nav></footer>"
    "<img src='/stray-{n}.png' alt='Stray'>"
    "</body></html>"
)

#: The same page with no landmark at all - the shape the fallback is for.
#: Every image is `body` to the markup, and only where a browser measured
#: the document may position say otherwise.
FLAT = (
    "<html><body>"
    "<img src='/logo.svg' alt='Regions' width='200' height='50'>"
    "<img src='/hero-{n}.jpg' alt='Hero'>"
    "<img src='/x.png' alt='' width='30' height='30'>"
    "</body></html>"
)


def _crawl(html: str, n: int = 3) -> CrawlResult:
    pages = [Page(url=f"{BASE}/{i or ''}", requested_url=f"{BASE}/{i or ''}", status=200,
                  content_type="text/html", content=html.replace("{n}", str(i)))
             for i in range(n)]
    return CrawlResult(start_url=BASE + "/", tier=Tier.T2, pages=pages)


def _inventory(result: dict, page: int = 0) -> dict[str, dict]:
    return {i["src"]: i for i in result["pages"][page]["image_inventory"]}


# --- AU1: where an image sits -----------------------------------------------

def test_landmarks_decide_the_region_and_the_footers_nav_is_the_footer():
    """A `<nav>` inside a `<footer>` is footer furniture.

    Read off the whole stack rather than the innermost landmark, which is
    the nav: grouping the site's legal links with the masthead would put
    them above the content on the one screen an operator opens to see what
    is above the content.
    """
    by = _inventory(snapshot(_crawl(LANDMARKS)))
    assert by["/logo.svg"]["region_class"] == "header"
    assert by["/menu.svg"]["region_class"] == "header"
    assert by["/hero-0.jpg"]["region_class"] == "body"
    assert by["/x.png"]["region_class"] == "footer"
    # The trap: `role="banner"` on a `<div>`. The stack pushed on the role
    # and popped on the tag, so the div never closed and this image - which
    # is outside every landmark - reported the banner.
    assert by["/stray-0.png"]["region_class"] == "body"
    assert by["/stray-0.png"]["region"] == "body"


def test_a_page_with_no_landmarks_says_body_and_does_not_guess():
    """Without a landmark and without a measurement there is nothing to
    read a region off, and `body` is the honest answer rather than a guess
    at where a logo usually sits."""
    by = _inventory(snapshot(_crawl(FLAT)))
    assert {i["region_class"] for i in by.values()} == {"body"}
    assert not any(i.get("region_from") for i in by.values())


def test_position_names_the_region_only_where_the_site_repeats_the_image():
    """The fallback, and the half of it that keeps it honest.

    Position on one page is not evidence of a template: a photograph at the
    top of one article is at the top of one article. So a measured
    `top_pct` moves an image into the header or the footer only alongside
    the share rule, and the row then says `region_from: position` - a band
    a browser inferred never reads as one the markup stated.
    """
    measured = {f"{BASE}/{i or ''}": {"/logo.svg": {"top_pct": 0.02},
                                      "/x.png": {"top_pct": 0.97},
                                      f"/hero-{i}.jpg": {"top_pct": 0.05}}
                for i in range(3)}
    by = _inventory(snapshot(_crawl(FLAT), measured))
    assert by["/logo.svg"]["region_class"] == "header"
    assert by["/logo.svg"]["region_from"] == "position"
    assert by["/x.png"]["region_class"] == "footer"
    # At the top of its page on every page, but a different file each time,
    # so it is one page's content and stays where the markup left it.
    assert by["/hero-0.jpg"]["region_class"] == "body"
    assert not by["/hero-0.jpg"].get("region_from")


# --- AU1: what the site repeats ---------------------------------------------

def test_the_furniture_is_template_and_one_pages_own_images_are_not():
    by = _inventory(snapshot(_crawl(LANDMARKS)))
    assert by["/logo.svg"]["template"] is True
    assert by["/x.png"]["template"] is True
    # A body image the site repeats is still one change - a CTA banner in
    # every post template is not this page's content.
    assert by["/cta.png"]["template"] is True
    assert by["/hero-0.jpg"]["template"] is False


def test_two_pages_are_not_enough_to_call_anything_a_template():
    """On a two-page crawl every image on both pages is on 100% of them,
    which is arithmetic rather than evidence - and the cost of believing it
    is a fix card reading `fixes 2 pages` about a photograph.

    The landmarks still decide: a header image is furniture because that is
    what a header is, not because it was counted.
    """
    assert TEMPLATE_MIN_PAGES == 3
    by = _inventory(snapshot(_crawl(LANDMARKS, n=2)))
    assert by["/logo.svg"]["template"] is True
    assert by["/cta.png"]["template"] is False


# --- AU2 and AU4: one finding, over every page it is on ---------------------

def test_a_template_images_problem_is_one_finding_over_all_its_pages():
    """The step's whole reason. One missing alt on a footer icon was a
    finding per page; on a 248-page site that is 248 findings, 248 fix
    cards, and a sidebar badge saying Images has 248 problems when it has
    one."""
    facts = [extract_facts(p) for p in _crawl(LANDMARKS, n=6).pages]
    found = OnPageModule()._image_checks(facts)
    footer = [f for f in found if f.evidence.get("image") == "/x.png"]
    assert footer, [f.evidence.get("image") for f in found]
    for f in footer:
        assert len(f.affected_urls) == 6, (f.check_id, f.affected_urls)
        assert f.evidence["pages"] == 6 and f.evidence["template"] is True
        # The sentence stops being about one page when the row does.
        assert "every one of the 6 pages" in f.summary, f.summary
    # And a page's own image is still its own: six heroes, six findings.
    heroes = [f for f in found
              if str(f.evidence.get("image") or "").startswith("/hero-")]
    assert heroes and all(len(f.affected_urls) == 1 for f in heroes)


def test_the_sweep_and_the_record_mark_the_same_images_as_template():
    """Two writings of the rule would be two answers to "how many problems
    does this part have" - the count on the badge and the count in the
    table - which is the disagreement AU2 is about."""
    crawl = _crawl(LANDMARKS, n=4)
    stored = _inventory(snapshot(crawl))
    facts = [extract_facts(p) for p in crawl.pages]
    swept = OnPageModule()._marked_inventories(facts, None)
    by_src = {i["src"]: i for i in swept[crawl.pages[0].url]}
    assert {s for s, i in stored.items() if i["template"]} \
        == {s for s, i in by_src.items() if i["template"]}


# --- AU6: the logo ----------------------------------------------------------

#: What the parser stores is the block's JSON, not the `<script>` that
#: carried it, so a clause calling `schema_logo` directly passes the one
#: and a page fixture embeds the other.
ENTITY = ('{"@type":"Organization","logo":"https://cdn.example/brandmark.svg",'
          '"image":"https://lh3.googleusercontent.com/shopfront.jpg"}')
SCHEMA = '<script type="application/ld+json">' + ENTITY + '</script>' 


def test_the_schema_names_the_logo_and_never_the_entitys_image():
    """`logo` only. An entity's `image` is routinely a photograph - a
    Google-hosted shopfront, most often - and reading it as the logo would
    have the part page telling an operator to replace their masthead with a
    picture of their door."""
    assert schema_logo([ENTITY]) == "https://cdn.example/brandmark.svg"


def test_the_logo_is_found_by_the_schema_before_the_markup():
    """The site's own declaration outranks a guess about filenames: a
    heuristic that disagreed with the schema would be this part arguing
    with the page it is describing."""
    inventory = [
        {"src": "https://cdn.example/brandmark.svg", "region_class": "header",
         "alt": "", "linked_to": None, "width": "200", "height": "50"},
        {"src": "/site-logo.png", "region_class": "header", "alt": "Logo",
         "linked_to": "/", "width": "180", "height": "40"},
    ]
    logo = identify_logo(inventory, [ENTITY])
    assert logo is inventory[0]
    assert logo["is_logo"] is True
    assert logo["logo_from"].startswith("the entity's declared logo")
    assert not inventory[1].get("is_logo")


def test_where_the_schema_is_silent_the_markup_decides_and_says_so():
    inventory = [
        {"src": "/icon-cart.svg", "region_class": "header", "alt": "Cart",
         "linked_to": "/cart", "width": "24", "height": "24"},
        {"src": "/regions-logo.svg", "region_class": "header", "alt": "Regions",
         "linked_to": "/", "width": "200", "height": "50"},
    ]
    logo = identify_logo(inventory, [], brand="Regions Group")
    assert logo is inventory[1]
    assert logo["logo_from"].startswith("a header image linked to the home page")


def test_an_unlinked_header_image_is_not_read_as_linked_to_the_home_page():
    """The dead end this clause is here for: the home test was
    `linked_to in ("/", "")`, so an image with no link at all satisfied it.
    Signal two then claimed a logo that the very next check reported as
    "not wrapped in a link" - one row asserting and denying one fact. The
    image is still the logo, by the third signal, and the sentence about it
    is now the only one."""
    inventory = [{"src": "/regions-logo.svg", "region_class": "header",
                  "alt": "Regions", "linked_to": None,
                  "width": "200", "height": "50"}]
    logo = identify_logo(inventory, [], brand="Regions")
    assert logo is inventory[0]
    assert logo["logo_from"].startswith("the first image in the header")


def test_the_logo_is_stored_on_the_record_and_read_by_the_sweep():
    """One writing, so the record and the finding cannot name different
    images as the logo. The record has no site to ask for a brand; the
    sweep has one, and it refines the second signal only - the brand's real
    work is judging the alt text, which is the sweep's job."""
    html = ("<html><head>" + SCHEMA + "</head><body><header>"
            "<a href='/'><img src='https://cdn.example/brandmark.svg' alt='logo' "
            "width='200' height='50'></a></header>"
            "<main><img src='/p-{n}.jpg' alt='P'></main></body></html>")
    crawl = _crawl(html)
    stored = _inventory(snapshot(crawl))
    assert stored["https://cdn.example/brandmark.svg"]["is_logo"] is True

    found = OnPageModule()._image_checks([extract_facts(p) for p in crawl.pages],
                                         brand="Regions Group")
    logo = [f for f in found if f.check_id == "img-logo"]
    assert len(logo) == 1, [f.summary for f in logo]
    assert len(logo[0].affected_urls) == 3, logo[0].affected_urls
    # `alt="logo"` is the brand's absence, and only the sweep can know it.
    assert "rather than the brand name" in logo[0].summary, logo[0].summary


def test_a_logo_wrapped_in_an_absolute_home_link_is_linked_home():
    """Observed on Birch, on the run this step was verified against.

    Its masthead is wrapped in `https://www.beacon.com.au/`, and the
    second signal understood `/` alone - so the logo was found by the third
    signal instead and `logo_from` read "the first image in the header that
    is not an icon". The image was right and the sentence about it was not,
    and the sentence is what an operator judges the answer by.

    Compared against the page's own origin rather than a stored domain: the
    crawl's URL is the one thing here that is certainly right about which
    site this is.
    """
    inventory = [{"src": "/brand.svg", "region_class": "header", "alt": "Regions",
                  "linked_to": "https://regions.fixture/", "width": "200",
                  "height": "50"}]
    logo = identify_logo(inventory, [], brand="Regions",
                         page_url="https://regions.fixture/about")
    assert logo is inventory[0]
    assert logo["logo_from"].startswith("a header image linked to the home page")

    # Another site's home page is not this site's, and a home page with a
    # query on it is a filtered view rather than the front door.
    for href in ("https://elsewhere.example/", "https://regions.fixture/?page=2",
                 "https://regions.fixture/about"):
        row = [{"src": "/brand.svg", "region_class": "header", "alt": "Regions",
                "linked_to": href, "width": "200", "height": "50"}]
        found = identify_logo(row, [], brand="Regions",
                              page_url="https://regions.fixture/about")
        assert found is row[0], href
        assert found["logo_from"].startswith("the first image in the header"), href


# --- AU7: per-image weight, and savings that were measured ------------------

def test_one_image_can_be_too_heavy_on_a_page_that_is_not():
    """The page budget is a budget for a page (brief v15), so a heavy image
    below the fold of an otherwise light page sits inside it and says
    nothing. `img-heavy` is the per-image ceiling, and it has two ways to
    fire because kilobytes alone miss a badly encoded thumbnail: 300 KB in
    a 400x300 box is 2.5 bytes a pixel, and a well-encoded photograph is
    under 0.5.
    """
    html = ("<html><body><main><img src='/thumb.png' alt='Thumb' width='400' "
            "height='300'></main></body></html>")
    page = Page(url=BASE + "/", requested_url=BASE + "/", status=200,
                content_type="text/html", content=html)
    measured = {BASE + "/": {"/thumb.png": {
        "weight_kb": 540, "rendered": {"1440": [400, 300]}, "lcp_candidate": False,
        "measured_kb": 45, "encoder": "WebP q60 at 400"}}}
    found = OnPageModule()._image_checks([extract_facts(page)], measured)
    heavy = [f for f in found if f.check_id == "img-heavy"]
    assert len(heavy) == 1, [f.check_id for f in found]
    row = heavy[0]
    assert row.evidence["bytes_per_pixel"] == 4.61, row.evidence
    assert row.evidence["rendered_at"] == [400, 300]
    # The whole of AU7's rule: the saving is on the row because it was
    # measured, and it names what it was measured with.
    assert row.evidence["measured_kb"] == 45
    assert row.evidence["encoder"] == "WebP q60 at 400"


def test_a_page_inside_both_ceilings_raises_nothing_heavy():
    """The fixture's own fitness, asserted rather than assumed: a check
    that fired on everything would satisfy the clause above by accident."""
    html = ("<html><body><main><img src='/ok.avif' alt='Fine' width='400' "
            "height='300' srcset='/ok-800.avif 800w' sizes='100vw'></main></body></html>")
    page = Page(url=BASE + "/", requested_url=BASE + "/", status=200,
                content_type="text/html", content=html)
    measured = {BASE + "/": {"/ok.avif": {
        "weight_kb": 40, "rendered": {"1440": [400, 300]}, "lcp_candidate": False}}}
    # `img-logo-not-assessed` is expected and is not about this page's
    # images: since
    # 2026-09-06 a site that declares no header landmark is told so once,
    # at INFO and held, because silence there read as "checked, fine".
    # What this clause is about is the weight rules firing on nothing.
    raised = [f.check_id for f in
              OnPageModule()._image_checks([extract_facts(page)], measured)]
    assert [c for c in raised if c != "img-logo-not-assessed"] == [], raised


def test_a_saving_is_never_stated_unless_it_was_measured():
    """AU7's rule, and the reason this module has no formula in it.

    "3.1 MB recoverable" is the one number on this part an operator acts on
    directly, so an estimate dressed as a measurement is the worst thing it
    could say. A row whose probe never ran carries no saving; a row whose
    probe ran and failed carries the reason and still no saving.
    """
    html = ("<html><body><main><img src='/heavy.jpg' alt='H' width='400' "
            "height='300'></main></body></html>")
    page = Page(url=BASE + "/", requested_url=BASE + "/", status=200,
                content_type="text/html", content=html)
    base = {"weight_kb": 900, "rendered": {"1440": [400, 300]}, "lcp_candidate": False}

    never = OnPageModule()._image_checks(
        [extract_facts(page)], {BASE + "/": {"/heavy.jpg": dict(base)}})
    for f in never:
        assert "measured_kb" not in f.evidence, f.check_id
        assert "reencode_error" not in f.evidence, f.check_id

    failed = OnPageModule()._image_checks(
        [extract_facts(page)],
        {BASE + "/": {"/heavy.jpg": {**base, "reencode_error": "the file could not be fetched"}}})
    heavy = next(f for f in failed if f.check_id == "img-heavy")
    assert heavy.evidence["reencode_error"] == "the file could not be fetched"
    assert "measured_kb" not in heavy.evidence


def test_the_re_encoder_reports_a_reason_rather_than_a_zero_saving():
    """Every failure path answers `reencode_error`, never `measured_kb: 0`.

    Driven against a URL that cannot resolve, so the clause needs no
    network and no fixture server: what it is about is the shape of the
    answer, and a saving of zero is a claim that re-encoding would gain
    nothing - which is exactly what a failed fetch does not know.
    """
    from clauditseo import reencode

    got = reencode.one("http://127.0.0.1:9/not-a-real-image.png", 400)
    assert "measured_kb" not in got, got
    assert got["reencode_error"], got


def test_a_bare_install_answers_rather_than_raising(monkeypatch):
    """The failure path a developer machine cannot see.

    `one()` opened with `from PIL import Image`, so a machine without
    Pillow raised `ModuleNotFoundError` instead of answering - breaking the
    promise in its own docstring, and contradicting the operator's ruling
    that "saving not measured" is the honest default on a bare install.
    `available()` was already correct and nothing here called it.

    Four consecutive green local runs missed it because the developer venv
    has Pillow; CI caught it on both platforms. So the import is simulated
    rather than skipped-around - a `skipif(not available())` would have
    made this clause silent on exactly the machines where the defect lives,
    which is how it stayed invisible in the first place.
    """
    import builtins

    from clauditseo import reencode

    real = builtins.__import__

    def without_pillow(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("No module named 'PIL'")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_pillow)

    assert reencode.available() is False
    got = reencode.one("http://127.0.0.1:9/not-a-real-image.png", 400)
    assert "measured_kb" not in got, got
    assert "install clauditseo[image]" in got["reencode_error"], got
    # And the batch caller answers with no rows rather than one exception
    # forty images into a run.
    assert reencode.measure([("http://127.0.0.1:9/a.png", 400)]) == {}


def test_the_audit_only_re_encodes_the_images_a_row_will_be_written_about():
    """The probe fetches the site's own assets, so what it fetches is worth
    stating: every candidate is already a failing row. It is a measurement
    of work the operator has been told to do, not a sweep of the site."""
    from clauditseo.api.app import _reencode_candidates

    measured = {
        BASE + "/": {
            # Over the flat ceiling.
            "/big.jpg": {"weight_kb": 900, "rendered": {"1440": [1200, 800]},
                         "resolved": BASE + "/big.jpg"},
            # Inside every ceiling, and a modern format: not a candidate.
            "/fine.avif": {"weight_kb": 40, "rendered": {"1440": [400, 300]},
                           "resolved": BASE + "/fine.avif"},
            # Light, but a legacy format, which is a row of its own.
            "/logo.png": {"weight_kb": 8, "rendered": {"1440": [200, 60]},
                          "resolved": BASE + "/logo.png"},
            # Nobody weighed it, so nothing can be said about it.
            "/unknown.jpg": {"rendered": {"1440": [800, 600]},
                             "resolved": BASE + "/unknown.jpg"},
        }}
    got = dict(_reencode_candidates(measured, {}))
    assert BASE + "/big.jpg" in got and got[BASE + "/big.jpg"] == 1200
    assert BASE + "/logo.png" in got
    assert BASE + "/fine.avif" not in got
    assert BASE + "/unknown.jpg" in got, (
        "a JPG is a candidate on its format alone, weighed or not")


def test_a_re_encode_that_gains_nothing_is_not_reported_as_a_saving():
    """Two rows on Birch's home page read as savings and were not.

    `T Logo_White.png` was re-encoded to 1 KB with no measured weight
    beside it - a saving needs something to be a saving *from* - and
    `jeremy-zero-...jpg` came out at 5 KB from 4 KB, which is a
    measurement that the file is already right. The engine records both
    faithfully; what changed is that the card stops calling either one a
    saving, and the page's total counts only the rows that gain.

    Asserted on the source, because what is wrong in both cases is a
    sentence rather than a number, and the numbers are correct.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    assert "i.measured_kb != null && i.weight_kb != null" in src, (
        "the card states a saving without a weight to measure it against")
    assert "re-encoding saves nothing here" in src, (
        "a re-encode that comes out larger still renders as an arrow down")
    assert "i.measured_kb < i.weight_kb);" in src, (
        "the recoverable total counts rows that gain nothing")


def test_the_bytes_per_pixel_rule_says_nothing_about_a_one_kilobyte_icon():
    """A departure from AU7's text, read on Birch.

    A 1 KB social icon rendering at 30x30 is 1.14 bytes a pixel and was
    raised as too heavy. The arithmetic is right and the finding is not:
    bytes per pixel measures how well a file is encoded, and below about
    twenty kilobytes there is nothing an operator could do about the
    answer. A finding nobody would act on crowds out the ones they would,
    which is AU2's complaint one rule further down.

    The flat ceiling keeps no floor and needs none, which is the other
    half of this clause: a file over 300 KB is over it whatever size it
    renders at.
    """
    html = ("<html><body><footer><img src='/icon.png' alt='' width='30' "
            "height='30'></footer><main><img src='/big.png' alt='B' width='40' "
            "height='30'></main></body></html>")
    page = Page(url=BASE + "/", requested_url=BASE + "/", status=200,
                content_type="text/html", content=html)
    measured = {BASE + "/": {
        # 1.14 bytes a pixel, and one kilobyte.
        "/icon.png": {"weight_kb": 1, "rendered": {"1440": [30, 30]}},
        # Far over the flat ceiling on a tiny box: still a finding.
        "/big.png": {"weight_kb": 400, "rendered": {"1440": [40, 30]}},
    }}
    heavy = [f.evidence["image"] for f in
             OnPageModule()._image_checks([extract_facts(page)], measured)
             if f.check_id == "img-heavy"]
    assert heavy == ["/big.png"], heavy


# --- relay item 138: a template row covers the pages its image is on -------

def test_a_template_rows_answer_covers_every_page_its_image_is_on():
    """Birch's first Images run reported 59 sweep rows the brief had not
    covered, almost all of them on the site's own furniture. The brief had
    answered every one - with a single template row, whose `page` names
    whichever page it happened to write it against. Matching on
    (check, page) could not see that, so a brief doing exactly what the
    contract asks for looked like a brief that had skipped fifty-nine
    pages.

    Keyed on the image rather than on the template flag: the flag is on the
    inventory and this function has the rows, and what makes a row answered
    is that the brief named that image for that check - through
    `also_resolves` as well as its own `check`.
    """
    import json
    from pathlib import Path

    from clauditseo.analysts.expert import _image_name, _uncovered
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    # The brief writes the image as a phrase, not a bare name - Birch's
    # rows read `19ecb7_f83....png (T Logo_White.png, w_371,h_508)` - and
    # the sweep holds the URL the CDN served. Both come down to one file.
    assert _image_name("19ecb7_f83.png (T Logo_White.png, w_371,h_508)") == "19ecb7_f83.png"
    assert _image_name("https://cdn.example/x/19ecb7_f83.png?w=300") == "19ecb7_f83.png"

    import tempfile
    tmp = Path(tempfile.mkdtemp())
    conn = connect(tmp / "u.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Cover Co")
    site_id = repo.create_site(conn, client, "cover.fixture")
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    urls = [f"https://cover.fixture/{n}" for n in ("", "a", "b")]
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
            " summary, affected_urls, fingerprint, evidence, created_at)"
            " VALUES (?, ?, 'ONP', 'img-no-srcset', 'medium', 'deterministic', 's', ?,"
            " 'fp-1', ?, '2026-09-05')",
            (repo.create_id(), run_id, json.dumps(urls),
             json.dumps({"image": "https://cdn.example/x/footer-map.png?w=40",
                         "template": True})))

    class Row:
        check = "ONP/img-no-srcset"
        page = "https://cover.fixture/"
        image = "footer-map.png (Footer map, w_40)"
        also_resolves: list = []

    # Answered on one page, by a row about that image: covered everywhere.
    assert _uncovered(conn, run_id, ["ONP/img-no-srcset"], [Row()], urls) == []

    # And a check the brief named nowhere is one omission, not three - the
    # sweep folded the finding over every page, and listing it per page is
    # the arithmetic AU2 removed from the badge still being done here.
    left = _uncovered(conn, run_id, ["ONP/img-no-srcset"], [], urls)
    assert len(left) == 1 and left[0]["pages"] == 3, left
