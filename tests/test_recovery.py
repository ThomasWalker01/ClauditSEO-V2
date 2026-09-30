"""Orphaned-run recovery at boot.

Runs execute on daemon threads inside the served process, so at startup no
thread can still own one. Anything left at 'running' is a corpse, whatever
its age — and a dashboard that shows a dead run as in-flight is lying about
the one thing an operator checks first.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

INTERRUPTED = "interrupted: server stopped while this run was in flight"


def _site_with_running_run(path):
    conn = connect(path)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Co"), "x.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")   # created now, 'running'
    conn.close()
    return run_id


def test_a_run_interrupted_moments_ago_is_recovered_at_boot(tmp_path, monkeypatch):
    """The window that mattered: a restart ten minutes after a crash left the
    run 'running' until some later restart happened to fall outside two
    hours — on a stable server, never."""
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    path = tmp_path / "recover.db"
    run_id = _site_with_running_run(path)

    client = TestClient(create_app(db_path=path))      # boot does the sweep
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "failed"
    assert run["error"] == INTERRUPTED


def test_the_age_guard_survives_for_multi_process_callers(tmp_path):
    """Opt-in, not the boot default: a deployment sharing one database across
    processes cannot assume a running row is orphaned."""
    path = tmp_path / "guard.db"
    _site_with_running_run(path)

    conn = connect(path)
    assert runs.recover_interrupted(conn, older_than_hours=2) == 0
    assert conn.execute("SELECT status FROM audit_runs").fetchone()["status"] \
        == "running"
    assert runs.recover_interrupted(conn) == 1          # default reaps it
    conn.close()


def test_recovery_is_idempotent_and_leaves_finished_runs_alone(tmp_path):
    path = tmp_path / "idem.db"
    _site_with_running_run(path)
    conn = connect(path)

    assert runs.recover_interrupted(conn) == 1
    assert runs.recover_interrupted(conn) == 0, \
        "a second boot must not re-stamp an already-failed run"

    # A completed run is untouched by any number of restarts.
    site = conn.execute("SELECT id FROM sites").fetchone()["id"]
    done = runs.create_run(conn, site, ["TEC"], "T2")
    with conn:
        conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (done,))
    assert runs.recover_interrupted(conn) == 0
    assert conn.execute("SELECT status FROM audit_runs WHERE id=?",
                        (done,)).fetchone()["status"] == "complete"
    conn.close()
