"""Item 229 (Crawl, change 3): each size of the site on the Crawl page says
what it counts.

Three were on one screen with no word between them on twenty22 T3: the
header's "74 known" (declared plus everything the crawl fetched or found
linked), the block's "Published 53" (reached or declared), and a depth chart
summing to 48 (every stored page, three 404s included). The block now says
how its 53 relates to the 74, and the chart names its own population.
(Changes 1 and 2 were items 212 and 206.)
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://sizes.fixture"


def _p(path, status=200, outlinks=()):
    return {"url": BASE + path, "status": status, "content_type": "text/html",
            "outlinks": [BASE + o for o in outlinks]}


EVIDENCE = {
    "start_url": BASE + "/",
    # Reached: /, /a. Errored: /gone. Linked but never fetched: /x, /y.
    "pages": [_p("/", outlinks=("/a", "/gone", "/x")), _p("/a", outlinks=("/y",)),
              _p("/gone", status=404)],
    "sitemap_entries": [BASE + "/", BASE + "/a", BASE + "/d"],
    "sitemaps": [{"url": BASE + "/sitemap.xml", "status": 200}],
}


def _run(conn, site_id):
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_evidence(conn, run_id, EVIDENCE)
    runs.mark_complete(conn, run_id, now_iso())
    # What a real audit records, and what makes it the site's reading.
    conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?",
                 ('["/", "/a", "/gone"]', run_id))
    conn.commit()
    return run_id


def test_the_payloads_carry_the_known_size_and_the_error_pages(tmp_path):
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "sizes.fixture")
    run_id = _run(conn, site_id)
    now = runs.crawl_now_payload(conn, run_id)
    assert now["published"] == 3, now                  # / /a /d
    assert now["known"] == runs.site_size(EVIDENCE)["size"] == 6, now  # + /gone /x /y
    depth = runs.crawl_depth_payload(conn, run_id)
    assert depth["crawled"] == 3 and depth["errored"] == 1, depth


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("sizes")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Sizes Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "sizes.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = _run(conn, site["id"])
        conn.close()
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@needs_build
def test_the_page_says_how_the_sizes_relate(served):
    from playwright.sync_api import sync_playwright
    base, site_id, _ = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=crawl",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".crawl-now", timeout=15_000)
            text = pg.evaluate("""() => ({
              kv: document.querySelector('.crawl-now .cn-kv')?.textContent || '',
              note: document.querySelector('.cd-note')?.textContent || '',
            })""")
        finally:
            b.close()
    kv, note = (" ".join(t.split()) for t in (text["kv"], text["note"]))
    assert ("the 6 known also counts 3 URLs found linked or fetched that were neither "
            "reached nor in a sitemap") in kv, kv
    assert "Over the 3 URLs the crawl fetched, including 1 that returned an error." in note, note
