"""CQ-147. The expert page route must refuse before it spends when its fetch
did not return 200 — the refusal both sibling on-demand page routes make.

`Fetcher.fetch` does not raise: an `httpx.HTTPError` comes back as
`Page(status=0, error=...)`, and a 404 comes back as a `Page` with a status
and no error. `page_advisor` and `schema_advisor` each test
`page.error or page.status != 200` and return an `unavailable` envelope naming
what came back; the expert route assigned the object into `extra["page"]` and
fell through to `run_expert`, which resolves a model and bills.

**Why this asserts three things and not just the response.** An `unavailable`
envelope returned *after* the model ran is indistinguishable from one returned
before it — `run_expert` produces that same shape when a provider is missing,
so a test reading only the body would pass against the unfixed route. So the
assertions are: the envelope names the fetch status, `run_expert` was never
reached, and the ledger carries no row for the run. The middle one is what can
disagree with the unfixed code; the last is the operator-facing invariant, and
it would catch a later refusal moved to the wrong side of the call.

The population is derived from `EXPERT_TOOLS` rather than listed, because the
branch is shared by every page-scoped tool and a hard-coded list of three is
how a partial fix passes (DISCIPLINE rule 3).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import clauditseo.analysts.expert as expert_mod
from clauditseo.api.app import create_app
from clauditseo.crawler.fetch import Fetcher
from clauditseo.crawler.types import Page
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

DOMAIN = "example.com"
TARGET = f"https://{DOMAIN}/a-page-that-does-not-answer"

#: Every page-scoped tool, read from the product's own registry at import
#: time rather than listed here.
PAGE_TOOLS = sorted(t for t, v in expert_mod.EXPERT_TOOLS.items()
                    if v["scope"] == "page")

#: The two shapes `Fetcher.fetch` returns for a fetch that did not succeed:
#: `error` set with status 0 for a transport failure, status alone for an
#: HTTP refusal. `page.error or page.status != 200` is one condition covering
#: both, so both are driven.
FAILURES = {
    "transport": dict(status=0,
                      error="ConnectError: [Errno -2] Name or service not known"),
    "http-404": dict(status=404, error=None),
}


def _api(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDITSEO_ALLOW_ARBITRARY_START_URL", raising=False)
    db = tmp_path / "expert-refusal.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client_id = repo.create_client(conn, op, "Refusal Co")
    site_id = repo.create_site(conn, client_id, DOMAIN)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    conn.close()
    return TestClient(create_app(db_path=db)), db, run_id


def _fetch_that_fails(monkeypatch, **failure):
    """robots.txt answers normally; the target does not.

    Robots has to succeed for the test to reach the branch under test at all —
    a failed robots fetch is answered by a different refusal a few lines
    above it, and a test taking that exit would pass without ever running the
    code it names.
    """
    def fake_fetch(self, url: str) -> Page:
        if url.endswith("/robots.txt"):
            return Page(url=url, requested_url=url, status=200,
                        content="User-agent: *\nAllow: /\n",
                        content_type="text/plain")
        return Page(url=url, requested_url=url, **failure)
    monkeypatch.setattr(Fetcher, "fetch", fake_fetch)


def _spy_on_spending(monkeypatch):
    """Record any attempt to resolve a model or run a brief, and let it
    succeed. Raising instead would make the unfixed route answer 500, which is
    a different signal from the one this guard is about.
    """
    reached: list[str] = []
    real_model_for_tool = expert_mod.model_for_tool

    def spy_run_expert(*args, **kwargs):
        reached.append("run_expert")
        return {"status": "ok", "report": "a brief that should not exist"}

    def spy_model_for_tool(*args, **kwargs):
        reached.append("model_for_tool")
        return real_model_for_tool(*args, **kwargs)

    monkeypatch.setattr(expert_mod, "run_expert", spy_run_expert)
    monkeypatch.setattr(expert_mod, "model_for_tool", spy_model_for_tool)
    return reached


def _ledger_rows(db, run_id: str) -> list:
    conn = connect(db)
    try:
        return conn.execute(
            "SELECT operation, quantity FROM cost_entries WHERE run_id=?",
            (run_id,)).fetchall()
    finally:
        conn.close()


@pytest.mark.parametrize("tool_id", PAGE_TOOLS)
def test_no_page_scoped_brief_spends_on_a_fetch_that_did_not_return_200(
        tmp_path, monkeypatch, tool_id):
    client, db, run_id = _api(tmp_path, monkeypatch)
    _fetch_that_fails(monkeypatch, **FAILURES["http-404"])
    reached = _spy_on_spending(monkeypatch)

    answer = client.post(f"/api/runs/{run_id}/expert/{tool_id}",
                         json={"url": TARGET})

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["status"] == "unavailable", body
    assert "could not fetch the page" in body.get("reason", ""), body
    assert "404" in body["reason"], body["reason"]
    assert reached == [], (
        f"{tool_id}: the route reached {reached} after a fetch that returned "
        "404 — a model was resolved on evidence the server does not have")
    assert _ledger_rows(db, run_id) == [], (
        f"{tool_id}: a cost ledger row was written for a page that was never "
        "retrieved")


@pytest.mark.parametrize("shape", sorted(FAILURES))
def test_both_shapes_of_a_failed_fetch_are_refused_and_named(
        tmp_path, monkeypatch, shape):
    """The control for the parametrisation above. `page.error or
    page.status != 200` is one condition covering two shapes, and a fix
    testing only the status would let every transport failure through — that
    `Page` carries `status=0`, which is falsy in the wrong hands.
    """
    client, db, run_id = _api(tmp_path, monkeypatch)
    _fetch_that_fails(monkeypatch, **FAILURES[shape])
    reached = _spy_on_spending(monkeypatch)

    answer = client.post(f"/api/runs/{run_id}/expert/content-brief",
                         json={"url": TARGET})

    body = answer.json()
    assert body["status"] == "unavailable", body
    expected = FAILURES[shape]["error"] or str(FAILURES[shape]["status"])
    assert expected in body["reason"], (
        f"{shape}: the refusal does not say what came back — "
        f"{body['reason']!r}")
    assert reached == [], f"{shape}: the route reached {reached}"
    assert _ledger_rows(db, run_id) == [], f"{shape}: a ledger row was written"


def test_a_fetch_that_did_return_200_still_reaches_the_brief(
        tmp_path, monkeypatch):
    """The other control, and the one that stops this guard being satisfied by
    a route that refuses everything. A 200 must still spend.
    """
    client, db, run_id = _api(tmp_path, monkeypatch)

    def fake_fetch(self, url: str) -> Page:
        if url.endswith("/robots.txt"):
            return Page(url=url, requested_url=url, status=200,
                        content="User-agent: *\nAllow: /\n",
                        content_type="text/plain")
        return Page(url=url, requested_url=url, status=200,
                    content="<html><head><title>A page</title></head>"
                            "<body><h1>A page</h1></body></html>",
                    content_type="text/html")
    monkeypatch.setattr(Fetcher, "fetch", fake_fetch)
    reached = _spy_on_spending(monkeypatch)

    answer = client.post(f"/api/runs/{run_id}/expert/content-brief",
                         json={"url": TARGET})

    assert answer.status_code == 200, answer.text
    assert "run_expert" in reached, (
        "a page that fetched cleanly was refused — the guard is not a "
        "condition, it is a wall")
