"""Item 178, commits 2 to 5: nothing that spends or removes is one press from
rest (UI audit patterns A and B).

- Every spend control is `SpendButton`: the price on the control in words, held
  with its reason in text until its data belongs to the selection, and a
  confirmation naming the site, the audit and the price before it fires.
- Every delete is `DangerButton`: the danger tone and a confirmation naming what
  goes. `window.confirm` is gone; no screen deletes on the press.
- The client report's hold is drawn by every surface that acts on the report -
  the landing's button, the strip's Deliver chapter and Generate - from one
  answer, so the landing's held button and a live Generate are never both true
  (08-3). The nav was a fourth, and is not: the operator's decision of
  2026-09-18, asserted here as the bar holding none of it.
- A destructive control sits a row-height from the save beside it.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.needs_build import needs_build

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _src(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def _all_tsx() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in SRC.glob("*.tsx")}


# ---- source guards ---------------------------------------------------------

#: Pills in the paid tone that are not themselves the spend: each opens or IS a
#: confirmation that states the price. Anything else in the paid tone must be a
#: `SpendButton`.
PAID_TONE_ALLOWED = {
    "confirm.tsx": 1,     # the confirming button inside the spend dialog
    "spend.tsx": 1,       # SpendButton itself
    "catalogue.tsx": 2,   # Run all, which opens the batch confirmation, and its commit
    "anatomy.tsx": 1,     # a part's "Run the N not run", which opens that confirmation
}


def test_every_paid_control_is_the_spend_control_or_opens_a_confirmation():
    counts = {name: len(re.findall(r'tone="action-paid"', text))
              for name, text in _all_tsx().items()}
    over = {n: c for n, c in counts.items() if c > PAID_TONE_ALLOWED.get(n, 0)}
    assert not over, (
        "a control in the paid tone that is not SpendButton - it spends on the press, "
        f"unpriced or unconfirmed: {over}")


def test_no_screen_confirms_with_the_browser_dialog():
    hits = [n for n, t in _all_tsx().items() if "window.confirm(" in t]
    assert not hits, f"window.confirm is not the product's confirmation: {hits}"


#: DELETE requests that remove nothing a person made: each puts a setting back
#: to the deployment's, or un-ticks a mark, and the same row re-sets it.
DELETE_NOT_DESTRUCTIVE = {
    ("admin.tsx", "/api/models/briefs/"): "an analysis default back to the tier's model",
    ("admin.tsx", '"/api/models/tiers"'): "tier models back to config; the chosen ones are a press away",
    ("fixloop.tsx", "/attempt"): "un-ticks a fix attempt, which the same checkbox ticks again",
}


def test_every_delete_request_is_behind_the_danger_confirmation():
    """An `api.del` fires from `DangerButton`'s `onConfirm`, or from a function
    only such a button calls."""
    loose: list[str] = []
    for name, text in _all_tsx().items():
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "api.del" not in line or line.strip().startswith(("//", "*")):
                continue
            if any(name == f and frag in line for (f, frag) in DELETE_NOT_DESTRUCTIVE):
                continue
            window = "\n".join(lines[max(0, i - 40): i + 1])
            if "onConfirm" in window:
                continue
            # A named handler: it is only ever handed to `onConfirm`.
            handlers = re.findall(r"const (\w+) = async", window)
            if handlers:
                h = handlers[-1]
                uses = re.findall(rf"(\w+)=\{{(?:\(\w*\) => )?{h}\b", text)
                if uses and set(uses) == {"onConfirm"}:
                    continue
            loose.append(f"{name}:{i + 1}: {line.strip()}")
    assert not loose, "a delete that does not ask first:\n" + "\n".join(loose)


def test_the_spend_and_danger_words_are_the_registrys():
    from clauditseo import glossary
    ids = {e["id"] for e in glossary.entries()} if hasattr(glossary, "entries") else {
        e["id"] for e in __import__("json").loads(glossary.PATH.read_text(encoding="utf-8"))["entries"]}
    for needed in ("spend-unpriced", "spend-checking", "danger-undone", "report-held", "state-loading"):
        assert needed in ids, needed
    confirm = _src("confirm.tsx")
    assert 'entry("spend-unpriced")' in confirm and 'entry("danger-undone")' in confirm
    # `tools.tsx` left this list with item 188. The registry words it was
    # read for - the spend and danger sentences - are `confirm.tsx`'s and
    # `spend.tsx`'s, which is where they are asserted from.
    code = [ln for name in ("spend.tsx", "confirm.tsx", "scanmatrix.tsx")
            for ln in _src(name).splitlines()
            if not ln.strip().startswith(("*", "/*", "//", "{/*"))]
    copies = [ln.strip() for ln in code if re.search(r'"(no estimate yet|checking the price|cannot be undone)"', ln)]
    assert not copies, f"an inline copy of a registered word: {copies}"


# ---- rendered ----------------------------------------------------------------

pytest.importorskip("playwright")


def _plant_open_high(conn, run_id):
    from tests.test_a_held_client_report_never_pays_for_its_plan import _plant_open_high as plant
    return plant(conn, run_id)


@pytest.fixture(scope="module")
def held_site():
    from tests.test_coverage import DIMS, _Hub, _run
    from tests.test_triage_ranks_the_section_rail import _serve

    server, thread, db, base = _serve("heldsurfaces")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Held Surfaces"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "heldsurfaces.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        site_id, fp = _plant_open_high(conn, run_id)
        conn.close()
        yield base, db, run_id, site_id, fp
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.integrity_threshold
@needs_build
def test_a_held_report_is_held_on_every_surface_that_acts_on_it(held_site):
    from playwright.sync_api import sync_playwright

    base, db, run_id, site_id, fp = held_site
    conn = connect(db)
    runs.set_state(conn, site_id, fp, "open")
    assert runs.client_report_hold(conn, site_id), "precondition: the fixture holds the report"
    conn.close()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="networkidle")
            pg.wait_for_selector(".bl-sentence[data-run]", timeout=30_000)
            pg.wait_for_selector(".seq-deliver .seq-chapter-state", timeout=30_000)
            landing = pg.evaluate("""() => ({
              held: [...document.querySelectorAll('.bl-buttons .bl-held')].length,
              live: [...document.querySelectorAll('.bl-buttons a.bl-secondary')]
                      .filter((a) => /client report/i.test(a.textContent)).length,
              deliver: document.querySelector('.seq-deliver .seq-chapter-state')?.textContent ?? '',
              inBar: document.querySelectorAll('.topbar .report-held, .nav-held').length,
            })""")
            assert landing["held"] == 1 and landing["live"] == 0, landing
            assert landing["deliver"].startswith("held for assessment"), landing
            # The bar is not one of the surfaces, by the operator's decision of
            # 2026-09-18: the hold is on what acts on the report, not on the
            # chrome that points at it. Said in four places at once the words
            # stopped carrying, and 187px of them in a row measured full gave
            # the page 83px of sideways scroll from 1120 to 1386px.
            assert landing["inBar"] == 0, (
                f"the client report's hold is back in the bar: {landing}")

            pg.goto(f"{base}/#/sites/{site_id}/reports", wait_until="networkidle")
            pg.wait_for_selector("#generate-held.report-held", timeout=30_000)
            gen = pg.evaluate("""() => {
              const b = [...document.querySelectorAll('.report-gen button')]
                .find((x) => /generate/i.test(x.textContent));
              return { disabled: b?.getAttribute('aria-disabled'), cls: b?.className ?? '' };
            }""")
            assert gen["disabled"] == "true", (
                f"the landing holds the client report and Generate is live: {gen}")
            before = httpx.get(f"{base}/api/sites/{site_id}/reports", timeout=30)
            # A held control is `aria-disabled`, which Playwright will not press
            # by default; the operator can, and the press must do nothing.
            pg.click(".report-gen button:has-text('Generate')", force=True)
            pg.wait_for_timeout(800)
            after = httpx.get(f"{base}/api/sites/{site_id}/reports", timeout=30)
            if before.status_code == 200:
                assert before.json() == after.json(), "a held Generate made a document"

            # Assessed: every surface lifts together.
            conn = connect(db)
            for row in conn.execute("SELECT DISTINCT fingerprint FROM findings WHERE run_id=?"
                                    " AND lower(severity) IN ('critical','high')", (run_id,)):
                runs.set_state(conn, site_id, row["fingerprint"], "accepted-risk")
            conn.close()
            # A reload: the same address again is not a new request for the hold.
            pg.reload(wait_until="networkidle")
            pg.wait_for_function("""() => {
              const b = [...document.querySelectorAll('.report-gen button')]
                .find((x) => /generate/i.test(x.textContent));
              return b && b.getAttribute('aria-disabled') !== 'true';
            }""", timeout=30_000)
            assert pg.locator("#generate-held").count() == 0
            assert pg.locator(".report-held").count() == 0
        finally:
            browser.close()


@needs_build
def test_a_spend_asks_first_and_escape_spends_nothing(held_site):
    """The Tools single-analysis run: the dialog names the site and the price,
    Escape closes it with focus back on the control, and nothing was posted."""
    from playwright.sync_api import sync_playwright

    base, db, run_id, site_id, fp = held_site
    posted: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        pg.on("request", lambda r: posted.append(r.url) if r.method == "POST" and "/expert/" in r.url else None)
        try:
            # The Analyses catalogue since item 188 retired Tools. Same
            # control and same dialog - `.spend-btn` is `spend.tsx`'s and the
            # confirm is `confirm.tsx`'s, both shared - on the screen that now
            # lists the paid analyses. No click to reveal: the catalogue lists
            # its rows, where Tools needed a tool opening first.
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings",
                    wait_until="networkidle")
            pg.wait_for_selector(".spend-btn", timeout=30_000)
            pg.wait_for_function(
                "() => [...document.querySelectorAll('.spend-btn')].some((b) => b.getAttribute('aria-disabled') !== 'true')",
                timeout=30_000)
            opener = pg.locator(".spend-btn:not([aria-disabled='true'])").first
            label = opener.inner_text()
            assert re.search(r"·\s*(~USD|no estimate yet)", label), label
            opener.click()
            dialog = pg.locator("[role=alertdialog].confirm-spend")
            dialog.wait_for(timeout=10_000)
            text = dialog.inner_text()
            assert "heldsurfaces.fixture" in text and "Price:" in text, text
            assert pg.evaluate("document.activeElement.textContent.trim()") == "Cancel"
            pg.keyboard.press("Escape")
            dialog.wait_for(state="detached", timeout=5_000)
            assert pg.evaluate("document.activeElement.classList.contains('spend-btn')"), (
                "closing the confirmation did not return focus to the control that opened it")
            pg.wait_for_timeout(500)
            assert not posted, f"cancelled, and it spent anyway: {posted}"
        finally:
            browser.close()


@needs_build
def test_a_remove_is_a_row_height_from_save_and_asks_first(held_site):
    """10-1: the Keys table stacked remove 0 px under save and removed on the
    press, in the free action's green."""
    from playwright.sync_api import sync_playwright

    base, *_ = held_site
    name = "CLAUDITSEO_OPENPAGERANK_KEY"
    assert httpx.put(f"{base}/api/keys/{name}", json={"value": "fixture-not-a-key-0000"},
                     timeout=30).status_code == 200
    deleted: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width in (1440, 1100, 390):
                pg = browser.new_page(viewport={"width": width, "height": 1000})
                pg.on("request", lambda r: deleted.append(r.url) if r.method == "DELETE" else None)
                pg.goto(f"{base}/#/admin?tab=keys", wait_until="networkidle")
                pg.wait_for_selector(".act-gap .danger-btn", timeout=30_000)
                gap = pg.evaluate("""() => {
                  const out = [];
                  for (const cell of document.querySelectorAll('.act-gap')) {
                    const s = cell.querySelector('.save-btn'), d = cell.querySelector('.danger-btn');
                    if (!s || !d) continue;
                    const a = s.getBoundingClientRect(), b = d.getBoundingClientRect();
                    const dx = Math.max(b.left - a.right, a.left - b.right);
                    const dy = Math.max(b.top - a.bottom, a.top - b.bottom);
                    out.push({ dx, dy, tone: getComputedStyle(d).color,
                               danger: d.classList.contains('tone-action-danger') });
                  }
                  return out;
                }""")
                assert gap, "no save beside a remove to measure"
                for g in gap:
                    assert g["danger"], g
                    assert max(g["dx"], g["dy"]) >= 24, f"{width}px: remove is not a row-height from save: {g}"
                pg.click(".act-gap .danger-btn")
                pg.locator("[role=alertdialog].confirm-danger").wait_for(timeout=10_000)
                pg.click("[role=alertdialog] button:has-text('Cancel')")
                pg.wait_for_timeout(300)
                assert not deleted, f"{width}px: cancelled, and the key was removed: {deleted}"
                pg.close()
            browser.close()
    finally:
        httpx.delete(f"{base}/api/keys/{name}", timeout=30)
