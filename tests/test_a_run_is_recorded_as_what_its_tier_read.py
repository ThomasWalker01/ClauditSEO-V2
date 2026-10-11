"""A run that named no scope is recorded as what its tier read (item 253).

Round-2 audit of the Audit pane, AC-01, Critical. The by-hand launcher posts
no `scope`, and the route recorded `full` for anything that was not nav-only:
a one-page T1, the T2 site sample and the adaptive pulse alike. `full` is a
reading of the site, so a one-page run replaced the Latest View's
crawl-relative blocks, became a reference run, and its silence cleared
cross-page findings it never looked for - what item 240 was meant to end.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clauditseo.db import migrate as migrate_mod
from clauditseo.db.connection import connect
from clauditseo.db.migrate import applied, migrate
from clauditseo.persistence import repo, runs
from clauditseo.scanscope import depth_for, scope_for_tier

REPAIR = "0070_by_hand_runs_are_what_their_tier_read.py"


def test_the_tier_says_what_an_unscoped_run_read():
    assert scope_for_tier("T1") == "page"
    assert scope_for_tier("T2") == "site"
    assert scope_for_tier("T3") == "full"
    assert scope_for_tier("T2", nav_only=True) == "nav"
    assert scope_for_tier("auto") is None, "an adaptive run has not chosen yet"


def test_the_depth_says_whether_a_model_ran():
    assert depth_for(False) == "quick"
    assert depth_for(True) == "standard"
    assert depth_for(True, "deep") == "deep"


@pytest.fixture()
def launched(tmp_path, monkeypatch):
    """The launch route with the crawl thread stubbed out: the row is what
    these read, and it is written before the thread starts."""
    from fastapi.testclient import TestClient

    import clauditseo.api.app as app_mod
    monkeypatch.setattr(app_mod, "_execute_run", lambda *a, **k: None)
    db = tmp_path / "launch.db"
    client = TestClient(app_mod.create_app(db_path=db))
    c = client.post("/api/clients", json={"name": "Launch Co"}).json()
    site = client.post(f"/api/clients/{c['id']}/sites", json={"domain": "launch.fixture"}).json()
    conn = connect(db)

    def launch(body: dict) -> sqlite3.Row:
        resp = client.post(f"/api/sites/{site['id']}/audits", json=body)
        assert resp.status_code == 202, resp.text
        run_id = resp.json()["run_id"]
        # Each launch has to finish before the next is allowed.
        conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (run_id,))
        conn.commit()
        return conn.execute("SELECT * FROM audit_runs WHERE id=?", (run_id,)).fetchone()

    yield launch, conn
    conn.close()


def test_a_by_hand_t1_is_a_page_scan_and_not_a_reading_of_the_site(launched):
    launch, _ = launched
    row = launch({"dims": ["TEC"], "tier": "T1", "analyst": False})
    assert row["scan_scope"] == "page", row["scan_scope"]
    assert row["scan_depth"] == "quick"
    assert row["scan_url"] == "https://launch.fixture/", row["scan_url"]
    assert row["scope_source"] == "derived-from-tier", row["scope_source"]
    assert not runs.reads_site(row), "a one-page run stood as a reading of the site"


def test_a_by_hand_t2_is_the_site_and_t3_is_full(launched):
    launch, _ = launched
    t2 = launch({"dims": ["TEC"], "tier": "T2", "analyst": False})
    assert t2["scan_scope"] == "site" and runs.reads_site(t2)
    assert t2["scan_url"] is None, "a site scan is not about its entry page"
    t3 = launch({"dims": ["TEC"], "tier": "T3", "analyst": True})
    assert t3["scan_scope"] == "full" and t3["scan_depth"] == "standard"
    nav = launch({"dims": ["TEC"], "tier": "T2", "nav_only": True})
    assert nav["scan_scope"] == "nav"


def test_a_stated_scope_and_depth_are_stored_as_stated(launched):
    launch, _ = launched
    row = launch({"scope": "site", "depth": "quick"})
    assert (row["scan_scope"], row["scan_depth"]) == ("site", "quick")
    assert row["scope_source"] == "posted", row["scope_source"]


def test_an_adaptive_run_has_no_scope_until_its_tier_is_stamped(launched):
    """`auto` chooses its own breadth. Until it has, the row says nothing;
    `set_tier` then records what the executed tier read."""
    launch, conn = launched
    row = launch({"dims": ["TEC"]})
    assert row["tier"] == "T1" and row["scan_scope"] is None, dict(row)
    assert row["scope_source"] is None, "a source was claimed for a scope not yet chosen"
    assert not runs.reads_site(row)

    runs.set_tier(conn, row["id"], "T1")          # the pulse was enough
    stopped = conn.execute("SELECT * FROM audit_runs WHERE id=?", (row["id"],)).fetchone()
    assert stopped["scan_scope"] == "page" and not runs.reads_site(stopped)
    assert stopped["scope_source"] == "derived-from-tier"

    second = launch({"dims": ["TEC"]})
    runs.set_tier(conn, second["id"], "T2")       # it escalated
    deep = conn.execute("SELECT * FROM audit_runs WHERE id=?", (second["id"],)).fetchone()
    assert deep["scan_scope"] == "site" and runs.reads_site(deep)


def test_stamping_the_tier_never_overwrites_a_stated_scope(launched):
    launch, conn = launched
    row = launch({"dims": ["TEC"], "tier": "T2", "nav_only": True})
    runs.set_tier(conn, row["id"], "T3")
    assert tuple(conn.execute("SELECT scan_scope, scope_source FROM audit_runs WHERE id=?",
                              (row["id"],)).fetchone()) == ("nav", "derived-from-tier")
    posted = launch({"scope": "site", "depth": "quick", "tier": "T2"})
    runs.set_tier(conn, posted["id"], "T3")
    assert tuple(conn.execute("SELECT scan_scope, scope_source FROM audit_runs WHERE id=?",
                              (posted["id"],)).fetchone()) == ("site", "posted")


def test_a_one_page_run_does_not_write_the_latest_views_blocks(launched):
    """The consequence the audit named: `Reading.site_reading` is what lets
    a run replace a crawl-relative block and clear a cross-page finding."""
    launch, conn = launched
    row = launch({"dims": ["TEC"], "tier": "T1", "analyst": False})
    conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?",
                 (json.dumps(["/"]), row["id"]))
    conn.commit()
    reading = runs.Reading.of_stored(conn, row["id"])
    assert reading is not None and not reading.site_reading
    state, why = runs.measured(reading, "ONP", "title-duplicate", [])
    assert state == "unmeasured", (state, why)


# ---- the page floor -------------------------------------------------------------

def _row(conn, site, scope, read, known, tier="T3"):
    run_id = runs.create_run(conn, site, ["TEC"], tier, scan_scope=scope)
    conn.execute("UPDATE audit_runs SET status='complete', crawled_paths=?, known_paths=?"
                 " WHERE id=?", (json.dumps([f"/p{i}" for i in range(read)]), known, run_id))
    conn.commit()
    return run_id


def test_a_site_wide_label_needs_half_of_what_the_run_knew_or_fifty(tmp_path):
    """The channel's answer of 2026-10-02. Judged on the run's own evidence,
    so a replay gives the same answer; half, because a real crawl of a small
    site does not reach every declared page (twenty22: 45 of 49)."""
    conn = connect(tmp_path / "floor.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Floor Co"), "floor.fixture")
    cases = {
        "45 of 49, twenty22's reference": (_row(conn, site, "site", 45, 49), True),
        "3 of 49, a full crawl cut short": (_row(conn, site, "full", 3, 49), False),
        "50 of 400, the site sample": (_row(conn, site, "site", 50, 400), True),
        "40 of 60 discovered, no sitemap": (_row(conn, site, "full", 40, 60), True),
        "1 of 12 discovered, no sitemap": (_row(conn, site, "full", 1, 12), False),
        "nothing says how big the site is": (_row(conn, site, "site", 3, None), True),
        "a nav scan, however much it read": (_row(conn, site, "nav", 60, 60), False),
    }
    for name, (run_id, want) in cases.items():
        row = conn.execute("SELECT * FROM audit_runs WHERE id=?", (run_id,)).fetchone()
        assert runs.reads_site(row) is want, name
        # The SQL twin asks the same question of the same row.
        sql = conn.execute(f"SELECT 1 FROM audit_runs WHERE id=? AND {runs.kind_is_site_reading()}",
                           (run_id,)).fetchone()
        assert bool(sql) is want, f"{name}: the SQL twin disagrees"
        joined = conn.execute(
            "SELECT 1 FROM audit_runs r WHERE r.id=? AND " + runs.kind_is_site_reading("r.kind"),
            (run_id,)).fetchone()
        assert bool(joined) is want, f"{name}: the aliased SQL twin disagrees"
    conn.close()


def test_what_a_run_knew_is_its_sitemap_or_its_own_frontier():
    ok = [{"status": 200}]
    assert runs.known_paths_of({"sitemap_entry_total": 49, "sitemaps": ok,
                                "stats": {"fetched": 48, "queue_remaining": 0}}) == 49
    # No sitemap answered: what the crawl itself discovered.
    assert runs.known_paths_of({"sitemap_entry_total": 0, "sitemaps": [{"status": 404}],
                                "stats": {"fetched": 40, "queue_remaining": 20}}) == 60
    assert runs.known_paths_of({"stats": {"fetched": 1, "queue_remaining": 11}}) == 12
    assert runs.known_paths_of({}) is None and runs.known_paths_of(None) is None
    assert runs.known_paths_of({"pages": []}) is None, "no count was read as zero pages"


# ---- the repair --------------------------------------------------------------

def _before_the_repair(db: Path) -> sqlite3.Connection:
    conn = connect(db)
    applied(conn)
    for path in migrate_mod._files():
        if path.name == REPAIR:
            continue
        with conn:
            if path.suffix == ".py":
                migrate_mod._apply_python(path, conn)
            else:
                conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
    return conn


def test_the_repair_relabels_the_rows_the_old_route_wrote(tmp_path):
    conn = _before_the_repair(tmp_path / "old.db")
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Scope Co"), "scope.fixture")

    def plant(tier, scope, depth, analyst=False, kind="audit"):
        run_id = runs.create_run(conn, site, ["TEC"], tier, analyst_enabled=analyst,
                                 kind=kind, scan_scope=scope, scan_depth=depth)
        conn.execute("UPDATE audit_runs SET status='complete', scan_scope=?, crawled_paths=?"
                     " WHERE id=?", (scope, json.dumps(["/"]), run_id))
        return run_id

    ids = {
        "by_hand_t1": plant("T1", "full", None),
        "by_hand_t2": plant("T2", "full", None),
        "by_hand_t3_paid": plant("T3", "full", None, analyst=True),
        "chooser_full": plant("T3", "full", "quick"),
        "chooser_site": plant("T2", "site", "deep", analyst=True),
        "nav": plant("T2", "nav", None),
        "verify": plant("T2", None, None, kind="verify"),
    }
    conn.commit()

    assert migrate(conn) == [REPAIR]
    got = {name: tuple(conn.execute(
               "SELECT scan_scope, scan_depth, scope_source FROM audit_runs WHERE id=?",
               (run_id,)).fetchone()) for name, run_id in ids.items()}
    assert got == {
        "by_hand_t1": ("page", "quick", "derived-from-tier"),
        "by_hand_t2": ("site", "quick", "derived-from-tier"),
        # A model ran and the row does not say which: the depth stays unsaid.
        "by_hand_t3_paid": ("full", None, "derived-from-tier"),
        "chooser_full": ("full", "quick", None),
        "chooser_site": ("site", "deep", None),
        "nav": ("nav", None, None),
        "verify": (None, None, None),
    }, got
    assert migrate(conn) == [], "the repair ran twice"
    # The site's Latest View was rebuilt, and says why.
    reason = conn.execute("SELECT reason FROM latest_view_log WHERE site_id=?"
                          " ORDER BY rowid DESC LIMIT 1", (site,)).fetchone()
    assert reason and reason[0].startswith("0070"), reason
    conn.close()
