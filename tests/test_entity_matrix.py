"""The entity matrix: the site's entities against where each is named (item
136o Tab 4).

The row verdict is the engine's and reuses `CNT/entity-page-verdict`'s
URL+Title+H1 rule, so the matrix and the per-page verdict cannot disagree.
Body is omitted until a body-text signal exists (a separate decision); every
other column is exact from stored evidence.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.persistence import repo, runs


@pytest.fixture()
def run(tmp_path):
    conn = connect(tmp_path / "c.db"); migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site_id, ["CNT"], "T2")

    def page(path, title, h1, anchors=(), schema=(), body=""):
        return {"url": "https://x.test" + path, "status": 200,
                "title": title, "h1": h1,
                "opening": body,
                "outline": [[2, h1, True, body]] if body else [],
                "links": [{"anchor": a, "url": "https://x.test/x"} for a in anchors],
                "schema_inventory": list(schema)}

    pages = [
        # Bridging: owned (url+title+h1 all name it).
        page("/bridging", "Bridging finance | Acme", "Bridging finance",
             schema=[{"type": "Service", "properties": {"name": "Bridging finance"}}]),
        # Equipment: mentioned in an anchor only, not owned.
        page("/", "Home | Acme", "Welcome",
             anchors=["Equipment finance", "Bridging finance"],
             body="We offer Invoice finance and other lending across the country."),
    ]
    conn.execute("UPDATE audit_runs SET crawl_evidence=? WHERE id=?",
                 (json.dumps({"pages": pages}), run_id))
    conn.commit()
    yield conn, run_id, site_id
    conn.close()


SITE = Site(domain="x.test", brand="Acme", sub_services=[
    {"name": "Bridging finance", "url": "https://x.test/bridging"},   # owned
    {"name": "Equipment finance", "url": "https://x.test/equipment"}, # anchor only
    {"name": "Invoice finance", "url": "https://x.test/invoice"},     # body only
    {"name": "Debtor lending", "url": "https://x.test/debtor"}])      # nowhere


def _rows(conn, run_id):
    pl = runs.entity_matrix_payload(conn, run_id, SITE)
    return {r["entity"]: r for r in pl["rows"]}, pl


def test_an_entity_named_in_url_title_and_h1_is_owned(run):
    conn, run_id, _ = run
    rows, _ = _rows(conn, run_id)
    assert rows["Bridging finance"]["verdict"] == "owned"
    assert rows["Bridging finance"]["cells"]["url"] == 1
    assert rows["Bridging finance"]["cells"]["title"] == 1
    assert rows["Bridging finance"]["cells"]["h1"] == 1


def test_footer_only_is_mentioned_not_owned(run):
    """Named in an anchor on the home page, nowhere in a URL/Title/H1: the
    site knows the entity exists but no page is about it."""
    conn, run_id, _ = run
    rows, _ = _rows(conn, run_id)
    e = rows["Equipment finance"]
    assert e["verdict"] == "mentioned", e
    assert e["cells"]["anchors"] >= 1 and e["cells"]["url"] == 0


def test_an_entity_named_nowhere_is_absent(run):
    conn, run_id, _ = run
    rows, _ = _rows(conn, run_id)
    assert rows["Debtor lending"]["verdict"] == "absent", rows["Debtor lending"]
    assert not any(rows["Debtor lending"]["cells"].values())


def test_the_schema_column_counts_declaring_nodes_only(run):
    """A `Service` node declaring the name counts; a node of another type
    that merely carries the name does not."""
    conn, run_id, _ = run
    rows, _ = _rows(conn, run_id)
    assert rows["Bridging finance"]["cells"]["schema"] == 1
    # Equipment finance has no schema node.
    assert rows["Equipment finance"]["cells"]["schema"] == 0


def test_the_summary_counts_the_verdicts(run):
    conn, run_id, _ = run
    _, pl = _rows(conn, run_id)
    s = pl["summary"]
    assert s["entities"] == 4
    assert s["owned"] == 1 and s["mentioned"] == 2 and s["absent"] == 1
    assert s["with_schema"] == 1


def test_the_reading_line_leads_with_the_first_absent_service(run):
    """Every service is not owned here (one absent), so the reading names it
    rather than the schema cross-reference."""
    conn, run_id, _ = run
    _, pl = _rows(conn, run_id)
    assert "Debtor lending" in pl["reading"], pl["reading"]


def test_a_coverage_gap_becomes_a_row_and_agrees(run):
    """Every `gap` node must appear as an `absent` or `mentioned` entity, and
    no `owned` entity may be a gap. Both directions (item 136o)."""
    conn, run_id, site_id = run
    # A gap on an entity the pages do not own.
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
        " summary, affected_urls, fingerprint, created_at, evidence)"
        " VALUES (?, ?, 'CNT', 'gap', 'medium', 'model-judgement', 'g', '[]',"
        " 'g1', ?, ?)",
        (repo.create_id(), run_id, repo.now_iso(),
         json.dumps({"node": "Trade finance"})))
    conn.commit()
    rows, _ = _rows(conn, run_id)
    assert "Trade finance" in rows, list(rows)
    tf = rows["Trade finance"]
    # A gap node is absent or mentioned, never owned.
    assert tf["verdict"] in ("absent", "mentioned"), tf
    # And it carries the Map column, being a Coverage node.
    assert tf["cells"]["map"] == 1
    # No owned entity is a gap: Bridging (owned) is not among the gap nodes.
    assert rows["Bridging finance"]["kind"] != "from Coverage · gap"


def test_no_site_and_no_record_is_none(run):
    conn, run_id, _ = run
    assert runs.entity_matrix_payload(conn, run_id, None) is None
    assert runs.entity_matrix_payload(conn, None, SITE) is None


def test_the_body_column_counts_mentions_in_the_stored_prose(run):
    """Body reads the opening and the text after each heading - the prose the
    crawl stores on every page. `Invoice finance` is named in the home page's
    body but nowhere in a URL/Title/H1, so it becomes `mentioned`, and the
    Body cell counts it."""
    conn, run_id, _ = run
    rows, pl = _rows(conn, run_id)
    assert rows["Invoice finance"]["cells"]["body"] >= 1, rows["Invoice finance"]
    # It has a body mention, so it is mentioned, not absent.
    assert rows["Invoice finance"]["verdict"] == "mentioned"
    # The payload states the body basis honestly.
    assert "buried past those windows" in pl["body_basis"], pl["body_basis"]


def test_a_record_with_no_entities_is_none_not_an_empty_matrix(run):
    """The tab shows its absent-state ("set the record's entities") only if
    the payload is None. A matrix with zero rows would draw an empty table
    instead - which is what the running product showed before this."""
    conn, run_id, _ = run
    from clauditseo.engine.types import Site
    assert runs.entity_matrix_payload(conn, run_id, Site(domain="x.test")) is None
