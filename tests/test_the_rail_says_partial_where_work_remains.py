"""The strip's cards are done, partial or next, one next at a time, and the
standing counts stand in the scope bar.

Brief step 2 (`_plans/site-screen-reorg-brief-2026-09-03.md`, WF-01, CQ-03,
UI-02). The strip ticked a step on "anything at all": step 4 wore a tick
beside "23 not run", and step 6 wore one while step 5 said "do this next". A
step is now done, partial (started and not finished) or idle; the next step
is the first idle one, so a partial step is ongoing rather than blocking;
each card carries a state and no sentence restating its pane's subtitle; and
the standing counts sit in the scope bar beside the pick they do not follow,
rather than in a pane of their own.

**Why a browser.** The words are painted by class and by text from a computed
list, and the position of the counts relative to the picker is a matter of
what the document holds where.

**Three fixtures.** `test_the_analyses_pane_reads_one_audit.py`'s site holds
two audits, the older with one brief: the newer, which the screen reads, has
step 4 idle and next. `one_brief` is a site whose one audit holds an unread
brief: step 4 is partial and untick. (The partial clause read the older audit
through `run=` in the address; item 239 step 5 made the address name no
audit, so the brief sits on the audit the screen reads.) The rendered
sweep's fixture holds a client deliverable, so step 6 has a count; whether it
is done or partial is decided by step 5, and the clause asserts that
agreement rather than a fixed word.
"""

from __future__ import annotations

import pytest

from tests.test_a11y_rendered import DIST
from tests.test_a11y_rendered import served as sweep_served  # noqa: F401  (reused fixture)
from tests.test_the_analyses_pane_reads_one_audit import served  # noqa: F401  (reused fixture)
from tests.parts import ANATOMY_READY
from tests.test_the_analyses_pane_reads_one_audit import TOOL

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_JS = """() => {
  const card = (li) => ({
    name: (li.querySelector('.seq-name')?.textContent || '').trim(),
    done: li.classList.contains('seq-done'),
    tick: !!li.querySelector('.seq-tick'),
    partial: li.classList.contains('seq-partial'),
    word: (li.querySelector('.seq-word')?.textContent || '').trim(),
    next: li.classList.contains('seq-next'),
    state: (li.querySelector('.seq-state')?.textContent || '').trim(),
    notes: li.querySelectorAll('.seq-note').length,
  });
  const bar = document.querySelector('.run-scope');
  return {
    cards: [...document.querySelectorAll('.seq-step')].map(card),
    figuresInBar: bar ? bar.querySelectorAll('.bl-sentence b').length : 0,
    stampInBar: !!bar?.querySelector('.cur-when'),
    standsPanes: [...document.querySelectorAll('.cur-head .head-label')]
      .map((h) => h.textContent.trim()),
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


def _read(browser, base, site_id):
    pg = browser.new_page()
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
                timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        # The shop is Analyses' body with no part open (brief v24 step BO).
        pg.wait_for_selector(".catalogue-shop .catalogue-table", timeout=30_000)
        # The Analyses card reads the lanes, which arrive after the tree.
        pg.wait_for_function(
            "() => { const li = [...document.querySelectorAll('.seq-step')]"
            ".find((el) => (el.querySelector('.seq-name')?.textContent || '').trim() === 'Analyses');"
            " return li && /to read|available|analysis not run/"
            ".test(li.querySelector('.seq-state')?.textContent || ''); }",
            timeout=30_000)
        return pg.evaluate(_JS)
    finally:
        pg.close()


def _card(got, name):
    hit = [c for c in got["cards"] if c["name"] == name]
    assert len(hit) == 1, (name, got["cards"])
    return hit[0]


@pytest.fixture(scope="module")
def one_brief():
    """One completed audit holding one brief nobody has opened."""
    import httpx

    from clauditseo.db.connection import connect
    from clauditseo.persistence import runs
    from tests.test_coverage import DIMS, _Hub, _run
    from tests.test_triage_ranks_the_section_rail import _serve

    server, thread, db, base = _serve("onebrief")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Brief Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "onebrief.fixture"}, timeout=30).json()
        conn = connect(db)
        run = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run, _run(_Hub()))
        runs.store_expert_report(conn, run, TOOL, {
            "model": "test-model", "report": "# Hygiene\n\nOne brief.", "findings": []})
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_a_step_with_briefs_still_unrun_is_partial_not_done(browser, one_brief):
    base, site_id = one_brief
    got = _read(browser, base, site_id)
    analyses = _card(got, "Analyses")
    # The free half leads since brief v17 step AV5; what this clause is
    # about is that a brief has landed and nobody has opened it, which is
    # still said and is still what makes the step partial.
    assert "1 to read" in analyses["state"], analyses
    assert analyses["partial"] and analyses["word"] == "partial", analyses
    assert not analyses["done"] and not analyses["tick"], (
        f"step 4 is ticked with briefs still unrun: {analyses}")
    assert not analyses["next"], (
        f"a partial step is ongoing, not the thing to do next: {analyses}")


def test_a_step_nothing_has_begun_on_is_idle_and_the_first_such_is_next(browser, served):
    base, site_id, _older, newer = served
    got = _read(browser, base, site_id)
    analyses = _card(got, "Analyses")
    # Nothing begun: no brief to read, and the line says so by not
    # saying otherwise (brief v17 step AV5 leads with the free count).
    assert "to read" not in analyses["state"], analyses
    assert analyses["state"].endswith(("available", "analysis not run")), analyses
    assert not analyses["partial"] and analyses["word"] == "", analyses
    assert not analyses["done"], analyses
    # Precheck has not run on this site, so its step is the first idle one,
    # and Precheck folds into Audit since brief v24 step BN.
    nexts = [c["name"] for c in got["cards"] if c["next"]]
    assert nexts == ["Audit"], nexts


@pytest.mark.parametrize("which", ["served", "one_brief"])
def test_there_is_one_next_step_or_none_never_two(browser, request, which):
    # Both shapes of step 4, idle and partial (item 239 step 5: two sites,
    # where this read one site's two audits through the address).
    base, site_id = request.getfixturevalue(which)[:2]
    got = _read(browser, base, site_id)
    nexts = [c["name"] for c in got["cards"] if c["next"]]
    assert len(nexts) <= 1, nexts
    # And the next destination is never one that is done, and says one word:
    # a destination folding a begun step and the next (brief v24 step BN)
    # can be partial underneath, and says "next" only.
    for c in got["cards"]:
        if c["next"]:
            assert not c["done"], c
            assert c.get("word", "") in ("", "next"), c


def test_no_card_restates_its_panes_subtitle(browser, served):
    base, site_id, _older, newer = served
    got = _read(browser, base, site_id)
    assert len(got["cards"]) == 4   # brief v24 step BN: four destinations
    assert all(c["notes"] == 0 for c in got["cards"]), got["cards"]
    assert all(c["state"] for c in got["cards"]), got["cards"]


def test_the_standing_counts_stand_in_the_scope_bar_and_not_in_a_pane(browser, served):
    base, site_id, _older, newer = served
    got = _read(browser, base, site_id)
    # The bar states the position in its sentence; the lanes and the stamp
    # heading them are the landing's since brief v24 step BM.
    assert got["figuresInBar"] > 0, got
    assert not got["stampInBar"], got
    # No standing pane at all since brief v2 step A: the counts are the
    # bar's and the rail is the rest of the frame.
    assert got["standsPanes"] == [], got["standsPanes"]


def test_the_report_step_agrees_with_the_record_step(browser, sweep_served):
    """Reports generated while step 5 still holds work are partial, never
    done; once the record is done, the same reports make the step done."""
    base, ids = sweep_served
    got = _read(browser, base, ids["site"])
    record, report = _card(got, "Record"), _card(got, "Client report")
    assert "generated" in report["state"], (
        f"precondition: the sweep fixture holds no client report: {report}")
    if record["done"]:
        assert report["done"] and not report["partial"], (record, report)
        assert "before step 5" not in report["state"], report
    else:
        assert report["partial"] and not report["done"] and not report["tick"], (
            f"reports generated before step 5 was done are ticked: {record} {report}")
        assert report["state"].endswith("before step 5"), report
