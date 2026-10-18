"""An analysis says what has changed since it ran (item 249, steps 2 to 4).

- **The reader changed.** An analysis is stamped with the reader that read
  it. One stamped with another version is re-read at startup, with no model
  call; one never stamped waits for `clauditseo reparse-contracts`.
- **The brief changed.** An analysis records the brief it was written under,
  and says "analysed under an earlier brief" where that brief has changed.
- **The automatic checks stopped seeing it.** A model row on a check the
  sweep can raise, whose pages every reading since has read without raising
  it, says so and offers Withdraw. twenty22 kept three HIGH `canonical-loop`
  cards for eight days with no way to retire them but a paid re-run.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.analysts import contract, expert
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import create_id, now_iso

BASE = "https://t.fixture"
PAGES = [BASE + "/", BASE + "/about/", BASE + "/blog/"]


@pytest.fixture()
def db(tmp_path):
    conn = connect(tmp_path / "since.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "T Co"), "t.fixture")
    yield conn, site_id
    conn.close()


def _audit(conn, site_id, at: str, raised: list[tuple[str, str]] = (), dims=("TEC",),
           pages=PAGES, scope="site") -> str:
    """One finished site reading, with the deterministic findings it raised."""
    run_id = runs.create_run(conn, site_id, list(dims), "T2", scan_scope=scope)
    runs.store_evidence(conn, run_id, {"pages": [{"url": u, "status": 200} for u in pages]})
    conn.execute("UPDATE audit_runs SET status='complete', started_at=?, finished_at=?,"
                 " created_at=?, crawled_paths=? WHERE id=?",
                 (at, at, at, json.dumps([u[len(BASE):] or "/" for u in pages]), run_id))
    for check, url in raised:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at) VALUES (?, ?, 'TEC', ?, 'high',"
            " 'deterministic', 's', ?, ?, ?)",
            (create_id(), run_id, check, json.dumps([url]), f"TEC:{check}:{url}", at))
    conn.commit()
    return run_id


def _analysis_row(conn, site_id, run_id, check: str, url: str, tool="indexability") -> None:
    row = {"check": f"TEC/{check}", "dimension": "TEC", "check_id": check, "page": url,
           "status": "FAIL", "severity": "high", "evidence": "x", "replacement": None, "note": ""}
    runs.store_expert_report(conn, run_id, tool, {
        "model": "stub", "report": "r", "findings": [],
        "contract": {"status": "read", "part": tool, "rows": [row], "dropped": [],
                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run_id, tool, "stub", [row])
    runs.recompute_contract_states(conn, site_id, tool)


def _row(conn, site_id, check: str) -> dict:
    return next(s for s in runs.site_states(conn, site_id)
                if s["check_id"] == check and s["source_word"] == "brief")


# ---- step 4 --------------------------------------------------------------------

def test_a_model_row_the_sweeps_have_stopped_seeing_says_since_when(db):
    conn, site_id = db
    first = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, first, "canonical-loop", BASE + "/about/")
    _audit(conn, site_id, "2026-09-25T00:00:00+00:00")
    _audit(conn, site_id, "2026-09-28T00:00:00+00:00")
    got = _row(conn, site_id, "canonical-loop")
    # The oldest reading in the unbroken run after the analysis.
    assert got["unseen_since"] == "2026-09-25T00:00:00+00:00", got["unseen_since"]
    assert got["state"] in ("open", "candidate", "regressed"), "nothing was retired for the operator"


def test_a_row_the_newest_sweep_raised_is_seen(db):
    conn, site_id = db
    first = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, first, "canonical-loop", BASE + "/about/")
    _audit(conn, site_id, "2026-09-25T00:00:00+00:00")
    _audit(conn, site_id, "2026-09-28T00:00:00+00:00",
           raised=[("canonical-loop", BASE + "/about/")])
    assert _row(conn, site_id, "canonical-loop")["unseen_since"] is None


def test_a_sweep_that_did_not_read_the_page_says_nothing(db):
    conn, site_id = db
    first = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, first, "canonical-loop", BASE + "/about/")
    _audit(conn, site_id, "2026-09-28T00:00:00+00:00", pages=[BASE + "/", BASE + "/blog/"])
    assert _row(conn, site_id, "canonical-loop")["unseen_since"] is None


def test_a_sweep_of_another_dimension_says_nothing(db):
    conn, site_id = db
    first = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, first, "canonical-loop", BASE + "/about/")
    _audit(conn, site_id, "2026-09-28T00:00:00+00:00", dims=("ONP",))
    assert _row(conn, site_id, "canonical-loop")["unseen_since"] is None


def test_a_check_only_a_model_can_raise_is_never_unseen(db):
    """The sweep's silence about a check it cannot raise is not evidence."""
    conn, site_id = db
    first = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, first, "parameter-policy", BASE + "/about/")
    _audit(conn, site_id, "2026-09-28T00:00:00+00:00")
    from clauditseo.checks import check_cost
    assert check_cost("TEC/parameter-policy") != "free", "the premise: a model-only check"
    assert _row(conn, site_id, "parameter-policy")["unseen_since"] is None


# ---- step 3 --------------------------------------------------------------------

def test_an_analysis_written_under_an_earlier_brief_says_so(db):
    conn, site_id = db
    run_id = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, run_id, "canonical-loop", BASE + "/about/")

    def brief_run():
        cat = next(c for c in runs.anatomy_view(conn, site_id)["categories"]
                   if c["key"] == "indexability")
        return cat["brief_run"]

    # Never recorded: not marked, because "changed" would be a guess.
    assert brief_run()["brief_changed"] is None
    conn.execute("UPDATE expert_reports SET brief_version=?", (expert.brief_version("indexability"),))
    assert brief_run()["brief_changed"] is False
    conn.execute("UPDATE expert_reports SET brief_version='0ldbr1ef'")
    assert brief_run()["brief_changed"] is True


def test_a_fresh_analysis_is_stored_with_both_versions(db):
    conn, site_id = db
    run_id = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    runs.store_expert_report(conn, run_id, "indexability", {
        "model": "stub", "report": "r", "findings": [],
        "brief_version": "abc12345", "reader_version": contract.reader_version()})
    row = conn.execute("SELECT brief_version, reader_version FROM expert_reports").fetchone()
    assert tuple(row) == ("abc12345", contract.reader_version())


def test_the_backfill_reads_the_brief_version_off_the_cache_key(db):
    """0072: the cache row written in the same call names the brief."""
    from clauditseo.db import migrate as migrate_mod
    conn, site_id = db
    run_id = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, run_id, "canonical-loop", BASE + "/about/")
    at = conn.execute("SELECT created_at FROM expert_reports").fetchone()[0]
    conn.execute("INSERT INTO analyst_cache (task, model_id, bundle_hash, result, tokens_in,"
                 " tokens_out, created_at) VALUES ('EXPERT:indexability#aaaa1111#bbbb2222',"
                 " 'stub', 'h', '{}', 0, 0, ?)", (at,))
    conn.execute("INSERT INTO analyst_cache (task, model_id, bundle_hash, result, tokens_in,"
                 " tokens_out, created_at) VALUES ('EXPERT:urls#aaaa1111#cccc3333',"
                 " 'stub', 'h2', '{}', 0, 0, ?)", (at,))
    conn.commit()
    path = next(p for p in migrate_mod._files() if p.name.startswith("0072_"))
    migrate_mod._apply_python(path, conn)
    assert conn.execute("SELECT brief_version FROM expert_reports").fetchone()[0] == "bbbb2222"


# ---- step 2 --------------------------------------------------------------------

def test_an_analysis_read_by_an_older_reader_is_re_read_at_startup(db, monkeypatch):
    conn, site_id = db
    run_id = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, run_id, "canonical-loop", BASE + "/about/")
    site_of = lambda record: Site(domain=record["domain"])  # noqa: E731

    # Never stamped: left for the one-off command.
    assert expert.reparse_stale(conn, site_of) == []
    # Stamped with the reader as it stands: nothing to do.
    conn.execute("UPDATE expert_reports SET reader_version=?", (contract.reader_version(),))
    assert expert.reparse_stale(conn, site_of) == []
    # Stamped by a reader that has since changed: re-read, and stamped again.
    conn.execute("UPDATE expert_reports SET reader_version='0ldr3ad3'")
    conn.commit()
    assert expert.reparse_stale(conn, site_of) == ["t.fixture"]
    row = conn.execute("SELECT reader_version, contract FROM expert_reports").fetchone()
    assert row[0] == contract.reader_version()
    assert json.loads(row[1])["reparsed"] is True
    cat = next(c for c in runs.anatomy_view(conn, site_id)["categories"]
               if c["key"] == "indexability")
    assert cat["brief_run"]["reread"] is True
    assert expert.reparse_stale(conn, site_of) == [], "a second start re-read it again"


def test_the_reader_version_follows_the_rules_file():
    assert len(contract.reader_version()) == 8
    assert contract.reader_version() == contract.reader_version()


# ---- the channel's three additions (answer 20261002-0935) ----------------------

def test_the_stamp_covers_the_rules_that_live_beside_the_reader(monkeypatch):
    """`contract_rules` is in expert.py. A change to it must change the
    stamp, or the analyses it governs are not re-read at the next start."""
    before = contract.reader_version()

    def contract_rules(*a, **k):        # a different body under the same name
        return None

    monkeypatch.setattr(expert, "contract_rules", contract_rules)
    assert contract.reader_version() != before


def test_startup_says_how_many_analyses_were_never_stamped(db, caplog):
    conn, site_id = db
    run_id = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, run_id, "canonical-loop", BASE + "/about/")
    with caplog.at_level("WARNING"):
        assert expert.reparse_stale(conn, lambda r: Site(domain=r["domain"])) == []
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "1 stored analysis has never been re-read" in said, said
    assert "clauditseo reparse-contracts" in said, said
    # And it was not re-read from here: the operator chooses when.
    assert conn.execute("SELECT reader_version FROM expert_reports").fetchone()[0] is None


def test_the_re_read_mark_carries_its_own_date(db):
    conn, site_id = db
    run_id = _audit(conn, site_id, "2026-09-18T00:00:00+00:00")
    _analysis_row(conn, site_id, run_id, "canonical-loop", BASE + "/about/")
    expert.reparse_report(conn, run_id, "indexability", Site(domain="t.fixture"))
    cat = next(c for c in runs.anatomy_view(conn, site_id)["categories"]
               if c["key"] == "indexability")
    assert cat["brief_run"]["reread"] is True
    assert cat["brief_run"]["reread_at"] and cat["brief_run"]["reread_at"] > "2026-10-01", cat["brief_run"]
