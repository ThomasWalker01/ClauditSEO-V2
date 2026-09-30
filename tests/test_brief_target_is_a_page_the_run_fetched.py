"""WF-89. A page-scoped brief's target, when the caller supplies none, must be
a page the run actually fetched — resolved against the same list the picker
offers, not read out of `start_url`.

`start_url` is the URL the crawl was *handed*, not one it retrieved. A `Page`
survives a failed fetch, so a run can carry a `start_url` and no eligible page
at all. The boundary read `(body.url if body else None) or
evidence.get("start_url")` and checked the result with `_validate_start_url`,
which judges the host and nothing else; the client omits `url` exactly when its
picker resolved to nothing (`tools.tsx:498,536` spread
`pageUrl ? { url: pageUrl } : {}`). So the two ends met at the one state
neither covers.

**Reproduced against the operator's own database rather than argued.** Of 13
`audit_runs` rows, 10 carry crawl evidence and 3 hold a `start_url` outside
their own eligible page list. One of the three, `d6592874`, is
`status='blocked' kind='audit'` on the real client site `www.acme.com.au`:
one page, `https://www.acme.com.au./`, `status: 0`, empty content type — so
zero eligible — and `_validate_start_url` passes that trailing-dot host. The
run is offered in the app's run bar with the Run button enabled. The two
fixtures below are that run's shape and `d4474b38`'s, which has eight eligible
pages and a `start_url` that is not among them.

**Why this asserts the ledger and the model, not only the status code.** The
sibling guard `test_expert_page_fetch_refusal.py` records the reason: an
envelope returned *after* a model ran is indistinguishable from one returned
before it. A 422 raised downstream of the spend would look identical from the
client, and that is the shape of failure this repository has shipped before.

**Why the population is derived.** Every page-scoped tool shares the branch, so
`EXPERT_TOOLS` is read at import rather than three names being listed here —
DISCIPLINE rule 3, a hard-coded list of three is how a partial fix passes.

**What this deliberately does not cover.** A `url` supplied in the body is
still checked for host only. Report 072 row 2 scopes the fix to the fallback,
its row 11 assigns class-level closure to the source fix that is gated on open
question 2, and no instance of a caller naming an unfetched page has been
observed. Stated here so the gap is a decision on the record rather than an
oversight the next reader has to rediscover.
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

DOMAIN = "acme.com.au"

#: The handed URL, taken verbatim from run `d6592874`. The trailing dot is
#: load-bearing: it is what `_validate_start_url` normalises away (CQ-121), so
#: this host passes the only check the boundary made.
HANDED = "https://www.acme.com.au./"

#: Every page-scoped tool, from the product's own registry.
PAGE_TOOLS = sorted(t for t, v in expert_mod.EXPERT_TOOLS.items()
                    if v["scope"] == "page")


def _page(url: str, status: int, content_type: str, depth: int = 0) -> dict:
    """One row in the shape `crawl_evidence` stores and `run_pages` reads."""
    return {"url": url, "requested_url": url, "status": status,
            "content_type": content_type, "click_depth": depth,
            "title": "A page", "word_count": 120}


#: `d6592874`'s shape: the crawl was handed a URL, attempted it, and retrieved
#: nothing. `status: 0` with an empty content type is what a transport failure
#: leaves behind.
NOTHING_FETCHED = {
    "start_url": HANDED,
    "pages": [_page(HANDED, 0, "")],
}

#: `d4474b38`'s shape: pages were fetched, and the handed URL is not one of
#: them. The picker resolves this to its first offered page, so the boundary
#: must too — refusing here would refuse a run the operator can work with.
FETCHED_BUT_NOT_THE_START = {
    "start_url": "http:www.acme.com.au",
    "pages": [_page(f"https://www.{DOMAIN}/about", 200, "text/html", depth=1),
              _page(f"https://www.{DOMAIN}/contact", 200, "text/html", depth=1)],
}

#: The control: the ordinary run every other test in the suite describes.
FETCHED_INCLUDING_THE_START = {
    "start_url": f"https://www.{DOMAIN}/",
    "pages": [_page(f"https://www.{DOMAIN}/deep", 200, "text/html", depth=3),
              _page(f"https://www.{DOMAIN}/", 200, "text/html", depth=0)],
}


def _api(tmp_path, monkeypatch, evidence: dict):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDITSEO_ALLOW_ARBITRARY_START_URL", raising=False)
    db = tmp_path / "brief-target.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client_id = repo.create_client(conn, op, "Acme")
    site_id = repo.create_site(conn, client_id, DOMAIN)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_evidence(conn, run_id, evidence)
    conn.close()
    return TestClient(create_app(db_path=db)), db, run_id


def _spy(monkeypatch):
    """Record any attempt to resolve a model or run a brief, and let it
    succeed — raising would answer 500, a different signal from this one.
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


def _fetch_succeeds(monkeypatch, seen: list[str] | None = None):
    """Every fetch answers 200 HTML.

    Deliberately permissive: with CQ-147's refusal in place a failing fetch
    would produce an `unavailable` envelope, and this guard would then pass
    for the wrong reason on the unfixed route. The target must be *reachable*
    for the question "was it a page this run fetched" to be the only one
    being asked.
    """
    def fake_fetch(self, url: str) -> Page:
        if seen is not None and not url.endswith("/robots.txt"):
            seen.append(url)
        if url.endswith("/robots.txt"):
            return Page(url=url, requested_url=url, status=200,
                        content="User-agent: *\nAllow: /\n",
                        content_type="text/plain")
        return Page(url=url, requested_url=url, status=200,
                    content="<html><head><title>A page</title></head>"
                            "<body><h1>A page</h1></body></html>",
                    content_type="text/html")
    monkeypatch.setattr(Fetcher, "fetch", fake_fetch)


def _ledger_rows(db, run_id: str) -> list:
    conn = connect(db)
    try:
        return conn.execute(
            "SELECT operation, quantity FROM cost_entries WHERE run_id=?",
            (run_id,)).fetchall()
    finally:
        conn.close()


@pytest.mark.parametrize("tool_id", PAGE_TOOLS)
def test_no_page_scoped_brief_runs_against_a_run_that_fetched_nothing(
        tmp_path, monkeypatch, tool_id):
    client, db, run_id = _api(tmp_path, monkeypatch, NOTHING_FETCHED)
    _fetch_succeeds(monkeypatch)
    reached = _spy(monkeypatch)

    answer = client.post(f"/api/runs/{run_id}/expert/{tool_id}", json={})

    assert answer.status_code == 422, (
        f"{tool_id}: the route answered {answer.status_code} for a run that "
        f"retrieved no page — {answer.text}")
    assert reached == [], (
        f"{tool_id}: the route reached {reached} for a run whose only page "
        "was never retrieved")
    assert _ledger_rows(db, run_id) == [], (
        f"{tool_id}: a cost ledger row was written against a run with no "
        "page a brief could read")


def test_the_refusal_names_the_run_so_the_operator_can_act_on_it(
        tmp_path, monkeypatch):
    """A 422 that does not say which run is a message the operator cannot use:
    the run bar offers several, and the one at fault is not the one named on
    screen anywhere else.
    """
    client, _db, run_id = _api(tmp_path, monkeypatch, NOTHING_FETCHED)
    _fetch_succeeds(monkeypatch)
    _spy(monkeypatch)

    answer = client.post(f"/api/runs/{run_id}/expert/content-brief", json={})

    detail = answer.json().get("detail", "")
    assert run_id in detail, (
        f"the refusal does not name the run it is about — {detail!r}")


def test_the_target_falls_back_to_a_page_the_run_did_fetch(
        tmp_path, monkeypatch):
    """The other half of the fix, and the one that stops it being a wall.

    A handed URL absent from the page list is the ordinary shape of a redirect
    or a normalisation, and the picker answers it by offering the first page it
    has. The boundary must resolve the same way, against the same list, or the
    screen and the server disagree about what the operator chose.
    """
    client, _db, run_id = _api(tmp_path, monkeypatch,
                               FETCHED_BUT_NOT_THE_START)
    fetched: list[str] = []
    _fetch_succeeds(monkeypatch, seen=fetched)
    reached = _spy(monkeypatch)

    answer = client.post(f"/api/runs/{run_id}/expert/content-brief", json={})

    assert answer.status_code == 200, answer.text
    assert "run_expert" in reached, (
        "a run with two fetched pages was refused — the fallback resolved to "
        "nothing where the picker would have offered a page")
    assert fetched and fetched[0] == f"https://www.{DOMAIN}/about", (
        "the brief did not read the page the picker offers first — "
        f"{fetched!r}")
    assert FETCHED_BUT_NOT_THE_START["start_url"] not in fetched, (
        "the handed start_url was fetched, and this run never retrieved it")


def test_a_start_url_the_run_did_fetch_is_still_the_default_target(
        tmp_path, monkeypatch):
    """The control for the control. The homepage stays the default where it is
    a page the run holds — the ordering `run_pages` already applies, which is
    why this fixture lists the deep page first.
    """
    client, _db, run_id = _api(tmp_path, monkeypatch,
                               FETCHED_INCLUDING_THE_START)
    fetched: list[str] = []
    _fetch_succeeds(monkeypatch, seen=fetched)
    reached = _spy(monkeypatch)

    answer = client.post(f"/api/runs/{run_id}/expert/content-brief", json={})

    assert answer.status_code == 200, answer.text
    assert "run_expert" in reached, "an ordinary run was refused"
    assert fetched and fetched[0] == f"https://www.{DOMAIN}/", (
        f"the default target is no longer the fetched start_url — {fetched!r}")


def test_the_picker_and_the_boundary_read_one_list(tmp_path, monkeypatch):
    """The structural half, asserted rather than left to review.

    `run_pages` is what the picker renders and the boundary is what honours
    the choice; while each filtered the evidence itself they could disagree,
    and the disagreement would be invisible until an operator picked the page
    that fell between them. This drives both ends of the same run and compares
    the answers.
    """
    client, _db, run_id = _api(tmp_path, monkeypatch,
                               FETCHED_BUT_NOT_THE_START)
    fetched: list[str] = []
    _fetch_succeeds(monkeypatch, seen=fetched)
    _spy(monkeypatch)

    offered = client.get(f"/api/runs/{run_id}/pages").json()
    client.post(f"/api/runs/{run_id}/expert/content-brief", json={})

    assert offered["pages"], "the picker offered nothing for this run"
    assert fetched and fetched[0] == offered["pages"][0]["url"], (
        "the boundary chose a target the picker does not offer first — "
        f"picker {offered['pages'][0]['url']!r}, boundary {fetched[0]!r}")
