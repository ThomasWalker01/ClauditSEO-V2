"""The provenance line names the latest audit that measured the part (item
212, as corrected by the channel, 20260924-0220-212).

The filing read "automatic checks 2026-09-23 · T2 · TEC" under a header
naming "Audit T3". The part page's automatic counts are the site's finding
states, which the latest audit to MEASURE the part moved, and the line names
exactly that audit. Its clause saying the line differed from the audit
picked above went with the picker (item 239 step 5); that the site screen
reads the same with and without a `run=` in the address is guarded by
`test_the_site_screen_picks_no_audit`.
"""

from __future__ import annotations

from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_line_names_the_latest_audit_that_measured_the_part(tmp_path):
    """The channel's correction (20260924-0220-212): the latest audit is not
    necessarily one that measured the part. A newer ONP-only audit must not be
    named on a TEC part."""
    import json as _json
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(tmp_path / "s.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "s.fixture")
    older = runs.create_run(conn, site, ["TEC", "ONP"], "T3")
    newer = runs.create_run(conn, site, ["ONP"], "T2")
    for rid, at in ((older, "2026-09-18T00:00:00+00:00"), (newer, "2026-09-23T00:00:00+00:00")):
        conn.execute("UPDATE audit_runs SET status='complete', kind='audit', started_at=?,"
                     " finished_at=? WHERE id=?", (at, at, rid))
    conn.commit()
    # Finished by hand, so the Latest View is built by its replay (item 239).
    from clauditseo.persistence import latest_view
    latest_view.rebuild(conn, site, "test")
    assert runs._latest_sweep(conn, site)["run_id"] == newer
    assert runs._latest_sweep(conn, site, "ONP")["run_id"] == newer
    assert runs._latest_sweep(conn, site, "TEC")["run_id"] == older, (
        "a TEC part names an audit that never measured TEC")
    assert runs._latest_sweep(conn, site, "LOC") is None
    _ = _json


def test_a_hold_on_a_check_that_fired_is_a_hold_on_the_fix():
    """Item 213, held on the source: the pill reads "fix held" where the
    check fired on the same page, and the title is never "not checked"."""
    src = (UI / "part_page.tsx").read_text(encoding="utf-8")
    assert '(fixHeld ? "fix held" : "Not assessable")' in src
    assert "— not checked`" not in src, "a card or tag still says a check that ran was not checked"
