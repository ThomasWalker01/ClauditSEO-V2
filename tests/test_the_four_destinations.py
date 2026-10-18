"""Brief v24 step BN: six steps become four destinations - Audit, Analyses,
Record, Client report. Precheck and Triage fold into Audit; History folds into
the Record; the Analyses shop sorts by rank.

The sequence logic is kept (the primary action reads it); only what is drawn
changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)
from tests.test_triage_rank_reaches_the_parts import served as ranked  # noqa: E402,F401
from tests.test_triage_ranks_the_section_rail import served_stale  # noqa: E402,F401
from tests.needs_build import needs_build

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
DESTINATIONS = ["Audit", "Analyses", "Record", "Client report"]

_SHOP_JS = """() => [...document.querySelectorAll('.catalogue-shop .crow-part th')]
  .map((th) => (th.querySelector('.crow-part-link')?.textContent || th.childNodes[0]?.textContent || '').trim())"""


def _page(base, route, ready, fn, width=1400):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": width, "height": 1000})
        try:
            pg.goto(f"{base}/{route}", wait_until="load", timeout=30_000)
            pg.wait_for_selector(ready, timeout=30_000)
            pg.wait_for_timeout(300)
            return fn(pg)
        finally:
            browser.close()


def _shop(pg):
    pg.wait_for_selector(".catalogue-shop .crow-part", timeout=30_000)
    return pg.evaluate(_SHOP_JS)


@needs_build
def test_four_destinations_and_no_ribbon(served):
    base, ids = served
    got = _page(base, f"#/sites/{ids['site']}?tab=findings", ".seq-step", lambda pg: pg.evaluate(
        "() => [...document.querySelectorAll('.seq-step a.seq-name')].map((a) => a.textContent.trim())"))
    assert got == DESTINATIONS, got


def test_the_primary_action_still_reads_the_sequence():
    src = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    header = src[src.index("export function StandingHeader"):src.index("export function SiteLanding")]
    # Item 168 added the count the action acts on, off the same index.
    # Item 179: the next step is chosen only once every source it reads has answered.
    assert "<PrimaryAction step={settled && seq.next >= 0 && seq.busyAt < 0 ? seq.steps[seq.next] : null}" in header
    assert "count={primaryCount(seq, data?.headline ?? null)}" in header
    # And what that count is out of, since audit F5: "880 not yet assessed"
    # beside a lane reading "Outstanding 1740" was one implicit subject over
    # two populations, so the button states this audit's total.
    assert "ofTotal={data?.headline?.assessed?.total ?? null} />" in header
    assert "<Sequence {...destinationsOf(seq)}" in header
    # The six steps are still built; four are drawn from them.
    # `name: "Triage"` was counted here too, until item 196 removed the step.
    assert src.count('name: "Precheck"') == 1


@needs_build
def test_audit_carries_precheck_counts_and_the_reaudit_panel(served):
    """The ranking block was third on this pane until item 196; the ranking is
    the audit's own now and reaches the reader as the order of the parts and
    of the catalogue rather than as a block to scroll to. Both aliases still
    resolve here, which is what keeps a stored `?tab=triage` link landing on a
    real pane rather than on the unknown-tab banner."""
    base, ids = served
    tops = _page(base, f"#/sites/{ids['site']}?tab=history", ".scan-matrix", lambda pg: pg.evaluate(
        """() => ['.pane-body .pre-panel', '.pane-body .scan-matrix']
             .map((s) => document.querySelector(s)?.getBoundingClientRect().top ?? null)"""))
    assert None not in tops, tops
    assert tops == sorted(tops), f"Audit is not precheck, then the chooser: {tops}"
    for alias in ("precheck", "triage"):
        name = _page(base, f"#/sites/{ids['site']}?tab={alias}", ".scan-matrix",
                     lambda pg: pg.inner_text("#pane-name"))
        assert name == "Audit", (alias, name)


@needs_build
def test_the_shop_sorts_by_rank_placed_first(ranked):
    """Brief v24 step BN: parts the ranking placed come first, in rank order.

    The expectation is read from the API rather than written here. It used to
    be a fixed five-part order taken from a staged triage report; since item
    196 the ranking is computed from what is open, so a constant would be
    asserting yesterday's data. Two things the product produces, compared
    against each other - and the clause still fails if the shop stops reading
    the rank, which is what it is for.
    """
    import httpx

    base, site_id, run_id = ranked
    lanes = httpx.get(f"{base}/api/runs/{run_id}/analyses", timeout=30).json()
    seen, want = set(), []
    for row in lanes["triage"]["ranked"]:
        part = row.get("category")
        if part and part not in seen:
            seen.add(part)
            want.append(part)
    labels = {p["key"]: p["label"] for p in lanes["parts"]}
    want = [labels.get(k, k) for k in want if k in labels]
    assert want, "the ranking placed no part, so there is no order to check"

    order = _page(base, f"#/sites/{site_id}?tab=findings",
                  ".catalogue-shop .crow-part", _shop)
    assert order[:len(want)] == want, (order, want)


@needs_build
def test_the_ranking_is_never_an_older_audits(served_stale):
    """What replaced the staleness clause, and why it is one line.

    A stored ranking could outlive the audit it described, so the shop did not
    reorder on it and Audit carried a note saying whose it was. The ranking is
    computed with the audit since item 196, so `stale` is False by
    construction - and this drives the two-audit fixture to say so on the
    wire, rather than trusting the constructor.
    """
    import httpx

    base, site_id, older, newer = served_stale
    lanes = httpx.get(f"{base}/api/runs/{newer}/analyses", timeout=30).json()
    assert lanes["triage"]["stale"] is False, lanes["triage"]
    assert lanes["triage"]["from_run"] == newer, lanes["triage"]


@needs_build
def test_record_holds_history_and_the_state_log(served):
    base, ids = served
    log = _page(base, f"#/sites/{ids['site']}?tab=all", ".state-filters", lambda pg: pg.evaluate(
        """() => ({ runs: document.querySelectorAll('.pane-body .runs-table').length,
                    views: [...document.querySelectorAll('.record-view a')].map((a) => a.textContent.trim()),
                    here: document.querySelector('.seq-step a[aria-current=step]')?.textContent.trim() })"""))
    assert log["runs"] == 0 and log["views"] == ["Findings", "Audits"] and log["here"] == "Record", log
    audits = _page(base, f"#/sites/{ids['site']}?tab=all&view=audits", ".runs-table", lambda pg: pg.evaluate(
        """() => ({ trend: document.querySelectorAll('.pane-body .st-root').length,
                    chooser: document.querySelectorAll('.pane-body .scan-matrix').length,
                    log: document.querySelectorAll('.pane-body .state-filters').length })"""))
    assert audits == {"trend": 1, "chooser": 0, "log": 0}, audits


@needs_build
def test_every_part_is_reachable_from_the_shop(served):
    """Brief v24 step BO's table: "reach a part with nothing open" lands on the
    shop. Every part header in it links to the part and carries its open
    count; the clean part is the case that matters, because a lane row only
    reaches a part with something open."""
    import httpx
    base, ids = served
    cats = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=60).json()["categories"]
    clean = next(c for c in cats if c["total"]["value"] == 0 and c["group"] != "workflow")

    def go(pg):
        pg.wait_for_selector(".catalogue-shop .crow-part-link", timeout=30_000)
        links = pg.evaluate("""() => [...document.querySelectorAll('.catalogue-shop .crow-part-link')]
          .map((a) => ({ label: a.textContent.trim(), href: a.getAttribute('href'),
                         open: a.parentElement.querySelector('.crow-part-open')?.textContent.trim() || '' }))""")
        target = next(l for l in links if l["label"] == clean["label"])
        pg.click(f".catalogue-shop .crow-part-link:text-is({clean['label']!r})")
        pg.wait_for_function(f"() => location.hash.includes('part={clean['key']}')", timeout=10_000)
        pg.wait_for_selector(".anat-pane h2.part-h2", timeout=15_000)
        return links, target, pg.inner_text(".anat-pane h2.part-h2")
    links, target, heading = _page(base, f"#/sites/{ids['site']}?tab=findings", ".catalogue-shop .crow-part", go)
    labels = {c["label"] for c in cats if c["group"] != "workflow"}
    assert {l["label"] for l in links} >= labels - {""}, (labels, links)
    assert target["open"].startswith("· 0"), target
    assert heading.strip().startswith(clean["label"]), heading


def test_no_sidebar_on_any_route(served):
    """Brief v24 step BO: the sidebar retires everywhere, in one commit. A
    rail that appears only inside a part is a navigation model that changes
    underfoot. Every route the accessibility sweep loads, and the source."""
    from playwright.sync_api import sync_playwright

    from tests.test_a11y_rendered import ROUTES

    base, ids = served
    assert not (SRC / "sidebar.tsx").exists(), "sidebar.tsx is still in the tree"
    for path in SRC.glob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        assert "site-sidebar" not in text and "anat-leaf" not in text, path.name
    seen = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        try:
            for name, route in ROUTES:
                try:
                    url = f"{base}/{route.format(**ids)}"
                except KeyError:
                    continue
                pg.goto(url, wait_until="load", timeout=30_000)
                pg.wait_for_timeout(700)
                seen[name] = pg.evaluate(
                    "() => document.querySelectorAll('.site-sidebar, .anat-tree, .anat-leaf, .site-layout').length")
        finally:
            browser.close()
    assert seen and not {k: v for k, v in seen.items() if v}, seen


@needs_build
def test_back_from_a_part_lands_on_the_landing_with_scope(served):
    """Back from a part returns to the landing with mode and scope intact,
    which BK guarantees through `?page=` in the hash."""
    import httpx
    from playwright.sync_api import sync_playwright

    base, ids = served
    view = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=60).json()
    page_url = next(p["url"] if isinstance(p, dict) else p for p in view["pages"])
    landing = f"#/sites/{ids['site']}?page={page_url}"

    def go(pg):
        pg.wait_for_selector(".cl-landing[data-mode=page] .cl-lane", timeout=30_000)
        start = pg.evaluate("() => location.hash")
        # Item 169: the parts left the lanes for the strip under them.
        link = pg.query_selector(".cl-landing .cl-parts a[href*='part=']")
        assert link, "nothing in the page's parts strip opens a part"
        link.click()
        pg.wait_for_function("() => location.hash.includes('part=')", timeout=15_000)
        pg.wait_for_selector(".anat-pane h2.part-h2", timeout=15_000)
        inside = pg.evaluate("() => location.hash")
        pg.go_back()
        pg.wait_for_function("() => !location.hash.includes('part=')", timeout=15_000)
        pg.wait_for_selector(".cl-landing", timeout=15_000)
        return start, inside, pg.evaluate(
            "() => ({ hash: location.hash, mode: document.querySelector('.cl-landing')?.dataset.mode })")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        try:
            pg.goto(f"{base}/{landing}", wait_until="load", timeout=30_000)
            start, inside, back = go(pg)
        finally:
            browser.close()
    assert "page=" in inside, f"opening the part dropped the page scope: {inside}"
    assert back["hash"] == start and back["mode"] == "page", (start, back)
