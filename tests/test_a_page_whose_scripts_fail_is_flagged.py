"""A page whose own scripts fail in the browser is flagged (item 247).

twenty22's home page was broken for visitors and no check said so: an
optimiser rewrote inline scripts into `data:` URIs, the site's own CSP
refused them, the theme's lazy loader threw, and seven images and a section
never appeared. The rendered pass had all of it in front of it and listened
for none of it. Now `axe.run_page` keeps what the page's scripts did
(`result["script_errors"]`), A11Y hands it to TEC through the context, and
TEC raises `scripts-blocked-by-csp`, `page-script-error` and
`script-failed-to-load`.
"""

from __future__ import annotations

import pytest

from clauditseo import axe
from clauditseo.crawler.types import CrawlResult, Page, Tier
from clauditseo.engine.types import Site
from clauditseo.modules.tec import TechnicalModule

BASE = "https://js.test"


# --- the mapping, no browser ----------------------------------------------

def _page(path: str) -> Page:
    return Page(url=BASE + path, requested_url=BASE + path, status=200,
                content_type="text/html; charset=utf-8",
                content="<html><body><p>x</p></body></html>")


def _run(script_errors: dict, paths=("/",)):
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages.extend(_page(p) for p in paths)
    ctx = {"crawl": crawl, "site": Site(domain="js.test"),
           "script_errors": script_errors}
    return [f for f in TechnicalModule().run(list(crawl.pages), Tier.T2, ctx)
            if f.check_id in ("scripts-blocked-by-csp", "page-script-error",
                              "script-failed-to-load")]


def _errors(**kw) -> dict:
    return {"exceptions": [], "csp_blocked": [], "failed_loads": [],
            "unloaded_images": 0, **kw}


def test_a_csp_that_blocks_the_pages_own_scripts_is_high_when_one_then_throws():
    """twenty22's shape: `data:` scripts refused, the theme's loader throws,
    seven images never load. The count travels into the summary."""
    got = _run({BASE + "/": _errors(
        csp_blocked=[{"directive": "script-src-elem", "blocked": "data", "source": ""}],
        exceptions=[{"message": "Cannot read properties of undefined (reading 'offsetLazyLoad')",
                     "source": BASE + "/wp-content/litespeed/js/cc74.js"}],
        unloaded_images=7)})
    by = {f.check_id: f for f in got}
    csp = by["scripts-blocked-by-csp"]
    assert csp.severity.value == "high", csp.severity
    assert csp.subject == "/" and csp.affected_urls == [BASE + "/"]
    assert "script-src-elem" in csp.summary, csp.summary
    assert "7 images never loaded" in csp.summary, csp.summary
    assert csp.evidence["images_never_loaded"] == 7
    assert csp.evidence["scripts_then_failing"] == 1
    assert "1 of the page's own scripts then fails." in csp.summary, csp.summary
    err = by["page-script-error"]
    assert err.severity.value == "medium"
    assert err.summary.startswith("1 of the page's own scripts on / fails with"), err.summary
    assert err.evidence["errors"][0]["source"].endswith("cc74.js")


def test_a_csp_block_with_nothing_failing_after_it_is_medium():
    got = _run({BASE + "/": _errors(
        csp_blocked=[{"directive": "script-src", "blocked": BASE + "/x.js", "source": ""}])})
    assert [f.check_id for f in got] == ["scripts-blocked-by-csp"]
    assert got[0].severity.value == "medium"
    assert "never loaded" not in got[0].summary


def test_third_party_scripts_are_listed_but_raise_nothing_on_their_own():
    """A CSP that blocks a CDN's beacon is the policy working, and a
    vendor's exception is the vendor's."""
    got = _run({BASE + "/": _errors(
        csp_blocked=[{"directive": "script-src-elem",
                      "blocked": "https://static.cloudflareinsights.com/beacon.min.js",
                      "source": ""}],
        exceptions=[{"message": "boom", "source": "https://plausible.io/js/pa.js"}],
        failed_loads=[{"url": "https://cdn.example/lib.js", "why": "HTTP 404"}])})
    assert got == [], [f.check_id for f in got]


def test_third_party_rows_travel_in_the_evidence_of_an_own_finding():
    got = _run({BASE + "/": _errors(
        exceptions=[{"message": "own", "source": ""},
                    {"message": "theirs", "source": "https://plausible.io/js/pa.js"}])})
    assert len(got) == 1
    assert [e["message"] for e in got[0].evidence["errors"]] == ["own"]
    assert [e["message"] for e in got[0].evidence["third_party_errors"]] == ["theirs"]


def test_a_script_that_fails_to_load_is_its_own_finding():
    got = _run({BASE + "/": _errors(
        failed_loads=[{"url": BASE + "/old.js", "why": "HTTP 404"}])})
    assert [f.check_id for f in got] == ["script-failed-to-load"]
    assert got[0].evidence["scripts"][0]["why"] == "HTTP 404"


def test_the_same_failure_on_every_rendered_page_is_one_finding():
    """Ruling (a) of item 246: per page, unless it is the template."""
    same = _errors(exceptions=[{"message": "acss is not defined",
                                "source": BASE + "/theme.js"}])
    got = _run({BASE + "/": same, BASE + "/a": same, BASE + "/b": same},
               paths=("/", "/a", "/b"))
    assert len(got) == 1, [(f.subject, f.affected_urls) for f in got]
    assert got[0].subject == "template"
    assert got[0].affected_urls == [BASE + "/", BASE + "/a", BASE + "/b"]
    assert "every one of the 3 rendered pages" in got[0].summary, got[0].summary
    assert got[0].evidence["pages"] == 3


def test_a_failure_on_some_pages_stays_per_page():
    same = _errors(exceptions=[{"message": "acss is not defined",
                                "source": BASE + "/theme.js"}])
    got = _run({BASE + "/": same, BASE + "/a": same, BASE + "/b": _errors()},
               paths=("/", "/a", "/b"))
    assert sorted(f.subject for f in got) == ["/", "/a"]


def test_a_page_with_no_errors_raises_nothing():
    assert _run({BASE + "/": _errors()}) == []


def test_the_first_frame_of_a_stack_names_the_script():
    stack = ("TypeError: x\n"
             "    at e.eachElement (https://t.test/wp-content/js/a.js?ver=1:1:28926)\n"
             "    at https://t.test/b.js:1:1")
    assert axe._frame_url(stack) == "https://t.test/wp-content/js/a.js?ver=1"
    assert axe._frame_url("TypeError: x") == ""
    assert axe._frame_url("    at https://t.test/b.js:1:1") == "https://t.test/b.js"


# --- the capture, which needs a browser ----------------------------------

#: twenty22's failure in miniature: a policy that allows only same-origin
#: scripts, a `data:` script that would define what the next one needs, and
#: a same-site script that throws without it.
CSP_PAGE = """<html lang=en><head><title>t</title></head><body><main>
<h1>h</h1>
<img alt="lazy, and its loader never runs" data-src="/pic.svg" width=40 height=40
     src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E">
<script src="data:text/javascript;base64,d2luZG93LnNldHRpbmdzPXt9"></script>
<script src="/theme.js"></script>
</main></body></html>"""

THEME_JS = "window.settings.offsetLazyLoad;"

CLEAN_PAGE = "<html lang=en><head><title>t</title></head><body><main><h1>h</h1></main></body></html>"


@pytest.mark.skipif(not axe.available(),
                    reason="needs clauditseo[render] and `playwright install chromium`")
def test_the_rendered_pass_keeps_what_the_pages_scripts_did():
    from tests.conftest import FixtureSite

    fixture = FixtureSite({
        "/": (200, {"Content-Security-Policy": "script-src 'self'"}, CSP_PAGE),
        "/theme.js": (200, {"Content-Type": "text/javascript"}, THEME_JS),
        "/clean": (200, {}, CLEAN_PAGE),
    }).start()
    try:
        result = axe.run_page(fixture.base_url + "/")
        clean = axe.run_page(fixture.base_url + "/clean")
    finally:
        fixture.stop()

    errs = result["script_errors"]
    assert [c["directive"] for c in errs["csp_blocked"]] == ["script-src-elem"], errs
    assert errs["csp_blocked"][0]["blocked"].startswith("data"), errs
    assert len(errs["exceptions"]) == 1, errs
    assert "offsetLazyLoad" in errs["exceptions"][0]["message"], errs
    assert errs["exceptions"][0]["source"].endswith("/theme.js"), errs
    # A script the policy refused is a CSP block and only that: counted as a
    # failed load too, the live home page read both about the same scripts.
    assert errs["failed_loads"] == [], errs
    # The placeholder a dead lazy loader leaves is `complete`, and is still
    # an image that never loaded.
    assert result["settle"]["unloaded_images"] == 1, result["settle"]
    assert clean["settle"]["unloaded_images"] == 0, clean["settle"]
    # axe's own script is added after the listening stops, so a policy that
    # would refuse it never charges the page with refusing it.
    assert not any("axe" in (c.get("source") or "") for c in errs["csp_blocked"])
    assert result["violations"] is not None

    assert clean["script_errors"] == {
        "exceptions": [], "csp_blocked": [], "failed_loads": [],
        "seen": {"exceptions": 0, "failed_loads": 0, "csp_blocked": 0}}, clean["script_errors"]


@pytest.mark.skipif(not axe.available(),
                    reason="needs clauditseo[render] and `playwright install chromium`")
def test_a_script_that_404s_is_a_failed_load():
    from tests.conftest import FixtureSite

    page = CLEAN_PAGE.replace("</main>", "<script src='/gone.js'></script></main>")
    fixture = FixtureSite({"/": (200, {}, page)}).start()
    try:
        result = axe.run_page(fixture.base_url + "/")
    finally:
        fixture.stop()
    failed = result["script_errors"]["failed_loads"]
    assert len(failed) == 1 and failed[0]["why"] == "HTTP 404", failed
    assert failed[0]["url"].endswith("/gone.js")
