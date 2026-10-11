"""Item 232 (International, change 1): an analysis the locale gate settled
as not applicable is held, with its reason, and nothing says one "has run".

On twenty22 the part's card said "Not applicable: this site presents one
locale", while the actions row offered "Run analysis · this audit" and the
line beneath it read "no analysis has run on this part" - the product's
usual wording for an analysis that is owed. Now the button is held with the
gate's reason and the line says the analysis does not apply.

The gate's reason names what would change its answer: "a target locale you
state". Since 3 October that input is on the gate card itself, stored on the
site (`sites.target_locales`, migration 0074), and the gate - re-derived on
every read - lifts once one is stated. The last test here drives it.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.db.connection import connect
from clauditseo.engine.types import Tier
from clauditseo.persistence import runs
from clauditseo.persistence.repo import now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://onelocale.fixture"
HTML = ("<html lang='en-AU'><head><title>One</title></head><body><main><h1>One</h1>"
        "<p>One locale, one market, one language on every page of the site.</p>"
        "</main></body></html>")


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP", "TEC"], "T2")
    pages = [Page(url=BASE + p, requested_url=BASE + p, status=200,
                  content_type="text/html", content=HTML) for p in ("/", "/a/")]
    runs.store_evidence(conn, run_id, snapshot(CrawlResult(start_url=BASE + "/", tier=Tier.T2,
                                                           pages=pages)))
    runs.mark_complete(conn, run_id, now_iso())
    conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?",
                 (json.dumps(["/", "/a/"]), run_id))
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("onelocale")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "One Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "onelocale.fixture"}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_gate_is_settled_on_this_fixture(served):
    base, site_id = served
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    part = next(c for c in view["categories"] if c["key"] == "intl")
    assert (part.get("gate") or {}).get("state") == "na", part.get("gate")


@needs_build
def test_the_run_control_is_held_and_nothing_says_one_has_run(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=intl",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-actions .act-brief", timeout=15_000)
            # The hold's reason arrives with the part's analyses. Under the
            # full suite's load the control was read while it still said
            # "Loading the analyses for this part…" (2026-10-02, 17:42).
            pg.wait_for_function(
                "() => !/^Loading/.test(document.querySelector('.part-actions .spend-why')?.textContent || 'Loading')",
                timeout=20_000)
            got = pg.evaluate("""() => ({
              held: document.querySelector('.part-actions .act-brief')?.getAttribute('aria-disabled'),
              why: document.querySelector('.part-actions .spend-why')?.textContent || '',
              prov: document.querySelector('.part-actions .part-prov')?.textContent || '',
            })""")
        finally:
            b.close()
    assert got["held"] == "true", got
    # Item 274: the gate's own sentence, not a second wording of it (row 12:
    # the gate's `why`).
    assert got["why"].startswith("hreflang does not apply: this site presents one locale"), got
    assert "has run" not in got["prov"] and "not applicable" in got["prov"], got


def test_a_target_locale_must_be_a_tag_and_is_stored_as_hreflang_writes_it(served):
    base, site_id = served
    bad = httpx.put(f"{base}/api/sites/{site_id}", json={"target_locales": "en-AU, English"},
                    timeout=30)
    assert bad.status_code == 422 and "English" in bad.text, bad.text
    from clauditseo.persistence import repo
    assert repo.locale_tags("en_au; EN-gb, en-AU, x-default") == ["en-AU", "en-GB", "x-default"]


@needs_build
def test_stating_a_target_locale_on_the_gate_card_lifts_the_gate(served):
    """Last in this module: it changes the site the tests above read."""
    from playwright.sync_api import sync_playwright
    base, site_id = served
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                pg = b.new_page(viewport={"width": 1568, "height": 1080})
                pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=intl", wait_until="load",
                        timeout=30_000)
                pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
                pg.wait_for_selector(".intl-gate .intl-target-input", timeout=15_000)
                pg.fill(".intl-gate .intl-target-input", "en-au, en-gb")
                pg.click(".intl-gate .intl-target button[type=submit]")
                # The part is re-read: the gate card goes, and the field stays
                # on the block with the record's own spelling.
                pg.wait_for_function("() => !document.querySelector('.intl-gate')", timeout=15_000)
                got = pg.evaluate("""() => ({
                  value: document.querySelector('.intl-target-input')?.value,
                  held: document.querySelector('.part-actions .act-brief')?.getAttribute('aria-disabled'),
                })""")
            finally:
                b.close()
        view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
        part = next(c for c in view["categories"] if c["key"] == "intl")
        assert part.get("gate") is None and part["target_locales"] == "en-AU, en-GB", part
        assert got["value"] == "en-AU, en-GB", got
        assert got["held"] != "true", got
    finally:
        httpx.put(f"{base}/api/sites/{site_id}", json={"target_locales": ""}, timeout=30)



def test_the_analysis_reads_the_stated_locales_and_a_run_input_still_wins():
    from clauditseo.analysts.expert import ABSENT, _hreflang_applies, build_context
    from clauditseo.engine.types import Site
    pages = [Page(url=BASE + p, requested_url=BASE + p, status=200,
                  content_type="text/html", content=HTML) for p in ("/", "/a/")]
    ev = snapshot(CrawlResult(start_url=BASE + "/", tier=Tier.T2, pages=pages))
    none = build_context("hreflang", ev, Site(domain="onelocale.fixture"))
    assert none["TARGET_LOCALES"] == ABSENT and _hreflang_applies(ev, none) is not None
    stated = build_context("hreflang", ev, Site(domain="onelocale.fixture",
                                                target_locales="en-AU, en-GB"))
    assert stated["TARGET_LOCALES"] == "en-AU, en-GB" and _hreflang_applies(ev, stated) is None
    run = build_context("hreflang", ev, Site(domain="onelocale.fixture", target_locales="en-AU"),
                        {"TARGET_LOCALES": "de-DE"})
    assert run["TARGET_LOCALES"] == "de-DE"
