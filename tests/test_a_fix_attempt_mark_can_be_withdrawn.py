"""WF-84. A mark the operator set must be one the operator can unset.

`POST /api/sites/{id}/states/{fingerprint}/attempt` records that a fix was
attempted. Nothing withdrew one. `mark(f, on)` in `dashboard/src/fixloop.tsx`
posted inside `if (on)` and the off branch mutated a browser `Set`; the
`clear these marks` button called `onClear`, wired at `anatomy.tsx` and
`views.tsx` to the same local state; and `seed()` unions the server's
`attempted_at` back into the tick set on every load, so a mark the operator
had just cleared reappeared on the next render. The tick was write-once and
the control beside it said otherwise.

**This is the affordance invariant, not a convenience.** The button names an
action — `clear these marks` — and the product could not perform it. The
consequence is not cosmetic: `attempted_at` drives the lifecycle the product
is sold on. The "awaiting a look" count keys on
`attempted_at IS NOT NULL AND state IN ('open','regressed')`, and the
deliverable prints `_(fix attempted)_` beside the finding, so a mis-tick the
operator noticed and cleared still reached a client's document.

**Why this file rather than a clause in
`tests/test_every_state_the_operator_owns_is_settable.py`.** That file is the
guard for exactly this rule — "a state the operator owns must be reachable
through the route the operator's button calls" — and it could not see this.
Its population is derived, correctly, from `runs.MODEL_BLIND_STATES`, and the
fix-attempt mark is not a state at all: it is the `attempted_at` column beside
the state. So the guard derived a population from the tree and the thing it
was meant to protect was outside it — the promoted guard's-population
invariant, in the shape where the derivation is right and the registry is the
wrong registry. Widening `MODEL_BLIND_STATES` to hold a non-state would have
been the wrong repair; a second registry, read the same way, is the right one.

`OPERATOR_OWNED_MARKS` below is that registry, and the population clause is
read off the app's own route table rather than off a literal list, so a third
operator-owned mark added to the record screen is in scope here without a line
changing.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from tests.needs_build import needs_build

#: Marks the operator sets on a finding through a route of their own, as
#: opposed to `runs.ALL_STATES`, which the record screen's state verbs write
#: through `POST /states/{fingerprint}`. One entry today. The population in
#: `test_every_operator_owned_mark_has_a_route_that_withdraws_it` is derived
#: from the app's routes rather than from this tuple; the tuple says which of
#: those routes is a *mark* and therefore owes an inverse.
OPERATOR_OWNED_MARKS = ("attempt",)


@pytest.fixture
def marked(tmp_path):
    """One site with a completed run and one finding marked fix-attempted.

    The mark is made through the route the operator's button calls, not by a
    hand-written `finding_states` row, so what this file withdraws is what the
    product actually stores.
    """
    from tests.test_coverage import DIMS, _Hub, _run

    db = tmp_path / "attempt.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Attempt Co")
    site_id = repo.create_site(conn, client, "attempt.fixture")
    run_id = runs.create_run(conn, site_id, DIMS, "T2")
    runs.complete_run(conn, run_id, _run(_Hub()))
    states = runs.site_states(conn, site_id)
    conn.close()

    assert states, "precondition: the run raised no findings to mark"
    api = TestClient(create_app(db_path=db))

    def row_of(fingerprint: str) -> dict:
        c = connect(db)
        try:
            for s in runs.site_states(c, site_id):
                if s["fingerprint"] == fingerprint:
                    return s
        finally:
            c.close()
        raise AssertionError(f"no stored row for {fingerprint!r}")

    fingerprint = states[0]["fingerprint"]
    api.post(f"/api/sites/{site_id}/states/{fingerprint}/attempt",
             json={"note": "raised the H1"}).raise_for_status()
    seeded = row_of(fingerprint)
    assert seeded["attempted_at"] is not None, (
        "precondition: the mark this file withdraws was never recorded, so a "
        "passing withdrawal would prove nothing")
    assert seeded["attempt_note"] == "raised the H1", (
        "precondition: the note went with the mark, so clearing it is "
        "observable separately from clearing the stamp")

    return api, site_id, fingerprint, [s["fingerprint"] for s in states], row_of


def test_a_mark_the_operator_set_can_be_withdrawn(marked):
    """The claim, at the store rather than at the status line.

    A 200 is a different claim from a cleared row — the reason
    `test_every_state_the_operator_owns_is_settable.py` reads the row back
    too — so this asserts on what `site_states` hands the screen after the
    withdrawal, which is the same shape `seed()` re-reads on every load.
    """
    api, site_id, fingerprint, _, row_of = marked

    resp = api.delete(f"/api/sites/{site_id}/states/{fingerprint}/attempt")
    assert resp.status_code == 200, (
        "the operator's `clear these marks` button has no route to call: "
        f"DELETE .../attempt answered {resp.status_code} {resp.text!r}. The "
        "mark is write-once, and the control beside it says it is not.")

    after = row_of(fingerprint)
    assert after["attempted_at"] is None and after["attempt_note"] is None, (
        "the route answered 200 and the finding still reads attempted_at="
        f"{after['attempted_at']!r}, attempt_note={after['attempt_note']!r}. "
        "`mark_attempt` is a bare UPDATE and its inverse can no-op the same "
        "way, so a 200 is not evidence the row moved.")


def test_withdrawing_a_mark_leaves_the_state_alone(marked):
    """The negative control. `attempted_at` and `state` are two facts about
    one finding — one the operator records, one a run derives — and a
    withdrawal that reset the state would let the record screen's tick undo a
    verdict a crawl reached, which is WF-61's defect through a second door.
    """
    api, site_id, fingerprint, _, row_of = marked

    before = row_of(fingerprint)["state"]
    api.delete(f"/api/sites/{site_id}/states/{fingerprint}/attempt")
    after = row_of(fingerprint)["state"]

    assert after == before, (
        f"withdrawing the fix-attempt mark moved the finding's state "
        f"{before!r} -> {after!r}. The mark is the operator's; the state is "
        "the run's.")


def test_the_withdrawal_reports_a_mark_it_did_not_clear(marked):
    """WF-95's rule, applied to the inverse on the day the inverse exists.

    `mark_attempt` has always answered 404 on a fingerprint with no row. An
    inverse answering an unconditional ok would be the asymmetry WF-95 closed,
    re-opened on the other verb.
    """
    api, site_id, _, fingerprints, _ = marked
    absent = "0" * 24
    assert absent not in fingerprints, (
        "precondition: the fingerprint chosen to be absent is one the run "
        "actually raised, so this asserts nothing about a miss")

    resp = api.delete(f"/api/sites/{site_id}/states/{absent}/attempt")
    assert resp.status_code == 404, (
        "the route was given a fingerprint with no row and answered "
        f"{resp.status_code} {resp.text!r}")


def test_every_operator_owned_mark_has_a_route_that_withdraws_it(tmp_path):
    """The population clause, and the reason this file is not one assertion.

    Read off `app.routes`, so a second mark added beside `attempt` is in scope
    without a line changing here. The non-emptiness assertion is not
    decoration: a path-matching bug that found no mark routes at all would
    otherwise make this pass by finding nothing, which is the vacuity the
    promoted guard's-population invariant names.
    """
    app = create_app(db_path=tmp_path / "routes.db")
    stem = "/api/sites/{site_id}/states/{fingerprint}/"
    found: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith(stem):
            continue
        found.setdefault(path[len(stem):], set()).update(
            getattr(route, "methods", None) or set())

    assert found, (
        f"no per-finding mark route was found under {stem!r} — the population "
        "is empty, so every assertion below it would pass by finding nothing")
    for mark in OPERATOR_OWNED_MARKS:
        assert mark in found, (
            f"{mark!r} is named as a mark the operator owns and no route "
            f"under {stem!r} serves it; the routes found were {sorted(found)}")
        assert "DELETE" in found[mark], (
            f"the operator can set {mark!r} through {sorted(found[mark])} and "
            "cannot unset it through anything. A mark with no inverse is a "
            "state the operator owns and cannot reach, which is the "
            "affordance invariant at the route layer.")


# --- the screen, as the operator drives it ---------------------------------
#
# The clauses above prove the route. They cannot see the half this finding was
# actually about: `mark`'s off branch and `clear` reached nothing but browser
# memory, and both are TypeScript. Shipping the route alone would be CQ-218's
# defect one round after it closed - six cases for the half the operator never
# sees and none for the half they read.

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit and no marks at all.

    Its own server rather than a shared fixture, for the reason
    `test_site_level_tick.py` gives about its own: this file ticks and unticks
    rows, and a fixture other files assert on for its counts would be a
    fixture this one mutates underneath them.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app as _create
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="attemptmark"))
    db = tmp / "clauditseo.db"
    app = _create(db_path=db)
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
                            json={"name": "Mark Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "mark.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _stored_marks(base: str, site_id: str) -> dict[str, str | None]:
    """`attempted_at` per fingerprint, read from the payload the screen reads.

    Off `/api/sites/{id}`, not off the database directly: this is the value
    `seed()` unions back into the tick set, so it is the one that decides
    whether a cleared mark comes back.
    """
    import httpx

    body = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()
    return {s["fingerprint"]: s["attempted_at"] for s in body["states"]}


@NEEDS_BROWSER
@needs_build
def test_a_mark_cleared_on_the_record_screen_is_gone_after_a_reload(served):
    """WF-84 where the operator meets it. DISCIPLINE rule 12.

    The reload is the assertion, not a flourish. Unticking always emptied the
    browser `Set`, so the chip vanished immediately even at the broken HEAD;
    what it did not do was reach the server, and `seed()` put the tick back on
    the next load. A test that ticked, cleared and looked without reloading
    would have passed against the defect.
    """
    from playwright.sync_api import sync_playwright

    base, site_id = served
    assert not any(_stored_marks(base, site_id).values()), (
        "precondition: the fixture already holds a fix-attempt mark, so a "
        "cleared one cannot be told from one that was never set")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            def open_record() -> None:
                pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                        timeout=30_000)
                pg.wait_for_selector("a.seq-name", timeout=30_000)
                pg.click("a.seq-name:text-is('Record')")
                # The record opens on open + regressed (plan §4a);
                # this reads rows in every state.
                pg.click('[aria-label="state filter"] [data-state="all"]')
                # The record groups by check since brief step 6; these read instances.
                pg.select_option('select[aria-label="group by"]', "none")
                pg.wait_for_selector("tr:has(code)", timeout=30_000)

            open_record()
            boxes = pg.query_selector_all("input.fix-chk")
            assert boxes, (
                "the record painted no fix-attempt checkbox, so this asserts "
                "nothing about clearing one")
            boxes[0].check()
            pg.wait_for_selector("span.st-marked", timeout=15_000)

            marks = _stored_marks(base, site_id)
            ticked = [fp for fp, at in marks.items() if at]
            assert len(ticked) == 1, (
                "precondition: ticking the box did not reach the server, so "
                f"there is no stored mark to clear - stored marks {ticked}")

            pg.click("button:has-text('clear these marks')")
            pg.wait_for_function(
                "() => !document.querySelector('span.st-marked')",
                timeout=15_000)

            open_record()
            still = [fp for fp, at in _stored_marks(base, site_id).items()
                     if at]
            assert not still, (
                "`clear these marks` was pressed and the server still holds "
                f"{still}. The button reached browser memory only, and "
                "`seed()` unions the stored mark back in on this reload.")
            assert not pg.query_selector("span.st-marked"), (
                "the mark was cleared and the reloaded record still paints "
                "`awaiting a look` - the chip the operator reads as proof "
                "the clear landed")
        finally:
            browser.close()


@NEEDS_BROWSER
@needs_build
def test_unticking_one_row_reaches_the_server(served):
    """The other half of `mark`, and the reason the `else` branch exists.

    `clear these marks` clears a whole list; a single untick is the verb an
    operator uses to correct one mis-tick, and it went through the same dead
    path. Asserted after a reload for the same reason as above.
    """
    from playwright.sync_api import sync_playwright

    base, site_id = served

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            def open_record() -> None:
                pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                        timeout=30_000)
                pg.wait_for_selector("a.seq-name", timeout=30_000)
                pg.click("a.seq-name:text-is('Record')")
                # The record opens on open + regressed (plan §4a);
                # this reads rows in every state.
                pg.click('[aria-label="state filter"] [data-state="all"]')
                # The record groups by check since brief step 6; these read instances.
                pg.select_option('select[aria-label="group by"]', "none")
                pg.wait_for_selector("tr:has(code)", timeout=30_000)

            open_record()
            box = pg.query_selector_all("input.fix-chk")[0]
            box.check()
            pg.wait_for_selector("span.st-marked", timeout=15_000)
            assert any(_stored_marks(base, site_id).values()), (
                "precondition: the tick never reached the server, so "
                "unticking has nothing to withdraw")

            box.uncheck()
            pg.wait_for_function(
                "() => !document.querySelector('span.st-marked')",
                timeout=15_000)

            open_record()
            still = [fp for fp, at in _stored_marks(base, site_id).items()
                     if at]
            assert not still, (
                "the row was unticked and the server still holds "
                f"{still}; `mark(f, false)` reached nothing but a browser Set")
        finally:
            browser.close()
