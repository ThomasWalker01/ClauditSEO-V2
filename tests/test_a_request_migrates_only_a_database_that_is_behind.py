"""A request asks the ledger whether the database is current, and runs the full
migration runner only when it is not.

Every request used to call `migrate()`, which globs the migrations directory
and reads and hashes each file for the drift check - ~9 ms per call, on routes
whose own work was a few milliseconds. The file checks run at startup and on
`clauditseo migrate`; what a request still needs is the schema, so a database
replaced under a running service must still be brought up to date.
"""

from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db import migrate as runner
from clauditseo.db.connection import connect


def test_a_current_database_is_not_migrated_again_on_a_request(tmp_path, monkeypatch):
    client = TestClient(create_app(db_path=tmp_path / "api.db"))

    def _read_the_files():
        raise AssertionError("a request re-read the migrations directory")

    # After startup, which has already read them.
    monkeypatch.setattr(runner, "_files", _read_the_files)
    assert client.get("/api/clients").status_code == 200


def test_a_database_replaced_under_the_service_is_migrated_on_the_next_request(tmp_path):
    db = tmp_path / "api.db"
    client = TestClient(create_app(db_path=db))
    assert client.get("/api/clients").status_code == 200

    db.unlink()
    for sidecar in (tmp_path / "api.db-wal", tmp_path / "api.db-shm"):
        sidecar.unlink(missing_ok=True)

    assert client.get("/api/clients").status_code == 200
    conn = connect(db)
    assert runner.is_current(conn, runner.migration_names())
    conn.close()


def test_is_current_answers_both_ways(tmp_path):
    names = runner.migration_names()
    conn = connect(tmp_path / "t.db")
    # No ledger at all: not current, and not an error.
    assert runner.is_current(conn, names) is False
    runner.migrate(conn)
    assert runner.is_current(conn, names) is True
    # One recorded migration missing from the ledger: behind.
    conn.execute("DELETE FROM schema_migrations WHERE filename = ?", (min(names),))
    assert runner.is_current(conn, names) is False
    conn.close()
