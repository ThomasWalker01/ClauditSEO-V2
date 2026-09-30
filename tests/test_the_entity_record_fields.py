"""Item 145 step BH: the three entity fields the AI surface brief names, and
the suggestion read off the site's own schema.

`ai-surface.md` reads `legal_name`, `registered_ids` and external profiles,
and until migration 0063 this product's site record held none of them: every
check that needed one could only ever come back `not_assessable` naming a
field the operator had no way to set.

The suggestion exists because the values are usually already in the markup.
It is offered and never applied, which is the whole of the design: two of the
brief's checks judge the record against that same markup, so a record filled
from it would make them agree with themselves.
"""

from __future__ import annotations

import json
import sqlite3

from clauditseo.analysts import ai_surface
from clauditseo.engine.types import Site
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

HOME = "https://record.fixture/"
ORG = {"@context": "https://schema.org", "@type": "Organization",
       "@id": HOME + "#org", "name": "Acme Pest Control",
       "legalName": "Acme Pest Control Pty Ltd",
       "taxID": "12 345 678 901",
       "identifier": {"@type": "PropertyValue", "name": "ACN", "value": "345 678 901"},
       "sameAs": ["https://www.linkedin.com/company/acme",
                  "https://www.facebook.com/acme"]}


def _site(conn) -> str:
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Fixture")
    return repo.create_site(conn, client, "record.fixture")


def _run_with_home(conn, site_id, blocks, kind="audit", scope="full") -> str:
    """One stored run whose home page carries these JSON-LD blocks."""
    page = {"url": HOME, "requested_url": HOME, "status": 200,
            "content_type": "text/html", "title": "Acme",
            "jsonld_raw": [{"source": "inline", "text": json.dumps(b)} for b in blocks]}
    # `kind` and `scan_scope` are what make this a reading of the site: the
    # suggestion asks for the home page, and a verification or a page scan
    # carries only the pages it was pointed at.
    run_id = repo.create_id()
    conn.execute(
        "INSERT INTO audit_runs (id, site_id, dimensions, tier, status, engine_version,"
        " analyst_enabled, started_at, created_at, crawl_evidence, kind, scan_scope)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, site_id, json.dumps(["ONP", "AIS"]), "T2", "complete", "0.27.0", 0,
         "2026-09-16T00:00:00+00:00", "2026-09-16T00:00:00+00:00",
         json.dumps({"start_url": HOME, "pages": [page]}), kind, scope))
    conn.commit()
    # Finished by hand, so the Latest View is built by its replay (item 239):
    # the home page's facts are read from there, and `jsonld_raw` is ONP's.
    from clauditseo.persistence import latest_view
    latest_view.rebuild(conn, site_id, "test")
    return run_id


def _conn(tmp_path) -> sqlite3.Connection:
    conn = connect(tmp_path / "record.db")
    migrate(conn)
    return conn


def test_the_three_fields_are_columns_and_survive_a_round_trip(tmp_path):
    """Migration 0063. `registered_ids` and `external_profiles` are JSON, so
    they come back as a list and a list of maps rather than strings."""
    conn = _conn(tmp_path)
    site_id = _site(conn)
    repo.update_site(conn, site_id, **{
        "legal_name": "Acme Pest Control Pty Ltd",
        "registered_ids": ["ABN 12 345 678 901"],
        "external_profiles": [{"url": "https://www.linkedin.com/company/acme", "claimed": True}]})
    rec = repo.site_record(repo.get_site(conn, site_id))
    assert rec["legal_name"] == "Acme Pest Control Pty Ltd"
    assert rec["registered_ids"] == ["ABN 12 345 678 901"]
    assert rec["external_profiles"] == [
        {"url": "https://www.linkedin.com/company/acme", "claimed": True}]


def test_the_brief_reads_the_record_rather_than_stating_a_missing_field():
    """The context said "the site record has no such field yet" for
    `legal_name` and `registered_ids`, which was true and is not any more."""
    site = Site(domain="record.fixture", legal_name="Acme Pest Control Pty Ltd",
                registered_ids=["ABN 12 345 678 901"])
    block = ai_surface.site_entities(site)
    assert "- legal_name: Acme Pest Control Pty Ltd" in block
    assert '- registered_ids: ["ABN 12 345 678 901"]' in block
    assert "no such field yet" not in block
    # And an empty one is an empty record field like any other.
    empty = ai_surface.site_entities(Site(domain="record.fixture"))
    assert "- legal_name: " + ai_surface.ABSENT in empty


def test_a_profiles_claimed_state_is_stated_and_never_guessed():
    """Three states: an unanswered `claimed` is not a "no". An unclaimed
    profile is a different fix from an unlinked one, and only the operator
    knows which it is."""
    site = Site(domain="record.fixture", external_profiles=[
        {"url": "https://a.test/x", "claimed": True},
        {"url": "https://b.test/x", "claimed": False},
        {"url": "https://c.test/x"}])
    text = ai_surface.external_profiles(site)
    assert "https://a.test/x · claimed" in text
    assert "https://b.test/x · not claimed" in text
    assert "https://c.test/x · claimed state not stated" in text
    # Empty says what the prompt asks it to say.
    assert "reads `sameas_sources` alone" in ai_surface.external_profiles(
        Site(domain="record.fixture"))


def test_the_suggestion_reads_the_home_pages_entity_node(tmp_path):
    conn = _conn(tmp_path)
    site_id = _site(conn)
    _run_with_home(conn, site_id, [ORG])
    got = runs.entity_record_suggestions(conn, site_id)
    assert got["home"] == HOME and got["entity_type"] == "Organization"
    assert got["legal_name"] == "Acme Pest Control Pty Ltd"
    # Whichever key holds an identifier, in ID_KEYS order, never reshaped.
    assert got["registered_ids"] == ["12 345 678 901", "ACN: 345 678 901"]
    # A pin says the site asserts the profile, not that anyone claimed it.
    assert got["external_profiles"] == [
        {"url": "https://www.linkedin.com/company/acme", "claimed": None},
        {"url": "https://www.facebook.com/acme", "claimed": None}]


def test_a_suggestion_is_never_written_to_the_record(tmp_path):
    """The reason the panel offers rather than applies: `entity-unresolvable`
    judges the node's `sameAs` against the record's identifiers, and
    `entity-footprint-unlinked` judges the record's profiles against what the
    pages pin. A record filled from that markup agrees with itself."""
    conn = _conn(tmp_path)
    site_id = _site(conn)
    _run_with_home(conn, site_id, [ORG])
    runs.entity_record_suggestions(conn, site_id)
    rec = repo.site_record(repo.get_site(conn, site_id))
    assert rec["legal_name"] is None
    assert not rec["registered_ids"] and not rec["external_profiles"]


def test_a_narrow_run_is_not_read_as_the_site(tmp_path):
    """A page scan carries the pages it was pointed at. Read as the site, its
    first page would be offered as the entity's home."""
    conn = _conn(tmp_path)
    site_id = _site(conn)
    _run_with_home(conn, site_id, [ORG], kind="page-scan", scope="page")
    assert runs.entity_record_suggestions(conn, site_id)["run_id"] is None


def test_a_site_with_no_crawl_or_no_entity_node_suggests_nothing(tmp_path):
    conn = _conn(tmp_path)
    site_id = _site(conn)
    bare = runs.entity_record_suggestions(conn, site_id)
    assert bare["run_id"] is None and bare["registered_ids"] == []
    _run_with_home(conn, site_id, [{"@context": "https://schema.org",
                                    "@type": "WebPage", "name": "Acme"}])
    got = runs.entity_record_suggestions(conn, site_id)
    assert got["run_id"] and got["legal_name"] is None
    assert got["external_profiles"] == []


def test_the_panel_offers_and_the_save_is_the_operators(tmp_path):
    """The screen half of the same rule: the panel fills the boxes and the
    operator presses save. Held on the source, because the claim is about
    what the component does not do."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "admin.tsx").read_text(encoding="utf-8")
    panel = src[src.index("function EntitySuggestionsPanel"):src.index("function SiteRecordForm")]
    assert "api.get<EntitySuggestions>" in panel, "it reads the suggestion route"
    assert "api.put" not in panel and "api.post" not in panel, (
        "the panel writes nothing: the operator's save is what makes a value the record's")
    assert "/api/sites/${site.id}/entity-suggestions" in panel
