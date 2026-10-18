"""Step 2 of the suggested order says an audit is running, and does not offer
to start another while it is.

`sequenceSteps` knew two states for the audit step: `last ran <date>` and
`never run`. Mid-first-audit the strip therefore read "2. Audit — never run",
marked it as the step to do next, and its action opened the launcher — a
second concurrent audit one click from the sentence saying none had run.
`_plans/site-screen-ia-plan-v2.md` §5b names it, and §7 step 2 is the fix: a
running state, the launch action withheld while it is true.

**Why a browser.** The state is made of two payloads: the anatomy payload,
which cannot see a run that has not finished, and the site's run list, which
can. What is asserted is what the strip paints once both have arrived and been
put together, and then what it paints after the run completes — which is the
polling container noticing the transition and re-reading the position (the
hoist's own promise, tested here because this is the first state that needs
it).

**The fixture puts the running audit at the front of the order.** `next` is
the first step not done, and the precheck is step 1, so a site with no
precheck would carry the badge on step 1 whatever step 2 said. A precheck is
computed in-process against a local fixture site and stored the way the route
stores it, so step 1 is done and the step the work is at is the one running.
That is what makes the "running now" badge and the headline reachable; the
docstring says so rather than leaving it to be inferred from the setup.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id
from tests.test_a11y_rendered import DIST

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: The step this file is about, as the strip names it.
STEP = "Audit"

#: The audit-step card and the headline above it, read at one instant.
_READ_JS = """(name) => {
  const li = [...document.querySelectorAll('.seq-step')].find(
    (el) => (el.querySelector('.seq-name')?.textContent || '').trim() === name);
  if (!li) return null;
  return {
    // Audit folds Precheck and Triage in (brief v24 step BN): its panel line
    // is "Precheck: ... · Audit: ... · Triage: ...", and this reads the
    // audit step's own part of it.
    state: (((li.querySelector('.seq-state')?.textContent || '').split(' · ')
      .find((s) => s.startsWith('Audit: ')) || '').replace(/^Audit: /, '')).trim(),
    precheck: (((li.querySelector('.seq-state')?.textContent || '').split(' · ')
      .find((s) => s.startsWith('Precheck: ')) || '')).trim(),
    badge: (li.querySelector('.seq-badge')?.textContent || '').trim(),
    tick: !!li.querySelector('.seq-tick'),
    launch: !!li.querySelector('.seq-action a[href$="?tab=history"]'),
    run: li.querySelector('.seq-open-run')?.getAttribute('href') || null,
    nextName: (document.querySelector('.seq-next .seq-name')?.textContent || '').trim(),
  };
}"""

ROBOTS = "User-agent: *\nAllow: /\n"
HOME = ("<html><head><title>Running fixture</title></head><body>"
        "<nav><a href='/about'>About</a></nav></body></html>")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding a stored precheck and one audit still running."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.precheck import run_precheck
    from tests.conftest import FixtureSite
    from tests.test_coverage import DIMS

    tmp = Path(tempfile.mkdtemp(prefix="inflight"))
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
                            json={"name": "Inflight Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "inflight.fixture"}, timeout=30).json()

        # The precheck, stored the way `run_site_precheck` stores it, so step
        # 1 is done and the badge can reach step 2.
        fixture = FixtureSite({
            "/robots.txt": (200, {"Content-Type": "text/plain"}, ROBOTS),
            "/": (200, {}, HOME),
            "/about": (200, {}, HOME),
        }).start()
        try:
            result = run_precheck(fixture.base_url + "/", delay_s=0)
        finally:
            fixture.stop()
        conn = connect(db)
        with conn:
            conn.execute(
                "INSERT INTO prechecks (id, site_id, checked_at, entry_url,"
                " took_ms, sitemap_state, payload_json) VALUES (?,?,?,?,?,?,?)",
                (create_id(), site["id"], result.checked_at, result.entry_url,
                 result.took_ms, result.sitemap_state,
                 json.dumps(result.to_dict())))
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        conn.close()
        yield base, site["id"], run_id, db
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_a_running_audit_is_said_and_not_offered_again(served):
    import httpx
    from playwright.sync_api import sync_playwright

    base, site_id, run_id, db = served

    pre = httpx.get(f"{base}/api/sites/{site_id}/precheck", timeout=30)
    assert pre.status_code == 200 and pre.json(), (
        "precondition: no stored precheck, so step 1 is not done and the "
        "badge cannot reach step 2 whatever it says")
    live = [r for r in httpx.get(f"{base}/api/sites/{site_id}", timeout=30)
            .json()["runs"] if r["status"] in ("pending", "running")]
    assert [r["id"] for r in live] == [run_id], (
        f"precondition: the run list does not hold the one running audit: {live}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".seq-step", timeout=30_000)
            # Both payloads: the strip paints from the anatomy reply and the
            # run list arrives separately, so wait for the word rather than
            # for the card.
            pg.wait_for_function(
                f"({_READ_JS})({STEP!r})?.state.startsWith('running')",
                timeout=15_000)
            # And the precheck's own fetch, which is a third request: read
            # before it answers and step 1 is still the step the work is at.
            pg.wait_for_function(
                f"({_READ_JS})({STEP!r})?.precheck.startsWith('Precheck: counted')",
                timeout=15_000)
            card = pg.evaluate(_READ_JS, STEP)

            assert card["state"].startswith("running"), card
            assert not card["launch"], (
                "an audit is running and the step still offers to start one: "
                f"{card}")
            assert card["run"] == f"#/runs/{run_id}", (
                f"the running step does not open the run it names: {card}")
            assert card["badge"] == "running now", card
            assert card["nextName"] == STEP, (
                "the step the work is at is not the running one — the "
                f"precheck fixture did not do its job: {card}")

            # Now it finishes. The polling container sees the transition and
            # re-reads the position; nothing on the page is reloaded.
            from tests.test_coverage import _Hub, _run
            conn = connect(db)
            runs.complete_run(conn, run_id, _run(_Hub()))
            conn.close()

            pg.wait_for_function(
                f"({_READ_JS})({STEP!r})?.state.startsWith('last ran')",
                timeout=20_000)
            after = pg.evaluate(_READ_JS, STEP)
            assert after["launch"] and after["run"] is None, (
                f"the audit finished and the launcher is not back: {after}")
            # It used to say "next" here: Triage folded into Audit (brief v24
            # step BN) and was the first idle step, so the pill that stopped
            # running took the badge. Item 196 removed that step, and nothing
            # else is idle in this state - Analyses is partial, which the rule
            # calls ongoing rather than blocking, and Record is never offered
            # as next (item 170).
            #
            # So the strip points at nothing after an audit now. Asserted as
            # the fact it is, rather than dropped: if a later change makes the
            # sequence point at Analyses instead, this clause should be the
            # thing that notices, because that is a decision about what the
            # operator is told to do next and it has not been taken.
            assert after["badge"] != "next", (
                "the audit pill says 'next' after finishing, which is the "
                f"step it just completed: {after}")
            assert after["nextName"] in (None, "", "Analyses"), (
                "the sequence points somewhere new after an audit; if that is "
                f"intended it is a product decision, not a test update: {after}")
        finally:
            browser.close()


def test_a_step_running_again_says_running_and_not_done(served):
    """The operator, 2026-09-25, on twenty22: "The page displays DONE and
    running now". An audit had completed, so the step drew its `done` tick,
    and a second was running, so it drew the badge beside it: one pill, two
    states, against its own one-word rule. While it runs, it says so alone."""
    import httpx
    from playwright.sync_api import sync_playwright
    from tests.test_coverage import DIMS, _Hub, _run

    base, site_id, run_id, db = served
    conn = connect(db)
    # A completed audit to be "done" with, whichever clause ran first.
    if conn.execute("SELECT status FROM audit_runs WHERE id=?", (run_id,)).fetchone()[0] != "complete":
        runs.complete_run(conn, run_id, _run(_Hub()))
    again = runs.create_run(conn, site_id, DIMS, "T2")
    conn.close()
    live = [r["id"] for r in httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["runs"]
            if r["status"] in ("pending", "running")]
    assert live == [again], live
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load", timeout=30_000)
            pg.wait_for_function(f"({_READ_JS})({STEP!r})?.badge === 'running now'",
                                 timeout=15_000)
            # Settled, as the clause above waits: the strip paints from the
            # anatomy reply, the run list and the precheck, and "done" is
            # decided only once the first has answered.
            pg.wait_for_function(
                f"({_READ_JS})({STEP!r})?.precheck.startsWith('Precheck: counted')",
                timeout=15_000)
            pg.wait_for_function(
                "() => document.querySelector('.site-main')?.dataset.anatomy === 'loaded'",
                timeout=15_000)
            pg.wait_for_timeout(500)
            card = pg.evaluate(_READ_JS, STEP)
        finally:
            browser.close()
    conn = connect(db)
    runs.complete_run(conn, again, _run(_Hub()))
    conn.close()
    assert card["badge"] == "running now" and not card["tick"], card

