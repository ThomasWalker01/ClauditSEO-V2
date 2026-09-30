"""The Record's part select (brief v24 step BO; channel ruling 2026-09-15).

The sidebar was the control that narrowed the Record to a part. With it
retired, the Record carries a select of its own, "All parts" first, then each
part with its open count, writing `?part=` and reading it back, so a stored
link still lands on the filter and the existing clear control still clears it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)
from tests.needs_build import needs_build  # noqa: F401

#: Every clause in this file serves `dashboard/dist` and drives a
#: browser against it, so the gate is the file's rather than each
#: clause's (item 190). Local only: CI builds the bundle and fails on
#: any skip.
pytestmark = needs_build


_JS = """() => ({
  hash: location.hash,
  value: document.querySelector('.part-select')?.value ?? null,
  options: [...document.querySelectorAll('.part-select option')].map((o) => o.textContent.trim()),
  chip: (document.querySelector('.part-chip')?.textContent || '').trim(),
  rows: document.querySelectorAll('.pane-body table.findings tbody tr').length,
})"""


def test_the_record_part_select_writes_the_address_and_reads_it_back(served):
    import httpx
    from playwright.sync_api import sync_playwright

    base, ids = served
    cats = [c for c in httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=60).json()["categories"]
            if c["group"] != "workflow"]
    target = next(c for c in cats if c["total"]["value"] > 0)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}?tab=all", wait_until="load", timeout=30_000)
            pg.wait_for_selector(".part-select", timeout=30_000)
            pg.click('[aria-label="state filter"] [data-state="all"]')
            pg.wait_for_timeout(300)
            before = pg.evaluate(_JS)
            pg.select_option(".part-select", target["key"])
            pg.wait_for_function(f"() => location.hash.includes('part={target['key']}')", timeout=10_000)
            pg.wait_for_selector(".part-chip", timeout=10_000)
            chosen = pg.evaluate(_JS)
            pg.reload(wait_until="load")
            pg.wait_for_selector(".part-chip", timeout=30_000)
            reloaded = pg.evaluate(_JS)
            pg.select_option(".part-select", "")
            pg.wait_for_function("() => !location.hash.includes('part=')", timeout=10_000)
            pg.wait_for_function("() => !document.querySelector('.part-chip')", timeout=10_000)
            cleared = pg.evaluate(_JS)
        finally:
            browser.close()
    assert before["value"] == "" and before["options"][0] == "All parts", before
    assert len(before["options"]) == len(cats) + 1, before["options"]
    assert f"{target['label']} · {target['total']['value']} open" in before["options"], before["options"]
    assert "tab=all" in chosen["hash"], "choosing a part on the Record left the Record"
    assert chosen["value"] == target["key"] and chosen["chip"].startswith(target["label"]), chosen
    assert reloaded["value"] == target["key"], reloaded
    assert cleared["value"] == "" and cleared["chip"] == "", cleared
