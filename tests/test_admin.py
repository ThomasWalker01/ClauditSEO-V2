"""Admin surface: database snapshots, provider status and cache control.

The snapshot rules matter more than the button. A copy of a live SQLite file
can silently omit writes still in the write-ahead log, and a backup that is
trusted but incomplete is worse than none — so every snapshot here is
verified before it is reported as a success.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import backup as backup_mod
from clauditseo.persistence import repo


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "admin.db"
    conn = connect(path)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Backup Co")
    repo.create_site(conn, client, "backup.example")
    yield conn, path
    conn.close()


def test_snapshot_captures_writes_still_in_the_wal(db):
    """The failure a plain file copy hides: rows written but not yet
    checkpointed must appear in the snapshot."""
    conn, path = db
    op = repo.ensure_default_operator(conn)
    for i in range(30):
        repo.create_client(conn, op, f"Late Client {i}")
    assert conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 31

    result = backup_mod.create_backup(conn, path)
    assert result["status"] == "ok"
    assert result["integrity"] == "ok"
    assert result["rows"]["clients"] == 31

    restored = sqlite3.connect(result["path"])
    assert restored.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 31
    names = {r[0] for r in restored.execute("SELECT name FROM clients")}
    assert "Late Client 29" in names
    restored.close()


def test_snapshot_is_usable_without_stopping_the_server(db):
    """Taken through a live connection, so writes can continue around it."""
    conn, path = db
    first = backup_mod.create_backup(conn, path)
    op = repo.ensure_default_operator(conn)
    repo.create_client(conn, op, "Added After Backup")
    second = backup_mod.create_backup(conn, path)

    # Two snapshots in the same second must not collide and silently
    # overwrite each other.
    assert first["name"] != second["name"]
    assert second["rows"]["clients"] == first["rows"]["clients"] + 1
    assert len(backup_mod.list_backups(path)) == 2
    # The earlier snapshot is untouched by later writes.
    earlier = sqlite3.connect(first["path"])
    assert earlier.execute(
        "SELECT COUNT(*) FROM clients WHERE name='Added After Backup'"
    ).fetchone()[0] == 0
    earlier.close()


def test_listing_and_stats_report_the_real_numbers(db):
    conn, path = db
    backup_mod.create_backup(conn, path)
    stats = backup_mod.database_stats(conn, path)
    assert stats["bytes"] > 0
    assert stats["rows"]["clients"] == 1 and stats["rows"]["sites"] == 1

    listed = backup_mod.list_backups(path)
    assert len(listed) == 1 and listed[0]["bytes"] > 0
    assert listed[0]["name"].startswith("clauditseo-")


def test_restore_is_documented_not_automated(db):
    """Restoring discards every audit since the snapshot; it should take a
    considered act, not one click."""
    _, path = db
    steps = backup_mod.restore_instructions(path)
    assert any("stop-service" in s for s in steps)
    assert any("-wal" in s for s in steps)


def test_clearing_the_analyst_cache_reports_what_it_removed(db):
    conn, _ = db
    with conn:
        conn.execute(
            "INSERT INTO analyst_cache (task, model_id, bundle_hash, result,"
            " created_at) VALUES ('T', 'm', 'h', '[]', datetime('now'))")
    assert backup_mod.clear_analyst_cache(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM analyst_cache").fetchone()[0] == 0


# --- API ---------------------------------------------------------------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    return TestClient(create_app(db_path=tmp_path / "api-admin.db"))


def test_admin_overview_never_exposes_a_key_value(api):
    body = api.get("/api/admin").json()
    assert body["auth_mode"] == "open local mode"
    assert body["database"]["rows"]["clients"] == 0
    assert body["models"]["fast"] and body["models"]["deep"]
    for status in body["providers"].values():
        # A whitelist, not a spot check: the point is that nothing
        # else is in there, so a value can never be added by accident.
        assert set(status) == {"configured", "detail", "env",
                               "managed", "source"}
    assert body["restore_steps"]


def test_backup_endpoint_writes_a_verified_snapshot(api):
    api.post("/api/clients", json={"name": "Snapshot Co"})
    created = api.post("/api/admin/backup", json={})
    assert created.status_code == 201
    assert created.json()["integrity"] == "ok"
    assert created.json()["rows"]["clients"] == 1

    listed = api.get("/api/admin").json()["backups"]
    assert len(listed) == 1
    assert listed[0]["name"] == created.json()["name"]


def test_admin_requires_auth_when_a_token_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_TOKEN", "s3cret")
    client = TestClient(create_app(db_path=tmp_path / "auth-admin.db"))
    assert client.get("/api/admin").status_code == 401
    assert client.post("/api/admin/backup", json={}).status_code == 401
    ok = client.get("/api/admin", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
