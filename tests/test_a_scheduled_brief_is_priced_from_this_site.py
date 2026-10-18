"""UX-77: the price on a site's schedule screen is drawn from that site.

**The operator answered the question this guard was waiting on.** Report 080
asked it and reports 081, 083, 084 and 085 carried it unanswered; it is Q-1 in
`QUESTIONS.md`, and the answer is *per site* (operator, 2026-08-22), carried
here by relay item 071. So the schedule screen's brief price is a per-site
figure, and this file is the guard that says so in a way that can fail.

**What the defect was.** `expert_estimates` selected from `expert_reports` with
no site filter, and `GET /api/sites/{id}/schedule` called it as
`runs.expert_estimates(conn)`, under copy on that screen reading "the price
shown is what that brief has actually cost here before - not an estimate". So a
recurring spend was committed for one client against a price measured on
another, under a sentence stating the opposite. Measured read-only against
`data/clauditseo.db` at report 085: 38 stored briefs across four sites -
`www.acme.com.au` 25, `https://www.13acme.com.au/` 11, `twenty22.co` 1, and
the `seed-normal.test` fixture 1 - all in one population.

**The fixture row is in the fixture below on purpose.** KI-50 is that a seed
site's priced brief sits inside the live population every unscoped surface
reads. Under the per-site answer that disposes of itself by construction
rather than by a rule about test data, and the only way to show *that* is to
put a fixture site in the population and assert it does not reach a real one's
price.

**The populations are chosen so that no assertion can pass by accident**
(DISCIPLINE rule 5). One site holds a single `0.10` brief, another two at
`5.00`, the fixture site one at `0.00`: the install-wide median is `2.55` and
differs from every site's own median, so a guard reading the unscoped figure
cannot report the scoped one.

**Pure Python, deliberately** - nothing here loads `dashboard/dist`, so
`scripts/prove_fail.py` can answer for this file.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

# domain -> the costs its stored `indexability` briefs carry. One row per
# (run, tool) is enforced by the table, so each sample needs its own run.
POPULATION = {
    "voltaic.test": (0.10,),
    "acme.test": (5.00, 5.00),
    "seed-normal.test": (0.00,),
}

# What the unscoped estimator returns over all four rows: sorted
# [0.0, 0.1, 5.0, 5.0], so the median is the mean of the middle pair. Written
# out because it is the number every assertion below is defined against.
INSTALL_WIDE = 2.55


def _seed(conn) -> None:
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Three Sites Co")
    for domain, costs in POPULATION.items():
        site = repo.create_site(conn, client, domain)
        for cost in costs:
            run_id = runs.create_run(conn, site, ["TEC"], "T2")
            runs.store_expert_report(conn, run_id, "indexability",
                                     {"model": "m", "report": "r",
                                      "tokens": 30_000, "cost": cost})


@pytest.fixture
def three_site_db(tmp_path):
    path = tmp_path / "per-site-price.db"
    conn = connect(path)
    migrate(conn)
    _seed(conn)
    conn.close()
    return path


@pytest.fixture
def sites(three_site_db):
    conn = connect(three_site_db)
    try:
        client = repo.list_clients(conn)[0]["id"]
        return {s["domain"]: s["id"] for s in repo.list_sites(conn, client)}
    finally:
        conn.close()


def _schedule_row(api, site_id, tool_id="indexability"):
    payload = api.get(f"/api/sites/{site_id}/schedule").json()
    return next(a for a in payload["available"] if a["tool_id"] == tool_id)


def test_the_schedule_screen_prices_a_brief_from_this_site_alone(
        three_site_db, sites, monkeypatch):
    """The finding, at the boundary the operator commits money across.

    `0.10` is what this brief has cost on `voltaic.test`. `2.55` is what it has
    cost across an install the operator was never shown, and it is the number
    the modal multiplied by a cadence into an annual forecast.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    api = TestClient(create_app(db_path=three_site_db))

    row = _schedule_row(api, sites["voltaic.test"])

    assert row["typical_cost"] != INSTALL_WIDE, (
        "the schedule screen prices this site's brief from every site's "
        "history, under copy saying the price is what it has cost here")
    assert row["typical_cost"] == 0.10
    assert row["cost_samples"] == 1, (
        "the price is scoped to this site but the count beside it is not, so "
        "the frame and the figure describe different populations")
    assert row["samples"] == 1


def test_a_second_site_gets_its_own_price_from_the_same_install(
        three_site_db, sites, monkeypatch):
    """Two sites, one database, two different answers.

    A single-site assertion cannot tell a working filter from an estimator
    that happens to return the first site's number.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    api = TestClient(create_app(db_path=three_site_db))

    row = _schedule_row(api, sites["acme.test"])

    assert row["typical_cost"] == 5.00
    assert row["cost_samples"] == 2


def test_a_fixture_sites_brief_never_prices_a_real_sites_brief(
        three_site_db, sites, monkeypatch):
    """KI-50, disposed of by construction rather than by a rule.

    `seed-normal.test` carries a `0.00` brief. Under the per-site answer it
    prices `seed-normal.test` and nothing else, so no rule about excluding
    test data is owed.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    api = TestClient(create_app(db_path=three_site_db))

    assert _schedule_row(api, sites["seed-normal.test"])["typical_cost"] == 0.00
    for domain in ("voltaic.test", "acme.test"):
        row = _schedule_row(api, sites[domain])
        assert row["cost_samples"] == len(POPULATION[domain]), (
            domain + "'s price is drawn from a population this site does not "
            "have, so the fixture site's brief is inside a real site's price")


def test_the_schedule_payload_says_which_site_the_price_covers(
        three_site_db, sites, monkeypatch):
    """The scope travels with the value, at the wire.

    The endpoint re-serialises the estimator field by field, so a scope
    computed upstream is dropped here unless it is carried deliberately -
    the shape that lost the TLS floor between the probe that measured it and
    the panel that needed it (B-11). Without this key a reader cannot tell a
    scoped figure from an unscoped one that happens to agree.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    api = TestClient(create_app(db_path=three_site_db))

    row = _schedule_row(api, sites["voltaic.test"])

    assert row["scoped_to_site"] == sites["voltaic.test"]


def test_the_estimator_takes_a_site_and_the_unscoped_call_still_works(
        three_site_db):
    """The estimator is the owner; the two populations, side by side.

    The unscoped call is asserted rather than removed because it is still
    reachable: `site_id` is optional everywhere it is taken, so a caller with
    no site in hand gets the install-wide figure by asking for nothing.

    **This paragraph used to name `/api/playbook` as that caller, and it was
    wrong.** That route is fetched by `dashboard/src/tools.tsx` and
    `dashboard/src/expert.tsx` with a site already chosen, and both paint the
    figure beside a control that spends money — UX-77, carried at High through
    six reports and fixed by relay item 083, which passes `site_id` there and
    at the two run routes and the triage prompt.
    `tests/test_a_brief_is_priced_from_this_site_on_every_surface.py` is that
    half's guard. What survives of the original claim is only the shape: an
    optional filter, and a default that means install-wide.
    """
    conn = connect(three_site_db)
    try:
        client = repo.list_clients(conn)[0]["id"]
        ids = {s["domain"]: s["id"] for s in repo.list_sites(conn, client)}
        install_wide = runs.expert_estimates(conn)["indexability"]
        scoped = runs.expert_estimates(
            conn, site_id=ids["voltaic.test"])["indexability"]
    finally:
        conn.close()

    assert install_wide["cost"] == INSTALL_WIDE
    assert install_wide["cost_samples"] == 4
    assert install_wide["scoped_to_site"] is None
    assert scoped["cost"] == 0.10
    assert scoped["cost_samples"] == 1
    assert scoped["scoped_to_site"] == ids["voltaic.test"]
