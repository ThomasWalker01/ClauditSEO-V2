"""Fixtures for the rendered tests: a real server, two seeded sites, a browser.

**The name is historical.** This file guarded triage's rank on the section
rail and the pane that sold the ranking; item 196 retired both, and its three
clauses went with them. What 28 other test files import from it - `_serve`,
`served`, `served_stale` and `browser` - is all that is left, and all that
ever mattered to them.

It is not renamed because 29 import statements would have to move with it, and
a mistake in any of them fails at COLLECTION, where one bad name takes the
whole suite down rather than one file. Deleting this file outright did exactly
that: 29 errors in four seconds. The cost of the misnomer is a reader's
double-take; the cost of the rename is paid at the worst place to pay it.

`served_stale` seeds two audits with a ranking stored against the older one.
Nothing reads the staleness any more - the ranking is computed with the audit
since item 196 - but the fixture is a site with two audits, which several
tests want for reasons of their own.
table and two controls, the one that spends marked and unpressed.

Brief v4 Item 3c (`_plans/site-screen-brief-v4-2026-09-03.md`) gave triage
its pane back - the rank stays on the sidebar (brief v4 Item 3a), and the
ranking itself, its reader and its re-run stand on `?tab=triage`. The
history below is the rail's, kept for the fixtures.

Brief step 3 (`_plans/site-screen-reorg-brief-2026-09-03.md`, WF-03, UX-04).
The Triage pane's only consumers were the section rail and the catalogue
above it (WF-03), and its copy promised tools beside each row (UX-04). The
rank triage gave each part is now a number beside the part's name; the
control that makes the ranking stands at the head of the list, with the
spend mark it always carried; the ranked list opens beside the rail on
request; and `?tab=triage` lands on the Analyses pane, where the rail is.

This replaces `test_triage_has_a_pane_of_its_own.py` (2026-09-02), whose
fixtures it keeps: one site with an audit and no ranking, and one with two
audits and a ranking stored on the older - so the rail can be read in both
of its states, and the older ranking's report is still read from the run it
was made on rather than from this audit (the 2026-09-02 defect).

**What this does not drive.** Running triage spends model tokens and needs
a provider, so the control is asserted present and unpressed. The report
opened is the stored one, which is free.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST
from tests.parts import ANATOMY_READY

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_JS = """() => {
  // Triage folds into the Audit destination since brief v24 step BN.
  const step = [...document.querySelectorAll('.seq-step')].find(
    (el) => (el.querySelector('.seq-name')?.textContent || '').trim() === 'Audit');
  return {
    name: (document.querySelector('.pane-name')?.textContent || '').trim(),
    current: (document.querySelector('a.seq-name[aria-current=step]')?.textContent || '').trim(),
    hash: window.location.hash,
    // The Triage pane's head: one start control and its note (brief v4 3c).
    heads: document.querySelectorAll('.pane-body .tri-pane-head').length,
    starts: document.querySelectorAll('.pane-body .tri-start').length,
    start: (document.querySelector('.tri-pane-head .tri-start button')?.textContent || '').trim(),
    startMarked: !!document.querySelector('.tri-pane-head .tri-start button .spend-mark'),
    note: (document.querySelector('.anat-rail-note')?.textContent || '').trim(),
    toggle: (document.querySelector('.tri-pane-head .tri-read')?.textContent || '').trim(),
    // The rank column, part by part.
    // The rank digit stands on the shop's part header since brief v24 step BO.
    ranks: [...document.querySelectorAll('.catalogue-shop .crow-part')].map((li) => ({
      part: (li.querySelector('.crow-part-link')?.textContent || '').trim(),
      rank: (li.querySelector('.anat-rank')?.textContent || '').trim(),
    })),
    // The lane note that names triage - the lanes carry notes of their own
    // under the same class.
    pointer: (() => {
      const p = [...document.querySelectorAll('.pane-body .lane-note')]
        .find((el) => /triage/i.test(el.textContent || ''));
      return { text: (p?.textContent || '').trim(), links: p ? p.querySelectorAll('a').length : -1 };
    })(),
    step: { href: step?.querySelector('a.seq-name')?.getAttribute('href') || null,
            // The triage step's own action, among the folded steps' actions.
            link: [...(step?.querySelectorAll('.seq-action a') || [])].map((a) => a.getAttribute('href'))
              .find((h) => h && h.endsWith('?tab=triage')) || null,
            buttons: step ? step.querySelectorAll('button').length : -1,
            state: (step?.querySelector('.seq-state')?.textContent || '').trim(),
            done: !!step?.classList.contains('seq-done'),
            partial: !!step?.classList.contains('seq-partial') },
    panels: document.querySelectorAll('.pane-body .tri-panel').length,
    notes: document.querySelectorAll('.pane-body .tri-note').length,
    stale: document.querySelectorAll('.pane-body .tri-stale').length,
    buys: [...document.querySelectorAll('.pane-body .tri-buy')].map((b) => ({
      tool: (b.querySelector('button')?.textContent || '').trim(),
      cost: (b.querySelector('.arow-cost')?.textContent || '').trim(),
      marked: !!b.querySelector('.spend-mark'),
    })),
    report: document.querySelectorAll('.pane-body .sec-report').length,
    errors: document.querySelectorAll('.pane-body p.error').length,
  };
}"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(prefix: str):
    import tempfile

    import uvicorn

    from clauditseo.api.app import create_app

    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    db = tmp / "clauditseo.db"
    app = create_app(db_path=db)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")
    return server, thread, db, f"http://127.0.0.1:{port}"


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit and no ranking."""
    import httpx

    from tests.test_coverage import DIMS, _Hub, _run

    server, thread, db, base = _serve("triagerail")
    try:
        client = httpx.post(f"{base}/api/clients",
                            json={"name": "Triage Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "triage.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def served_stale():
    """Two audits, and a ranking stored on the OLDER one - so the ranking the
    lanes carry for the newer audit is stale."""
    import httpx

    from tests.test_coverage import DIMS, _Hub, _run

    server, thread, db, base = _serve("triagestale")
    try:
        client = httpx.post(f"{base}/api/clients",
                            json={"name": "Stale Triage Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "staletriage.fixture"}, timeout=30).json()
        conn = connect(db)
        result = _run(_Hub())
        older = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, older, result)
        runs.store_expert_report(
            conn, older, "triage",
            {"model": "test-model", "report": "# Triage\n\nRanked once.",
             "findings": [{"code": "img-alt-missing", "severity": "high",
                           "summary": "Images lack alt text."}]})
        time.sleep(1.1)
        newer = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, newer, result)
        conn.close()
        yield base, site["id"], older, newer
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()
