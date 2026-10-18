"""A cause with two or more templates opens to them, one row each, with
its own accept ×N and re-audit these N; the instances open beneath the
template.

Brief v3 step M (`_plans/site-screen-brief-v3-2026-09-03.md`, UX-15). On
the operator's own site, Headings → heading-skip opened straight to
forty-five instances, and the template split (146/38/43 pages) was a line
of text on the cause row. The split is three rows now. "Re-audit these N"
is the Record's verify path narrowed to the template's findings - no route
takes a page list, so it is the findings' pages the crawl looks at again.

**Why the wire is rewritten here.** The sweep's fixture has fourteen
top-level pages and no path with ten beneath it, so no template forms
there and the split never paints. The two payloads the screen reads are
answered through the page's own route table with heading-skip spread over
`/blog/` (12 pages), `/docs/` (11) and two pages with no shared template -
the screen's rule, exercised on a shape the fixture cannot grow. The verbs
are intercepted the same way, so nothing moves in the shared fixture.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import json

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

BUCKETS = {
    "hs-blog": [f"https://fixture.test/blog/post-{n}" for n in range(1, 13)],
    "hs-docs": [f"https://fixture.test/docs/page-{n}" for n in range(1, 12)],
    "hs-rest": ["https://fixture.test/about", "https://fixture.test/contact"],
}

_JS = """() => {
  const rows = [...document.querySelectorAll('table.causes tbody tr')];
  const kind = (tr) => tr.classList.contains('cause-row') ? 'cause'
    : tr.classList.contains('cause-template-row') ? 'template'
    : tr.classList.contains('cause-confirm') ? 'confirm'
    : tr.classList.contains('pages-row') ? 'pages' : 'instance';
  return {
    causes: rows.filter((tr) => kind(tr) === 'cause').map((tr) => ({
      check: (tr.querySelector('code')?.textContent || '').trim(),
      pages: (() => {
        // The pages a cause row accounts for. Since item 155 the cell is a
        // count carrying its population - `12 of 16 pages crawled`, and a
        // second span for what the record holds outside the assessed set -
        // so the number is read off the count's own data rather than the
        // cell's text, which is that item's clause and not this one's. The
        // two halves sum to what the cell used to show alone.
        const c = tr.querySelector('td.num [data-population]');
        if (!c) return (tr.querySelector('td.num')?.textContent || '').trim();
        const v = Number(c.getAttribute('data-value') || 0);
        const out = Number(
          tr.querySelector('td.num .prev-outside')?.getAttribute('data-outside') || 0);
        return String(v + out);
      })(),
      expanded: tr.querySelector('.group-toggle')?.getAttribute('aria-expanded'),
    })),
    templates: rows.filter((tr) => kind(tr) === 'template').map((tr) => ({
      name: (tr.querySelector('.tmpl-name')?.textContent || '').trim(),
      n: (tr.querySelector('.tmpl-n')?.textContent || '').trim(),
      pages: (() => {
        // The pages a cause row accounts for. Since item 155 the cell is a
        // count carrying its population - `12 of 16 pages crawled`, and a
        // second span for what the record holds outside the assessed set -
        // so the number is read off the count's own data rather than the
        // cell's text, which is that item's clause and not this one's. The
        // two halves sum to what the cell used to show alone.
        const c = tr.querySelector('td.num [data-population]');
        if (!c) return (tr.querySelector('td.num')?.textContent || '').trim();
        const v = Number(c.getAttribute('data-value') || 0);
        const out = Number(
          tr.querySelector('td.num .prev-outside')?.getAttribute('data-outside') || 0);
        return String(v + out);
      })(),
      expanded: tr.querySelector('.group-toggle')?.getAttribute('aria-expanded'),
      inline: tr.querySelectorAll('td:last-child > button').length,
      verbs: [...tr.querySelectorAll('details.row-more button')].map((b) => b.textContent.trim()),
    })),
    instances: rows.filter((tr) => kind(tr) === 'instance').length,
    confirms: rows.filter((tr) => kind(tr) === 'confirm').length,
    confirmText: (rows.find((tr) => kind(tr) === 'confirm')?.textContent || '').trim(),
  };
}"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def _spread(rows: list[dict], url_key: str) -> list[dict]:
    """Every `http-status-error` row becomes one row per bucket, keyed by the
    bucket's fingerprint; every other row stands as it was.

    `http-status-error` since brief v17 step AX, and filed under Crawl &
    sitemaps: Headings, then Content, each gained a renderer and lost the
    cause table this is a test about. The check is a stand-in either way -
    the rows are the test's own, posted through the route table."""
    out, done = [], False
    for r in rows:
        if r.get("check_id") != "http-status-error":
            out.append(r)
            continue
        if done:
            continue
        done = True
        for fp, urls in BUCKETS.items():
            row = dict(r, fingerprint=fp, state="open", names_a_page=True, source="deterministic")
            row[url_key] = urls
            if "pages" in row:
                row["pages"] = len(urls)
            if "total" in row:
                row["total"] = len(urls)
            out.append(row)
    return out


def _open(browser, base, site_id, posted: list):
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    on_the_layout_of_last_resort(pg)

    def site(route):
        res = route.fetch()
        data = res.json()
        data["states"] = _spread(data["states"], "affected_urls")
        route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

    def anatomy(route):
        res = route.fetch()
        data = res.json()
        # The spread rows are filed under Crawl & sitemaps, whatever
        # category the server put the fixture's own row in. Content gained
        # a renderer at brief v17 step AX and has no cause table, and this
        # is a test about the cause table - so the rows have to sit under a
        # part that still has one. The check id is the test's own either
        # way; what decides which page a part gets is the category.
        moved = []
        for c in data["categories"]:
            kept = [f for f in c["findings"] if f.get("check_id") != "http-status-error"]
            moved += [f for f in _spread(c["findings"], "urls")
                      if f.get("check_id") == "http-status-error"]
            c["findings"] = kept
            # The doctored payload has to keep the payload's own shape: since
            # item 156 `total` is a count carrying its population, so writing
            # a bare integer here would serve the screen a shape the type says
            # cannot arrive.
            c["total"] = {**c["total"], "value": len(kept)}
        for c in data["categories"]:
            if c["key"] == "crawl":
                c["findings"] = c["findings"] + moved
                c["total"] = {**c["total"], "value": len(c["findings"])}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

    def verb(route):
        posted.append((route.request.url, route.request.post_data))
        if route.request.url.endswith("/verify"):
            fps = json.loads(route.request.post_data or "{}").get("fingerprints", [])
            body = {"outcomes": [{"fingerprint": fp, "cleared": True, "decided": True,
                                  "outcome": "cleared"} for fp in fps]}
        else:
            body = {"ok": True}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    pg.route(f"**/api/sites/{site_id}", site)
    pg.route(f"**/api/sites/{site_id}/anatomy*", anatomy)
    pg.route(f"**/api/sites/{site_id}/states/*", verb)
    pg.route(f"**/api/sites/{site_id}/verify", verb)
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Crawl & sitemaps')
    pg.wait_for_selector("table.causes tbody tr.cause-row", timeout=15_000)
    return pg


def test_the_cause_opens_to_three_rows_not_its_instances(browser, served):
    base, ids = served
    posted: list = []
    pg = _open(browser, base, ids["site"], posted)
    try:
        before = pg.evaluate(_JS)
        pg.click('table.causes tbody tr.cause-row:has(code:text-is("TEC/http-status-error")) .group-toggle')
        pg.wait_for_selector("table.causes tbody tr.cause-template-row", timeout=15_000)
        opened = pg.evaluate(_JS)
        pg.click('table.causes tbody tr.cause-template-row:has(.tmpl-name:text-is("Template /blog/*")) .group-toggle')
        pg.wait_for_selector("table.causes tbody tr:not(.cause-row):not(.cause-template-row):has(code)",
                             timeout=15_000)
        under = pg.evaluate(_JS)
    finally:
        pg.close()
    skip = [c for c in before["causes"] if c["check"] == "TEC/http-status-error"]
    assert len(skip) == 1 and skip[0]["pages"] == "25", before["causes"]
    assert before["templates"] == [] and before["instances"] == 0, before
    assert [t["name"] for t in opened["templates"]] == [
        "Template /blog/*", "Template /docs/*", "No shared template"], opened["templates"]
    assert [t["pages"] for t in opened["templates"]] == ["12", "11", "2"], opened["templates"]
    assert opened["instances"] == 0, "the cause opened to its instances, not its templates"
    assert all(t["inline"] == 0 for t in opened["templates"]), opened["templates"]
    assert all(t["verbs"] == ["accept ×1", "re-audit these 1"] for t in opened["templates"]), opened["templates"]
    assert under["instances"] == 1, under
    assert [t["expanded"] for t in under["templates"]] == ["true", "false", "false"], under["templates"]
    assert posted == [], posted


def test_accept_asks_first_and_re_audit_narrows_the_verify_to_the_template(browser, served):
    base, ids = served
    posted: list = []
    pg = _open(browser, base, ids["site"], posted)
    try:
        pg.click('table.causes tbody tr.cause-row:has(code:text-is("TEC/http-status-error")) .group-toggle')
        pg.wait_for_selector("table.causes tbody tr.cause-template-row", timeout=15_000)
        docs = 'table.causes tbody tr.cause-template-row:has(.tmpl-name:text-is("Template /docs/*"))'
        pg.click(f"{docs} details.row-more summary")
        pg.click(f'{docs} button:text-is("accept ×1")')
        pg.wait_for_selector("table.causes tbody tr.cause-confirm", timeout=15_000)
        asked = pg.evaluate(_JS)
        assert posted == [], "accept moved a finding before its second press"
        pg.click('table.causes tbody tr.cause-confirm button:has-text("yes, accept risk")')
        pg.wait_for_function(
            "() => document.querySelectorAll('table.causes tbody tr.cause-confirm').length === 0",
            timeout=15_000)
        pg.wait_for_selector("table.causes tbody tr.cause-template-row", timeout=15_000)
        blog = 'table.causes tbody tr.cause-template-row:has(.tmpl-name:text-is("Template /blog/*"))'
        pg.click(f"{blog} details.row-more summary")
        pg.click(f'{blog} button:text-is("re-audit these 1")')
        pg.wait_for_function(
            "() => !document.querySelector('table.causes button[aria-busy=\"true\"]')", timeout=15_000)
        pg.wait_for_timeout(300)
    finally:
        pg.close()
    assert asked["confirms"] == 1 and "on 1 finding under Template /docs/*" in asked["confirmText"], asked
    states = [(u, b) for u, b in posted if "/states/" in u]
    verifies = [(u, b) for u, b in posted if u.endswith("/verify")]
    assert [u.rsplit("/", 1)[1] for u, _ in states] == ["hs-docs"], states
    assert all(json.loads(b)["state"] == "accepted-risk" for _, b in states), states
    assert len(verifies) == 1 and json.loads(verifies[0][1])["fingerprints"] == ["hs-blog"], verifies
