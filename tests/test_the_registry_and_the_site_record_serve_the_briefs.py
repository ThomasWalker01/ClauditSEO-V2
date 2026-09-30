"""The check registry carries the briefs' own checks with their defaults,
some per status; the site record carries the local-SEO facts the briefs
read, edited on Admin > Sites and written through the site patch; and the
two brief lists the dashboard kept in TypeScript read the header payload
instead (brief v11 step AI).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from clauditseo import anatomy
from clauditseo.analysts import contract
from clauditseo.checks import brief_only_checks, default_severities, default_severity
from clauditseo.modules.onp import DEFAULT_SEVERITY
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")


def test_the_registry_lists_the_briefs_checks_with_the_operators_defaults():
    d = default_severities()
    assert d["ONP/meta-desc-length"] == "medium"
    assert d["ONP/heading-skip"] == "medium"            # raised from low, the operator's call
    assert d["ONP/title-entity-alignment"] == "medium"
    assert d["ONP/h1-triple-restated"] == {"FAIL": "high", "WARN": "low"}
    assert default_severity("ONP/h1-triple-restated", "FAIL") == "high"
    assert default_severity("ONP/h1-triple-restated", "WARN") == "low"
    assert default_severity("ONP/h1-triple-restated", "PASS-OVERRIDE") == "high"
    for c in ("h1-title-verbatim", "h2-support", "h2-location-service", "h2-overstuffed",
              "h2-question-unanswered", "h3-sub-service", "h3-geo-map"):
        assert d[f"ONP/{c}"] == "medium", c
    assert d["ONP/h1-brand-repeated"] == "low" and d["ONP/h1-hook"] == "low"
    # Eleven of the Headings and Title & description sets, and seven more
    # the Images brief raises that no crawl here can compute (brief v15
    # step AQ): weight, rendered width, OCR, the destination of a link and
    # the image sitemap are none of them in the stored inventory.
    # 47: eighteen through brief v15, less `img-review-schema` which step
    # AS moved to the Structured data part, plus the ten schema checks no
    # crawl can answer - each needs a judgement rather than a reading -
    # plus the four LNK checks brief v17 step AW registered, which need the
    # site's hub map or an entity triple, plus the thirteen Content checks
    # step AX registered across its four analysis prompts, plus the three the
    # crawl brief registered at item 137 (brief v18 step AZ): `crawl-budget-waste`
    # and `render-policy` are its analysis checks, and `ua-server-refusal` is
    # HELD until the UA matrix and the CDN/WAF field land (task 4) — all three
    # cost a model call and no TEC sweep emits them.
    #
    # No longer all `ONP/`: the register spans every module that keeps one,
    # which is what made it a register rather than a list in `onp.py`.
    # +3 at item 137 (brief v18 step BA): indexability's analysis checks
    # noindex-intent, redirect-map-correctness and parameter-policy, model-judged
    # and held, join TEC's brief-only register.
    # +4 at item 141 (brief v19 step BB): the URLs & parameters brief's four
    # analysis checks — url-slug-not-descriptive, url-slug-entity (HELD until the
    # page triple), url-parameter-policy and url-rename — none emitted by a sweep.
    # +5 at item 141 (brief v19 step BC): the Speed brief's five analysis checks
    # — critical-path, lcp-cause, cls-cause, inp-cause, third-party-policy —
    # which PRF joins the register for; its free checks keep inline severities.
    only = brief_only_checks()
    # 59 before brief v20, then +9 Mobile and +11 International at items 147
    # and 148 = 79, then **-6 at brief 160**: the trace made
    # horizontal-overflow, tap-target, viewport-units, viewport-injected,
    # viewport-divergent and viewport-late measurable, so each moved out of the
    # brief-only register and into TEC's severity table on the run where a
    # sweep could raise it. Mobile keeps three here, and they are the three
    # that are judgement rather than measurement, so no capture will move them.
    # +10 at item 143 step BD: SEC's six analysis checks and its four held ones
    # (reputation, open-ports, origin-exposed, admin-hostnames), which no sweep
    # raises in this build.
    # +10 at item 145 step BH: the AI surface brief's analysis checks
    # (llms-txt-coverage/-thin/-conflict/-authored, id-page-absent,
    # entity-type-generic, entity-footprint-unlinked, entity-alignment,
    # entity-enrichment, answer-liftable).
    assert len(only) == 93, sorted(only)
    # TEC joins ONP/LNK/CNT since item 137 (brief v18 step AZ); PRF joins since
    # item 141 (brief v19 step BC) for the Speed brief's analysis checks.
    #
    # INT joins at item 148 (brief v20) and is the first member with NO MODULE.
    # It comes from `checks.LABEL_ONLY_REGISTRIES`: `intl` is ANALYSIS_ONLY, no
    # sweep covers it, so `INT` names where a finding came from without
    # claiming one. Mobile's nine arrive under `TEC`, not a new prefix, which
    # is item 147's opposite call — `mobile` was already a TEC category.
    # SEC joins at item 143 step BD: its analysis and held checks. AIS at item
    # 145 step BH: the AI surface brief's analysis checks.
    assert {c.split("/")[0] for c in only} == {"ONP", "LNK", "CNT", "TEC",
                                               "PRF", "INT", "SEC", "AIS"}, sorted(only)
    # Every brief-only check files under the part its brief writes to.
    assert anatomy.CHECK_CATEGORY["title-entity-alignment"] == "title-desc"
    # Headings' own brief-only checks all begin with `h`; so, since brief
    # v17 step AW, does `LNK/hub-spoke-gap`, which is not one of them. The
    # dimension is what tells them apart.
    assert all(anatomy.CHECK_CATEGORY[c.split("/")[1]] == "headings"
               for c in brief_only_checks()
               if c.startswith("ONP/") and c.split("/")[1].startswith("h"))
    assert all(c in DEFAULT_SEVERITY for c in ("h1-hook", "h3-geo-map"))


def test_a_per_status_default_is_applied_by_status_and_extra_fields_travel():
    block = json.dumps({"strategy": "triple", "rows": [
        {"check": "ONP/h1-triple-restated", "page": "/a", "status": "WARN", "severity": "HIGH",
         "evidence": "x", "replacement": "y", "page_type": "location"},
        {"check": "ONP/h1-triple-restated", "page": "/b", "status": "FAIL", "severity": "LOW",
         "evidence": "x", "replacement": "y", "page_type": "service"}]})
    got = contract.parse("```json\n" + block + "\n```\n", ["ONP/h1-triple-restated"],
                         ["https://f.local/a", "https://f.local/b"], defaults=default_severities())
    by = {r.page[-1]: r for r in got.rows}
    assert by["a"].severity == "low" and not by["a"].raised        # WARN's default; raised without a note
    assert by["b"].severity == "high"                              # FAIL's default over a lower value
    assert by["a"].extra == {"page_type": "location"} and got.strategy == "triple"


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("siterecord")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Record Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "record.fixture"}, timeout=30).json()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


FIELDS = {
    "brand": "Acme Pest Control", "gbp_primary_category": "Pest Control Service",
    "service_area_entity": "Greater Melbourne", "title_strategy": "neighbourhood",
    "neighbourhoods": ["Richmond", "Hawthorn"],
    "entity_variants": {"pest control": ["pest management", "exterminator"]},
    "sub_services": [{"name": "Termite inspection", "url": "/termites"}],
    "location_pages": [{"url": "/pest-control-richmond", "location_entity": "Richmond Victoria"}],
    "page_types": {"/blog/2024": "blog", "/pest-control-richmond": "location"},
    # The entity record the AI surface brief reads (item 145 step BH,
    # migration 0063). `claimed` is a three-state field: an unanswered one is
    # not a "no", so `null` travels.
    "legal_name": "Acme Pest Control Pty Ltd",
    "registered_ids": ["ABN 12 345 678 901", "ACN 345 678 901"],
    "external_profiles": [{"url": "https://www.linkedin.com/company/acme", "claimed": True},
                          {"url": "https://www.facebook.com/acme", "claimed": False},
                          {"url": "https://au.trustpilot.com/review/acme", "claimed": None}],
}


def test_the_site_patch_writes_every_field_and_the_record_route_reads_them_back(served):
    base, site_id = served
    put = httpx.put(f"{base}/api/sites/{site_id}", json=FIELDS, timeout=30)
    assert put.status_code == 200, put.text
    rec = httpx.get(f"{base}/api/sites/{site_id}/record", timeout=30).json()
    for k, v in FIELDS.items():
        assert rec[k] == v, (k, rec.get(k))
    # A bad strategy is refused; a partial patch leaves the rest alone.
    assert httpx.put(f"{base}/api/sites/{site_id}", json={"title_strategy": "sideways"}, timeout=30).status_code == 422
    httpx.put(f"{base}/api/sites/{site_id}", json={"brand": "Acme"}, timeout=30)
    rec = httpx.get(f"{base}/api/sites/{site_id}/record", timeout=30).json()
    assert rec["brand"] == "Acme" and rec["neighbourhoods"] == ["Richmond", "Hawthorn"]
    # The detail route parses the JSON fields the same way.
    detail = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()
    assert detail["location_pages"] == FIELDS["location_pages"]


def test_no_brief_list_remains_in_typescript():
    for name in ("PHASE_GROUPS", "PAGE_EXPERTS", "ONPAGE_EXPERTS"):
        assert not any(name in p.read_text(encoding="utf-8") for p in SRC.glob("*.ts*")), name
    views = (SRC / "views.tsx").read_text(encoding="utf-8")
    assert 'x.type === "page"' in views, "the run page's page briefs come from the lanes payload"
    admin = (SRC / "admin.tsx").read_text(encoding="utf-8")
    assert "lanes.parts" in admin, "the workbench groups by the payload's parts"


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_admin_sites_shows_the_fields_and_saves_them(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        try:
            pg.goto(f"{base}/#/admin?tab=sites", wait_until="load", timeout=30_000)
            pg.wait_for_selector(".site-record", timeout=30_000)
            got = pg.evaluate("""() => ({
              labels: [...document.querySelector('.site-record').querySelectorAll('.sel-lbl')].map((l) => l.textContent.trim()),
              brand: document.querySelector('.site-record input[aria-label="Brand for record.fixture"]')?.value,
              strategy: document.querySelector('.site-record select[aria-label="title strategy for record.fixture"]')?.value,
            })""")
            pg.fill('.site-record input[aria-label="GBP primary category for record.fixture"]', "Pest Control Service")
            pg.click('.card:has(input[aria-label="Brand for record.fixture"]) .site-record-acts button')
            pg.wait_for_function(
                f"() => fetch('{base}/api/sites/{site_id}/record').then((r) => r.json())"
                ".then((s) => s.gbp_primary_category === 'Pest Control Service')", timeout=15_000)
        finally:
            b.close()
    assert got["labels"] == ["Brand", "GBP primary category", "Service area entity", "Title strategy",
                             "Neighbourhoods", "Entity variants", "Sub-services", "Location pages",
                             "Page types",
                             # What the Images brief reads (brief v15 step AQ).
                             "Platform", "Image pipeline", "Breakpoints",
                             "LCP image budget (KB)", "Page image budget (KB)",
                             "Review provenance",
                             # What "too heavy" is for one image (v16 AU7).
                             "Per-image budget (KB)", "Bytes per rendered pixel",
                             "Re-encode quality",
                             # What the Structured data brief reads (v16 AS).
                             # `sameAs sources` and `Citation sources` are two
                             # boxes because the distinction is the finding: a
                             # directory in sameAs claims the entity *is* that
                             # page.
                             "NAP", "sameAs sources",
                             # The entity record (item 145 BH). Three boxes
                             # apart from `sameAs sources`, because that is
                             # what the markup should pin and these are the
                             # entity itself and its footprint.
                             "Legal name", "Registered identifiers",
                             "External profiles",
                             "Citation sources",
                             "Locations", "ID page URI", "Canonical @id",
                             "Priority internal targets",
                             # What the Security brief reads (v20 BD); the map
                             # is what script-inventory classifies against.
                             "Stack", "CDN / WAF",
                             # The AI surface's two inputs (item 145 BG).
                             "AI crawler policy", "Blocked at the firewall on purpose",
                             "AI real-visitor data source",
                             "Third-party map",
                             "Active probing authorised", "Reputation source",
                             "Plugin directory feed"], got
    assert got["brand"] == "Acme" and got["strategy"] == "neighbourhood", got
