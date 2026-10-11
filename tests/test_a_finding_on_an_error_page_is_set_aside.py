"""A page-level Links finding on a page that now answers an error is set
aside (channel ruling 20261011-0745; screen audits round 3, Links AC-01).

On twenty22 five automatic Links findings sat on pages later crawls fetched
as 404. A page fetched with an error is not "read", so `measured` called them
unmeasured forever: they stayed in the open counts and the link suggestions,
telling the operator to add links to a 404. `fixed` would claim a repair, so
the ruling adds `set-aside`.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.persistence import repo, runs
from clauditseo.persistence.runs import Reading, measured

GONE = "/on-page-seo/"


def _reading(errored=(), crawled=("/",)):
    return Reading("r", frozenset({"LNK"}), frozenset(crawled), frozenset(), frozenset(),
                   True, frozenset(errored))


def test_measured_says_inapplicable_only_where_every_page_errored():
    url = [f"https://t.co{GONE}"]
    assert measured(_reading({GONE}), "LNK", "inlinks-low", url)[0] == "inapplicable"
    # broken-internal measures the error itself, so it is never set aside.
    assert measured(_reading({GONE}), "LNK", "broken-internal", url)[0] == "unmeasured"
    # A finding naming a page that answered and one that did not is not.
    two = url + ["https://t.co/about/"]
    assert measured(_reading({GONE}), "LNK", "inlinks-low", two)[0] != "inapplicable"
    # An analysis's row is measured by its analysis, never here.
    assert measured(_reading({GONE}), "LNK", "inlinks-low", url,
                    source="model-judgement")[0] == "unmeasured"


@pytest.fixture
def ledger(tmp_path):
    api = TestClient(create_app(db_path=tmp_path / "c.db"))
    client_id = api.post("/api/clients", json={"name": "T"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "https://t.co/"}).json()["id"]
    conn = connect(tmp_path / "c.db")
    run_id = runs.create_run(conn, site_id, ["LNK"], "T2")
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
        " affected_urls, fingerprint, created_at) VALUES (?, ?, 'LNK', 'inlinks-low',"
        " 'low', 'deterministic', 's', ?, 'fp-gone', ?)",
        (repo.create_id(), run_id, json.dumps([f"https://t.co{GONE}"]), repo.now_iso()))
    conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                 " updated_at) VALUES (?, 'fp-gone', 'open', ?, ?)",
                 (site_id, run_id, repo.now_iso()))
    conn.commit()
    yield conn, site_id
    conn.close()


def _state(conn, site_id):
    return conn.execute("SELECT state FROM finding_states WHERE site_id=? AND"
                        " fingerprint='fp-gone'", (site_id,)).fetchone()["state"]


def _step(conn, site_id, reading, current=()):
    from dataclasses import replace
    run_id = runs.create_run(conn, site_id, ["LNK"], "T2")
    runs._advance_states(conn, site_id, run_id, repo.now_iso(), current=set(current),
                         about_the_run=set(), reading=replace(reading, run_id=run_id),
                         blocked=False)
    conn.commit()


def test_the_error_sets_it_aside_and_absence_leaves_it(ledger):
    conn, site_id = ledger
    _step(conn, site_id, _reading({GONE}))
    assert _state(conn, site_id) == "set-aside"
    # A later run that does not raise it changes nothing.
    _step(conn, site_id, _reading(crawled=("/", GONE)))
    assert _state(conn, site_id) == "set-aside"


def test_raised_again_it_reopens_as_open_never_regressed(ledger):
    conn, site_id = ledger
    _step(conn, site_id, _reading({GONE}))
    _step(conn, site_id, _reading(crawled=("/", GONE)), current={"fp-gone"})
    assert _state(conn, site_id) == "open"


def test_it_leaves_the_open_counts(ledger):
    conn, site_id = ledger
    _step(conn, site_id, _reading({GONE}))
    current = runs.current_state(conn, site_id)
    assert current["open"] == 0 and current["set_aside"] == 1, current


def test_the_vocabularies_place_it():
    assert "set-aside" in runs.ALL_STATES and "set-aside" in runs.MODEL_BLIND_STATES
    assert "set-aside" not in runs.LIVE_STATES
    assert "set-aside" not in runs.OPERATOR_SETTABLE_STATES


def test_the_record_names_it_and_its_address_selects_it():
    """Found on twenty22 after the Links re-check: the button filtered, but
    `?state=set-aside` was refused by the address's own list, and the group
    line said the engine's "set-aside"."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    views = (src / "views.tsx").read_text(encoding="utf-8")
    assert '"set-aside",' in views.split("const STATE_FILTERS", 1)[1].split("];", 1)[0]
    assert '"set-aside"' in views.split("const LISTABLE", 1)[1].split("];", 1)[0]
    record = (src / "pane_record.tsx").read_text(encoding="utf-8")
    assert 'k === "set-aside" ? "on an error page" : k' in record
    assert '["set-aside", "On an error page", (s) => s.state === "set-aside"]' in record
