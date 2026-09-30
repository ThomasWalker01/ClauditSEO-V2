"""UX-77: every surface that prices a brief prices it from the site in front of you.

**The other half of a fix that landed on one screen of four.** Relay item 071
carried `QUESTIONS.md` Q-1's answer — *per site* (operator, 2026-08-22) — into
`expert_estimates` and into `GET /api/sites/{id}/schedule`, and
`tests/test_a_scheduled_brief_is_priced_from_this_site.py` is that screen's
guard. Its neighbours were not changed. Reports 088, 090, 091, 092, 094 and 095
carried UX-77 at High for exactly that reason, ranked first in every one of
them: three more surfaces and the dispatcher prompt still called
`expert_estimates` with no site.

**Where the price is read matters more than how many places read it.** The two
screens this covers are the two on which a brief is *bought* — the Tools
workbench and the Brief panel — and the fourth reader is the SPEND NEXT table
inside the triage prompt, which is the model's only evidence when it recommends
a purchase. So one client's measured cost was presented as another's beside the
control that spends it, and again to the model that advises spending it. That
is failure class 1 in the money, and it is why the finding outranked its own
remedy's size.

**`/api/playbook`'s own comment argued the opposite, and this file is the
disagreement resolved.** It read *"deliberately not changed by that answer — the
question was about a screen showing one site's price, and this screen shows
none"*. True of the endpoint's name; false of both its callers, which fetch it
with a site already chosen and paint the figure beside a paid control. The route
keeps its unscoped behaviour when given no `site_id`, so a caller that really is
install-wide is unaffected — and `test_the_unscoped_call_is_still_install_wide`
below holds that door open rather than assuming it.

**The populations are chosen so that no assertion can pass by accident**
(DISCIPLINE rule 5), on the same principle as the schedule guard: one site holds
a single `0.10` brief, another two at `5.00`, the fixture site one at `0.00`, so
the install-wide median is `2.55` and differs from every site's own. A surface
reading the unscoped figure cannot report a scoped one.

**Pure Python, deliberately** — nothing here loads `dashboard/dist`, so
`scripts/prove_fail.py` can answer for this file.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

TOOL = "indexability"

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


def _seed(conn) -> dict[str, str]:
    """Three sites, one shared install, plus one *bare* run per site.

    The bare run carries no expert report on purpose. `_triage_data` and the
    workbench both skip a tool that has already run against the run in hand, so
    a run that priced the brief cannot be the run used to ask what the brief
    would cost.
    """
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Three Sites Co")
    bare = {}
    for domain, costs in POPULATION.items():
        site = repo.create_site(conn, client, domain)
        for cost in costs:
            run_id = runs.create_run(conn, site, ["TEC"], "T2")
            runs.store_expert_report(conn, run_id, TOOL,
                                     {"model": "m", "report": "r",
                                      "tokens": 30_000, "cost": cost})
        bare[domain] = runs.create_run(conn, site, ["TEC"], "T2")
    return bare


@pytest.fixture
def three_site_db(tmp_path):
    path = tmp_path / "per-surface-price.db"
    conn = connect(path)
    migrate(conn)
    bare = _seed(conn)
    conn.close()
    return path, bare


@pytest.fixture
def sites(three_site_db):
    path, _ = three_site_db
    conn = connect(path)
    try:
        client = repo.list_clients(conn)[0]["id"]
        return {s["domain"]: s["id"] for s in repo.list_sites(conn, client)}
    finally:
        conn.close()


@pytest.fixture
def api(three_site_db, monkeypatch):
    path, _ = three_site_db
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    return TestClient(create_app(db_path=path))


def _brief(api, tool=TOOL, site_id=None):
    q = f"?site_id={site_id}" if site_id else ""
    return api.get(f"/api/playbook{q}").json()["experts"][tool]


# -- the workbench and the Brief panel: /api/playbook ------------------------

def test_the_workbench_prices_a_brief_from_the_chosen_site(api, sites):
    """`dashboard/src/tools.tsx` fetches this route with a site selected.

    `0.10` is what this brief has cost on `voltaic.test`. `2.55` is what it has
    cost across an install the operator was never shown, painted beside the
    control that buys the brief.
    """
    row = _brief(api, site_id=sites["voltaic.test"])

    assert row["typical_cost"] != INSTALL_WIDE, (
        "the workbench prices this site's brief from every site's history, "
        "beside the control that spends money on it")
    assert row["typical_cost"] == 0.10
    assert row["runs_costed"] == 1, (
        "the price is scoped to this site but the count beside it is not, so "
        "the frame and the figure describe different populations")
    assert row["runs_sampled"] == 1


def test_a_second_site_gets_its_own_price_from_the_same_install(api, sites):
    """Two sites, one database, two different answers.

    A single-site assertion cannot tell a working filter from an endpoint that
    happens to return the first site's number.
    """
    row = _brief(api, site_id=sites["acme.test"])

    assert row["typical_cost"] == 5.00
    assert row["runs_costed"] == 2


def test_the_workbench_payload_says_which_site_the_price_covers(api, sites):
    """The scope travels with the value, at the wire.

    This endpoint re-serialises the estimator field by field, so a scope
    computed upstream is dropped unless it is carried deliberately. It matters
    more here than on the schedule route: one path now answers both ways
    depending on a query parameter, so a reader cannot infer the scope from the
    URL either. Giving the key a *reader* is CQ-198 and is not asserted here.
    """
    assert _brief(api, site_id=sites["voltaic.test"])["scoped_to_site"] == \
        sites["voltaic.test"]
    assert _brief(api)["scoped_to_site"] is None


def test_the_unscoped_call_is_still_install_wide(api):
    """The door the fix deliberately leaves open.

    `site_id` is optional because a caller genuinely not looking at a site
    wants the install-wide figure, and the route is still reached that way.
    Asserted rather than assumed, so that "scope it everywhere" cannot later be
    read as "scope it unconditionally".
    """
    row = _brief(api)

    assert row["typical_cost"] == INSTALL_WIDE
    assert row["runs_costed"] == 4


def test_an_unknown_site_is_refused_rather_than_quietly_widened(api):
    """A bad id must not degrade to the figure it was passed to avoid.

    The failure mode worth guarding is not a crash: it is a route that ignores
    an id it cannot resolve and answers install-wide anyway, which is the exact
    defect wearing the fix's clothes.
    """
    resp = api.get("/api/playbook?site_id=no-such-site")

    assert resp.status_code == 404
    assert "site" in resp.json()["detail"]


# -- the run surfaces: /api/runs/{id}/expert and /analyses -------------------

def test_the_run_brief_index_prices_from_the_runs_own_site(api, three_site_db,
                                                           sites):
    """A run belongs to exactly one site, so there is no install-wide reading.

    `check_run` already resolved the run in order to authorise it; its
    `site_id` was being thrown away one line later.
    """
    _, bare = three_site_db
    payload = api.get(f"/api/runs/{bare['voltaic.test']}/expert").json()

    est = payload["estimates"][TOOL]
    assert est["cost"] == 0.10
    assert est["scoped_to_site"] == sites["voltaic.test"]


def test_the_analyses_lanes_price_from_the_runs_own_site(api, three_site_db):
    """The same figure again, through `analyses.lanes`.

    Both run routes are asserted rather than one: they build their estimates
    independently, and the finding cited both.
    """
    _, bare = three_site_db
    payload = api.get(f"/api/runs/{bare['acme.test']}/analyses").json()

    row = next(r for r in (*payload["ready"], *payload["available"])
               if r["tool"] == TOOL)
    assert row["est_cost"] == 5.00


def test_two_runs_on_two_sites_disagree_about_the_same_brief(api,
                                                             three_site_db):
    """The pair, so neither route can pass by returning a constant."""
    _, bare = three_site_db

    def cost(domain):
        return api.get(f"/api/runs/{bare[domain]}/expert") \
                  .json()["estimates"][TOOL]["cost"]

    assert cost("voltaic.test") == 0.10
    assert cost("acme.test") == 5.00


# -- the dispatcher prompt: SPEND NEXT --------------------------------------

def test_the_spend_next_prices_the_model_reads_are_this_sites(three_site_db,
                                                              sites,
                                                              monkeypatch):
    """The reader most exposed, and the one with no screen to check it against.

    `_triage_data` held `site_id` two lines above the call and passed only
    `pages`, so the prices inside the prompt that recommends a purchase were
    medians across every client. A model cannot notice that the figure is about
    somebody else; an operator reading a screen at least might.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    from clauditseo.api.app import _triage_data
    from clauditseo.config import settings

    path, bare = three_site_db
    conn = connect(path)
    try:
        run = runs.get_run(conn, bare["voltaic.test"])
        data = _triage_data(conn, run, {"id": sites["voltaic.test"]},
                            settings(), {"pages": []})
    finally:
        conn.close()

    price = next(t["price"] for t in data["available_briefs"]
                 if t["tool"] == TOOL)
    assert "0.10" in price, (
        f"the SPEND NEXT table offers this brief at {price!r}, which is not "
        "what it has cost on this site")
    assert "2.55" not in price
