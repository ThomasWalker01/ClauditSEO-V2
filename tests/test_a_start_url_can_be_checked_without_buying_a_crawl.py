"""WF-82: the only way to find out whether the crawler will accept a URL is
to buy a crawl.

First raised in report 065 and carried at **High by every report since** --
065 through 100, thirty-three of them -- with no remediation item proposed
after 065's own item 4 and no disposition ever recorded. It is the oldest
open, undispositioned finding in the register, and it is reached now because
report 051's cohort closed and the walk arrived at report 065.

**Its evidence is an action the operator recorded rather than a line of
code.** `OPERATOR_ACTIONS.md:139` writes up, as unintended, a trailing-dot
control URL -- `https://www.acme.com.au./` -- posted to
`POST /api/sites/{site_id}/audits` to check whether CQ-121's `rstrip` had
landed. It had. The URL was accepted, and accepting it *is* launching: the
route created audit run `d6592874beb14451bb85ffacecafc1dc`, which reached
`status blocked` and is permanent, because WF-81 records that there is no
`DELETE /api/sites/{site_id}`. The route's own note says that this one spent
nothing was luck rather than design.

**The defect is not that validation happens too late.** It does not:
`app.py` calls `_validate_start_url` and raises 422 *before*
`runs.create_run`, so a URL the crawler would refuse already costs nothing.
The defect runs the other way, which is the direction the operator met --
there is no way to ask whether a URL *would be accepted*, because the only
door that answers the question also does the work when the answer is yes.
Report 065 counted three of the four callers of `_validate_start_url` as
having that shape.

**One predicate, two doors -- which is why this check may not restate the
rule.** This function's own history is two doors disagreeing about what a
host is: CQ-121 was a trailing-dot FQDN normalised on the probe path and not
the launch path, and CQ-133 was an unparseable string that was a readable 422
at one door and an unhandled 500 at four others. A check that answered
"acceptable" from its own copy of the logic would be a third door and the
next entry in that list, so
`test_the_check_refuses_exactly_what_the_launch_refuses` compares the two
answers rather than asserting a string.

**Report 065's open question 2 is not registered and does not block this.**
It asks whether the shape should be a read-only route or a `dry_run` flag on
`POST .../audits`, and it never became a `QUESTIONS.md` row -- checked at
HEAD rather than assumed. Report 065's own remediation item 4 chose: *"Add a
read-only start-URL check the operator can call before committing to a run,
and point the audit launcher at it."* That is what this guards. The flag was
not taken because the finding is that the launch route is the only door, and
a mode on that route leaves it the only door.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.persistence import repo
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate

#: The operator's own control, verbatim from `OPERATOR_ACTIONS.md:139`, and
#: the site it was posted against. Kept as data rather than prose so the case
#: below reproduces the recorded action rather than an approximation of it.
RECORDED_DOMAIN = "www.acme.com.au"
RECORDED_CONTROL_URL = "https://www.acme.com.au./"

VIEWS = (pathlib.Path(__file__).resolve().parents[1]
         / "dashboard" / "src" / "views.tsx")


@pytest.fixture()
def launcher(tmp_path, monkeypatch):
    """A site and the launch route, with the worker intercepted.

    Stubbed for the reason `test_a_section_refresh_starts_what_it_says` gives
    for stubbing it: the question here is what the routes DECIDE about a URL,
    and letting the thread through would crawl a real domain to answer it.
    The stub also means that a case which accidentally launches still leaves
    its row in `audit_runs` to be counted -- which is what the no-run
    assertions below read.
    """
    from clauditseo.api import app as app_mod

    db = tmp_path / "wf82.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Acme")
    site_id = repo.create_site(conn, client, RECORDED_DOMAIN)

    monkeypatch.setattr(app_mod, "_execute_run", lambda *a, **k: None)
    yield conn, TestClient(create_app(db_path=db)), site_id
    conn.close()


def _runs(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM audit_runs").fetchone()["n"]


def _check(api, site_id: str, url: str):
    return api.get(f"/api/sites/{site_id}/start-url-check", params={"url": url})


# --- the defect -------------------------------------------------------------

def test_a_start_url_can_be_checked_without_starting_anything(launcher):
    """The question the operator had, asked without buying the answer."""
    conn, api, site_id = launcher
    assert _runs(conn) == 0, "the fixture already holds a run"

    resp = _check(api, site_id, "https://www.acme.com.au/pricing")

    assert resp.status_code == 200, resp.text
    assert resp.json()["acceptable"] is True, resp.json()
    assert resp.json()["problem"] is None, resp.json()
    assert _runs(conn) == 0, (
        "asking whether a start URL is acceptable created an audit run -- "
        "which is WF-82 itself, now with an extra door")


def test_the_operator_s_recorded_control_no_longer_costs_a_run(launcher):
    """`OPERATOR_ACTIONS.md:139`, reproduced and made free.

    The recorded action is the trailing-dot host: it *is* acceptable, and
    that is precisely why it cost a run -- the launch route's way of saying
    yes is to start the audit. Asserting `acceptable is True` rather than
    `False` is the point of the case.
    """
    conn, api, site_id = launcher

    resp = _check(api, site_id, RECORDED_CONTROL_URL)

    assert resp.status_code == 200, resp.text
    assert resp.json()["acceptable"] is True, (
        f"{RECORDED_CONTROL_URL} reads unacceptable against "
        f"{RECORDED_DOMAIN}; CQ-121's rstrip is what makes it acceptable, so "
        f"this is either a regression of CQ-121 or a second copy of the rule")
    assert _runs(conn) == 0, (
        "the operator's control still creates a permanent run; WF-81 records "
        "that there is no route to delete it")


def test_the_check_refuses_exactly_what_the_launch_refuses(launcher):
    """Two doors, one predicate -- compared rather than restated.

    The refusal string is not written down here. It is read off the launch
    route's own 422 and required to be the answer the check gives, so a
    change to `_validate_start_url`'s wording cannot leave the two doors
    disagreeing while both still pass.
    """
    conn, api, site_id = launcher
    off_site = "https://not-the-clients-site.example/"

    launched = api.post(f"/api/sites/{site_id}/audits",
                        json={"dims": ["ONP"], "tier": "T1",
                              "start_url": off_site})
    assert launched.status_code == 422, launched.text
    refusal = launched.json()["detail"]

    checked = _check(api, site_id, off_site)
    assert checked.status_code == 200, checked.text
    assert checked.json()["acceptable"] is False, checked.json()
    assert checked.json()["problem"] == refusal, (
        "the check and the launch give different reasons for refusing the "
        "same URL, which is the CQ-121/CQ-133 shape one door along")


def test_the_launcher_offers_the_check_beside_the_field(launcher):
    """Report 065 item 4's second half: *point the audit launcher at it*.

    A route nobody can reach from the screen leaves the operator where they
    were -- reaching for curl, which is how the recorded action happened.
    Read from `views.tsx` source rather than from a built bundle so that
    `scripts/prove_fail.py` can answer this case; its own docstring rejects
    tests whose subject is `dashboard/dist`.
    """
    src = VIEWS.read_text(encoding="utf-8")
    assert "start-url-check" in src, (
        "the launcher screen never calls the read-only check, so the only "
        "way to find out whether a start URL is acceptable is still to press "
        "Run audit")


# --- counter-assertions: floors this fix must not withdraw -------------------

def test_a_valid_start_url_still_starts_a_run(launcher):
    """The capability the check is added beside, not in place of."""
    conn, api, site_id = launcher

    resp = api.post(f"/api/sites/{site_id}/audits",
                    json={"dims": ["ONP"], "tier": "T1",
                          "start_url": "https://www.acme.com.au/pricing"})

    assert resp.status_code == 202, resp.text
    assert _runs(conn) == 1, "the launch route stopped creating runs"


def test_an_off_site_start_url_still_buys_nothing(launcher):
    """The floor that was already holding, asserted so that the new door
    cannot be read as having introduced it."""
    conn, api, site_id = launcher

    resp = api.post(f"/api/sites/{site_id}/audits",
                    json={"dims": ["ONP"], "tier": "T1",
                          "start_url": "https://not-the-clients-site.example/"})

    assert resp.status_code == 422, resp.text
    assert _runs(conn) == 0, "a refused start URL created a run"
