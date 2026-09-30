"""Step 5 of the suggested order is done when the fix loop is settled, not
when the site is clean.

`sequenceSteps` in `dashboard/src/anatomy.tsx` marked *Fix and verify* done on
`outstanding === 0 && audited`, and `next` is the first step not done. On the
operator's own install `outstanding` is 1085, so step 5 was never done, `next`
never moved past it, and *Client report* could not be recommended for the
product's entire life — the strip's last step was decoration. The site-screen
plan (`_plans/site-screen-ia-plan-v2.md` §4c) records the decision: step 5's
`done` means "nothing awaiting verification", which is the step's own work
finished, and `awaiting_a_look` is exactly that count.

**Why a browser rather than the source.** `done` is a boolean on a list the
strip renders from, and the rule the finding is about is what the strip
*paints*: a tick on the step, and no "do this next" badge on it, while the
standing position above still says how many are outstanding. A regex over the
TypeScript would be satisfied by a comment, and this file's own docstring
quotes the old expression.

**What this fixture can and cannot show.** It holds one audit with open
findings and no marks — `outstanding > 0`, `awaiting_a_look == 0`, asserted as
a precondition off the payload the strip reads. That is enough to show step 5
ticked with findings outstanding, which is the whole of the change. It is NOT
enough to show the badge landing on step 6: `next` is the first step not done
and the precheck, triage and analyses steps are not done on this fixture, so
the badge sits on step 1 here whatever step 5 does. The test says which half
it drives rather than implying both — the guard-population invariant.

The second test is the other direction: one mark, set through the route the
tick calls, and the tick comes off — because a settled loop is the claim, and
a claim that cannot be falsified by the thing it is about is not a claim.
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

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: The step this file is about, as the strip names it. Copied from
#: `sequenceSteps` rather than matched loosely, so a rename fails here
#: instead of matching a different step.
STEP = "Record"

#: The card for `STEP`, read off the rendered strip: whether it carries the
#: done tick, whether the next-badge sits on it, and its state line. One
#: evaluate, because the three are one card's state at one instant.
_CARD_JS = """(name) => {
  const li = [...document.querySelectorAll('.seq-step')].find(
    (el) => (el.querySelector('.seq-name')?.textContent || '').trim() === name);
  if (!li) return null;
  return {
    done: li.classList.contains('seq-done'),
    tick: !!li.querySelector('.seq-tick'),
    next: !!li.querySelector('.seq-badge'),
    state: (li.querySelector('.seq-state')?.textContent || '').trim(),
  };
}"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit with open findings and no marks.

    Its own server, for the reason `test_a_fix_attempt_mark_can_be_withdrawn.py`
    gives about its own: the second test here sets a mark, and a fixture other
    files assert on for its counts would be a fixture this one mutates.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="fixstep"))
    db = tmp / "clauditseo.db"
    app = create_app(db_path=db)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")

    base = f"http://127.0.0.1:{port}"
    try:
        client = httpx.post(f"{base}/api/clients",
                            json={"name": "Step Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "step.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _current(base: str, site_id: str) -> dict:
    """The standing position off the payload the strip reads."""
    import httpx

    body = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    return body["current"]


def _card(pg, base: str, site_id: str) -> dict:
    pg.goto(f"{base}/#/sites/{site_id}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".seq-step", timeout=30_000)
    # The strip renders before the position arrives (plan §5c) and says
    # "loading…" until it does; the card this reads is the settled one.
    pg.wait_for_function(
        f"(() => {{ const c = ({_CARD_JS})({STEP!r}); "
        "return c && c.state !== 'loading…'; })()", timeout=30_000)
    card = pg.evaluate(_CARD_JS, STEP)
    assert card is not None, (
        f"the strip rendered no step named {STEP!r}; the steps it did render "
        "are what this file is about, so it cannot assert on any of them")
    return card


def test_the_fix_step_is_ticked_with_findings_outstanding_and_nothing_marked(
        served):
    """The change itself: outstanding findings, no marks, step 5 done."""
    from playwright.sync_api import sync_playwright

    base, site_id = served
    cur = _current(base, site_id)
    assert cur["last_audit"], "precondition: the fixture holds no audit"
    assert cur["outstanding"] > 0, (
        "precondition: nothing is outstanding, so a tick here would be the "
        "old rule and the new one agreeing")
    assert cur["awaiting_a_look"] == 0, (
        "precondition: the fixture already holds a mark")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            card = _card(pg, base, site_id)
        finally:
            browser.close()

    assert card["done"] and card["tick"], (
        f"{STEP!r} is not ticked with {cur['outstanding']} outstanding and "
        f"nothing awaiting a look: {card}. That is the old rule — done means "
        "clean — under which `next` can never pass this step.")
    assert not card["next"], (
        f"the do-this-next badge sits on {STEP!r} while nothing awaits a "
        f"look: {card}")
    # The tick beside a count is honest only because the line says both
    # facts: how many are outstanding, and that none of them is waiting.
    assert card["state"].startswith(f"{cur['outstanding']} outstanding"), card
    assert "none awaiting a look" in card["state"], card


def test_one_mark_takes_the_tick_off(served):
    """The other direction, through the route the tick calls."""
    import httpx
    from playwright.sync_api import sync_playwright

    base, site_id = served
    states = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["states"]
    open_fps = [s["fingerprint"] for s in states if s["state"] == "open"]
    assert open_fps, "precondition: no open finding to mark"

    r = httpx.post(f"{base}/api/sites/{site_id}/states/{open_fps[0]}/attempt",
                   json={"note": ""}, timeout=30)
    assert r.status_code == 200, r.text
    cur = _current(base, site_id)
    assert cur["awaiting_a_look"] == 1, cur

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            card = _card(pg, base, site_id)
        finally:
            browser.close()

    assert not card["done"] and not card["tick"], (
        f"one finding awaits a look and {STEP!r} still carries the done "
        f"tick: {card}")
    assert card["state"] == "1 awaiting a look", card
