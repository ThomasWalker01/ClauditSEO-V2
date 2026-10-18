"""KI-19. One brief, one call at a time — the server is where that is decided.

Measured on run `1d85ff71c29e47eaa9b27e146fca6589`: `cost_entries` carries two
`EXPERT:hreflang` rows, 09:12:12 (8,987 tokens, $0.066342) and 09:12:29 (9,407
tokens, $0.063329), against a single `expert_reports` row at 09:12:29 matching
the later charge. `PRIMARY KEY (run_id, tool_id)` discarded the first: the
report the earlier charge paid for no longer exists, and the orphan cost row is
its only trace.

**Why the server and not the buttons.** The two client controls that were meant
to prevent this cannot see each other — the sweep's Run reads
`disabled={!workingSet.length}` and never consults `busyTool` — and neither of
them can see a second browser, a second tab, or a `curl`. A control that is
bypassed by opening the app twice is not where a charge gets refused. The
client checks are worth having and are still there; this file is about the one
that cannot be walked around.

**Why `run_expert` is replaced by a fake that blocks.** The defect needs two
calls *overlapping*, and a real brief is a minute-long provider call. The fake
holds the first call inside the route — exactly where the real one would be —
until the test lets it go, so the second request arrives while the first is
genuinely in flight rather than after it. It writes the same ledger row the
real path writes, so what is counted is the product's count of how many times
it reached the point of spending, not the test's opinion of it.

**What can disagree with the fix.** Against the unfixed route both calls reach
`run_expert` and both log a charge, so the first test here reads two ledger
rows where it demands one. The third test is the control that stops the gate
being satisfied by a route that refuses everything: once the first call has
returned, the same brief must run again.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import clauditseo.analysts.expert as expert_mod
from clauditseo.api import app as app_mod
from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

DOMAIN = "example.com"
#: The brief the measurement was taken on. Site-scoped, so the route reaches
#: the provider call without a page fetch standing in the way.
TOOL = "hreflang"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "reentrant-brief.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client_id = repo.create_client(conn, op, "Twice Co")
    site_id = repo.create_site(conn, client_id, DOMAIN)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    conn.close()
    return TestClient(create_app(db_path=db)), db, run_id


class Provider:
    """Stands in for `run_expert`: bills, then blocks until released.

    `entered` is set once a call is inside, so the test can send the second
    request at the only moment that reproduces the defect.
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, conn, run_id, tool_id, *args, **kwargs):
        with self._lock:
            self.calls.append(tool_id)
            first = len(self.calls) == 1
        runs.log_cost(conn, run_id, "test", f"EXPERT:{tool_id}", "tokens",
                      9000, actual_cost=0.065)
        self.entered.set()
        # Only the first entrant is held. A second one that got this far has
        # already proved the defect, and blocking it too would deadlock the
        # test into a timeout — the failure would then be "the test never
        # released the first call" rather than the assertion naming the two
        # charges, which is the diagnostic the next reader needs.
        if first:
            # Bounded: a fix that deadlocks a second call rather than refusing
            # it must fail this suite, not hang it.
            assert self.release.wait(30), "the test never released the first call"
        return {"status": "ok", "report": "a brief that ran once"}


def _charges(db, run_id: str) -> list:
    conn = connect(db)
    try:
        return conn.execute(
            "SELECT operation FROM cost_entries WHERE run_id=? "
            "ORDER BY created_at", (run_id,)).fetchall()
    finally:
        conn.close()


def _post_in_a_thread(client, run_id: str, sink: dict) -> threading.Thread:
    def go():
        try:
            sink["response"] = client.post(f"/api/runs/{run_id}/expert/{TOOL}")
        except Exception as exc:                      # noqa: BLE001
            sink["error"] = exc
    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    return thread


def test_a_second_start_of_a_running_brief_is_refused_and_does_not_bill(
        api, monkeypatch):
    client, db, run_id = api
    provider = Provider()
    monkeypatch.setattr(expert_mod, "run_expert", provider)

    first: dict = {}
    thread = _post_in_a_thread(client, run_id, first)
    assert provider.entered.wait(30), "the first brief never reached the provider"

    second = client.post(f"/api/runs/{run_id}/expert/{TOOL}")

    assert second.status_code == 409, (
        f"a second concurrent start of {TOOL} was answered "
        f"{second.status_code}: {second.text}")
    assert TOOL in second.json()["detail"], second.json()

    provider.release.set()
    thread.join(30)
    assert not thread.is_alive(), "the first call never returned"
    assert first.get("response") is not None, first
    assert first["response"].status_code == 200, first["response"].text

    assert provider.calls == [TOOL], (
        f"the route reached the provider {len(provider.calls)} times for one "
        "brief — the second overlapping call spent")
    charges = _charges(db, run_id)
    assert len(charges) == 1, (
        f"{len(charges)} ledger rows for one brief on one run — this is "
        "KI-19's two charges against a single surviving report")


def test_the_refused_call_leaves_the_running_one_reported_as_running(
        api, monkeypatch):
    """The second half of KI-19: the register's `pop` was unconditional.

    A call that never took the slot must not be able to give it back. With the
    old `pop`, the refused sibling returning cleared the key belonging to the
    call still executing, and the panel fell back to "Not run against this
    audit yet" on a brief that was running.
    """
    client, _db, run_id = api
    provider = Provider()
    monkeypatch.setattr(expert_mod, "run_expert", provider)

    first: dict = {}
    thread = _post_in_a_thread(client, run_id, first)
    assert provider.entered.wait(30), "the first brief never reached the provider"

    refused = client.post(f"/api/runs/{run_id}/expert/{TOOL}")
    assert refused.status_code == 409, refused.text

    index = client.get(f"/api/runs/{run_id}/expert")
    assert index.status_code == 200, index.text
    running = [f["tool"] for f in index.json().get("in_flight", [])]

    provider.release.set()
    thread.join(30)

    assert TOOL in running, (
        f"the refused call cleared the register: in_flight was {running} while "
        f"{TOOL} was still executing")


def test_the_brief_can_be_run_again_once_the_first_call_has_finished(
        api, monkeypatch):
    """The control. A gate that never reopens is a wall, and a brief that can
    be run only once against a run is a worse defect than the one fixed.
    """
    client, db, run_id = api
    provider = Provider()
    provider.release.set()                    # nothing blocks; both calls run
    monkeypatch.setattr(expert_mod, "run_expert", provider)

    one = client.post(f"/api/runs/{run_id}/expert/{TOOL}")
    two = client.post(f"/api/runs/{run_id}/expert/{TOOL}")

    assert one.status_code == 200, one.text
    assert two.status_code == 200, two.text
    assert provider.calls == [TOOL, TOOL], provider.calls
    assert len(_charges(db, run_id)) == 2, (
        "a brief run twice in sequence billed once — the slot was never "
        "released")


def test_the_register_is_given_back_only_by_the_call_that_took_it():
    """The claim contract on its own, below the route.

    Stated here as well as end-to-end because it is the invariant the route's
    `finally` relies on, and a later change reverting `_release_in_flight` to
    an unconditional `pop` would still pass the tests above on any run where
    the route happened not to produce a losing caller.
    """
    run_id, tool_id = "a-run-that-is-not-in-the-database", "a-tool"
    app_mod._release_in_flight(run_id, tool_id, 0)     # start from empty

    token = app_mod._claim_in_flight(run_id, tool_id)
    assert token is not None
    assert app_mod._claim_in_flight(run_id, tool_id) is None, (
        "two callers were handed the same slot")

    app_mod._release_in_flight(run_id, tool_id, token + 1000)
    assert [f["tool"] for f in app_mod._in_flight_for(run_id)] == [tool_id], (
        "a foreign token released a slot it never held")

    app_mod._release_in_flight(run_id, tool_id, token)
    assert app_mod._in_flight_for(run_id) == []
    again = app_mod._claim_in_flight(run_id, tool_id)
    assert again is not None, "the slot did not reopen after its holder left"
    app_mod._release_in_flight(run_id, tool_id, again)
