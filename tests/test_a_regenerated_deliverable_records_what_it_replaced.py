"""WF-91 / Q-9: pressing `regenerate` says which document it replaced.

`QUESTIONS.md` **Q-9** — *what should pressing regenerate do to the deliverable
row that was pressed: supersede it, rewrite it in place, or leave it and gain a
way to prune?* — answered by the operator on 23 August 2026: **supersede**.

The defect the answer settles was measured rather than argued. `POST
/api/reports` always writes a row and a file, and left the pressed row exactly
as it was — so that row kept its `superseded` or `unknown` renderer and kept
offering the control for ever. Audit 074 counted the cost on the operator's own
database: **14 rows offering `regenerate`, 11 of them on one site, 9 of those 11
mutually indistinguishable** on every column the table renders — `2026-08-16 ·
comparison · client · 3 audits since · predates renderer tracking`. Nine presses
would have produced nine more, all dated the same day, with nothing recording
which replaced which.

**What this file guards is both halves of the answer, because either alone is a
different answer.** That the replacement records what it replaced is the
supersede half; that the replaced document is still listed, still readable and
byte-identical afterwards is the half that distinguishes *supersede* from
*rewrite in place*, which was rejected on the ground that it destroys the record
of what a client was actually sent. A regression to either would satisfy a guard
written for only the other.

The direction of the column is deliberate and is asserted here too: `supersedes`
is written on the **new** row, so a regeneration is one INSERT and never an
UPDATE of a row describing a document a client may already hold. The screen
needs the other direction, and `client_reports()` derives `superseded_by` over
the site's own rows. See `clauditseo/db/migrations/0028_report_supersedes.sql`.

The browser half — that the replaced row stops being *offered* the control — is
in `tests/test_deliverable_regenerate.py`, beside the four clauses that guard
the control existing at all. Here is the register; there is the screen.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.persistence import repo, runs
from clauditseo.reporting import generate as gen

# Reused rather than rebuilt, for the reason
# `test_report_register_and_file_are_one_fact.py` gives: this is the one
# definition of "a database a report can actually be generated from", and
# `generate()` will not write anything without completed runs behind it.
from tests.test_reporting_g7 import db_with_runs  # noqa: F401

#: The fixture's database, by the name it gives it. `db_with_runs` yields an
#: open connection and not a path, and the API clauses need a second connection
#: to the same file — so the path is reconstructed from the `tmp_path` both the
#: fixture and the test are handed, which pytest guarantees is the same one.
DB = "g7.db"


def _site_of(conn: sqlite3.Connection, run_id: str) -> str:
    return conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                        (run_id,)).fetchone()["site_id"]


def _row(rows: list[dict], report_id: str) -> dict:
    got = [r for r in rows if r["id"] == report_id]
    assert got, f"{report_id[:8]} is not in the register: {[r['id'][:8] for r in rows]}"
    return got[0]


def test_the_replacement_records_which_document_it_replaced(db_with_runs, tmp_path):
    """The supersede half, read from the register rather than from the screen.

    Both directions are asserted because the screen states both: the replaced
    row says what took its place, and the replacement says what it was made
    from. A fix that stored the column and never surfaced the reverse lookup
    would leave the row that keeps offering the control exactly as it was,
    which is the finding.
    """
    conn, run_ids = db_with_runs
    out = tmp_path / "out"
    out.mkdir()
    site_id = _site_of(conn, run_ids[0])

    first = gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out)
    second = gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out,
                          supersedes=first["id"])

    stored = conn.execute("SELECT supersedes FROM reports WHERE id=?",
                          (second["id"],)).fetchone()["supersedes"]
    assert stored == first["id"], (
        "the regenerated document does not record which one it replaced, so "
        "the register cannot say which document replaced which: "
        f"supersedes={stored!r}")

    rows = runs.client_reports(conn, site_id)
    assert _row(rows, first["id"])["superseded_by"] == second["id"], (
        "the replaced row does not know it was replaced, so the screen keeps "
        "offering it a control whose action has already been taken - which is "
        "WF-91 in the shape it was measured in")
    assert _row(rows, second["id"])["supersedes"] == first["id"]
    # The direction, asserted rather than assumed. Storing it the other way
    # round would satisfy the two assertions above through the same derived
    # keys while turning every regeneration into an UPDATE of a delivered
    # document's row.
    assert _row(rows, first["id"])["supersedes"] is None
    assert _row(rows, second["id"])["superseded_by"] is None


def test_the_document_it_replaced_is_still_there_and_unchanged(db_with_runs, tmp_path):
    """The half that makes this `supersede` and not `rewrite in place`.

    Rewriting the row was one of the three answers put to the operator, and it
    was rejected because the replaced row is the artefact a client was actually
    sent - the one thing this register exists to hold. Read from disk as well
    as from the register, because a row surviving while its file was rewritten
    underneath it is the same loss in a place the register cannot see.
    """
    conn, run_ids = db_with_runs
    out = tmp_path / "out"
    out.mkdir()
    site_id = _site_of(conn, run_ids[0])

    first = gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out)
    was_path = Path(first["path"])
    was_text = was_path.read_text(encoding="utf-8")
    was_row = dict(conn.execute(
        "SELECT id, path, created_at, renderer_version FROM reports WHERE id=?",
        (first["id"],)).fetchone())

    second = gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out,
                          supersedes=first["id"])

    assert second["id"] != first["id"], "the regeneration reused the row's id"
    assert second["path"] != first["path"], (
        "the replacement was written over the document it replaced: "
        f"{second['path']}")
    assert was_path.exists(), (
        "the document a client was sent is gone from disk after a regeneration")
    assert was_path.read_text(encoding="utf-8") == was_text, (
        "the replaced document's text changed under it - the register no "
        "longer holds what the client actually received")
    now_row = dict(conn.execute(
        "SELECT id, path, created_at, renderer_version FROM reports WHERE id=?",
        (first["id"],)).fetchone())
    assert now_row == was_row, (
        f"the replaced register row was rewritten: {was_row} -> {now_row}")

    rows = runs.client_reports(conn, site_id)
    assert first["id"] in [r["id"] for r in rows], (
        "the replaced document dropped out of the register, which is the "
        "delete answer rather than the supersede one")


def test_the_route_the_control_presses_carries_it(db_with_runs, tmp_path):
    """End to end through `POST /api/reports`, which is what the button calls.

    The persistence clauses above would pass with the parameter unreachable
    from the screen - `generate()` has three callers and only one of them is
    the control. This is the one that fails if the route drops the field.
    """
    conn, run_ids = db_with_runs
    out = tmp_path / "out"
    out.mkdir()
    site_id = _site_of(conn, run_ids[0])
    first = gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out)

    api = TestClient(create_app(db_path=tmp_path / DB))
    made = api.post("/api/reports", json={
        "template": "run", "audience": "client", "run_ids": [run_ids[0]],
        "supersedes": first["id"]})
    assert made.status_code == 201, f"{made.status_code}: {made.text[:300]}"

    listed = api.get(f"/api/sites/{site_id}/client-reports")
    assert listed.status_code == 200, listed.text[:300]
    rows = listed.json()["reports"]
    assert _row(rows, first["id"])["superseded_by"] == made.json()["id"], (
        "the route accepted the field and the register did not record it, so "
        "the screen still offers the pressed row a control it has already used")


def test_the_document_itself_says_it_was_replaced(db_with_runs, tmp_path):
    """The second surface for one fact, which DISCIPLINE rule 3 asks for.

    `GET /api/client-reports/{id}` is what the reading screen loads, and it is
    where the register's "replaced by" link lands. A reader who opens a
    document directly - from a bookmark, or from the link on the row that
    replaced it - reaches none of the table's wording, so a document that has
    since been replaced would look exactly like one that has not on the screen
    whose whole question is "what did we actually tell them".
    """
    conn, run_ids = db_with_runs
    out = tmp_path / "out"
    out.mkdir()
    first = gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out)

    api = TestClient(create_app(db_path=tmp_path / DB))
    made = api.post("/api/reports", json={
        "template": "run", "audience": "client", "run_ids": [run_ids[0]],
        "supersedes": first["id"]})
    assert made.status_code == 201, f"{made.status_code}: {made.text[:300]}"

    old_doc = api.get(f"/api/client-reports/{first['id']}")
    assert old_doc.status_code == 200, old_doc.text[:300]
    assert old_doc.json().get("superseded_by") == made.json()["id"], (
        "the document a client was sent does not say it has been replaced, "
        "on the one screen that exists to answer what they were told")

    new_doc = api.get(f"/api/client-reports/{made.json()['id']}")
    assert new_doc.status_code == 200, new_doc.text[:300]
    assert new_doc.json().get("supersedes") == first["id"], (
        "the replacement does not say what it was regenerated from")


def test_a_replacement_for_a_report_that_does_not_exist_is_refused(
        db_with_runs, tmp_path):
    """404, matching `read_client_report` rather than 403.

    The same reasoning that endpoint carries: a member should not learn which
    report ids exist by watching the status code change. Silently ignoring an
    unknown id is the failure this rules out - it would write a document that
    claims to replace nothing while the screen goes on offering the control.
    """
    conn, run_ids = db_with_runs
    api = TestClient(create_app(db_path=tmp_path / DB))
    made = api.post("/api/reports", json={
        "template": "run", "audience": "client", "run_ids": [run_ids[0]],
        "supersedes": "0" * 32})
    assert made.status_code == 404, (
        "a regeneration naming a report that does not exist was not refused "
        f"({made.status_code}): {made.text[:300]}")


def test_a_document_cannot_supersede_one_belonging_to_another_client(
        db_with_runs, tmp_path):
    """Refused in `generate()`, so all three callers inherit it.

    A cross-site link would put a "replaced by" link on one client's register
    pointing at another client's document - worse than the duplicate row it
    was added to fix. Enforced where the blocked-run refusal is, and for the
    reason written there: a rule enforced at the route is a rule the CLI and
    the seeding script walk past.
    """
    conn, run_ids = db_with_runs
    out = tmp_path / "out"
    out.mkdir()

    op = repo.ensure_default_operator(conn)
    other_client = repo.create_client(conn, op, "Another Co")
    other_site = repo.create_site(conn, other_client, "other.fixture")
    stranger = repo.create_id()
    conn.execute(
        "INSERT INTO reports (id, site_id, run_ids, template, audience, path,"
        " created_at) VALUES (?, ?, '[]', 'run', 'client', ?, ?)",
        (stranger, other_site, str(out / "stranger.md"), repo.now_iso()))
    conn.commit()

    with pytest.raises(ValueError, match="another site"):
        gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out,
                     supersedes=stranger)

    api = TestClient(create_app(db_path=tmp_path / DB))
    made = api.post("/api/reports", json={
        "template": "run", "audience": "client", "run_ids": [run_ids[0]],
        "supersedes": stranger})
    assert made.status_code == 422, (
        "the route let one client's deliverable supersede another's "
        f"({made.status_code}): {made.text[:300]}")
