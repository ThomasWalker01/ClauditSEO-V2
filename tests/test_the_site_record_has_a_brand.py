"""The brand a site's copy carries is on the site record (brief v11 step
AI): a column, a field on the site's row, a `brand` on the site patch,
and the runner reads it before falling back to the pages' title tails -
listing that fallback under the contract's assumptions when it does.
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.analysts.expert import _brand_of
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.persistence import repo
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")


def test_the_record_holds_a_brand_and_the_patch_writes_it(tmp_path):
    conn = connect(tmp_path / "brand.db")
    migrate(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sites)")}
    assert "brand" in cols
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Brand Co")
    site_id = repo.create_site(conn, client, "fixture.local")
    assert repo.get_site(conn, site_id)["brand"] is None
    repo.update_site(conn, site_id, brand="Fixture")
    assert repo.get_site(conn, site_id)["brand"] == "Fixture"
    repo.update_site(conn, site_id, business_type="lender")        # leaves the brand alone
    assert repo.get_site(conn, site_id)["brand"] == "Fixture"
    repo.update_site(conn, site_id, brand="")                       # clears it
    assert repo.get_site(conn, site_id)["brand"] is None


def test_the_runner_prefers_the_record_and_names_its_fallback():
    pages = [{"title": "Loans | Acme"}, {"title": "Apply | Acme"}, {"title": "About"}]
    assert _brand_of(pages, Site(domain="www.acme.com.au", brand="Acme Finance")) == ("Acme Finance", None)
    brand, why = _brand_of(pages, Site(domain="www.acme.com.au"))
    assert brand == "Acme" and why.startswith("brand not set on the site record; taken as 'Acme' from the tail")
    brand, why = _brand_of([{"title": "Home"}], Site(domain="https://www.acme.com.au/"))
    assert brand == "Acme" and why.endswith("from the domain")


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("brand")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Brand Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "brand.fixture"}, timeout=30).json()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_site_patch_sets_the_brand_and_home_carries_it(served):
    base, site_id = served
    put = httpx.put(f"{base}/api/sites/{site_id}", json={"brand": "Fixture"}, timeout=30)
    assert put.status_code == 200, put.text
    assert httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["brand"] == "Fixture"
    rows = httpx.get(f"{base}/api/overview", timeout=30).json()
    rows = rows if isinstance(rows, list) else rows.get("sites", rows.get("rows", []))
    mine = next(r for r in rows if r["site_id"] == site_id)
    assert mine["brand"] == "Fixture"


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_field_on_the_sites_row_writes_the_record(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        try:
            pg.goto(f"{base}/#/", wait_until="load", timeout=30_000)
            # Item 176: the brand is a fact on the card, edited behind it.
            pg.wait_for_selector(".home-card", timeout=30_000)
            pg.click(".home-card .home-card-manage > summary")
            pg.wait_for_selector(".brand-field", state="visible", timeout=30_000)
            field = pg.locator(".brand-field").first
            assert field.input_value() == "Fixture"
            field.fill("Fixture Co")
            field.press("Enter")
            pg.wait_for_function(
                f"() => fetch('{base}/api/sites/{site_id}').then((r) => r.json()).then((s) => s.brand === 'Fixture Co')",
                timeout=15_000)
        finally:
            b.close()
    assert httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["brand"] == "Fixture Co"
