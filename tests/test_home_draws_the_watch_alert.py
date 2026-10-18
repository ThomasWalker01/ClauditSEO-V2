"""Home draws a watched change as the alert it is (item 260, the Home audit's
AC-01).

"One change is being watched." was the whole of what Home said about a
`watch_changes` alert: a count, in a sentence whose verb said the product had
it in hand, for alerts that run from llms.txt at medium to a robots.txt that
stopped answering at critical. The landing draws the same payload as a toned
line. Home now draws its head - the worst severity and what changed - and opens
the landing with that line open.
"""

from __future__ import annotations

import json

from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)

pytestmark = needs_build


def _home(served, watch, on_landing=False):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            def overview(route):
                body = route.fetch().json()
                for s in body["sites"]:
                    if s["site_id"] == ids["site"]:
                        s["watch"] = watch
                route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
            pg.route("**/api/overview", overview)

            def site(route):
                body = route.fetch().json()
                body["watch"] = watch
                route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
            # The landing reads the site's own payload; it is given the same
            # changes so the line the card opens is the one it reported.
            pg.route(f"**/api/sites/{ids['site']}", site)
            pg.goto(f"{base}/#/", wait_until="load")
            card = f".home-card[data-site='{ids['site']}']"
            pg.wait_for_selector(card, timeout=30_000)
            pg.wait_for_timeout(300)
            got = pg.evaluate(f"""() => {{
              const c = document.querySelector("{card}");
              const w = c.querySelector('.home-card-watch');
              const a = w && w.querySelector('a');
              return {{ text: c.textContent.replace(/\\s+/g, ' '),
                        watch: w && w.textContent.replace(/\\s+/g, ' ').trim(),
                        cls: w && w.className, href: a && a.getAttribute('href') }}; }}""")
            if on_landing and got["href"]:
                pg.click(f"{card} .home-card-watch a")
                pg.wait_for_selector(".alertline", timeout=30_000)
                pg.wait_for_timeout(500)
                got["landing"] = pg.evaluate("""() => ({
                  hash: location.hash,
                  open: document.querySelector('.alertline-head').getAttribute('aria-expanded'),
                  body: (document.querySelector('.alertline-body') || {}).textContent || '' })""")
            return got
        finally:
            browser.close()


def test_a_robots_txt_that_stopped_answering_is_critical_on_home(served):
    got = _home(served, [{"what": "robots.txt HTTP status", "before": 200, "after": 404,
                          "severity": "critical"}])
    assert got["watch"] == "critical robots.txt changed", got
    assert "alert-critical" in got["cls"], got
    assert "being watched" not in got["text"], got["text"]


def test_the_worst_of_several_leads_and_the_door_opens_the_landing_with_the_line_open(served):
    base, ids = served
    got = _home(served, [{"what": "llms.txt HTTP status", "before": 404, "after": None,
                          "severity": "medium"},
                         {"what": "sitemap presence", "before": True, "after": False,
                          "severity": "high"}], on_landing=True)
    assert got["watch"] == "high llms.txt, sitemap presence changed", got
    assert got["href"] == f"#/sites/{ids['site']}?alert=open", got
    assert "landing" in got, got
    assert got["landing"]["open"] == "true", got["landing"]
    assert "robots" not in got["landing"]["body"] and "sitemap presence" in got["landing"]["body"], (
        got["landing"])


def test_no_change_draws_no_alert(served):
    got = _home(served, [])
    assert got["watch"] is None, got
    assert "being watched" not in got["text"]
