"""WF-68. A state the operator owns must be reachable through the route the
operator's button calls.

`runs.ALL_STATES` holds six values and splits cleanly in two.
`runs.LIVE_STATES` — candidate, open, fixed, regressed — are **derived by a
run**: the lifecycle walk in `runs.py:1180-1185` decides them from what the
crawl saw. `runs.MODEL_BLIND_STATES` — accepted-risk, withdrawn — are the
**operator's own judgements**, which no run can reach, and which exist only
because a person recorded one.

`POST /api/sites/{id}/states/{fingerprint}` accepted `("open", "accepted-risk")`
and refused the other four with a 422. Three of those four are correct
refusals and this file asserts one of them stays: an operator hand-setting
`fixed` writes a repair claim no run gathered, which is WF-61's defect with the
product's own control pointed at it. `withdrawn` was the fourth, and it was not
a refusal anybody decided — it is the value that was added to the schema
(migration `0023`) and to every reader without being added to the one writer.

What that cost is not hypothetical. `0023`'s own header records it: an audit of
`www.acme.com.au` reached the site by a URL that could not be served and
raised `not-https` and `robots-missing` against a site that is HTTPS and serves
`robots.txt`. Before `withdrawn` existed "a false finding could only be filed
as one of two lies — `fixed`, which credits a repair nobody made, or
`accepted-risk`, which records an operator decision nobody took." After it
existed, the product still could not file one, because the route said 422.

Meanwhile every reader had shipped: `runs.py:2757` counts it, `api.ts:329`
types it, `views.tsx:864-865` offers it in the state filter, `fixloop.tsx:259`
prints what it means in rendered text, and `anatomy.tsx:374` paints `N
withdrawn` on the panel. So three screens named a state and nothing could act
on one — the affordance invariant, at a High floor.

*Three addresses in this paragraph, not two, and the third is why a report is
not evidence.* CQ-151 named `runs.py:2730` and `runs.py:2539-2543`, and
recorded that the rest "were checked line by line and are correct".
`views.tsx:854` was not: at `207fa07`, the commit report 087 audited, line 854
was already the prose "to accept a risk. Candidates are model findings seen
once" and the state filter was at `:864-865`. Found by re-running the check
rather than by reading the report's account of it — which is CQ-195's own
lesson arriving one paragraph later.

**The population is derived, not listed.** `MODEL_BLIND_STATES` is the registry
and this file reads it, so a seventh operator state added there is in scope
without a line changing here. A hand-kept tuple is the shape that let
`withdrawn` reach six readers and one writer in the first place — `runs.py:25-33`
is that account, written by the round that found it.

*A dead end that has since been closed, kept because the assertions below
still take the long way round and the reason should not be a mystery.* This
paragraph read, correctly at the time: "`runs.set_state` is a bare UPDATE
(`runs.py:2539-2543`) and silently no-ops on a fingerprint with no row, unlike
`mark_attempt` beside it, which returns a bool the route turns into a 404."
Two things about that are now wrong, and CQ-151 is both. The address was never
`set_state` — `clauditseo/persistence/runs.py:2539-2543` is inside
`site_states`, and `set_state` begins at `:2554`. And the behaviour changed at
WF-95: `set_state` now returns `cur.rowcount > 0`
(`clauditseo/persistence/runs.py:2554-2570`) and its route answers 404 on a
fingerprint with no row, which `test_the_route_reports_a_state_it_did_not_write`
in this same file asserts. So a 200 IS now evidence the write landed.

The assertions below still read the state back out of `site_states` rather than
trusting the 200, and that is deliberate rather than left over: a route
returning the right status is a different claim from the stored row holding the
right state, and this file is about the second.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs


@pytest.fixture
def settled(tmp_path):
    """One site with a completed run, so every fingerprint has a live row.

    A real run rather than a hand-written `finding_states` row, because the
    fingerprint the route takes is the one `site_states` hands the screen and
    deriving it any other way would be asserting against a shape the product
    does not serve.
    """
    from tests.test_coverage import DIMS, _Hub, _run

    db = tmp_path / "states.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "State Co")
    site_id = repo.create_site(conn, client, "state.fixture")
    run_id = runs.create_run(conn, site_id, DIMS, "T2")
    runs.complete_run(conn, run_id, _run(_Hub()))
    states = runs.site_states(conn, site_id)
    conn.close()

    assert states, "precondition: the run raised no findings to set a state on"
    api = TestClient(create_app(db_path=db))

    def state_of(fingerprint: str) -> str | None:
        c = connect(db)
        try:
            for s in runs.site_states(c, site_id):
                if s["fingerprint"] == fingerprint:
                    return s["state"]
        finally:
            c.close()
        return None

    return api, site_id, [s["fingerprint"] for s in states], state_of


@pytest.mark.parametrize("state", runs.MODEL_BLIND_STATES)
def test_every_state_the_operator_owns_can_be_set_through_the_api(settled, state):
    """The operator's own judgements are the ones no run can reach, so the
    route is the only way they are ever recorded. One of the two 422'd."""
    api, site_id, fingerprints, state_of = settled
    fingerprint = fingerprints[0]

    resp = api.post(f"/api/sites/{site_id}/states/{fingerprint}",
                    json={"state": state})
    assert resp.status_code == 200, (
        f"{state!r} is in runs.MODEL_BLIND_STATES — a state a run cannot "
        "derive, so the operator's control is the only thing that can ever "
        f"record it — and the route refuses it: {resp.status_code} "
        f"{resp.text!r}")
    assert state_of(fingerprint) == state, (
        f"the route answered 200 for {state!r} and the finding reads "
        f"{state_of(fingerprint)!r} — `runs.set_state` is a bare UPDATE and "
        "no-ops when nothing matches, so a 200 is not evidence on its own")


def test_a_state_a_run_derives_is_still_refused(settled):
    """The negative control, and the reason this is not "accept everything".

    `fixed` says a run looked and the finding was gone. An operator setting it
    by hand writes that claim with no run behind it — WF-61's defect, reached
    through the product's own control instead of through a stale verification.
    Widening the allow-list past the states a person owns is the failure this
    asserts against.
    """
    api, site_id, fingerprints, state_of = settled
    fingerprint = fingerprints[0]
    before = state_of(fingerprint)

    resp = api.post(f"/api/sites/{site_id}/states/{fingerprint}",
                    json={"state": "fixed"})
    assert resp.status_code == 422, (
        "`fixed` is derived by a run's own evidence, and the route accepted it "
        f"by hand: {resp.status_code} {resp.text!r}")
    assert state_of(fingerprint) == before, (
        f"the route refused `fixed` with {resp.status_code} and the finding "
        f"moved {before!r} -> {state_of(fingerprint)!r} anyway")


def test_the_route_reports_a_state_it_did_not_write(settled):
    """WF-95, and the dead end above closed rather than worked around.

    `set_state` was a bare UPDATE with no rowcount check and the route returned
    an unconditional ok, so a POST naming a fingerprint with no row answered
    200 and wrote nothing. `mark_attempt` six lines below it in the same module
    has always raised 404 for exactly that miss; the asymmetry is what this
    closes.

    The fingerprint is deliberately well-formed and simply absent. A malformed
    one would be a different question — whether the route validates its input —
    and the defect here is about a write that was refused by the data rather
    than by the route.
    """
    api, site_id, fingerprints, _ = settled
    absent = "0" * 24
    assert absent not in fingerprints, (
        "precondition: the fingerprint chosen to be absent is one the run "
        "actually raised, so this asserts nothing about a miss")

    resp = api.post(f"/api/sites/{site_id}/states/{absent}",
                    json={"state": "withdrawn"})
    assert resp.status_code == 404, (
        "the route was given a fingerprint with no row and answered "
        f"{resp.status_code} {resp.text!r}. Three verbs on the record screen "
        "write an operator's judgement onto a client's permanent record "
        "through this route; a success it did not verify is indistinguishable "
        "from one it did.")


def test_the_route_names_the_states_it_will_take(settled):
    """A refusal an operator cannot act on is the affordance defect one layer
    down. The detail has to name what would have worked, and it has to name
    the states the route actually takes rather than a copy that can drift from
    them — so it is read back against the registry, not against a literal.
    """
    api, site_id, fingerprints, _ = settled

    resp = api.post(f"/api/sites/{site_id}/states/{fingerprints[0]}",
                    json={"state": "no-such-state"})
    assert resp.status_code == 422, resp.text
    detail = resp.json().get("detail", "")
    for state in runs.MODEL_BLIND_STATES:
        assert state in detail, (
            f"the refusal does not name {state!r}, which the route accepts, so "
            f"an operator is told no and not told what to send: {detail!r}")
