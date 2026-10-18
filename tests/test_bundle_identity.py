"""The served bundle must say which build it is, and must not be stale.

`app.py` mounts `dashboard/dist` with `StaticFiles`. `restart-service.ps1` —
whose first line says it exists so the service "picks up code changes" —
stops the task, restarts it and polls `/api/health`. It never rebuilds. The
only script that runs `npm run build` is `dev.ps1`.

So a dashboard fix reaches the operator only if they happen to rebuild by
hand, and nothing on any screen or endpoint tells them which UI they are
looking at: `/api/health` reports the *server's* version, and the Admin
footer renders that same server version — drawn by whatever bundle is on
disk. Round 020 measured the gap at twelve hours: `dashboard/dist` dated
00:08 against a fix that landed at 12:41, with the served JavaScript still
containing a string that commit had removed. Nine tenths of that round's
delta could not be driven, and the audit had no way to know until it grepped
the bundle.

The build id needs no new tooling. Vite already emits a content-hashed asset
name — `index-<hash>.js` — which changes exactly when the bundle changes.
Reading it from `dist/index.html` cannot drift from the thing it identifies,
where a version constant written by hand would.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dashboard" / "dist"
SRC = ROOT / "dashboard" / "src"


def test_the_built_bundle_is_not_older_than_its_source():
    """Only meaningful where a build exists.

    CI's `python` matrix never runs `npm run build`, so `dist` is absent
    there and this asserts nothing — correctly, because a missing dashboard
    is a different state from a stale one. Where a build *is* present, it is
    what the server serves, and serving a bundle older than the source it
    was built from is the defect.
    """
    index = DIST / "index.html"
    if not index.is_file():
        return  # no build here; nothing is being served

    newest = max(SRC.rglob("*"), key=lambda p: p.stat().st_mtime)
    built, changed = index.stat().st_mtime, newest.stat().st_mtime
    assert built >= changed, (
        f"dashboard/dist is older than dashboard/src — the server is "
        f"serving a bundle that predates the source. "
        f"dist/index.html {built:.0f}, {newest.relative_to(ROOT).as_posix()} "
        f"{changed:.0f}, behind by {(changed - built) / 60:.0f} minutes. "
        f"Run `npm run build` in dashboard/.")


def test_health_reports_which_bundle_is_being_served(tmp_path):
    """The server's own version is not an answer to "which UI is this".

    Both were the same string before this, so an operator comparing them
    learned nothing: the footer drew the server's version using whatever
    JavaScript happened to be on disk.
    """
    from fastapi.testclient import TestClient

    from clauditseo import __version__
    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate

    db = tmp_path / "health.db"
    conn = connect(db)
    migrate(conn)
    conn.close()

    body = TestClient(create_app(db_path=db)).get("/api/health").json()
    assert "bundle" in body, (
        f"/api/health does not report a bundle id: {body}")

    if (DIST / "index.html").is_file():
        assert body["bundle"], "a build is present but no bundle id was reported"
        assert body["bundle"] != __version__, (
            "the bundle id is the server version, which is the thing it has "
            "to be distinguishable from")
    else:
        assert body["bundle"] is None, (
            f"no build is present, so the id must be null: {body['bundle']!r}")


def test_health_says_whether_the_running_process_holds_the_current_source(tmp_path):
    """The other half of "which thing am I looking at".

    The bundle id above answers it for the dashboard. Nothing answered it for
    the Python: `/api/health` reported a version string compiled into the
    running process, so a server fourteen source files behind looked identical
    to a current one from every surface a browser or an operator could reach.
    The only thing that could tell them apart was a PowerShell script nothing
    called, which is how the same finding was raised in rounds 029 through 033.

    Written after the change rather than before it, and said so here rather
    than left to be inferred: the defect was proven at the running product —
    `/api/health` returning `engine_version 0.8.0` against a tree at `0.9.0` —
    not by this test failing first.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate

    db = tmp_path / "freshness.db"
    conn = connect(db)
    migrate(conn)
    conn.close()

    body = TestClient(create_app(db_path=db)).get("/api/health").json()

    for field in ("started_at", "source_mtime", "source_newest",
                  "source_newer_than_process"):
        assert field in body, f"/api/health does not report {field}: {body}"

    assert body["source_newest"].endswith(".py"), (
        "source_newest must name the file the timestamp came from — a bare "
        "timestamp cannot be checked against anything")
    assert isinstance(body["source_newer_than_process"], bool), (
        "the answer is stated, not left to a reader to derive from two "
        "timestamps — nobody comparing them is the entire failure mode")
