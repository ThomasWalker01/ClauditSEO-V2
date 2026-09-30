"""The tick the server refuses, and the refusals nobody can read.

`audits/DISPOSITIONS.md`'s engineering cohort, two live rows at eleven rounds:

- **a site-level finding offers a tick the POST refuses 422** —
  `modules/loc.py:104-113`; `fixloop.tsx:172-179`. Report 066 carries it as
  UX-17.
- **`FixTick` states its disabled reason only in a `title`** —
  `dashboard/src/fixloop.tsx:160-172`. Report 066 carries it as UX-16.

**Why one file.** Both are `FixTick`'s disclosure contract and only that: what
it offers, and what it says when it offers nothing. The first needs a third
refusal branch; writing that branch's reason into a `title` would ship the
second defect in new code, so the two are one change or the fix is worse than
the finding.

**What the server does.** `pages_for_findings` keeps `u for u in
affected_urls if u.startswith("http")` and the verify route answers **422**
`these findings name no page to re-fetch — they are site-level, and are judged
by a full audit` when that comes to nothing
(`clauditseo/api/app.py:1511-1517`). Five of the twelve findings a default
fixture audit raises are in exactly that state — `contrast-not-assessed`,
`cwv-not-assessed`, `third-party-scripts-none`, `backlinks-not-assessed`,
`llms-txt-missing` — all `open`, all `deterministic`, all offered a tick.

**Why the client is told rather than deciding.** The anatomy payload truncates
`urls` to ten while `pages` counts the untruncated list, and neither is the
server's predicate — that filters on `startswith("http")`. A client-side
re-derivation would be a second implementation of one rule, which is the shape
of CQ-134 and of the provenance tag's nineteen copies. So the rule keeps one
owner, `runs.names_a_page`, and travels on the row — the argument
`_finding_dict` already records for `specialist`: "the server decides, so a
row cannot offer a control the server would refuse."

**Why hover text is not disclosure.** `views.tsx` already settled it for the
tab strip, in the product's own words: *"Hover text alone fails the reader who
is not using a mouse and the one who does not think to hover."* `FixTick` is
the same control class and had the same defect.

**Split across the two CI legs**, the convention
`test_measured_share_on_screen.py` and `test_spend_mark.py` both record. The
server half and the payload half run everywhere; the half about what the
browser painted drives a real server with a real browser and runs in
`rendered-a11y`, where a skip fails the job.
"""

from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST

NEEDS_BROWSER = pytest.mark.skipif(
    not axe.available() or not (DIST / "index.html").is_file(),
    reason="needs clauditseo[render], `playwright install chromium`, and a "
           "built dashboard (npm run build in dashboard/)")

#: The check id the default fixture audit raises with no page behind it. Named
#: rather than counted, so a failure says which one moved.
SITE_LEVEL = "AIS/llms-txt-missing"
#: One that does name a page, so every assertion below has a control.
PAGED = "TEC/robots-missing"
#: A third, put into `withdrawn` so the state column has something to explain.
#: UX-43 is about what that state *means*, and no audit produces one: it is an
#: operator judgement, so a control has to record it.
#:
#: **The detour this fixture used to take is gone, and what it recorded is
#: worth keeping.** Until WF-68 closed, these two lines set `accepted-risk`
#: through the route the operator's button calls and `withdrawn` through the
#: persistence layer, because the route refused the second — "a state exists
#: in the data that the API refuses to set". Both go through the route now,
#: which is the point: a fixture reaching a state by a path the product does
#: not have is a fixture that cannot notice the product does not have it.
WITHDRAWN = "TEC/sitemap-missing"
#: A fourth, put into `fixed`, because that is the state the record painted no
#: verb at all on. WF-61: a run marks a finding `fixed` when it is absent from
#: a later run, and absence is not always a repair — on the operator's own
#: install 2 of the 18 `fixed` rows are `cwv-not-assessed` and
#: `sitemap-coverage-not-assessed`, scope limitations that went away because
#: the second run did not measure them either. Nothing in the product could
#: take one of those back.
#:
#: **The 2 was 13 until CQ-189, and the reason is worth more than the digit.**
#: 13 is a real figure from a different query: joining every historical
#: `findings` row to a `fixed` state gives 36 rows, of which those two checks
#: are 9 and 4. The sentence paired a numerator over `findings` with a
#: denominator over `finding_states`.
#:
#: **Both figures count `finding_states` rows, but only the first can be
#: derived from that table alone — CQ-195.** This comment said "both figures
#: here are over `finding_states` alone", which is true of the 18 and cannot
#: be true of the 2: `finding_states` has no `check_id` column, so restricting
#: by check id needs `findings`. The 18 is
#: `SELECT COUNT(*) FROM finding_states WHERE state='fixed'`. The 2 is that
#: same row set narrowed by a correlated `EXISTS` against `findings` on
#: `fingerprint` — correlated rather than joined, because `findings` holds one
#: row per run and a plain join multiplies a fingerprint by the number of runs
#: that raised it, which is how 9 and 4 arise. Both queries are executed
#: against a two-run fixture by
#: `test_the_derivation_stated_beside_the_fixed_count_can_be_run` below, which
#: also asserts the two forms disagree, so this paragraph cannot go stale
#: without a red suite.
#:
#: The argument does not rest on the size: one clearance the product cannot
#: take back is the case, and there are two.
#:
#: **This one does go through the persistence layer, and the distinction from
#: `WITHDRAWN` above is the whole point rather than an inconsistency.** `fixed`
#: is a conclusion a run draws from its own evidence; the route refuses it by
#: design and `test_every_state_the_operator_owns_is_settable.py` holds that
#: refusal in place. A fixture reaching a *machine-derived* state by machinery
#: is using the only mechanism there is. A fixture reaching an
#: *operator-owned* state that way is covering for a control that should exist
#: and does not, which is what the note above records.
#: A real finding rather than `cwv-not-assessed`: since brief v2 step F a
#: coverage note - what the audit could not measure - is a strip of its own
#: under the table, with no verb, and is not a row this test can read.
# `TEC/security-headers` until item 143 step BD purged it; `viewport-missing`
# is the fixture's remaining TEC row no other constant here names.
FIXED = "TEC/viewport-missing"
#: A fifth, put into `candidate`, because that is the one state the record
#: paints and deliberately offers no verb on (`dashboard/src/views.tsx:971`:
#: *"`candidate` gets none of them, deliberately"*). CQ-190: without this row
#: the dead-end guard below asserted a universal property against a fixture
#: that could not paint the one exception, so it proved nothing and would have
#: reddened the day the fixture grew a brief. Measured on the operator's own
#: install when the finding was raised: 272 rows stand in `candidate`,
#: 178 of them on one site, every one painted verbless.
#:
#: **Reached through `set_state`, and the divergence from production is named
#: rather than glossed.** A run only ever writes `candidate` for `EXP:*`
#: findings (`clauditseo/persistence/runs.py:1198-1203`), so no ordinary check
#: id arrives in this state by itself. That is acceptable here, and only here,
#: because the property under test is what the record paints for a *state*:
#: the verb table filters on `s.state` alone and reads nothing else off the
#: row (`dashboard/src/views.tsx:999`). A guard that also asserted about the
#: finding's provenance could not use this row.
CANDIDATE = "ONP/canonical-missing"

#: States the record paints with no verb **on purpose**, each with the line
#: that decided it. Written out rather than derived from which states happen
#: to carry verbs: a guard that read the exemptions off the cell it checks
#: would take its evidence from its own subject and could then only ever pass,
#: which is DISCIPLINE rule 5 and the reason CQ-190 existed at all.
#:
#: - `candidate` — `dashboard/src/views.tsx:971`. A finding seen once is not
#:   yet a fact, so there is nothing to accept, retract or restore until a
#:   second run confirms it.
#:
#: Adding a state here is a product decision and should carry its own line.
#: The guard below is what makes that cost visible: a new state arriving with
#: no verb and no entry here reddens rather than passing quietly.
VERBLESS_BY_DESIGN = frozenset({"candidate"})


def _seeded(tmp_path):
    """One completed audit through the real writer, in its own database."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    from tests.test_coverage import DIMS, _Hub, _run

    conn = connect(tmp_path / "tick.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Tick Co")
    site_id = repo.create_site(conn, client, "x.test")
    run_id = runs.create_run(conn, site_id, DIMS, "T2")
    runs.complete_run(conn, run_id, _run(_Hub()))
    return conn, site_id, run_id


def _pageless(conn, site_id) -> list[str]:
    """Fingerprints the verify route cannot fetch a page for, from the rows."""
    return [r["fingerprint"] for r in conn.execute(
        "SELECT fs.fingerprint, f.affected_urls FROM finding_states fs"
        " JOIN findings f ON f.fingerprint = fs.fingerprint"
        " WHERE fs.site_id=?", (site_id,)).fetchall()
        if not [u for u in json.loads(r["affected_urls"] or "[]")
                if u.startswith("http")]]


# --- the premise, measured rather than read --------------------------------

def test_the_derivation_stated_beside_the_fixed_count_can_be_run(tmp_path):
    """CQ-195. The `FIXED` comment above tells the next reader how to re-derive
    its two figures; this runs that method rather than trusting it.

    **Two runs, deliberately.** `finding_states` holds one row per fingerprint
    and `findings` holds one per run, so the moment a site has been audited
    twice the check-id restriction needs a correlated subquery and a plain join
    silently multiplies. One run cannot tell the two apart, which is exactly
    why the wrong derivation read as right.

    *Dead end, recorded so it is not re-tried:* the restriction cannot be
    written against `finding_states` alone. That table is `site_id,
    fingerprint, state, changed_by_run, updated_at, attempted_at,
    attempt_note`, and the form the comment used to state -
    `... WHERE state='fixed' AND check_id IN (...)` - raises
    `sqlite3.OperationalError: no such column: check_id`. Asserted below rather
    than described, so the shorter wrong query cannot come back quietly.
    """
    from clauditseo.persistence import runs
    from tests.test_coverage import DIMS, _Hub, _run

    conn, site_id, _ = _seeded(tmp_path)
    second = runs.create_run(conn, site_id, DIMS, "T2")
    runs.complete_run(conn, second, _run(_Hub()))
    marks = {f"{s['dimension']}/{s['check_id']}": s["fingerprint"]
             for s in runs.site_states(conn, site_id)}
    runs.set_state(conn, site_id, marks[FIXED], "fixed")
    runs.set_state(conn, site_id, marks[WITHDRAWN], "fixed")

    # The population, so nothing below can pass by finding nothing.
    check_id = FIXED.split("/", 1)[1]
    rows_per_fingerprint = conn.execute(
        "SELECT COUNT(*) FROM findings WHERE fingerprint=?",
        (marks[FIXED],)).fetchone()[0]
    assert rows_per_fingerprint > 1, (
        "the inflation this test is about needs a fingerprint carrying more "
        "than one findings row")

    # The unrestricted figure: the 18 on the operator's install.
    total = conn.execute(
        "SELECT COUNT(*) FROM finding_states WHERE site_id=? AND state='fixed'",
        (site_id,)).fetchone()[0]
    assert total == 2

    # The restricted figure: the 2 on the operator's install, and the form the
    # comment above now states.
    restricted = conn.execute(
        "SELECT COUNT(*) FROM finding_states s WHERE s.site_id=?"
        " AND s.state='fixed' AND EXISTS ("
        "  SELECT 1 FROM findings f WHERE f.fingerprint = s.fingerprint"
        "  AND f.check_id = ?)", (site_id, check_id)).fetchone()[0]
    assert restricted == 1

    # And the naive join, which is what CQ-189 corrected. It must disagree, or
    # this test is asserting a distinction that does not exist.
    naive = conn.execute(
        "SELECT COUNT(*) FROM finding_states s JOIN findings f"
        " ON f.fingerprint = s.fingerprint WHERE s.site_id=?"
        " AND s.state='fixed' AND f.check_id = ?",
        (site_id, check_id)).fetchone()[0]
    assert naive > restricted, (
        f"naive join {naive} did not inflate past the correlated {restricted}")

    with pytest.raises(sqlite3.OperationalError, match="no such column"):
        conn.execute(
            "SELECT COUNT(*) FROM finding_states WHERE site_id=?"
            " AND state='fixed' AND check_id = ?", (site_id, check_id))
    conn.close()


def test_the_fixture_raises_findings_a_crawl_can_never_judge(tmp_path):
    """Precondition, so nothing below can go vacuous.

    Counted off the stored rows, not off the module source: the finding has to
    survive `complete_run` and reach `finding_states` as `open` and
    `deterministic` before the screen would offer it a tick at all.
    """
    conn, site_id, _ = _seeded(tmp_path)
    rows = conn.execute(
        "SELECT f.dimension, f.check_id, f.affected_urls, f.source, fs.state"
        " FROM finding_states fs"
        " JOIN findings f ON f.fingerprint = fs.fingerprint"
        " WHERE fs.site_id=?", (site_id,)).fetchall()
    tickable = {f"{r['dimension']}/{r['check_id']}": r for r in rows
                if r["state"] in ("open", "regressed")
                and r["source"] == "deterministic"}
    pageless = [k for k, r in tickable.items()
                if not [u for u in json.loads(r["affected_urls"] or "[]")
                        if u.startswith("http")]]
    assert SITE_LEVEL in pageless, (
        f"the fixture no longer raises {SITE_LEVEL} with no page behind it; "
        f"the pageless tickable findings are {pageless}")
    assert PAGED in tickable and PAGED not in pageless, (
        f"the fixture no longer raises {PAGED} against a page, so the control "
        "every assertion below leans on is gone")
    conn.close()


def test_the_verify_route_refuses_a_batch_of_site_level_findings(tmp_path):
    """The 422 itself, from the endpoint rather than from a reading of it.

    This is what the tick promises and the product declines to do, and it is
    asserted here so the screen's refusal below is measured against the
    server's behaviour and not against a sentence in this file.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    from clauditseo.persistence import runs

    conn, site_id, _ = _seeded(tmp_path)
    pageless = _pageless(conn, site_id)
    assert pageless, "precondition: nothing pageless to ask about"
    target = runs.pages_for_findings(conn, site_id, pageless)
    assert target["found"] and not target["urls"], (
        f"the server can re-fetch {target['urls']} for findings that name no "
        "page, so the 422 below is not the refusal this test is about")
    conn.close()

    client = TestClient(create_app(db_path=tmp_path / "tick.db"))
    resp = client.post(f"/api/sites/{site_id}/verify",
                       json={"fingerprints": pageless})
    assert resp.status_code == 422, (
        f"the verify route answered {resp.status_code} for a batch of "
        "site-level findings; the tick's promise is no longer refused, and "
        "this finding may have been closed at the other end")
    assert "no page to re-fetch" in resp.json()["detail"]


# --- the payload -----------------------------------------------------------

def test_both_payloads_say_whether_a_finding_names_a_page(tmp_path):
    """One rule, one owner, on every row that carries a tick.

    Both screens that render `FixTick` are asserted here, because a field the
    server computes for one and not the other is the hand-kept list DISCIPLINE
    rule 3 is about — and the anatomy screen is the one whose own `pages`
    count could be mistaken for this answer.
    """
    from clauditseo.persistence import runs

    conn, site_id, _ = _seeded(tmp_path)

    states = {f"{s['dimension']}/{s['check_id']}": s
              for s in runs.site_states(conn, site_id)}
    assert states[SITE_LEVEL]["names_a_page"] is False, (
        "the site screen's row for a site-level finding does not say it names "
        "no page, so the tick has nothing to branch on")
    assert states[PAGED]["names_a_page"] is True

    tree = runs.anatomy_view(conn, site_id)
    findings = {f"{f['dimension']}/{f['check_id']}": f
                for cat in tree["categories"] for f in cat["findings"]}
    assert findings[SITE_LEVEL]["names_a_page"] is False
    assert findings[PAGED]["names_a_page"] is True
    conn.close()


def test_the_payload_answer_is_the_verify_route_s_own_rule(tmp_path):
    """Not a second implementation: the same rule, asked twice.

    `pages_for_findings` decides what the crawl fetches and the 422 is `not
    target["urls"]`. Every row's `names_a_page` is compared against that
    verdict, per finding, so the screen and the server cannot drift.
    """
    from clauditseo.persistence import runs

    conn, site_id, _ = _seeded(tmp_path)
    for s in runs.site_states(conn, site_id):
        target = runs.pages_for_findings(conn, site_id, [s["fingerprint"]])
        assert s["names_a_page"] is bool(target["urls"]), (
            f"{s['dimension']}/{s['check_id']} is served "
            f"names_a_page={s['names_a_page']} while the verify route would "
            f"fetch {target['urls']}")
    conn.close()


# --- the screen, as painted ------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def ticked():
    """A real server holding one audit, with one finding put beyond ticking.

    Its own server rather than `test_a11y_rendered.py`'s `served`, for that
    fixture's own stated reason: it is asserted on by several files for its
    run count and its trend, and adding state to it to prove something about
    another screen is how a shared fixture stops being readable.

    Both operator-set rows go through the route the operator's button calls,
    so the state refusal is reached the way the product reaches it. See the
    note above `WITHDRAWN` for what the second one used to do instead.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.persistence import runs
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="sitelevel"))
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
                            json={"name": "Tick Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "tick.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        marks = {f"{s['dimension']}/{s['check_id']}": s["fingerprint"]
                 for s in runs.site_states(conn, site["id"])}
        conn.close()
        httpx.post(f"{base}/api/sites/{site['id']}/states/{marks[PAGED]}",
                   json={"state": "accepted-risk"},
                   timeout=30).raise_for_status()
        httpx.post(f"{base}/api/sites/{site['id']}/states/{marks[WITHDRAWN]}",
                   json={"state": "withdrawn"},
                   timeout=30).raise_for_status()
        conn = connect(db)
        runs.set_state(conn, site["id"], marks[FIXED], "fixed")
        runs.set_state(conn, site["id"], marks[CANDIDATE], "candidate")
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _record_rows(base: str, site_id: str) -> list[dict]:
    """Every row the record paints, with its state, its verbs and their `why`.

    Read off the rows themselves rather than enumerated from `ALL_STATES` —
    the filter above the table decides what is on screen, so a population
    taken from the registry would assert about rows that are not there.

    **The selector sweeps every painted row and not the first match, and that
    is deliberate rather than incidental.** It caught the WF-61 fix being
    applied to a duplicated copy of the record section: the screen painted
    `PRF/cwv-not-assessed` twice, once with the new verbs and once with an
    empty cell, and every `pg.inner_text`-style helper in this file would have
    read the first match and passed. A guard that reads one row cannot see a
    screen rendering two.

    `titles` is positional against `verbs` — same nodes, same order, one
    query — because pairing them by label in Python would need the label to
    be unique per row, which is a property nothing enforces.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
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
            return pg.eval_on_selector_all(
                "tbody tr:has(code)",
                "els => els.map(e => {"
                " const bs = Array.from("
                "   e.querySelectorAll('td:last-child button'));"
                " return {"
                "  check: e.querySelector('code')?.innerText,"
                "  state: e.querySelector('[class*=\"tone-state-\"]')?.innerText?.trim(),"
                "  verbs: bs.map(b => b.innerText.trim()),"
                "  titles: bs.map(b => b.getAttribute('title') || '')};})")
        finally:
            browser.close()


def _record_cells(base: str, site_id: str, reader) -> dict[str, str]:
    """The record tab's two fix cells, read by `reader` off a real browser."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
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
            return {check: reader(pg,
                                  f"tr:has(code:text-is('{check}')) td.fix-col")
                    for check in (SITE_LEVEL, PAGED)}
        finally:
            browser.close()


@NEEDS_BROWSER
def test_the_record_offers_no_tick_for_a_finding_no_crawl_can_judge(ticked):
    """UX-17, settled where the operator meets it: the painted row.

    DISCIPLINE rule 12 — the tree is not where a screen counts. The control
    the server would refuse must not be on the screen at all, and a row that
    does name a page and is open must still carry one, so this cannot be
    passed by removing the tick everywhere.
    """
    base, site_id = ticked
    cells = _record_cells(base, site_id,
                          lambda pg, sel: pg.inner_html(sel))
    assert "fix-chk" not in cells[SITE_LEVEL], (
        f"{SITE_LEVEL} names no page, so a verification of it alone is "
        f"refused 422 — and the record still offers the tick: "
        f"{cells[SITE_LEVEL]!r}")
    assert "fix-chk" not in cells[PAGED], (
        f"precondition: {PAGED} was set accepted-risk, so it carries no tick "
        f"for the other reason: {cells[PAGED]!r}")


def _state_cell(base: str, site_id: str, check: str) -> str:
    """The record's state cell for one check, as text a browser produced."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
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
            return pg.inner_text(
                f"tr:has(code:text-is('{check}')) td:has([class*='tone-state-'])")
        finally:
            browser.close()


@NEEDS_BROWSER
def test_the_record_says_what_withdrawn_means_without_a_mouse(ticked):
    """UX-43, on the surface where the state is actually visible.

    `withdrawn` is the one state whose whole meaning was unreachable. It was
    written twice into `title` attributes — `FixState`'s branch below and the
    Current pane's excluded line in `anatomy.tsx` — and on The record, where a
    withdrawn row is listed by default, it was not written at all: the cell
    renders `{s.state}` and nothing else, so the word arrives with no account
    of itself on any input device.

    `inner_text`, not `inner_html`, for `test_every_refusal_...`'s reason one
    test down: a sentence in a `title` is in the markup and not in the text,
    and the whole of the finding is that the operator cannot read it.

    Asserted on the sentence's own words rather than on a class name, because
    a class proves a component mounted and not that it said anything — and
    `STATE_MEANING`'s value is the thing under test.
    """
    base, site_id = ticked
    text = _state_cell(base, site_id, WITHDRAWN)
    assert "withdrawn" in text.lower(), (
        f"precondition: {WITHDRAWN} is not showing as withdrawn: {text!r}")
    assert "never true" in text.lower(), (
        f"the record paints {text.strip()!r} — the word `withdrawn` with no "
        "statement that the finding was never true, which is the whole of "
        "what the state means and the only thing that tells the operator "
        "this is not a fix")


@NEEDS_BROWSER
def test_every_refusal_the_record_paints_is_readable_without_a_mouse(ticked):
    """UX-16, on the text a browser produced.

    `inner_text`, not `inner_html`: a reason held in a `title` attribute is in
    the markup and not in the text, which is the whole of the finding. The
    product settled this for its own tab strip — "hover text alone fails the
    reader who is not using a mouse and the one who does not think to hover"
    — and this holds the control beside it to the same standard.

    Both reachable refusals are driven: the state branch, via a row the
    fixture set `accepted-risk` through the API, and the page branch, via a
    finding the sweep raised with no page behind it.
    """
    base, site_id = ticked
    cells = _record_cells(base, site_id,
                          lambda pg, sel: pg.inner_text(sel))
    for check, text in cells.items():
        assert len(text.strip()) > 3, (
            f"the record's fix cell for {check} paints {text.strip()!r} and "
            "keeps its reason in a `title`, so an operator who is not using a "
            "mouse is told nothing at all about why there is no tick")
    assert "page" in cells[SITE_LEVEL].lower(), (
        "the refusal for a site-level finding does not say a page is what is "
        f"missing: {cells[SITE_LEVEL]!r}")
    assert "open" in cells[PAGED].lower(), (
        "the refusal for an accepted-risk finding does not say the state is "
        f"why: {cells[PAGED]!r}")


@NEEDS_BROWSER
def test_the_record_can_reach_every_state_a_run_cannot(ticked):
    """WF-68, on the surface where the operator meets it.

    `runs.MODEL_BLIND_STATES` is the pair no crawl can ever derive — the
    operator's own judgements — so the record's action cell is the only thing
    in the product that will ever record one. `accepted-risk` had a control;
    `withdrawn` had a schema, a count, a TypeScript union, a filter entry and
    a rendered explanation, and no control anywhere.

    **The population is derived and the mapping is not assumed.** This does
    not look for a button named after a state — the labels are verbs (`accept
    risk`, `withdraw`) and asserting on them would be asserting on this
    round's wording. It presses each button the cell offers on an open row,
    reads what state the row lands in, and requires the reachable set to cover
    `MODEL_BLIND_STATES`. A seventh operator state added to that constant
    fails here until something on this screen can set it.

    DISCIPLINE rule 12: the tree is not where a screen counts. The state is
    read back out of the row the browser painted after the press, not out of
    the response — the route answers 200 and `runs.set_state` is a bare UPDATE
    that no-ops on a fingerprint with no row, so a 200 is not evidence.
    """
    from playwright.sync_api import sync_playwright

    from clauditseo.persistence import runs

    base, site_id = ticked
    reached: dict[str, str] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            def open_record():
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
            # Every row the record paints as `open`, with the check id that
            # names it — one row is spent per button, and the ids come off the
            # screen rather than from the fixture's own constants so a row the
            # filter happens to hide is never chosen.
            open_rows = pg.eval_on_selector_all(
                "tr:has(.tone-state-open)",
                "els => els.map(e => e.querySelector('code')?.innerText)")
            open_rows = [r for r in open_rows if r]
            labels = pg.eval_on_selector_all(
                f"tr:has(code:text-is('{open_rows[0]}')) td:last-child button",
                "els => els.map(e => e.innerText.trim())")

            assert labels, (
                "the record offers no control at all on an open finding, so "
                "no state a run cannot derive is reachable from any screen")
            assert len(open_rows) >= len(labels), (
                f"precondition: {len(labels)} controls to press and only "
                f"{len(open_rows)} open rows to spend on them: {open_rows!r}")

            for row, label in zip(open_rows, labels):
                sel = f"tr:has(code:text-is('{row}')) td:last-child"
                pg.click(f"{sel} button:text-is('{label}')")
                # Item 178: withdraw and accept risk ask first.
                if pg.locator("[role=alertdialog]").count():
                    pg.click("[role=alertdialog] .confirm-go")
                pg.wait_for_selector(
                    f"tr:has(code:text-is('{row}')) [class*='tone-state-']:not(.tone-state-open)",
                    timeout=30_000)
                reached[label] = pg.inner_text(
                    f"tr:has(code:text-is('{row}')) [class*='tone-state-']").strip()
                open_record()
        finally:
            browser.close()

    missing = [s for s in runs.MODEL_BLIND_STATES
               if s not in reached.values()]
    assert not missing, (
        f"no control on the record puts a finding into {missing!r}. Pressing "
        f"every button the cell offers reached {reached!r}, and those states "
        "are in `runs.MODEL_BLIND_STATES` — the ones no run can derive, so a "
        "screen is the only thing that will ever record them")


@NEEDS_BROWSER
def test_no_state_the_record_paints_is_a_dead_end(ticked):
    """WF-61's second clause: nothing in the product can retract them.

    A run writes `fixed` when a finding is absent from a later run, and
    absence is not a repair — on the operator's own install 2 of the 18
    `fixed` rows are `cwv-not-assessed` and `sitemap-coverage-not-assessed`,
    scope limitations that went away because the second run did not measure
    them either (CQ-189: this read 13 and the account is beside `FIXED`
    above). The record painted `accept risk` on two states and `reopen`
    on one, by two hand-written branches, so `fixed` and `candidate` carried
    no verb at all and a wrong verdict was permanent.

    **The assertion is a property of the cell, not a list of states.** Every
    row the record paints must offer at least one control, whatever state it
    is in — so a state added to `ALL_STATES` later cannot arrive as a dead end
    the way `withdrawn` arrived without a writer. It deliberately does not
    assert *which* verbs: `reopen` on an already-open row would be noise, and
    a test that demanded one per state would be asserting this round's
    judgement rather than the property that matters.

    **One exemption, named here rather than inferred from the screen (CQ-190).**
    `candidate` is verbless on purpose — `dashboard/src/views.tsx:971` says so
    and gives the reason: a finding seen once is not yet treated as a fact, so
    there is nothing to accept, retract or restore until a second run confirms
    it. Until this round the guard asserted the opposite universally and passed
    anyway, because the fixture wrote three states and `candidate` was not one
    of them, while 272 rows stood in it on the operator's own install. Driven
    at `localhost:8020` when the finding was raised: 50 candidate rows painted,
    every verb list empty.

    The exemption is a **written constant**, not a derivation from which states
    happen to carry verbs. Narrowing it to *"the states the screen offers verbs
    on"* was the other option on the table and it is the shape DISCIPLINE rule 5
    forbids: the guard would take its evidence from the cell it is checking and
    could then only ever pass. A constant keeps the original property intact —
    a sixth state arriving with no verb and no entry here still reddens this.

    The precondition below is doubled for the same reason. `fixed` was already
    asserted onto the screen so the state this test is about cannot silently
    leave it; `candidate` now is too, because an exemption that passes when its
    row is absent is an exemption with no case behind it.

    `fixed` is named on top of that property, because it is the state this
    closes and a general assertion that happened to pass on four states and
    fail on the fifth is a general assertion nobody would read.

    **The selector sweeps every painted row and not the first match, and that
    is deliberate rather than incidental.** It caught the fix for this finding
    being applied to a duplicated copy of the record section: the screen
    painted `PRF/cwv-not-assessed` twice, once with the new verbs and once
    with an empty cell, and every `pg.inner_text`-style helper in this file
    would have read the first match and passed. A guard that reads one row
    cannot see a screen rendering two.
    """
    rows = _record_rows(*ticked)

    painted = {r["state"] for r in rows if r["state"]}
    for required in ("fixed", *VERBLESS_BY_DESIGN):
        assert required in painted, (
            f"precondition: the record paints no `{required}` row, so a state "
            f"this test is about is not on screen. States painted: "
            f"{sorted(painted)}")

    mute = sorted({r["state"] for r in rows if not r["verbs"]}
                  - VERBLESS_BY_DESIGN)
    assert not mute, (
        f"the record paints rows in {mute} and offers no control on any of "
        "them, so a finding that reaches one of those states can never be "
        "moved out of it by the operator. If one of those is deliberate, it "
        "belongs in `VERBLESS_BY_DESIGN` with the line that decided it. Rows: "
        + repr([r for r in rows if not r["verbs"]][:4]))


@NEEDS_BROWSER
def test_every_verb_the_record_offers_says_what_pressing_it_does(ticked):
    """UX-81. The control that retracts a finding explained itself nowhere.

    `accept risk` shipped with a hover explanation and `withdraw` beside it
    with none, on every row the verb was offered on — 45 open and 5 regressed
    on `www.acme.com.au` when the finding was raised. The sentence that
    would have explained it was reachable only *after* the press, because
    `StateNote` renders `STATE_MEANING` and `withdrawn` is what the row
    becomes, not what it is.

    **Asserted over every painted verb rather than over the two that were
    missing one.** A list of two would have been a record of this instance;
    the property is that a control writing an operator's judgement onto a
    client's record says what it writes, and a fourth verb added later is in
    scope without a line changing here.

    What this does *not* assert is which words. `test_dashboard_a11y.py` owns
    the other side of that — no `title` under `dashboard/src` may share four
    consecutive words with a `STATE_MEANING` sentence — so a `why` that
    paraphrased the state instead of describing the press fails there rather
    than here. The two guards are deliberately in different files: this one
    needs a browser and that one is a source sweep.
    """
    rows = _record_rows(*ticked)

    offered = {v for r in rows for v in r["verbs"]}
    assert offered, (
        "precondition: the record painted no verb at all, so this asserts "
        f"nothing. Rows: {rows[:3]!r}")

    mute = sorted({(r["state"], v)
                   for r in rows
                   for v, why in zip(r["verbs"], r["titles"])
                   if not (why or "").strip()})
    assert not mute, (
        f"the record offers {mute} with no account of what pressing them "
        "does, beside verbs that have one. Each pair is (state, verb). A "
        "verb's `why` says what the press does to the record; the state's own "
        "meaning stays owned by `STATE_MEANING` in `fixloop.tsx`.")
